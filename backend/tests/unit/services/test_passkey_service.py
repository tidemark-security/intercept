from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

from app.models.enums import UserRole, UserStatus
from sqlmodel import select
from webauthn.helpers.structs import UserVerificationRequirement

from app.models.models import UserAccount, WebAuthnChallenge
from app.services.passkey_service import PasskeyService
import pytest


def test_extract_transports_uses_response_transports() -> None:
    credential = {
        "response": {
            "transports": ["USB", "nfc", "invalid"],
        }
    }

    transports = PasskeyService._extract_transports(credential)

    assert transports == ["usb", "nfc"]


def test_extract_transports_falls_back_to_top_level_transports() -> None:
    credential = {
        "response": {"transports": []},
        "transports": ["hybrid", "ble"],
    }

    transports = PasskeyService._extract_transports(credential)

    assert transports == ["hybrid", "ble"]


def test_extract_transports_falls_back_to_platform_attachment() -> None:
    credential = {
        "response": {"transports": []},
        "authenticatorAttachment": "platform",
    }

    transports = PasskeyService._extract_transports(credential)

    assert transports == ["internal"]


@pytest.mark.asyncio
async def test_load_config_falls_back_to_cors_origins(monkeypatch) -> None:
    service = PasskeyService()

    async def _fake_get(_self, key: str, default=None):
        if key == "auth.passkeys.expected_origins":
            return None
        return default

    def _fake_get_local(key: str, default=None):
        if key == "cors_origins":
            return ["https://app.example.com"]
        if key == "auth.session.cookie_domain":
            return "example.com"
        return default

    monkeypatch.setattr(
        "app.services.passkey_service.SettingsService.get",
        _fake_get,
    )
    monkeypatch.setattr("app.services.passkey_service.get_local", _fake_get_local)

    config = await service._load_config(db=None)  # type: ignore[arg-type]

    assert config.rp_id == "example.com"
    assert config.expected_origins == ["https://app.example.com"]


@pytest.mark.asyncio
async def test_load_config_parses_json_string_expected_origins(monkeypatch) -> None:
    service = PasskeyService()

    async def _fake_get(_self, key: str, default=None):
        if key == "auth.passkeys.expected_origins":
            return '["https://one.example.com", "https://two.example.com"]'
        return default

    def _fake_get_local(key: str, default=None):
        if key == "cors_origins":
            return ["https://fallback.example.com"]
        if key == "auth.session.cookie_domain":
            return "example.com"
        return default

    monkeypatch.setattr(
        "app.services.passkey_service.SettingsService.get",
        _fake_get,
    )
    monkeypatch.setattr("app.services.passkey_service.get_local", _fake_get_local)

    config = await service._load_config(db=None)  # type: ignore[arg-type]

    assert config.expected_origins == [
        "https://one.example.com",
        "https://two.example.com",
    ]


@pytest.mark.asyncio
async def test_load_config_normalizes_list_origins(monkeypatch) -> None:
    service = PasskeyService()

    async def _fake_get(_self, key: str, default=None):
        if key == "auth.passkeys.expected_origins":
            return [" https://one.example.com ", "", "https://two.example.com"]
        return default

    monkeypatch.setattr(
        "app.services.passkey_service.SettingsService.get",
        _fake_get,
    )
    monkeypatch.setattr(
        "app.services.passkey_service.get_local",
        lambda key, default=None: "example.com" if key == "auth.session.cookie_domain" else default,
    )

    config = await service._load_config(db=None)  # type: ignore[arg-type]

    assert config.expected_origins == [
        "https://one.example.com",
        "https://two.example.com",
    ]


@pytest.mark.asyncio
async def test_create_challenge_deletes_expired_rows(session_maker: Any) -> None:
    now = datetime.now(timezone.utc)
    expired = WebAuthnChallenge(
        challenge="expired",
        flow_type="authentication",
        expires_at=now - timedelta(minutes=1),
    )
    active = WebAuthnChallenge(
        challenge="active",
        flow_type="authentication",
        expires_at=now + timedelta(minutes=5),
    )

    async with session_maker() as session:
        session.add_all([expired, active])
        await session.commit()

        created = await PasskeyService()._create_challenge(
            session,
            challenge="new",
            flow_type="authentication",
            ttl_seconds=300,
        )
        await session.commit()
        challenges = (await session.execute(select(WebAuthnChallenge))).scalars().all()

    assert {challenge.challenge for challenge in challenges} == {"active", "new"}
    assert created.expires_at > now


@pytest.mark.asyncio
async def test_begin_authentication_returns_decoy_without_active_passkey(monkeypatch) -> None:
    service = PasskeyService()
    now = datetime.now(timezone.utc)
    user = UserAccount(
        id=uuid4(),
        username="admin",
        email="admin@example.com",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        password_hash="hashed",
        password_updated_at=now,
        created_at=now,
        updated_at=now,
    )

    class _Result:
        def scalar_one_or_none(self):
            return user

    class _Db:
        async def execute(self, _query):
            return _Result()

    async def _empty_passkeys(*_args, **_kwargs):
        return []

    async def _load_config(*_args, **_kwargs):
        return SimpleNamespace(
            rp_id="localhost",
            timeout_ms=60_000,
            challenge_ttl_seconds=300,
            user_verification=UserVerificationRequirement.REQUIRED,
        )

    admission_id = uuid4()
    reserve_admission = AsyncMock(return_value=admission_id)
    finalize_admission = AsyncMock()

    monkeypatch.setattr(service, "list_user_passkeys", _empty_passkeys)
    monkeypatch.setattr(service, "_load_config", _load_config)
    monkeypatch.setattr(
        service,
        "_reserve_authentication_admission",
        reserve_admission,
    )
    monkeypatch.setattr(
        service,
        "_finalize_authentication_admission",
        finalize_admission,
    )
    monkeypatch.setattr(
        "app.services.passkey_service.oidc_local_credential_policy.capabilities_for",
        AsyncMock(return_value=SimpleNamespace(passkey_allowed=True)),
    )

    result, selected_user = await service.begin_authentication(  # type: ignore[arg-type]
        _Db(),
        username="admin",
        source_address="198.51.100.10",
    )

    assert selected_user is None
    assert result["options"]["allowCredentials"] == []
    reserve_admission.assert_awaited_once()
    finalize_admission.assert_awaited_once()
    assert finalize_admission.await_args.kwargs["admission_id"] == admission_id
    assert finalize_admission.await_args.kwargs["user_id"] is None
