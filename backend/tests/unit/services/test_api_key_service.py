from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import hash_opaque_token
from app.core.api_key_scopes import (
    API_ADMIN_SCOPE,
    API_READ_SCOPE,
    API_WRITE_SCOPE,
)
from app.models.enums import AccountType, UserStatus
from app.models.models import ApiKey, AuditLog, UserAccount
from app.services.api_key_service import (
    ApiKeyExpiredError,
    ApiKeyExpirationError,
    ApiKeyPolicyError,
    ApiKeyScopeError,
    ApiKeyScopeValidationError,
    ApiKeyNotFoundError,
    ApiKeyRevokedError,
    ApiKeyService,
    ApiKeyUserNotFoundError,
    UserInactiveError,
)
from app.services.oidc_local_credential_policy import LocalCredentialCapabilities


class _IndependentAuditSession:
    def __init__(self) -> None:
        self.pending: list[AuditLog] = []
        self.committed: list[AuditLog] = []

    async def __aenter__(self) -> _IndependentAuditSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, *_: object, **__: object) -> None:
        return None

    async def scalar(self, *_: object, **__: object) -> int:
        return 0

    def add(self, item: object) -> None:
        if isinstance(item, AuditLog):
            self.pending.append(item)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed.extend(self.pending)
        self.pending.clear()

    async def rollback(self) -> None:
        self.pending.clear()


class _EncodingForbiddenApiKey(str):
    """A large credential that exposes any attempt to hash its full value."""

    def encode(self, *_: object, **__: object) -> bytes:
        raise AssertionError("overlong API keys must be rejected before hashing")


def _service_dependencies() -> tuple[SimpleNamespace, UserAccount, SimpleNamespace]:
    user = UserAccount(
        id=uuid4(),
        username="api-key-owner",
        account_type=AccountType.NHI,
        status=UserStatus.ACTIVE,
    )
    db = SimpleNamespace(
        get=AsyncMock(return_value=user),
        add=Mock(),
        flush=AsyncMock(),
    )
    audit_service = SimpleNamespace(api_key_created=AsyncMock())
    return db, user, audit_service


@pytest.mark.asyncio
async def test_create_api_key_normalizes_aware_future_expiration_to_utc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, user, audit_service = _service_dependencies()
    monkeypatch.setattr(
        "app.services.api_key_service.get_audit_service",
        lambda _: audit_service,
    )
    local_timezone = timezone(timedelta(hours=5, minutes=30))
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).astimezone(local_timezone)

    api_key, _ = await ApiKeyService().create_api_key(
        db,
        user_id=user.id,
        name="aware-future",
        expires_at=expires_at,
    )

    expected = expires_at.astimezone(timezone.utc)
    assert api_key.expires_at == expected
    assert api_key.expires_at.tzinfo is timezone.utc
    assert audit_service.api_key_created.await_args.kwargs["expires_at"] == expected
    db.get.assert_awaited_once_with(
        UserAccount,
        user.id,
        populate_existing=True,
        with_for_update=True,
    )


