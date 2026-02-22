from app.services.passkey_service import PasskeyService


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
