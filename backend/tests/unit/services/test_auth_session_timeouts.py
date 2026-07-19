from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.models.enums import SessionRevokedReason, UserStatus
from app.services import auth_service as auth_service_module
from app.services.audit_service import AuditContext
from app.services.auth_service import AuthService, SessionNotFoundError


class _Hasher:
    def hash(self, value: str) -> str:
        return f"hashed:{value}"


def _service() -> AuthService:
    service = AuthService(password_hasher=_Hasher())
    service._idle_timeout = timedelta(hours=1)
    service._absolute_timeout = timedelta(hours=12)
    return service


@pytest.mark.asyncio
async def test_new_session_stores_absolute_expiration(monkeypatch: pytest.MonkeyPatch) -> None:
    audit_service = SimpleNamespace(login_success=AsyncMock())
    monkeypatch.setattr(auth_service_module, "get_audit_service", lambda db: audit_service)
    db = SimpleNamespace(add=Mock(), flush=AsyncMock())
    user = SimpleNamespace(
        id=uuid4(),
        username="analyst",
        role="ANALYST",
        status=UserStatus.ACTIVE,
    )
    before = datetime.now(timezone.utc)

    result = await _service().create_session_for_user(
        db,
        user=user,
        metadata=AuditContext(),
    )

    after = datetime.now(timezone.utc)
    assert before + timedelta(hours=12) <= result.session.expires_at <= after + timedelta(hours=12)
    assert result.session.expires_at > result.session.last_seen_at + timedelta(hours=1)


@pytest.mark.asyncio
async def test_session_is_revoked_after_idle_timeout() -> None:
    now = datetime.now(timezone.utc)
    session = SimpleNamespace(
        revoked_at=None,
        revoked_reason=None,
        expires_at=now + timedelta(hours=10),
        last_seen_at=now - timedelta(hours=1, seconds=1),
        user=SimpleNamespace(status=UserStatus.ACTIVE),
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: session))
    )

    with pytest.raises(SessionNotFoundError):
        await _service()._resolve_active_session(db, "token")

    assert session.revoked_reason == SessionRevokedReason.SESSION_TIMEOUT
    assert session.revoked_at is not None


@pytest.mark.asyncio
async def test_active_session_refreshes_idle_window_without_extending_absolute_expiration() -> None:
    now = datetime.now(timezone.utc)
    absolute_expiration = now + timedelta(hours=2)
    session = SimpleNamespace(
        revoked_at=None,
        revoked_reason=None,
        expires_at=absolute_expiration,
        last_seen_at=now - timedelta(minutes=30),
        user=SimpleNamespace(status=UserStatus.ACTIVE),
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: session))
    )

    resolved = await _service()._resolve_active_session(db, "token")

    assert resolved is session
    assert session.last_seen_at >= now
    assert session.expires_at == absolute_expiration


@pytest.mark.asyncio
async def test_rate_limiter_rebuilds_when_hot_settings_change(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = {
        "auth.login.rate_limit_attempts": 1,
        "auth.login.rate_limit_window_seconds": 60,
    }

    async def fake_get(self, key: str, default=None):
        return settings.get(key, default)

    monkeypatch.setattr(
        "app.services.settings_service.SettingsService.get",
        fake_get,
    )
    service = _service()
    db = SimpleNamespace()

    assert await service.check_rate_limit(db, "analyst:127.0.0.1") == (True, None)
    allowed, _ = await service.check_rate_limit(db, "analyst:127.0.0.1")
    assert allowed is False

    settings["auth.login.rate_limit_attempts"] = 2

    assert await service.check_rate_limit(db, "analyst:127.0.0.1") == (True, None)
    assert service._rate_limiter_config == (2, 60)