@pytest.mark.asyncio
async def test_create_api_key_treats_naive_future_expiration_as_utc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, user, audit_service = _service_dependencies()
    monkeypatch.setattr(
        "app.services.api_key_service.get_audit_service",
        lambda _: audit_service,
    )
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)

    api_key, _ = await ApiKeyService().create_api_key(
        db,
        user_id=user.id,
        name="naive-future",
        expires_at=expires_at,
    )

    expected = expires_at.replace(tzinfo=timezone.utc)
    assert api_key.expires_at == expected
    assert audit_service.api_key_created.await_args.kwargs["expires_at"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expires_at",
    [
        pytest.param(datetime.now(timezone.utc), id="now"),
        pytest.param(datetime.now(timezone.utc) - timedelta(days=1), id="past"),
        pytest.param(datetime.now(timezone.utc).replace(tzinfo=None), id="naive-now"),
    ],
)
async def test_create_api_key_rejects_non_future_expiration_for_direct_callers(
    expires_at: datetime,
) -> None:
    db, user, _ = _service_dependencies()

    with pytest.raises(ApiKeyExpirationError, match="Expiration date must be in the future"):
        await ApiKeyService().create_api_key(
            db,
            user_id=user.id,
            name="invalid-expiration",
            expires_at=expires_at,
        )

    db.get.assert_not_awaited()
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_api_key_uses_typed_error_for_missing_user() -> None:
    db, user, _ = _service_dependencies()
    db.get.return_value = None

    with pytest.raises(ApiKeyUserNotFoundError, match=f"User {user.id} not found"):
        await ApiKeyService().create_api_key(
            db,
            user_id=user.id,
            name="missing-owner",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )

    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_api_key_rejects_inactive_owner() -> None:
    db, user, _ = _service_dependencies()
    user.status = UserStatus.DISABLED

    with pytest.raises(ApiKeyPolicyError, match="active account"):
        await ApiKeyService().create_api_key(
            db,
            user_id=user.id,
            name="inactive-owner",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )

    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_api_key_persists_explicit_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, user, audit_service = _service_dependencies()
    monkeypatch.setattr(
        "app.services.api_key_service.get_audit_service",
        lambda _: audit_service,
    )

    api_key, _ = await ApiKeyService().create_api_key(
        db,
        user_id=user.id,
        name="read-write",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        scopes={API_WRITE_SCOPE, API_READ_SCOPE},
    )

    assert api_key.scopes == [API_READ_SCOPE, API_WRITE_SCOPE]


@pytest.mark.asyncio
async def test_create_api_key_rejects_scope_above_owner_role() -> None:
    db, user, _ = _service_dependencies()

    with pytest.raises(ApiKeyScopeValidationError, match="not permitted"):
        await ApiKeyService().create_api_key(
            db,
            user_id=user.id,
            name="over-scoped",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            scopes={API_ADMIN_SCOPE},
        )

    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_api_key_rejects_expiration_beyond_configured_maximum() -> None:
    db, user, _ = _service_dependencies()

    with pytest.raises(ApiKeyExpirationError, match="90 days"):
        await ApiKeyService(max_lifetime_days=90).create_api_key(
            db,
            user_id=user.id,
            name="too-long",
            expires_at=datetime.now(timezone.utc) + timedelta(days=91),
            scopes={API_READ_SCOPE},
        )

    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_api_key_enforces_oidc_local_credential_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, user, _ = _service_dependencies()
    monkeypatch.setattr(
        "app.services.api_key_service.oidc_local_credential_policy.capabilities_for",
        AsyncMock(
            return_value=LocalCredentialCapabilities(
                password_login_allowed=False,
                passkey_allowed=False,
                api_key_allowed=False,
            )
        ),
    )

    with pytest.raises(ApiKeyPolicyError):
        await ApiKeyService().create_api_key(
            db,
            user_id=user.id,
            name="forbidden-local-key",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            scopes={API_READ_SCOPE},
        )

    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_validate_api_key_treats_naive_persisted_expiration_as_utc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, user, audit_service = _service_dependencies()
    audit_service.api_key_auth_success = AsyncMock()
    api_key = ApiKey(
        user_id=user.id,
        name="legacy-naive-expiration",
        prefix="tmi_legacy12",
        key_hash=hash_opaque_token("legacy-key"),
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
        scopes=[API_READ_SCOPE],
    )
    api_key.user = user
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: api_key),
        ),
        get=AsyncMock(return_value=user),
    )
    monkeypatch.setattr(
        "app.services.api_key_service.get_audit_service",
        lambda _: audit_service,
    )

    result = await ApiKeyService().validate_api_key(db, raw_key="legacy-key")

    assert result.api_key is api_key
    assert api_key.expires_at.tzinfo is timezone.utc


