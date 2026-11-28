from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from unittest.mock import AsyncMock

import app.services.oidc_service as oidc_module
from app.core.security import hash_opaque_token
from app.services.oidc_discovery_cache import OIDCDiscoveryCache
from app.services.oidc_service import (
    OIDCConfigurationError,
    OIDCConsumedStateError,
    OIDCProviderConfiguration,
    OIDCService,
    oidc_redirect_origin,
    validate_oidc_discovery_url,
    validate_oidc_provider_metadata,
    validate_oidc_redirect_uri,
)


CANONICAL_CALLBACK = "https://intercept.example/api/v1/auth/oidc/callback"


def _provider(
    *,
    client_secret: str | None = "secret",
    authorization_endpoint: str = "https://idp.example/authorize",
) -> OIDCProviderConfiguration:
    return OIDCProviderConfiguration(
        discovery_url="https://idp.example/.well-known/openid-configuration",
        issuer="https://idp.example",
        authorization_endpoint=authorization_endpoint,
        token_endpoint="https://idp.example/token",
        jwks_uri="https://idp.example/jwks",
        client_id="intercept-client",
        client_secret=client_secret,
        scopes="openid email profile",
        provider_name="Example IdP",
        redirect_uri=CANONICAL_CALLBACK,
    )


@pytest.mark.asyncio
async def test_begin_login_uses_s256_pkce_and_canonical_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OIDCService()
    stored: list[Any] = []
    db = SimpleNamespace(add=stored.append, flush=AsyncMock())

    async def fake_load_provider(_db: Any) -> OIDCProviderConfiguration:
        return _provider()

    async def fake_reserve(
        _db: Any,
        *,
        auth_request: Any,
        policy: Any,
    ) -> None:
        _ = policy
        stored.append(auth_request)
        await db.flush()

    monkeypatch.setattr(service, "_load_provider_configuration", fake_load_provider)
    service._auth_request_service = SimpleNamespace(reserve=fake_reserve)

    authorization_url, _, verifier = await service.begin_login(
        db,
        redirect_to="https://intercept.example/cases",
    )

    params = parse_qs(urlparse(authorization_url).query)
    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    assert params["redirect_uri"] == [CANONICAL_CALLBACK]
    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"] == [expected_challenge]
    assert 43 <= len(verifier) <= 128
    assert stored[0].browser_binding_hash == hash_opaque_token(verifier)
    assert verifier not in stored[0].browser_binding_hash


