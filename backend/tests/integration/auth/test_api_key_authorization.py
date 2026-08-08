"""Integration tests for API key authorization rules."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.api_key_scopes import (
    API_ADMIN_SCOPE,
    API_READ_SCOPE,
    API_WRITE_SCOPE,
)
from app.api.routes import soc_metrics as soc_metrics_routes
from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import (
    AnalystMetricsResponse,
    ApiKey,
    ApiKeyFailureSample,
    AuditLog,
    UserAccount,
)
from app.services.api_key_failure_sampling_service import (
    _API_KEY_FAILURE_ADVISORY_LOCK_ID,
)
from app.services.api_key_service import ApiKeyRevokedError, api_key_service
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _login_and_get_cookie(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    session_cookie = response.cookies.get("intercept_session")
    assert session_cookie is not None
    return session_cookie


@pytest.mark.asyncio
async def test_parallel_shared_api_key_validation_is_read_only_and_deadlock_free(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """Concurrent read requests must not upgrade shared API-key locks."""
    user = analyst_user_factory(username="parallel-shared-api-key-user")
    async with session_maker() as setup_db:
        setup_db.add(user)
        await setup_db.flush()
        api_key, raw_key = await api_key_service.create_api_key(
            setup_db,
            user_id=user.id,
            name="parallel shared validation",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            scopes={API_READ_SCOPE},
        )
        await setup_db.commit()
        api_key_id = api_key.id

    validation_barrier = asyncio.Barrier(2)

    async def validate_and_commit() -> None:
        async with session_maker() as validation_db:
            result = await api_key_service.validate_api_key(
                validation_db,
                raw_key=raw_key,
                required_scopes={API_READ_SCOPE},
                audit_success=False,
                skip_locked=True,
                shared_lock=True,
            )
            assert result.user.id == user.id
            await validation_barrier.wait()
            await validation_db.commit()

    await asyncio.wait_for(
        asyncio.gather(validate_and_commit(), validate_and_commit()),
        timeout=3,
    )

    async with session_maker() as read_db:
        stored_key = await read_db.get(ApiKey, api_key_id)
        assert stored_key is not None
        assert stored_key.last_used_at is None

    response = await client.get(
        "/api/v1/admin/auth/users/summary",
        headers={"x-api-key": raw_key},
    )
    assert response.status_code == 200
    async with session_maker() as read_db:
        stored_key = await read_db.get(ApiKey, api_key_id)
        assert stored_key is not None
        assert stored_key.last_used_at is not None


@pytest.mark.asyncio
async def test_api_key_failure_audits_are_sampled_by_source_key_and_reason(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    """One hostile source cannot turn random credentials into unbounded audit rows."""
    admin = admin_user_factory(username="api-key-audit-sampling-admin")
    nhi_user = UserAccount(
        username="api-key-audit-sampling-nhi",
        email="api-key-audit-sampling-nhi@example.com",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
    )
    async with session_maker() as setup_db:
        setup_db.add_all([admin, nhi_user])
        await setup_db.flush()
        expired_key, expired_raw_key = await api_key_service.create_api_key(
            setup_db,
            user_id=nhi_user.id,
            name="expired audit control",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            scopes={API_READ_SCOPE},
        )
        expired_key.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await setup_db.commit()

    session_cookie = await _login_and_get_cookie(
        client,
        username=admin.username,
        password=DEFAULT_TEST_PASSWORD,
    )

    unknown_credentials = ["x" * 4096] + [
        f"tmi_random_invalid_{index:02d}" for index in range(19)
    ]
    for raw_key in unknown_credentials:
        response = await client.get(
            "/api/v1/admin/auth/users/summary",
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["message"] == "Invalid API key"

    for _ in range(5):
        response = await client.get(
            "/api/v1/admin/auth/users/summary",
            headers={"x-api-key": expired_raw_key},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["message"] == "API key has expired"

    audit_response = await client.get(
        "/api/v1/admin/audit",
        params={"event_type": "auth.api_key.auth_failure", "size": 100},
        cookies={"intercept_session": session_cookie},
    )
    assert audit_response.status_code == 200
    failure_payloads = [
        json.loads(item["new_value"])
        for item in audit_response.json()["items"]
    ]
    unknown_payloads = [
        payload for payload in failure_payloads
        if payload["reason"] == "key_not_found"
    ]
    expired_payloads = [
        payload for payload in failure_payloads
        if payload["reason"] == "key_expired"
    ]

    assert 1 <= len(unknown_payloads) <= 3
    assert 1 <= len(expired_payloads) <= 3
    assert {payload["api_key_prefix"] for payload in unknown_payloads} == {None}
    assert {payload["api_key_prefix"] for payload in expired_payloads} == {
        expired_key.prefix
    }
    assert {payload["api_key_id"] for payload in expired_payloads} == {
        str(expired_key.id)
    }
    source_fingerprints = {
        payload["source_fingerprint"] for payload in unknown_payloads
    }
    assert len(source_fingerprints) == 1
    source_fingerprint = source_fingerprints.pop()
    assert len(source_fingerprint) == 64
    assert {
        payload["source_fingerprint"] for payload in expired_payloads
    } == {source_fingerprint}
    unknown_failure_fingerprints = {
        payload["failure_fingerprint"] for payload in unknown_payloads
    }
    expired_failure_fingerprints = {
        payload["failure_fingerprint"] for payload in expired_payloads
    }
    assert len(unknown_failure_fingerprints) == 1
    assert len(expired_failure_fingerprints) == 1
    assert unknown_failure_fingerprints.isdisjoint(expired_failure_fingerprints)


@pytest.mark.asyncio
async def test_api_key_failure_sampling_drops_sample_when_global_lock_is_busy(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Optional rejection telemetry must never queue authentication requests."""
    async with session_maker() as lock_holder:
        await lock_holder.execute(
            select(func.pg_advisory_xact_lock(_API_KEY_FAILURE_ADVISORY_LOCK_ID))
        )

        response = await asyncio.wait_for(
            client.get(
                "/api/v1/admin/auth/users/summary",
                headers={"x-api-key": "tmi_invalid_while_sampler_is_busy"},
            ),
            timeout=2,
        )

        assert response.status_code == 401
        assert response.json()["detail"]["message"] == "Invalid API key"

        async with session_maker() as read_db:
            sample_count = await read_db.scalar(
                select(func.count()).select_from(ApiKeyFailureSample)
            )
            audit_count = await read_db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.event_type == "auth.api_key.auth_failure")
            )

        assert sample_count == 0
        assert audit_count == 0