@pytest.mark.asyncio
async def test_validate_api_key_rejects_missing_required_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, user, _ = _service_dependencies()
    api_key = ApiKey(
        user_id=user.id,
        name="read-only",
        prefix="tmi_readonly",
        key_hash=hash_opaque_token("read-only-key"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        scopes=[API_READ_SCOPE],
    )
    api_key.user = user
    outer_db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: api_key),
        ),
        get=AsyncMock(return_value=user),
        rollback=AsyncMock(),
    )
    audit_db = _IndependentAuditSession()
    service = ApiKeyService(audit_session_factory=lambda: audit_db)

    with pytest.raises(ApiKeyScopeError) as exc_info:
        await service.validate_api_key(
            outer_db,
            raw_key="read-only-key",
            required_scopes={API_WRITE_SCOPE},
        )

    assert exc_info.value.missing_scopes == frozenset({API_WRITE_SCOPE})
    assert api_key.last_used_at is None


@pytest.mark.asyncio
async def test_invalid_api_key_audit_survives_caller_rollback_without_committing_caller_work() -> None:
    outer_db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: None),
        ),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    audit_db = _IndependentAuditSession()
    service = ApiKeyService(audit_session_factory=lambda: audit_db)

    with pytest.raises(ApiKeyNotFoundError):
        await service.validate_api_key(outer_db, raw_key="invalid-direct-key")

    outer_db.commit.assert_not_awaited()
    outer_db.rollback.assert_awaited_once()
    assert len(audit_db.committed) == 1
    assert audit_db.committed[0].event_type == "auth.api_key.auth_failure"
    assert '"reason": "key_not_found"' in (audit_db.committed[0].new_value or "")


@pytest.mark.asyncio
async def test_overlong_api_key_is_rejected_before_hashing() -> None:
    outer_db = SimpleNamespace(
        execute=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    audit_db = _IndependentAuditSession()
    service = ApiKeyService(audit_session_factory=lambda: audit_db)
    raw_key = _EncodingForbiddenApiKey("x" * 4096)

    with pytest.raises(ApiKeyNotFoundError):
        await service.validate_api_key(outer_db, raw_key=raw_key)

    outer_db.execute.assert_not_awaited()
    outer_db.commit.assert_not_awaited()
    outer_db.rollback.assert_awaited_once()
    assert len(audit_db.committed) == 1
    assert '"reason": "key_not_found"' in (audit_db.committed[0].new_value or "")


@pytest.mark.asyncio
async def test_expired_api_key_audit_survives_caller_rollback() -> None:
    _, user, _ = _service_dependencies()
    api_key = ApiKey(
        user_id=user.id,
        name="expired-key",
        prefix="tmi_expired1",
        key_hash=hash_opaque_token("expired-key"),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    api_key.user = user
    outer_pending: list[AuditLog] = []

    async def rollback() -> None:
        outer_pending.clear()

    outer_db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: api_key),
        ),
        get=AsyncMock(return_value=user),
        add=outer_pending.append,
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(side_effect=rollback),
    )
    audit_db = _IndependentAuditSession()
    service = ApiKeyService(audit_session_factory=lambda: audit_db)

    with pytest.raises(ApiKeyExpiredError):
        await service.validate_api_key(outer_db, raw_key="expired-key")

    outer_db.commit.assert_not_awaited()
    outer_db.rollback.assert_awaited_once()
    assert outer_pending == []
    assert len(audit_db.committed) == 1
    assert '"reason": "key_expired"' in (audit_db.committed[0].new_value or "")


@pytest.mark.asyncio
async def test_legacy_long_lived_api_key_expires_at_configured_maximum() -> None:
    _, user, _ = _service_dependencies()
    now = datetime.now(timezone.utc)
    api_key = ApiKey(
        user_id=user.id,
        name="legacy-long-lived-key",
        prefix="tmi_legacylg",
        key_hash=hash_opaque_token("legacy-long-lived-key"),
        created_at=now - timedelta(days=91),
        expires_at=now + timedelta(days=274),
    )
    api_key.user = user
    outer_pending: list[AuditLog] = []

    async def rollback() -> None:
        outer_pending.clear()

    outer_db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: api_key),
        ),
        get=AsyncMock(return_value=user),
        add=outer_pending.append,
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(side_effect=rollback),
    )
    audit_db = _IndependentAuditSession()
    service = ApiKeyService(
        audit_session_factory=lambda: audit_db,
        max_lifetime_days=90,
    )

    with pytest.raises(ApiKeyExpiredError):
        await service.validate_api_key(
            outer_db,
            raw_key="legacy-long-lived-key",
        )

    outer_db.commit.assert_not_awaited()
    outer_db.rollback.assert_awaited_once()
    assert outer_pending == []
    assert len(audit_db.committed) == 1
    assert '"reason": "key_expired"' in (audit_db.committed[0].new_value or "")