@pytest.mark.asyncio
async def test_begin_login_merges_existing_authorization_endpoint_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OIDCService()
    db = SimpleNamespace()

    async def fake_load_provider(_db: Any) -> OIDCProviderConfiguration:
        return _provider(
            authorization_endpoint=(
                "https://idp.example/authorize?policy=signin&client_id=untrusted"
            )
        )

    async def fake_reserve(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(service, "_load_provider_configuration", fake_load_provider)
    service._auth_request_service = SimpleNamespace(reserve=fake_reserve)

    authorization_url, _, _ = await service.begin_login(
        db,
        redirect_to="https://intercept.example/cases",
    )

    parsed = urlparse(authorization_url)
    params = parse_qs(parsed.query)
    assert authorization_url.count("?") == 1
    assert params["policy"] == ["signin"]
    assert params["client_id"] == ["intercept-client"]
    assert params["redirect_uri"] == [CANONICAL_CALLBACK]
    assert "state" in params


def test_provider_display_name_is_not_part_of_authorization_snapshot() -> None:
    original = _provider()
    renamed = _provider()
    renamed.provider_name = "Renamed sign-in button"

    assert renamed.authorization_snapshot() == original.authorization_snapshot()


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeHTTPClient:
    def __init__(self) -> None:
        self.token_request: dict[str, Any] | None = None

    async def __aenter__(self) -> "_FakeHTTPClient":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def post(self, _url: str, *, data: dict[str, Any], auth: Any = None) -> _FakeResponse:
        self.token_request = {"data": data, "auth": auth}
        return _FakeResponse({"id_token": "signed-id-token"})

    async def get(self, _url: str) -> _FakeResponse:
        return _FakeResponse({"keys": [{"kid": "test"}]})


@pytest.mark.asyncio
@pytest.mark.parametrize("client_secret", ["secret", None])
async def test_token_exchange_forwards_verifier_and_same_canonical_callback(
    monkeypatch: pytest.MonkeyPatch,
    client_secret: str | None,
) -> None:
    service = OIDCService()
    fake_client = _FakeHTTPClient()
    verifier = "v" * 43
    user = SimpleNamespace(username="oidc-user")
    policy_events: list[str] = []

    async def fake_consume(
        _db: Any,
        *,
        state: str,
        browser_binding_token: str | None,
    ) -> SimpleNamespace:
        assert state == "state-token"
        assert browser_binding_token == verifier
        return SimpleNamespace(
            nonce="nonce",
            redirect_to="https://intercept.example/cases",
            created_at=datetime.now(timezone.utc),
        )

    async def fake_load_provider(_db: Any) -> OIDCProviderConfiguration:
        return _provider(client_secret=client_secret)

    async def fake_find_or_create_user(
        _db: Any,
        *,
        claims: dict[str, Any],
        issuer: str,
    ) -> Any:
        policy_events.append("identity")
        assert claims["sub"] == "subject-123"
        assert issuer == "https://idp.example"
        return user

    async def fake_acquire_oidc_policy_lock(
        _db: Any,
        *,
        shared: bool,
    ) -> None:
        assert shared is True
        policy_events.append("shared_gate")

    async def fake_setting_get(
        _self: Any,
        key: str,
        default: object = None,
    ) -> object:
        assert key == "oidc.enabled"
        policy_events.append("enabled_check")
        return True

    async def fake_is_safe_redirect_target(_db: Any, target: str) -> bool:
        assert target == "https://intercept.example/cases"
        policy_events.append("redirect_policy")
        return True

    monkeypatch.setattr(service, "_consume_auth_request", fake_consume)
    monkeypatch.setattr(service, "_load_provider_configuration", fake_load_provider)
    monkeypatch.setattr(
        service,
        "validate_id_token",
        lambda **_kwargs: {"sub": "subject-123"},
    )
    monkeypatch.setattr(service, "find_or_create_user", fake_find_or_create_user)
    monkeypatch.setattr(
        oidc_module,
        "acquire_oidc_policy_lock",
        fake_acquire_oidc_policy_lock,
    )
    monkeypatch.setattr(oidc_module.SettingsService, "get", fake_setting_get)
    monkeypatch.setattr(
        service,
        "is_safe_redirect_target",
        fake_is_safe_redirect_target,
    )
    monkeypatch.setattr(
        oidc_module.httpx,
        "AsyncClient",
        lambda **_kwargs: fake_client,
    )

    result = await service.exchange_code(
        SimpleNamespace(),
        code="authorization-code",
        state="state-token",
        browser_binding_token=verifier,
    )

    assert result[0] is user
    assert fake_client.token_request is not None
    assert fake_client.token_request["data"]["code_verifier"] == verifier
    assert fake_client.token_request["data"]["redirect_uri"] == CANONICAL_CALLBACK
    assert policy_events == [
        "shared_gate",
        "enabled_check",
        "redirect_policy",
        "identity",
    ]
    if client_secret is None:
        assert fake_client.token_request["auth"] is None
    else:
        assert fake_client.token_request["auth"] is not None


@pytest.mark.asyncio
async def test_token_exchange_rechecks_enabled_under_shared_policy_gate_before_identity_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OIDCService()
    fake_client = _FakeHTTPClient()
    identity_lookup = AsyncMock()
    events: list[str] = []

    async def fake_consume(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        events.append("state_consumed")
        return SimpleNamespace(
            nonce="nonce",
            redirect_to="https://intercept.example/cases",
            created_at=datetime.now(timezone.utc),
        )

    async def fake_load_provider(_db: Any) -> OIDCProviderConfiguration:
        return _provider()

    async def fake_acquire(
        _db: Any,
        *,
        shared: bool,
    ) -> None:
        assert shared is True
        events.append("shared_gate")

    async def fake_setting_get(
        _self: Any,
        key: str,
        default: object = None,
    ) -> object:
        assert key == "oidc.enabled"
        events.append("enabled_check")
        return False

    monkeypatch.setattr(service, "_consume_auth_request", fake_consume)
    monkeypatch.setattr(service, "_load_provider_configuration", fake_load_provider)
    monkeypatch.setattr(service, "find_or_create_user", identity_lookup)
    monkeypatch.setattr(
        service,
        "validate_id_token",
        lambda **_kwargs: {"sub": "subject-123"},
    )
    monkeypatch.setattr(oidc_module, "acquire_oidc_policy_lock", fake_acquire)
    monkeypatch.setattr(oidc_module.SettingsService, "get", fake_setting_get)
    monkeypatch.setattr(
        oidc_module.httpx,
        "AsyncClient",
        lambda **_kwargs: fake_client,
    )

    with pytest.raises(OIDCConsumedStateError, match="disabled"):
        await service.exchange_code(
            SimpleNamespace(),
            code="authorization-code",
            state="state-token",
            browser_binding_token="v" * 43,
        )

    assert events == ["state_consumed", "shared_gate", "enabled_check"]
    identity_lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_token_exchange_rejects_provider_configuration_rotated_during_remote_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OIDCService()
    fake_client = _FakeHTTPClient()
    identity_lookup = AsyncMock()
    redirect_check = AsyncMock(return_value=True)
    providers = [
        _provider(client_secret="compromised-secret"),
        _provider(client_secret="rotated-secret"),
    ]
    events: list[str] = []
    provider_load_count = 0

    async def fake_consume(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            nonce="nonce",
            redirect_to="https://intercept.example/cases",
            created_at=datetime.now(timezone.utc),
        )

    async def fake_load_provider(_db: Any) -> OIDCProviderConfiguration:
        nonlocal provider_load_count
        provider_load_count += 1
        events.append(f"provider_{provider_load_count}")
        return providers.pop(0)

    async def fake_acquire(
        _db: Any,
        *,
        shared: bool,
    ) -> None:
        assert shared is True
        events.append("shared_gate")

    async def fake_setting_get(
        _self: Any,
        key: str,
        default: object = None,
    ) -> object:
        assert key == "oidc.enabled"
        events.append("enabled_check")
        return True

    monkeypatch.setattr(service, "_consume_auth_request", fake_consume)
    monkeypatch.setattr(service, "_load_provider_configuration", fake_load_provider)
    monkeypatch.setattr(service, "find_or_create_user", identity_lookup)
    monkeypatch.setattr(service, "is_safe_redirect_target", redirect_check)
    monkeypatch.setattr(
        service,
        "validate_id_token",
        lambda **_kwargs: {"sub": "subject-123"},
    )
    monkeypatch.setattr(oidc_module, "acquire_oidc_policy_lock", fake_acquire)
    monkeypatch.setattr(oidc_module.SettingsService, "get", fake_setting_get)
    monkeypatch.setattr(
        oidc_module.httpx,
        "AsyncClient",
        lambda **_kwargs: fake_client,
    )

    with pytest.raises(OIDCConsumedStateError, match="configuration changed"):
        await service.exchange_code(
            SimpleNamespace(),
            code="authorization-code",
            state="state-token",
            browser_binding_token="v" * 43,
        )

    assert events == [
        "provider_1",
        "shared_gate",
        "enabled_check",
        "provider_2",
    ]
    identity_lookup.assert_not_awaited()
    redirect_check.assert_not_awaited()


@pytest.mark.parametrize(
    "uri",
    [
        CANONICAL_CALLBACK,
        "http://localhost:8080/api/v1/auth/oidc/callback",
        "http://127.0.0.1:8080/api/v1/auth/oidc/callback",
    ],
)
def test_canonical_callback_validation_accepts_https_and_loopback_http(uri: str) -> None:
    assert validate_oidc_redirect_uri(uri) == uri


@pytest.mark.parametrize(
    "uri",
    [
        "http://intercept.example/api/v1/auth/oidc/callback",
        "https://user:password@intercept.example/api/v1/auth/oidc/callback",
        "https://intercept.example/api/v1/auth/oidc/callback?next=evil",
        "https://intercept.example/api/v1/auth/oidc/callback#fragment",
        "file:///api/v1/auth/oidc/callback",
    ],
)
def test_canonical_callback_validation_rejects_unsafe_uris(uri: str) -> None:
    with pytest.raises(OIDCConfigurationError):
        validate_oidc_redirect_uri(uri)


def test_canonical_error_origin_is_derived_from_callback() -> None:
    assert oidc_redirect_origin(CANONICAL_CALLBACK) == "https://intercept.example"


def test_configured_discovery_url_explicitly_supports_https_query_parameters() -> None:
    discovery_url = (
        "https://idp.example/.well-known/openid-configuration?tenant=security"
    )

    assert validate_oidc_discovery_url(discovery_url) == discovery_url


@pytest.mark.parametrize(
    "discovery_url",
    [
        "http://idp.example/.well-known/openid-configuration",
        "//idp.example/.well-known/openid-configuration",
        "https://user:password@idp.example/.well-known/openid-configuration",
        "https://idp.example/.well-known/openid-configuration#fragment",
        " https://idp.example/.well-known/openid-configuration",
        "https://idp.example/.well-known/openid-configuration\n",
        "https://idp.example:/.well-known/openid-configuration",
        "https://idp.example:0/.well-known/openid-configuration",
        "https://idp.example:70000/.well-known/openid-configuration",
    ],
)
def test_configured_discovery_url_rejects_unsafe_values_before_network(
    discovery_url: str,
) -> None:
    with pytest.raises(OIDCConfigurationError, match="discovery URL"):
        validate_oidc_discovery_url(discovery_url)


def _discovery_metadata(**overrides: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "issuer": "https://idp.example/tenant",
        "authorization_endpoint": "https://idp.example/authorize",
        "token_endpoint": "https://idp.example/token",
        "jwks_uri": "https://idp.example/jwks",
    }
    metadata.update(overrides)
    return metadata


def test_oidc_provider_metadata_accepts_absolute_https_endpoints() -> None:
    metadata = _discovery_metadata(
        authorization_endpoint="https://idp.example/authorize?policy=signin",
    )

    assert validate_oidc_provider_metadata(metadata) == metadata


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("issuer", "http://idp.example/tenant"),
        ("issuer", "https://idp.example/tenant?query=forbidden"),
        ("issuer", "https://idp.example/tenant#fragment"),
        ("authorization_endpoint", "http://idp.example/authorize"),
        ("token_endpoint", "http://169.254.169.254/token"),
        ("token_endpoint", "https://user:password@idp.example/token"),
        ("jwks_uri", "javascript:alert(1)"),
        ("jwks_uri", "https://idp.example/jwks#fragment"),
    ],
)
def test_oidc_provider_metadata_rejects_unsafe_urls(
    field_name: str,
    value: str,
) -> None:
    with pytest.raises(OIDCConfigurationError, match=field_name):
        validate_oidc_provider_metadata(
            _discovery_metadata(**{field_name: value})
        )


