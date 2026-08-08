"""Integration tests for admin user management endpoints."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import AdminResetRequest, AuditLog, AuthSession, UserAccount
from app.services.admin_auth_service import AdminAuthBusyError, admin_auth_service
from app.services.audit_service import AuditContext
from app.services.auth_service import (
    AuthenticationConcurrencyError,
    SessionNotFoundError,
    auth_service,
)
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _login_and_get_cookie(client: AsyncClient, username: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200
    session_cookie = response.cookies.get("intercept_session")
    assert session_cookie is not None
    return session_cookie


@pytest.mark.asyncio
async def test_reciprocal_admin_updates_fail_fast_instead_of_deadlocking(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    admin_a = admin_user_factory(username="reciprocal-admin-a")
    admin_b = admin_user_factory(username="reciprocal-admin-b")
    async with session_maker() as setup_db:
        setup_db.add_all([admin_a, admin_b])
        await setup_db.commit()

    async with session_maker() as db_a, session_maker() as db_b:
        locked_a = await db_a.get(UserAccount, admin_a.id, with_for_update=True)
        locked_b = await db_b.get(UserAccount, admin_b.id, with_for_update=True)
        assert locked_a is not None
        assert locked_b is not None

        async def reciprocal_update(
            db: AsyncSession,
            *,
            actor: UserAccount,
            target: UserAccount,
        ) -> None:
            await admin_auth_service.update_user(
                admin_user_id=actor.id,
                target_user_id=target.id,
                description="reciprocal update",
                request_metadata=AuditContext(),
                db=db,
            )

        results = await asyncio.wait_for(
            asyncio.gather(
                reciprocal_update(db_a, actor=admin_a, target=admin_b),
                reciprocal_update(db_b, actor=admin_b, target=admin_a),
                return_exceptions=True,
            ),
            timeout=2,
        )
        assert all(isinstance(result, AdminAuthBusyError) for result in results)
        await db_a.rollback()
        await db_b.rollback()


@pytest.mark.asyncio
async def test_reciprocal_admin_password_resets_fail_fast_instead_of_deadlocking(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    admin_a = admin_user_factory(username="reciprocal-reset-admin-a")
    admin_b = admin_user_factory(username="reciprocal-reset-admin-b")
    async with session_maker() as setup_db:
        setup_db.add_all([admin_a, admin_b])
        await setup_db.commit()

    async with session_maker() as db_a, session_maker() as db_b:
        locked_a = await db_a.get(UserAccount, admin_a.id, with_for_update=True)
        locked_b = await db_b.get(UserAccount, admin_b.id, with_for_update=True)
        assert locked_a is not None
        assert locked_b is not None

        async def reciprocal_reset(
            db: AsyncSession,
            *,
            actor: UserAccount,
            target: UserAccount,
        ) -> None:
            await admin_auth_service.issue_password_reset(
                admin_user_id=actor.id,
                target_user_id=target.id,
                request_metadata=AuditContext(),
                db=db,
            )

        results = await asyncio.wait_for(
            asyncio.gather(
                reciprocal_reset(db_a, actor=admin_a, target=admin_b),
                reciprocal_reset(db_b, actor=admin_b, target=admin_a),
                return_exceptions=True,
            ),
            timeout=2,
        )
        assert all(isinstance(result, AdminAuthBusyError) for result in results)
        await db_a.rollback()
        await db_b.rollback()


@pytest.mark.asyncio
async def test_admin_disable_eventually_wins_over_overlapping_target_reads(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Queued emergency writes must not be starved by a stream of readers."""
    admin = admin_user_factory(username="writer-progress-admin")
    target = analyst_user_factory(username="writer-progress-target")
    async with session_maker() as setup_db:
        setup_db.add_all([admin, target])
        await setup_db.commit()

    admin_cookie = await _login_and_get_cookie(client, admin.username)
    target_cookie = await _login_and_get_cookie(client, target.username)

    async with session_maker() as first_reader_db:
        await auth_service.validate_session(
            first_reader_db,
            session_token=target_cookie,
            shared_lock=True,
        )

        disable_task = asyncio.create_task(
            client.patch(
                f"/api/v1/admin/auth/users/{target.id}/status",
                json={"status": "DISABLED"},
                cookies={"intercept_session": admin_cookie},
            )
        )
        await asyncio.sleep(0.2)
        assert not disable_task.done()

        # Once the writer is queued, later readers fail fast rather than
        # consuming database-pool connections behind the emergency change.
        async def overlapping_read() -> None:
            async with session_maker() as overlapping_reader_db:
                await auth_service.validate_session(
                    overlapping_reader_db,
                    session_token=target_cookie,
                    shared_lock=True,
                )
                await overlapping_reader_db.commit()

        overlapping_read_task = asyncio.create_task(overlapping_read())
        with pytest.raises(AuthenticationConcurrencyError):
            await asyncio.wait_for(overlapping_read_task, timeout=0.5)

        await first_reader_db.commit()
        response = await asyncio.wait_for(disable_task, timeout=3)

    assert response.status_code == 204, response.text
    async with session_maker() as retry_db:
        with pytest.raises(SessionNotFoundError):
            await auth_service.validate_session(
                retry_db,
                session_token=target_cookie,
                shared_lock=True,
            )
    async with session_maker() as read_db:
        stored_target = await read_db.get(UserAccount, target.id)
        assert stored_target is not None
        assert stored_target.status == UserStatus.DISABLED