@pytest.mark.asyncio
async def test_user_can_create_api_key_for_self(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    user = analyst_user_factory()

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    session_cookie = await _login_and_get_cookie(
        client,
        username=user.username,
        password=DEFAULT_TEST_PASSWORD,
    )

    response = await client.post(
        "/api/v1/api-keys",
        json={
            "name": "self-key",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == str(user.id)
    assert data["name"] == "self-key"
    assert data["key"]


@pytest.mark.asyncio
async def test_non_admin_cannot_create_api_key_for_other_user(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    acting_user = analyst_user_factory()
    target_user = analyst_user_factory()

    async with session_maker() as session:
        session.add(acting_user)
        session.add(target_user)
        await session.commit()

    session_cookie = await _login_and_get_cookie(
        client,
        username=acting_user.username,
        password=DEFAULT_TEST_PASSWORD,
    )

    response = await client.post(
        "/api/v1/api-keys",
        json={
            "name": "forbidden-key",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "user_id": str(target_user.id),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 403
    assert "admin" in response.json()["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_admin_cannot_create_api_key_for_human_account(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    human_target = analyst_user_factory()

    async with session_maker() as session:
        session.add(admin)
        session.add(human_target)
        await session.commit()

    session_cookie = await _login_and_get_cookie(
        client,
        username=admin.username,
        password=DEFAULT_TEST_PASSWORD,
    )

    response = await client.post(
        "/api/v1/api-keys",
        json={
            "name": "human-target-key",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "user_id": str(human_target.id),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 403
    assert "nhi" in response.json()["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_admin_can_create_api_key_for_nhi_account(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
) -> None:
    admin = admin_user_factory()
    nhi_user = UserAccount(
        username="svc.integration",
        role=admin.role,
        status=admin.status,
        account_type=AccountType.NHI,
        description="Integration account",
    )

    async with session_maker() as session:
        session.add(admin)
        session.add(nhi_user)
        await session.commit()

    session_cookie = await _login_and_get_cookie(
        client,
        username=admin.username,
        password=DEFAULT_TEST_PASSWORD,
    )

    response = await client.post(
        "/api/v1/api-keys",
        json={
            "name": "nhi-key",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "user_id": str(nhi_user.id),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == str(nhi_user.id)
    assert data["name"] == "nhi-key"


@pytest.mark.asyncio
async def test_admin_can_revoke_any_user_api_key(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    target_user = analyst_user_factory()

    async with session_maker() as session:
        session.add(admin)
        session.add(target_user)
        await session.commit()

        api_key, _ = await api_key_service.create_api_key(
            session,
            user_id=target_user.id,
            name="target-user-key",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        await session.commit()
        key_id = api_key.id

    session_cookie = await _login_and_get_cookie(
        client,
        username=admin.username,
        password=DEFAULT_TEST_PASSWORD,
    )

    response = await client.delete(
        f"/api/v1/api-keys/{key_id}",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 204

    async with session_maker() as session:
        revoked_key = await session.get(ApiKey, key_id)
        assert revoked_key is not None
        assert revoked_key.revoked_at is not None


@pytest.mark.asyncio
async def test_pre_cutoff_api_key_cannot_resurrect_after_missed_row_revocation(
    session_maker: Any,
) -> None:
    owner = UserAccount(
        username="svc.credential.cutoff",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
    )
    async with session_maker() as session:
        session.add(owner)
        await session.flush()
        api_key, raw_key = await api_key_service.create_api_key(
            session,
            user_id=owner.id,
            name="pre-cutoff-key",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            scopes={API_READ_SCOPE},
        )
        await session.commit()
        await session.refresh(api_key)
        key_id = api_key.id
        cutoff = api_key.created_at + timedelta(microseconds=1)

    async with session_maker() as session:
        persisted_owner = await session.get(UserAccount, owner.id)
        persisted_key = await session.get(ApiKey, key_id)
        assert persisted_owner is not None
        assert persisted_key is not None
        persisted_owner.credentials_invalidated_at = cutoff
        persisted_owner.status = UserStatus.ACTIVE
        persisted_key.revoked_at = None
        await session.commit()

    async with session_maker() as session:
        with pytest.raises(ApiKeyRevokedError):
            await api_key_service.validate_api_key(session, raw_key=raw_key)
        await session.rollback()

    async with session_maker() as session:
        persisted_key = await session.get(ApiKey, key_id)
        assert persisted_key is not None
        assert persisted_key.revoked_at is not None


@pytest.mark.asyncio
async def test_read_only_api_key_can_read_but_cannot_mutate(
    client: AsyncClient,
    session_maker: Any,
) -> None:
    owner = UserAccount(
        username="svc.read.only",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
    )
    async with session_maker() as session:
        session.add(owner)
        await session.flush()
        _, raw_key = await api_key_service.create_api_key(
            session,
            user_id=owner.id,
            name="read-only",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_READ_SCOPE},
        )
        await session.commit()

    headers = {"Authorization": f"Bearer {raw_key}"}
    list_response = await client.get("/api/v1/api-keys", headers=headers)
    create_response = await client.post(
        "/api/v1/api-keys",
        headers=headers,
        json={
            "name": "must-not-be-created",
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(days=30)
            ).isoformat(),
            "scopes": [API_READ_SCOPE],
        },
    )

    assert list_response.status_code == 200
    assert create_response.status_code == 403


@pytest.mark.asyncio
async def test_write_only_api_key_can_mutate_but_cannot_read(
    client: AsyncClient,
    session_maker: Any,
) -> None:
    owner = UserAccount(
        username="svc.write.only",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
    )
    async with session_maker() as session:
        session.add(owner)
        await session.flush()
        _, raw_key = await api_key_service.create_api_key(
            session,
            user_id=owner.id,
            name="write-only",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_WRITE_SCOPE},
        )
        await session.commit()

    headers = {"Authorization": f"Bearer {raw_key}"}
    create_response = await client.post(
        "/api/v1/context-entries",
        headers=headers,
        json={
            "body": "Created through a write-scoped API key",
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(days=30)
            ).isoformat(),
        },
    )
    list_response = await client.get("/api/v1/context-entries", headers=headers)

    assert create_response.status_code == 201
    assert list_response.status_code == 403


@pytest.mark.asyncio
async def test_api_key_cannot_create_an_additional_api_key(
    client: AsyncClient,
    session_maker: Any,
) -> None:
    owner = UserAccount(
        username="svc.key.delegation",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
    )
    async with session_maker() as session:
        session.add(owner)
        await session.flush()
        _, parent_key = await api_key_service.create_api_key(
            session,
            user_id=owner.id,
            name="delegating-parent",
            expires_at=datetime.now(timezone.utc) + timedelta(days=2),
            scopes={API_WRITE_SCOPE, API_ADMIN_SCOPE},
        )
        await session.commit()

    response = await client.post(
        "/api/v1/api-keys",
        headers={"Authorization": f"Bearer {parent_key}"},
        json={
            "name": "attenuated-child",
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(days=1)
            ).isoformat(),
            "scopes": [API_WRITE_SCOPE],
        },
    )

    assert response.status_code == 403
    assert "cannot be used" in response.json()["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_admin_api_requires_both_read_and_admin_scopes(
    client: AsyncClient,
    session_maker: Any,
) -> None:
    owner = UserAccount(
        username="svc.scoped.admin",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
    )
    async with session_maker() as session:
        session.add(owner)
        await session.flush()
        _, read_key = await api_key_service.create_api_key(
            session,
            user_id=owner.id,
            name="read-without-admin",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_READ_SCOPE},
        )
        _, admin_key = await api_key_service.create_api_key(
            session,
            user_id=owner.id,
            name="read-and-admin",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_READ_SCOPE, API_ADMIN_SCOPE},
        )
        await session.commit()

    denied = await client.get(
        "/api/v1/admin/auth/users",
        headers={"Authorization": f"Bearer {read_key}"},
    )
    allowed = await client.get(
        "/api/v1/admin/auth/users",
        headers={"Authorization": f"Bearer {admin_key}"},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_cross_user_api_key_listing_requires_admin_scope(
    client: AsyncClient,
    session_maker: Any,
) -> None:
    owner = UserAccount(
        username="svc.cross.user.reader",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
    )
    target = UserAccount(
        username="svc.cross.user.target",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
    )
    async with session_maker() as session:
        session.add_all([owner, target])
        await session.flush()
        _, read_key = await api_key_service.create_api_key(
            session,
            user_id=owner.id,
            name="read-without-admin",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_READ_SCOPE},
        )
        _, privileged_key = await api_key_service.create_api_key(
            session,
            user_id=owner.id,
            name="read-with-admin",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_READ_SCOPE, API_ADMIN_SCOPE},
        )
        await session.commit()

    path = f"/api/v1/api-keys?user_id={target.id}"
    denied = await client.get(
        path,
        headers={"Authorization": f"Bearer {read_key}"},
    )
    allowed = await client.get(
        path,
        headers={"Authorization": f"Bearer {privileged_key}"},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_cross_user_api_key_revocation_requires_admin_scope(
    client: AsyncClient,
    session_maker: Any,
) -> None:
    owner = UserAccount(
        username="svc.cross.user.revoker",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
    )
    target = UserAccount(
        username="svc.revocation.target",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
    )
    async with session_maker() as session:
        session.add_all([owner, target])
        await session.flush()
        target_key, _ = await api_key_service.create_api_key(
            session,
            user_id=target.id,
            name="target-key",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_READ_SCOPE},
        )
        _, write_key = await api_key_service.create_api_key(
            session,
            user_id=owner.id,
            name="write-without-admin",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_WRITE_SCOPE},
        )
        _, privileged_key = await api_key_service.create_api_key(
            session,
            user_id=owner.id,
            name="write-with-admin",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_WRITE_SCOPE, API_ADMIN_SCOPE},
        )
        target_key_id = target_key.id
        await session.commit()

    path = f"/api/v1/api-keys/{target_key_id}"
    denied = await client.delete(
        path,
        headers={"Authorization": f"Bearer {write_key}"},
    )
    assert denied.status_code == 403

    async with session_maker() as session:
        persisted_target_key = await session.get(ApiKey, target_key_id)
        assert persisted_target_key is not None
        assert persisted_target_key.revoked_at is None

    allowed = await client.delete(
        path,
        headers={"Authorization": f"Bearer {privileged_key}"},
    )
    assert allowed.status_code == 204


@pytest.mark.asyncio
async def test_cross_user_chat_listing_requires_admin_scope(
    client: AsyncClient,
    session_maker: Any,
) -> None:
    owner = UserAccount(
        username="svc.cross.user.chat.reader",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
    )
    target = UserAccount(
        username="svc.chat.target",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
    )
    async with session_maker() as session:
        session.add_all([owner, target])
        await session.flush()
        _, read_key = await api_key_service.create_api_key(
            session,
            user_id=owner.id,
            name="chat-read-without-admin",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_READ_SCOPE},
        )
        _, privileged_key = await api_key_service.create_api_key(
            session,
            user_id=owner.id,
            name="chat-read-with-admin",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_READ_SCOPE, API_ADMIN_SCOPE},
        )
        await session.commit()

    path = f"/api/v1/langflow/sessions?username={target.username}"
    denied = await client.get(
        path,
        headers={"Authorization": f"Bearer {read_key}"},
    )
    allowed = await client.get(
        path,
        headers={"Authorization": f"Bearer {privileged_key}"},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json() == []


@pytest.mark.asyncio
async def test_analyst_metrics_require_admin_scope(
    client: AsyncClient,
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = UserAccount(
        username="svc.metrics.admin",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
    )
    async with session_maker() as session:
        session.add(owner)
        await session.flush()
        _, read_key = await api_key_service.create_api_key(
            session,
            user_id=owner.id,
            name="metrics-read-without-admin",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_READ_SCOPE},
        )
        _, privileged_key = await api_key_service.create_api_key(
            session,
            user_id=owner.id,
            name="metrics-read-with-admin",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_READ_SCOPE, API_ADMIN_SCOPE},
        )
        await session.commit()

    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        soc_metrics_routes.metrics_service,
        "get_analyst_metrics",
        AsyncMock(
            return_value=AnalystMetricsResponse(
                start_time=now - timedelta(hours=1),
                end_time=now,
            )
        ),
    )

    denied = await client.get(
        "/api/v1/metrics?type=analyst",
        headers={"Authorization": f"Bearer {read_key}"},
    )
    allowed = await client.get(
        "/api/v1/metrics?type=analyst",
        headers={"Authorization": f"Bearer {privileged_key}"},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