@pytest.mark.asyncio
async def test_provider_discovery_reuses_validated_metadata_within_cache_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OIDCService()
    discovery_requests = 0

    async def fake_setting_get(
        _self: Any,
        key: str,
        default: object = None,
    ) -> object:
        return {
            "oidc.discovery_url": "https://idp.example/.well-known/openid-configuration",
            "oidc.client_id": "intercept-client",
        }.get(key, default)

    class DiscoveryClient:
        async def __aenter__(self) -> "DiscoveryClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def get(self, url: str) -> _FakeResponse:
            nonlocal discovery_requests
            assert url == "https://idp.example/.well-known/openid-configuration"
            discovery_requests += 1
            return _FakeResponse(_discovery_metadata())

    monkeypatch.setattr(oidc_module.SettingsService, "get", fake_setting_get)
    monkeypatch.setattr(
        oidc_module.httpx,
        "AsyncClient",
        lambda **_kwargs: DiscoveryClient(),
    )

    first = await service._load_provider_configuration(SimpleNamespace())
    second = await service._load_provider_configuration(SimpleNamespace())

    assert first.issuer == second.issuer == "https://idp.example/tenant"
    assert discovery_requests == 1


@pytest.mark.asyncio
async def test_provider_discovery_coalesces_concurrent_cache_misses() -> None:
    cache = OIDCDiscoveryCache()
    loader_started = asyncio.Event()
    release_loader = asyncio.Event()
    discovery_requests = 0

    async def load_metadata() -> dict[str, object]:
        nonlocal discovery_requests
        discovery_requests += 1
        loader_started.set()
        await release_loader.wait()
        return _discovery_metadata()

    first = asyncio.create_task(cache.get("https://idp.example/discovery", load_metadata))
    second = asyncio.create_task(cache.get("https://idp.example/discovery", load_metadata))
    await loader_started.wait()
    release_loader.set()

    assert await first == await second == _discovery_metadata()
    assert discovery_requests == 1


@pytest.mark.asyncio
async def test_provider_discovery_negative_caches_failures() -> None:
    cache = OIDCDiscoveryCache()
    discovery_requests = 0

    async def load_invalid_metadata() -> dict[str, object]:
        nonlocal discovery_requests
        discovery_requests += 1
        raise OIDCConfigurationError("OIDC discovery metadata is invalid")

    for _attempt in range(2):
        with pytest.raises(
            OIDCConfigurationError,
            match="OIDC discovery metadata is invalid",
        ):
            await cache.get(
                "https://idp.example/discovery",
                load_invalid_metadata,
            )

    assert discovery_requests == 1
