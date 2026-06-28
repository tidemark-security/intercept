from datetime import datetime, timezone
from uuid import uuid4

from app.models.enums import UserRole, UserStatus
from app.models.models import UserAccount
from app.services.passkey_service import PasskeyCredentialNotFoundError, PasskeyService
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

    async def _fake_get_typed_value(_self, key: str, default=None):
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
        "app.services.passkey_service.SettingsService.get_typed_value",
        _fake_get_typed_value,
    )
    monkeypatch.setattr("app.services.passkey_service.get_local", _fake_get_local)

    config = await service._load_config(db=None)  # type: ignore[arg-type]

    assert config.rp_id == "example.com"
    assert config.expected_origins == ["https://app.example.com"]


@pytest.mark.asyncio
async def test_load_config_parses_json_string_expected_origins(monkeypatch) -> None:
    service = PasskeyService()

    async def _fake_get_typed_value(_self, key: str, default=None):
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
        "app.services.passkey_service.SettingsService.get_typed_value",
        _fake_get_typed_value,
    )
    monkeypatch.setattr("app.services.passkey_service.get_local", _fake_get_local)

    config = await service._load_config(db=None)  # type: ignore[arg-type]

    assert config.expected_origins == [
        "https://one.example.com",
        "https://two.example.com",
    ]


@pytest.mark.asyncio
async def test_begin_authentication_requires_existing_active_passkey(monkeypatch) -> None:
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

    async def _fail_load_config(*_args, **_kwargs):
        raise AssertionError("passkey config should not load without credentials")

    monkeypatch.setattr(service, "list_user_passkeys", _empty_passkeys)
    monkeypatch.setattr(service, "_load_config", _fail_load_config)

    with pytest.raises(PasskeyCredentialNotFoundError):
        await service.begin_authentication(_Db(), username="admin")  # type: ignore[arg-type]