@pytest.mark.asyncio
async def test_admin_create_user_success(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    """Admin can successfully create a new analyst account with a password setup token."""
    admin = admin_user_factory()
    
    async with session_maker() as session:
        session.add(admin)
        await session.commit()
    
    # Login as admin to get session
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Create new user
    new_user_data = {
        "username": "new.analyst",
        "email": "new.analyst@example.com",
        "role": "ANALYST",
    }
    
    response = await client.post(
        "/api/v1/admin/auth/users",
        json=new_user_data,
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 201
    data = response.json()
    
    assert "userId" in data
    assert "expiresAt" in data
    assert data["resetToken"]
    
    # Verify user was created in database
    async with session_maker() as session:
        result = await session.execute(
            select(UserAccount).where(UserAccount.username == new_user_data["username"])
        )
        created_user = result.scalar_one_or_none()
        
        assert created_user is not None
        assert created_user.email == new_user_data["email"]
        assert created_user.role == UserRole.ANALYST
        assert created_user.status == UserStatus.ACTIVE
        assert created_user.must_change_password is False
        assert created_user.created_by_admin_id == admin.id
        assert created_user.password_hash is None

        reset_result = await session.execute(
            select(AdminResetRequest).where(AdminResetRequest.target_user_id == created_user.id)
        )
        reset_request = reset_result.scalar_one_or_none()
        assert reset_request is not None
        assert reset_request.token_hash


@pytest.mark.asyncio
async def test_admin_preprovisions_exact_oidc_identity_without_local_password_setup(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    admin = admin_user_factory(username="oidc.provisioning.admin")
    async with session_maker() as session:
        session.add(admin)
        await session.commit()

    session_cookie = await _login_and_get_cookie(client, admin.username)
    response = await client.post(
        "/api/v1/admin/auth/users/oidc",
        json={
            "username": "preprovisioned.oidc.user",
            "email": "preprovisioned.oidc.user@example.com",
            "role": "AUDITOR",
            "description": "Externally authenticated auditor",
            "oidc_issuer": "https://Issuer.example/Tenant",
            "oidc_subject": "Case-Sensitive-Subject",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 201, response.text
    user_id = UUID(response.json()["userId"])

    async with session_maker() as session:
        created_user = await session.get(UserAccount, user_id)
        reset_requests = (
            await session.execute(
                select(AdminResetRequest).where(
                    AdminResetRequest.target_user_id == user_id,
                )
            )
        ).scalars().all()
        audit_events = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.event_type == "auth.oidc.account_preprovisioned",
                    AuditLog.entity_id == str(user_id),
                )
            )
        ).scalars().all()

        assert created_user is not None
        assert created_user.account_type is AccountType.HUMAN
        assert created_user.username == "preprovisioned.oidc.user"
        assert str(created_user.email) == "preprovisioned.oidc.user@example.com"
        assert created_user.role is UserRole.AUDITOR
        assert created_user.description == "Externally authenticated auditor"
        assert created_user.oidc_issuer == "https://Issuer.example/Tenant"
        assert created_user.oidc_subject == "Case-Sensitive-Subject"
        assert created_user.password_hash is None
        assert created_user.password_updated_at is None
        assert created_user.created_by_admin_id == admin.id
        assert reset_requests == []
        assert len(audit_events) == 1
        assert audit_events[0].performed_by == str(admin.id)


@pytest.mark.asyncio
async def test_oidc_preprovisioning_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/admin/auth/users/oidc",
        json={
            "username": "unauthenticated.oidc.user",
            "email": "unauthenticated.oidc.user@example.com",
            "role": "ANALYST",
            "oidc_issuer": "https://issuer.example",
            "oidc_subject": "unauthenticated-subject",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_oidc_preprovisioning_requires_admin_role(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    analyst = analyst_user_factory(username="oidc.provisioning.nonadmin")
    async with session_maker() as session:
        session.add(analyst)
        await session.commit()

    session_cookie = await _login_and_get_cookie(client, analyst.username)
    response = await client.post(
        "/api/v1/admin/auth/users/oidc",
        json={
            "username": "nonadmin.oidc.user",
            "email": "nonadmin.oidc.user@example.com",
            "role": "ANALYST",
            "oidc_issuer": "https://issuer.example",
            "oidc_subject": "nonadmin-subject",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("collision", "message_fragment"),
    [
        ("identity", "OIDC identity"),
        ("username", "Username"),
        ("email", "Email"),
    ],
)
async def test_admin_oidc_preprovisioning_rejects_account_collisions(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
    collision: str,
    message_fragment: str,
) -> None:
    admin = admin_user_factory(username=f"oidc.collision.admin.{collision}")
    existing = analyst_user_factory(
        username=f"existing.oidc.{collision}",
        email=f"existing.oidc.{collision}@example.com",
    )
    existing.oidc_issuer = "https://issuer.example/Tenant"
    existing.oidc_subject = f"existing-subject-{collision}"
    async with session_maker() as session:
        session.add_all([admin, existing])
        await session.commit()

    payload = {
        "username": f"new.oidc.{collision}",
        "email": f"new.oidc.{collision}@example.com",
        "role": "ANALYST",
        "oidc_issuer": "https://new-issuer.example/Tenant",
        "oidc_subject": f"new-subject-{collision}",
    }
    if collision == "identity":
        payload["oidc_issuer"] = existing.oidc_issuer
        payload["oidc_subject"] = existing.oidc_subject
    elif collision == "username":
        payload["username"] = existing.username
    else:
        payload["email"] = str(existing.email)

    session_cookie = await _login_and_get_cookie(client, admin.username)
    response = await client.post(
        "/api/v1/admin/auth/users/oidc",
        json=payload,
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 400, response.text
    assert message_fragment in response.json()["detail"]["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "invalid_value", "case_name"),
    [
        ("oidc_issuer", " https://issuer.example/Tenant", "issuer-leading-space"),
        ("oidc_issuer", "https://issuer.example/Tenant ", "issuer-trailing-space"),
        ("oidc_issuer", "http://issuer.example/Tenant", "issuer-http"),
        ("oidc_issuer", "https://user@issuer.example/Tenant", "issuer-userinfo"),
        ("oidc_issuer", "https://issuer.example/Tenant?query=1", "issuer-query"),
        ("oidc_issuer", "https://issuer.example/Tenant#fragment", "issuer-fragment"),
        ("oidc_subject", " subject-with-spaces", "subject-leading-space"),
        ("oidc_subject", "subject-with-spaces ", "subject-trailing-space"),
    ],
)
async def test_admin_oidc_preprovisioning_rejects_invalid_exact_identity_values(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    field: str,
    invalid_value: str,
    case_name: str,
) -> None:
    admin = admin_user_factory(username=f"oidc.validation.admin.{case_name}")
    async with session_maker() as session:
        session.add(admin)
        await session.commit()

    payload = {
        "username": f"invalid.oidc.{case_name}",
        "email": f"invalid.oidc.{case_name}@example.com",
        "role": "ANALYST",
        "oidc_issuer": "https://issuer.example/Tenant",
        "oidc_subject": f"subject-{case_name}",
    }
    payload[field] = invalid_value
    session_cookie = await _login_and_get_cookie(client, admin.username)
    response = await client.post(
        "/api/v1/admin/auth/users/oidc",
        json=payload,
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_generic_user_update_rejects_oidc_identity_fields(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory(username="oidc.immutability.admin")
    user = analyst_user_factory(
        username="oidc.immutable.user",
        email="oidc.immutable.user@example.com",
    )
    user.oidc_issuer = "https://issuer.example/original"
    user.oidc_subject = "original-subject"
    async with session_maker() as session:
        session.add_all([admin, user])
        await session.commit()

    session_cookie = await _login_and_get_cookie(client, admin.username)
    response = await client.patch(
        f"/api/v1/admin/auth/users/{user.id}",
        json={
            "description": "must not be partially applied",
            "oidc_issuer": "https://issuer.example/replacement",
            "oidc_subject": "replacement-subject",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 422, response.text
    async with session_maker() as session:
        persisted = await session.get(UserAccount, user.id)
        assert persisted is not None
        assert persisted.description is None
        assert persisted.oidc_issuer == "https://issuer.example/original"
        assert persisted.oidc_subject == "original-subject"


@pytest.mark.asyncio
async def test_admin_create_nhi_with_override_timestamps(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    """Admin can create an NHI account with timestamp override capability."""
    admin = admin_user_factory()

    async with session_maker() as session:
        session.add(admin)
        await session.commit()

    session_cookie = await _login_and_get_cookie(client, admin.username)

    response = await client.post(
        "/api/v1/admin/auth/users/nhi",
        json={
            "username": "svc.migration",
            "role": "ANALYST",
            "assignable": False,
            "override_timestamps": True,
            "description": "Migration importer",
            "initial_api_key_name": "migration-key",
            "initial_api_key_expires_at": (
                datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)
            ).isoformat().replace("+00:00", "Z"),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 201, response.text
    assert response.json()["apiKey"]["scopes"] == ["api:read"]

    async with session_maker() as session:
        result = await session.execute(
            select(UserAccount).where(UserAccount.username == "svc.migration")
        )
        nhi_user = result.scalar_one_or_none()
        assert nhi_user is not None
        assert nhi_user.account_type == AccountType.NHI
        assert nhi_user.override_timestamps is True

    list_response = await client.get(
        "/api/v1/admin/auth/users",
        cookies={"intercept_session": session_cookie},
    )
    assert list_response.status_code == 200
    listed_user = next(
        item for item in list_response.json() if item["username"] == "svc.migration"
    )
    assert listed_user["overrideTimestamps"] is True


@pytest.mark.asyncio
async def test_admin_create_user_requires_authentication(
    client: AsyncClient,
) -> None:
    """Creating a user without authentication returns 401."""
    new_user_data = {
        "username": "test.user",
        "email": "test@example.com",
        "role": "ANALYST",
    }
    
    response = await client.post(
        "/api/v1/admin/auth/users",
        json=new_user_data,
    )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_create_user_requires_admin_role(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """Creating a user as non-admin returns 403."""
    analyst = analyst_user_factory()
    
    async with session_maker() as session:
        session.add(analyst)
        await session.commit()
    
    # Login as analyst
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Try to create user
    new_user_data = {
        "username": "test.user",
        "email": "test@example.com",
        "role": "ANALYST",
    }
    
    response = await client.post(
        "/api/v1/admin/auth/users",
        json=new_user_data,
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 403
    response_data = response.json()
    # HTTPException detail becomes the "detail" field in the response
    assert "detail" in response_data
    assert "admin" in response_data["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_admin_create_user_rejects_duplicate_username(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Creating a user with duplicate username returns 400."""
    admin = admin_user_factory()
    existing_analyst = analyst_user_factory()
    
    async with session_maker() as session:
        session.add(admin)
        session.add(existing_analyst)
        await session.commit()
    
    # Login as admin
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Try to create user with existing username
    new_user_data = {
        "username": existing_analyst.username,
        "email": "different@example.com",
        "role": "ANALYST",
    }
    
    response = await client.post(
        "/api/v1/admin/auth/users",
        json=new_user_data,
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 400
    response_data = response.json()
    assert "detail" in response_data
    assert "username" in response_data["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_non_admin_can_get_users_summary(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    admin_user_factory,
) -> None:
    """Authenticated non-admin users can load active human users for assignee dropdowns."""
    analyst = analyst_user_factory(username="analyst.viewer")
    admin = admin_user_factory(username="admin.visible")
    admin.oidc_issuer = "https://issuer.example"
    admin.oidc_subject = "admin-visible-subject"
    disabled_user = analyst_user_factory(username="analyst.disabled")
    disabled_user.status = UserStatus.DISABLED

    async with session_maker() as session:
        session.add(analyst)
        session.add(admin)
        session.add(disabled_user)
        await session.commit()

    session_cookie = await _login_and_get_cookie(client, analyst.username)

    response = await client.get(
        "/api/v1/admin/auth/users/summary",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    usernames = [item["username"] for item in payload]

    assert analyst.username in usernames
    assert admin.username in usernames
    assert disabled_user.username not in usernames
    assert all(item["accountType"] == "HUMAN" for item in payload)
    assert all("oidcIssuer" not in item for item in payload)
    assert all("oidcSubject" not in item for item in payload)


@pytest.mark.asyncio
async def test_users_summary_requires_authentication(
    client: AsyncClient,
) -> None:
    """Listing lightweight users still requires authentication."""
    response = await client.get("/api/v1/admin/auth/users/summary")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_non_admin_cannot_list_full_users(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """The router split must not widen access to admin-only user management endpoints."""
    analyst = analyst_user_factory(username="analyst.noadmin")

    async with session_maker() as session:
        session.add(analyst)
        await session.commit()

    session_cookie = await _login_and_get_cookie(client, analyst.username)

    response = await client.get(
        "/api/v1/admin/auth/users",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 403
    response_data = response.json()
    assert "detail" in response_data
    assert "admin" in response_data["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_admin_disable_user_success(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Admin can successfully disable an active user account."""
    admin = admin_user_factory()
    analyst = analyst_user_factory()
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        analyst_id = analyst.id
    
    # Login as admin
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Disable the analyst
    response = await client.patch(
        f"/api/v1/admin/auth/users/{analyst_id}/status",
        json={"status": "DISABLED"},
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 204
    
    # Verify user is disabled
    async with session_maker() as session:
        result = await session.get(UserAccount, analyst_id)
        assert result is not None
        assert result.status == UserStatus.DISABLED


@pytest.mark.asyncio
async def test_admin_disable_user_revokes_sessions(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Disabling a user revokes all their active sessions."""
    admin = admin_user_factory()
    analyst = analyst_user_factory()
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        analyst_id = analyst.id
    
    # Login as analyst to create a session
    analyst_login = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert analyst_login.status_code == 200
    
    # Login as admin
    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert admin_login.status_code == 200
    admin_session_cookie = admin_login.cookies.get("intercept_session")
    assert admin_session_cookie is not None
    
    # Verify analyst has active session
    async with session_maker() as session:
        result = await session.execute(
            select(AuthSession).where(
                AuthSession.user_id == analyst_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        active_sessions = result.scalars().all()
        assert len(active_sessions) == 1
    
    # Disable the analyst
    response = await client.patch(
        f"/api/v1/admin/auth/users/{analyst_id}/status",
        json={"status": "DISABLED"},
        cookies={"intercept_session": admin_session_cookie},
    )
    assert response.status_code == 204
    
    # Verify all sessions are revoked
    async with session_maker() as session:
        result = await session.execute(
            select(AuthSession).where(
                AuthSession.user_id == analyst_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        active_sessions = result.scalars().all()
        assert len(active_sessions) == 0


@pytest.mark.asyncio
async def test_admin_enable_user_success(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Admin can re-enable a disabled user account."""
    admin = admin_user_factory()
    analyst = analyst_user_factory()
    analyst.status = UserStatus.DISABLED
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        analyst_id = analyst.id
    
    # Login as admin
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Re-enable the analyst
    response = await client.patch(
        f"/api/v1/admin/auth/users/{analyst_id}/status",
        json={"status": "ACTIVE"},
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 204
    
    # Verify user is active
    async with session_maker() as session:
        result = await session.get(UserAccount, analyst_id)
        assert result is not None
        assert result.status == UserStatus.ACTIVE


@pytest.mark.asyncio
async def test_admin_lock_user_creates_indefinite_lock(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    analyst = analyst_user_factory()
    analyst.lockout_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    async with session_maker() as session:
        session.add_all([admin, analyst])
        await session.commit()
        analyst_id = analyst.id

    session_cookie = await _login_and_get_cookie(client, admin.username)
    response = await client.patch(
        f"/api/v1/admin/auth/users/{analyst_id}/status",
        json={"status": "LOCKED"},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 204
    async with session_maker() as session:
        refreshed = await session.get(UserAccount, analyst_id)
        assert refreshed is not None
        assert refreshed.status == UserStatus.LOCKED
        assert refreshed.lockout_expires_at is None


@pytest.mark.asyncio
async def test_admin_update_human_user_success(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Admin can update editable fields for a human user."""
    admin = admin_user_factory()
    analyst = analyst_user_factory(
        username="analyst.original",
        email="analyst.original@example.com",
    )
    analyst.description = "Original description"

    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        analyst_id = analyst.id

    session_cookie = await _login_and_get_cookie(client, admin.username)

    response = await client.patch(
        f"/api/v1/admin/auth/users/{analyst_id}",
        json={
            "username": "analyst.updated",
            "email": "analyst.updated@example.com",
            "role": "AUDITOR",
            "description": "Updated description",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 204

    async with session_maker() as session:
        updated_user = await session.get(UserAccount, analyst_id)
        assert updated_user is not None
        assert updated_user.username == "analyst.updated"
        assert updated_user.email == "analyst.updated@example.com"
        assert updated_user.role == UserRole.AUDITOR
        assert updated_user.description == "Updated description"

    list_response = await client.get(
        "/api/v1/admin/auth/users",
        cookies={"intercept_session": session_cookie},
    )

    assert list_response.status_code == 200
    listed_user = next(
        item for item in list_response.json() if item["id"] == str(analyst_id)
    )
    assert listed_user["description"] == "Updated description"


@pytest.mark.asyncio
async def test_admin_update_nhi_user_success(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    """Admin can update editable fields for an NHI user without email fields."""
    admin = admin_user_factory()
    now = datetime.now(timezone.utc)
    nhi_user = UserAccount(
        username="svc.original",
        account_type=AccountType.NHI,
        role=UserRole.ANALYST,
        description="Original service account",
        email=None,
        password_hash=None,
        status=UserStatus.ACTIVE,
        must_change_password=False,
        failed_login_attempts=0,
        created_at=now,
        updated_at=now,
        created_by_admin_id=admin.id,
    )

    async with session_maker() as session:
        session.add(admin)
        session.add(nhi_user)
        await session.commit()
        nhi_user_id = nhi_user.id

    session_cookie = await _login_and_get_cookie(client, admin.username)

    response = await client.patch(
        f"/api/v1/admin/auth/users/{nhi_user_id}",
        json={
            "username": "svc.updated",
            "role": "ADMIN",
            "description": "Updated service account",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 204

    async with session_maker() as session:
        updated_user = await session.get(UserAccount, nhi_user_id)
        assert updated_user is not None
        assert updated_user.username == "svc.updated"
        assert updated_user.role == UserRole.ADMIN
        assert updated_user.description == "Updated service account"
        assert updated_user.email is None


@pytest.mark.asyncio
async def test_admin_update_nhi_override_timestamps(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    """Admin can toggle timestamp override capability for NHI accounts."""
    admin = admin_user_factory()
    now = datetime.now(timezone.utc)
    nhi_user = UserAccount(
        username="svc.toggle",
        account_type=AccountType.NHI,
        role=UserRole.ANALYST,
        description="Service account",
        email=None,
        password_hash=None,
        status=UserStatus.ACTIVE,
        must_change_password=False,
        failed_login_attempts=0,
        override_timestamps=False,
        created_at=now,
        updated_at=now,
        created_by_admin_id=admin.id,
    )

    async with session_maker() as session:
        session.add(admin)
        session.add(nhi_user)
        await session.commit()
        nhi_user_id = nhi_user.id

    session_cookie = await _login_and_get_cookie(client, admin.username)

    response = await client.patch(
        f"/api/v1/admin/auth/users/{nhi_user_id}",
        json={"override_timestamps": True},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 204

    async with session_maker() as session:
        updated_user = await session.get(UserAccount, nhi_user_id)
        assert updated_user is not None
        assert updated_user.override_timestamps is True


@pytest.mark.asyncio
async def test_admin_cannot_enable_override_timestamps_for_human_user(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Timestamp override capability is NHI-only."""
    admin = admin_user_factory()
    analyst = analyst_user_factory()

    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        analyst_id = analyst.id

    session_cookie = await _login_and_get_cookie(client, admin.username)

    response = await client.patch(
        f"/api/v1/admin/auth/users/{analyst_id}",
        json={"override_timestamps": True},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 400
    assert "nhi" in response.json()["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_admin_update_status_requires_authentication(
    client: AsyncClient,
) -> None:
    """Updating user status without authentication returns 401."""
    user_id = uuid4()
    
    response = await client.patch(
        f"/api/v1/admin/auth/users/{user_id}/status",
        json={"status": "DISABLED"},
    )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_update_status_requires_admin_role(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """Updating user status as non-admin returns 403."""
    analyst = analyst_user_factory()
    target_user = analyst_user_factory()
    
    async with session_maker() as session:
        session.add(analyst)
        session.add(target_user)
        await session.commit()
        target_id = target_user.id
    
    # Login as analyst
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Try to disable user
    response = await client.patch(
        f"/api/v1/admin/auth/users/{target_id}/status",
        json={"status": "DISABLED"},
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_update_status_nonexistent_user(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    """Updating status of non-existent user returns 404."""
    admin = admin_user_factory()
    
    async with session_maker() as session:
        session.add(admin)
        await session.commit()
    
    # Login as admin
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Try to disable non-existent user
    fake_id = uuid4()
    response = await client.patch(
        f"/api/v1/admin/auth/users/{fake_id}/status",
        json={"status": "DISABLED"},
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 404
