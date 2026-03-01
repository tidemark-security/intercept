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
