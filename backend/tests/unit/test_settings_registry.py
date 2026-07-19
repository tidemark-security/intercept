import pytest

from app.core.settings_registry import (
    SETTINGS_REGISTRY,
    _def,
    _register,
    get_setting_default,
)


def test_register_rejects_existing_key_without_replacing_definition() -> None:
    key, existing = next(iter(SETTINGS_REGISTRY.items()))

    with pytest.raises(ValueError, match=key.replace(".", r"\.")):
        _register(_def(key, description="replacement"))

    assert SETTINGS_REGISTRY[key] is existing


def test_register_rejects_duplicate_key_within_batch_atomically() -> None:
    key = "test.duplicate.setting"

    with pytest.raises(ValueError, match=r"test\.duplicate\.setting"):
        _register(_def(key), _def(key))

    assert key not in SETTINGS_REGISTRY


def test_get_setting_default_rejects_unknown_keys() -> None:
    assert get_setting_default("enrichment.ldap.use_ssl") is True

    with pytest.raises(KeyError, match="unknown\\.setting"):
        get_setting_default("unknown.setting")
