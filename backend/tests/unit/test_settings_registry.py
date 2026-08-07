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


def test_dummy_data_routes_require_explicit_local_enablement() -> None:
    definition = SETTINGS_REGISTRY["dummy_data.enabled"]

    assert definition.env_var == "DUMMY_DATA_ENABLED"
    assert definition.local_only is True
    assert definition.default is False


def test_trusted_proxy_cidrs_are_explicit_local_configuration() -> None:
    definition = SETTINGS_REGISTRY["http.trusted_proxy_cidrs"]

    assert definition.env_var == "HTTP_TRUSTED_PROXY_CIDRS"
    assert definition.local_only is True
    assert definition.default == []


def test_password_hash_capacity_is_explicit_local_configuration() -> None:
    capacity = SETTINGS_REGISTRY["auth.password_work.max_concurrent"]
    lease = SETTINGS_REGISTRY["auth.password_work.lease_seconds"]

    assert capacity.env_var == "PASSWORD_HASH_MAX_CONCURRENT"
    assert capacity.local_only is True
    assert capacity.default == 8
    assert lease.env_var == "PASSWORD_HASH_LEASE_SECONDS"
    assert lease.local_only is True
    assert lease.default == 900


def test_oidc_jit_provisioning_requires_explicit_opt_in() -> None:
    definition = SETTINGS_REGISTRY["oidc.jit_provisioning"]

    assert definition.env_var == "OIDC_JIT_PROVISIONING"
    assert definition.default is False