@pytest.mark.asyncio
async def test_revoked_api_key_audit_survives_caller_rollback() -> None:
    _, user, _ = _service_dependencies()
    api_key = ApiKey(
        user_id=user.id,
        name="revoked-key",
        prefix="tmi_revoked1",
        key_hash=hash_opaque_token("revoked-key"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        revoked_at=datetime.now(timezone.utc),
    )
    api_key.user = user
    outer_pending: list[AuditLog] = []

    async def rollback() -> None:
        outer_pending.clear()

    outer_db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: api_key),
        ),
        get=AsyncMock(return_value=user),
        add=outer_pending.append,
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(side_effect=rollback),
    )
    audit_db = _IndependentAuditSession()
    service = ApiKeyService(audit_session_factory=lambda: audit_db)

    with pytest.raises(ApiKeyRevokedError):
        await service.validate_api_key(outer_db, raw_key="revoked-key")

    outer_db.commit.assert_not_awaited()
    outer_db.rollback.assert_awaited_once()
    assert outer_pending == []
    assert len(audit_db.committed) == 1
    assert '"reason": "key_revoked"' in (audit_db.committed[0].new_value or "")


@pytest.mark.asyncio
async def test_inactive_user_api_key_audit_survives_caller_rollback() -> None:
    _, user, _ = _service_dependencies()
    user.status = UserStatus.DISABLED
    api_key = ApiKey(
        user_id=user.id,
        name="inactive-user-key",
        prefix="tmi_inactive",
        key_hash=hash_opaque_token("inactive-user-key"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    api_key.user = user
    outer_pending: list[AuditLog] = []

    async def rollback() -> None:
        outer_pending.clear()

    outer_db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: api_key),
        ),
        get=AsyncMock(return_value=user),
        add=outer_pending.append,
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(side_effect=rollback),
    )
    audit_db = _IndependentAuditSession()
    service = ApiKeyService(audit_session_factory=lambda: audit_db)

    with pytest.raises(UserInactiveError):
        await service.validate_api_key(outer_db, raw_key="inactive-user-key")

    outer_db.commit.assert_not_awaited()
    outer_db.rollback.assert_awaited_once()
    assert outer_pending == []
    assert len(audit_db.committed) == 1
    assert '"reason": "user_inactive"' in (audit_db.committed[0].new_value or "")


@pytest.mark.asyncio
async def test_rejected_api_key_audits_do_not_exhaust_bounded_pool(
    async_engine: AsyncEngine,
) -> None:
    bounded_engine = create_async_engine(
        async_engine.url,
        future=True,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.5,
    )
    bounded_sessions = async_sessionmaker(
        bounded_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    service = ApiKeyService(audit_session_factory=bounded_sessions)

    async def reject(raw_key: str) -> None:
        async with bounded_sessions() as source_db:
            with pytest.raises(ApiKeyNotFoundError):
                await service.validate_api_key(source_db, raw_key=raw_key)

    try:
        await asyncio.wait_for(
            asyncio.gather(reject("invalid-concurrent-one"), reject("invalid-concurrent-two")),
            timeout=2,
        )

        async with bounded_sessions() as verification_db:
            result = await verification_db.execute(
                select(AuditLog).where(
                    AuditLog.event_type == "auth.api_key.auth_failure",
                )
            )
            audit_logs = list(result.scalars())

        assert len(audit_logs) == 2
        assert all('"reason": "key_not_found"' in (item.new_value or "") for item in audit_logs)
    finally:
        await bounded_engine.dispose()
