from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastmcp.server.auth.providers.in_memory import InMemoryOAuthProvider
from httpx import ASGITransport, AsyncClient
from key_value.aio.stores.postgresql import PostgreSQLStore
from key_value.aio.errors.wrappers import DecryptionError
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions

from app.mcp.auth import MCPConfigurationError, derive_mcp_keys
from app.mcp.runtime import (
    MCPAuthMode,
    build_mcp_runtime,
    build_native_oauth_storage,
    create_native_mcp_lifespan,
    load_mcp_auth_snapshot,
    normalize_asyncpg_url,
)
from app.services.mcp_registration_service import MCPRegistrationPolicy


class _Settings:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    async def get(self, key: str, default=None):
        return self.values.get(key, default)


def _base_settings(**overrides: object) -> _Settings:
    values: dict[str, object] = {
        "mcp.oauth.enabled": True,
        "mcp.oauth.public_base_url": "https://intercept.example",
        "mcp.oauth.login_base_url": "",
        "mcp.oauth.access_token_ttl_seconds": 3600,
        "mcp.oauth.refresh_token_ttl_days": 30,
        "oidc.enabled": False,
        "oidc.discovery_url": None,
        "oidc.client_id": None,
        "oidc.client_secret": None,
        "oidc.scopes": "openid email profile",
        "oidc.provider_name": "SSO",
        "oidc.jit_provisioning": True,
        "oidc.default_role": "ANALYST",
        "oidc.role_claim_path": "",
        "oidc.role_mapping": {},
    }
    values.update(overrides)
    return _Settings(values)


@pytest.mark.asyncio
async def test_local_auth_is_selected_only_when_app_oidc_is_disabled() -> None:
    snapshot = await load_mcp_auth_snapshot(_base_settings())

    assert snapshot.mode is MCPAuthMode.LOCAL_OAUTH
    assert snapshot.public_origin == "https://intercept.example"
    assert snapshot.login_origin == "https://intercept.example"
    assert snapshot.oauth_base_url == "https://intercept.example/mcp"
    assert snapshot.resource_url == "https://intercept.example/mcp/streamable/"
    assert snapshot.registration_policy == MCPRegistrationPolicy()


@pytest.mark.asyncio
async def test_registration_limits_are_frozen_and_must_be_positive() -> None:
    snapshot = await load_mcp_auth_snapshot(
        _base_settings(
            **{
                "mcp.oauth.registration_max_body_bytes": 8192,
                "mcp.oauth.registration_pending_quota": 75,
                "mcp.oauth.registration_total_quota": 125,
                "mcp.oauth.registration_per_ip_quota": 12,
                "mcp.oauth.registration_rate_window_seconds": 900,
                "mcp.oauth.registration_abandoned_ttl_seconds": 1800,
                "mcp.oauth.registration_active_ttl_seconds": 3_000_000,
                "mcp.oauth.pending_authorization_global_quota": 200,
                "mcp.oauth.pending_authorization_per_client_quota": 4,
                "mcp.oauth.pending_authorization_per_source_quota": 9,
                "mcp.oauth.cimd_fetch_reservation_ttl_seconds": 45,
                "mcp.oauth.cimd_cache_max_entries": 64,
            }
        )
    )

    assert snapshot.registration_policy == MCPRegistrationPolicy(
        max_body_bytes=8192,
        pending_quota=75,
        total_quota=125,
        per_ip_quota=12,
        rate_window_seconds=900,
        abandoned_ttl_seconds=1800,
        active_ttl_seconds=3_000_000,
        pending_authorization_global_quota=200,
        pending_authorization_per_client_quota=4,
        pending_authorization_per_source_quota=9,
        cimd_fetch_reservation_ttl_seconds=45,
        cimd_cache_max_entries=64,
    )

    with pytest.raises(MCPConfigurationError, match="registration limits"):
        await load_mcp_auth_snapshot(
            _base_settings(
                **{"mcp.oauth.registration_pending_quota": 0}
            )
        )

    with pytest.raises(MCPConfigurationError, match="registration limits"):
        await load_mcp_auth_snapshot(
            _base_settings(**{"mcp.oauth.cimd_cache_max_entries": 0})
        )

    with pytest.raises(MCPConfigurationError, match="registration limits"):
        await load_mcp_auth_snapshot(
            _base_settings(
                **{"mcp.oauth.pending_authorization_per_source_quota": 0}
            )
        )


@pytest.mark.asyncio
async def test_registration_abandoned_ttl_must_cover_rate_window() -> None:
    with pytest.raises(
        MCPConfigurationError,
        match="abandoned.*rate window",
    ):
        await load_mcp_auth_snapshot(
            _base_settings(
                **{
                    "mcp.oauth.registration_rate_window_seconds": 3600,
                    "mcp.oauth.registration_abandoned_ttl_seconds": 60,
                }
            )
        )


@pytest.mark.asyncio
async def test_registration_activity_ttl_covers_issued_token_lifetimes() -> None:
    snapshot = await load_mcp_auth_snapshot(
        _base_settings(
            **{
                "mcp.oauth.access_token_ttl_seconds": 7200,
                "mcp.oauth.refresh_token_ttl_days": 7,
                "mcp.oauth.registration_active_ttl_seconds": 60,
            }
        )
    )

    assert snapshot.registration_policy.active_ttl_seconds == 7 * 24 * 60 * 60


@pytest.mark.asyncio
async def test_complete_oidc_configuration_selects_proxy_mode() -> None:
    snapshot = await load_mcp_auth_snapshot(
        _base_settings(
            **{
                "oidc.enabled": True,
                "oidc.discovery_url": "https://issuer.example/.well-known/openid-configuration",
                "oidc.client_id": "client-id",
                "oidc.client_secret": "client-secret",
            }
        )
    )

    assert snapshot.mode is MCPAuthMode.OIDC_PROXY
    assert snapshot.oidc is not None
    assert snapshot.oidc.client_secret == "client-secret"
    assert snapshot.oidc.jit_provisioning is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "discovery_url",
    [
        "https://user:password@issuer.example/.well-known/openid-configuration",
        "https://issuer.example/.well-known/openid-configuration#fragment",
        " https://issuer.example/.well-known/openid-configuration",
        "https://issuer.example:0/.well-known/openid-configuration",
        "https://issuer.example:70000/.well-known/openid-configuration",
    ],
)
async def test_oidc_runtime_uses_strict_shared_discovery_url_contract(
    discovery_url: str,
) -> None:
    with pytest.raises(MCPConfigurationError, match="discovery URL"):
        await load_mcp_auth_snapshot(
            _base_settings(
                **{
                    "oidc.enabled": True,
                    "oidc.discovery_url": discovery_url,
                    "oidc.client_id": "client-id",
                    "oidc.client_secret": "client-secret",
                }
            )
        )


@pytest.mark.asyncio
async def test_oidc_jit_provisioning_defaults_off_in_runtime_snapshot() -> None:
    settings = _base_settings(
        **{
            "oidc.enabled": True,
            "oidc.discovery_url": "https://issuer.example/.well-known/openid-configuration",
            "oidc.client_id": "client-id",
            "oidc.client_secret": "client-secret",
        }
    )
    settings.values.pop("oidc.jit_provisioning")

    snapshot = await load_mcp_auth_snapshot(settings)

    assert snapshot.oidc is not None
    assert snapshot.oidc.jit_provisioning is False


@pytest.mark.asyncio
async def test_enabled_but_incomplete_oidc_fails_startup() -> None:
    with pytest.raises(MCPConfigurationError, match="OIDC"):
        await load_mcp_auth_snapshot(
            _base_settings(
                **{
                    "oidc.enabled": True,
                    "oidc.discovery_url": "https://issuer.example/.well-known/openid-configuration",
                    "oidc.client_id": "client-id",
                    "oidc.client_secret": "",
                }
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"oidc.scopes": "email profile"},
        {"oidc.default_role": "SUPERUSER"},
        {"oidc.role_mapping": {"security": "SUPERUSER"}},
    ],
)
async def test_invalid_oidc_identity_policy_fails_startup(
    overrides: dict[str, object],
) -> None:
    settings = {
        "oidc.enabled": True,
        "oidc.discovery_url": "https://issuer.example/.well-known/openid-configuration",
        "oidc.client_id": "client-id",
        "oidc.client_secret": "client-secret",
        **overrides,
    }

    with pytest.raises(MCPConfigurationError, match="OIDC"):
        await load_mcp_auth_snapshot(_base_settings(**settings))


@pytest.mark.asyncio
async def test_oauth_kill_switch_selects_api_keys_only() -> None:
    snapshot = await load_mcp_auth_snapshot(
        _base_settings(**{"mcp.oauth.enabled": False})
    )

    assert snapshot.mode is MCPAuthMode.API_KEY_ONLY


@pytest.mark.asyncio
async def test_api_key_only_default_does_not_require_oauth_public_origin() -> None:
    snapshot = await load_mcp_auth_snapshot(
        _base_settings(
            **{
                "mcp.oauth.enabled": False,
                "mcp.oauth.public_base_url": "",
            }
        )
    )

    assert snapshot.mode is MCPAuthMode.API_KEY_ONLY
    assert snapshot.public_origin == "http://localhost:8080"


@pytest.mark.asyncio
async def test_oauth_kill_switch_ignores_stale_interactive_auth_settings() -> None:
    snapshot = await load_mcp_auth_snapshot(
        _base_settings(
            **{
                "mcp.oauth.enabled": False,
                "mcp.oauth.public_base_url": "http://remote-host-without-tls.example",
                "mcp.oauth.login_base_url": "not-an-origin",
                "mcp.oauth.access_token_ttl_seconds": -1,
                "mcp.oauth.refresh_token_ttl_days": 0,
                "oidc.enabled": True,
                "oidc.discovery_url": "",
                "oidc.client_id": "",
                "oidc.client_secret": "",
            }
        )
    )

    assert snapshot.mode is MCPAuthMode.API_KEY_ONLY
    assert snapshot.oidc is None


@pytest.mark.asyncio
async def test_enabled_oauth_requires_an_explicit_public_origin() -> None:
    with pytest.raises(MCPConfigurationError, match="PUBLIC_BASE_URL"):
        await load_mcp_auth_snapshot(
            _base_settings(**{"mcp.oauth.public_base_url": ""})
        )


def test_native_storage_uses_unmasked_asyncpg_url_without_runtime_ddl() -> None:
    storage = build_native_oauth_storage(
        database_url=(
            "postgresql+asyncpg://intercept_user:real-password@postgres:5432/intercept"
        ),
        fernet_key=derive_mcp_keys("application-secret").storage_fernet_key,
    )

    assert isinstance(storage.postgres, PostgreSQLStore)
    assert isinstance(storage.encrypted, FernetEncryptionWrapper)
    assert storage.encrypted.key_value is storage.postgres
    assert storage.postgres._url == (
        "postgresql://intercept_user:real-password@postgres:5432/intercept"
    )
    assert storage.postgres._table_name == "fastmcp_oauth_kv"
    assert storage.postgres._auto_create is False


def test_normalize_asyncpg_url_rejects_non_postgresql_database() -> None:
    with pytest.raises(MCPConfigurationError):
        normalize_asyncpg_url("sqlite+aiosqlite:///tmp/intercept.db")


class _LifecycleStore:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _MarkerStorage:
    def __init__(self, value=None, error: Exception | None = None) -> None:
        self.value = value
        self.error = error
        self.puts: list[tuple[str, dict, str]] = []

    async def get(self, key: str, *, collection: str):
        if self.error is not None:
            raise self.error
        return self.value

    async def put(self, key: str, value: dict, *, collection: str):
        self.puts.append((key, value, collection))


@pytest.mark.asyncio
async def test_native_lifespan_creates_encrypted_key_marker() -> None:
    encrypted = _MarkerStorage()
    storage = SimpleNamespace(postgres=_LifecycleStore(), encrypted=encrypted)

    async with create_native_mcp_lifespan(storage)(SimpleNamespace()):
        pass

    assert encrypted.puts == [
        (
            "encryption-key-check",
            {"format": 1, "purpose": "fastmcp-oauth-storage"},
            "intercept-fastmcp-system",
        )
    ]


@pytest.mark.asyncio
async def test_native_lifespan_fails_clearly_for_wrong_storage_key() -> None:
    encrypted = _MarkerStorage(error=DecryptionError("wrong key"))
    storage = SimpleNamespace(postgres=_LifecycleStore(), encrypted=encrypted)

    with pytest.raises(MCPConfigurationError, match="encryption key"):
        async with create_native_mcp_lifespan(storage)(SimpleNamespace()):
            pass


@pytest.mark.asyncio
async def test_api_key_only_runtime_captures_auth_before_http_app_construction() -> None:
    snapshot = await load_mcp_auth_snapshot(
        _base_settings(**{"mcp.oauth.enabled": False})
    )

    runtime = await build_mcp_runtime(
        snapshot=snapshot,
        database_url="postgresql+asyncpg://user:password@postgres/intercept",
        secret_key="application-secret",
        session_factory=lambda: None,
    )

    assert runtime.server.auth is runtime.auth
    assert runtime.auth.server is None
    assert runtime.http_app.state.path == "/streamable/"
    assert [route.path for route in runtime.http_app.routes] == ["/streamable/"]
    assert runtime.well_known_routes == ()

    async with AsyncClient(
        transport=ASGITransport(app=runtime.mounted_app),
        base_url="http://localhost:8080",
    ) as client:
        unauthorized = await client.post(
            "/streamable/",
            headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )

    assert unauthorized.status_code == 401
    assert "resource_metadata=" not in unauthorized.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_api_key_recovery_mode_does_not_lock_transport_to_stale_origin() -> None:
    snapshot = await load_mcp_auth_snapshot(
        _base_settings(
            **{
                "mcp.oauth.enabled": False,
                "mcp.oauth.public_base_url": "https://stale.example",
            }
        )
    )
    runtime = await build_mcp_runtime(
        snapshot=snapshot,
        database_url="postgresql+asyncpg://user:password@postgres/intercept",
        secret_key="application-secret",
        session_factory=lambda: None,
    )

    async with AsyncClient(
        transport=ASGITransport(app=runtime.mounted_app),
        base_url="http://dev-box.internal:8000",
    ) as client:
        response = await client.post(
            "/streamable/",
            headers={
                "Origin": "http://dev-box.internal:8000",
                "Accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )

    assert response.status_code == 401


def _in_memory_provider_factory(snapshot, _token_hash_key):
    return InMemoryOAuthProvider(
        base_url=snapshot.oauth_base_url,
        resource_base_url=snapshot.oauth_base_url,
        required_scopes=["mcp:access"],
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["mcp:access"],
            default_scopes=["mcp:access"],
        ),
    )


@pytest.mark.asyncio
async def test_oauth_transport_rejects_untrusted_host_and_origin() -> None:
    snapshot = await load_mcp_auth_snapshot(_base_settings())
    runtime = await build_mcp_runtime(
        snapshot=snapshot,
        database_url="postgresql+asyncpg://user:password@postgres/intercept",
        secret_key="application-secret",
        session_factory=lambda: None,
        local_provider_factory=_in_memory_provider_factory,
    )

    async with AsyncClient(
        transport=ASGITransport(app=runtime.mounted_app),
        base_url="https://intercept.example",
    ) as client:
        wrong_host = await client.post(
            "/streamable/",
            headers={"Host": "attacker.example"},
        )
        wrong_origin = await client.post(
            "/streamable/",
            headers={"Origin": "https://attacker.example"},
        )
        canonical = await client.post(
            "/streamable/",
            headers={"Origin": "https://intercept.example"},
        )

    assert wrong_host.status_code == 421
    assert wrong_origin.status_code == 403
    assert canonical.status_code == 401


@pytest.mark.asyncio
async def test_direct_asgi_registration_body_cap_rejects_chunked_payload() -> None:
    snapshot = replace(
        await load_mcp_auth_snapshot(_base_settings()),
        registration_policy=MCPRegistrationPolicy(max_body_bytes=128),
    )
    runtime = await build_mcp_runtime(
        snapshot=snapshot,
        database_url="postgresql+asyncpg://user:password@postgres/intercept",
        secret_key="application-secret",
        session_factory=lambda: None,
        local_provider_factory=_in_memory_provider_factory,
    )

    async def oversized_body():
        yield b'{"client_name":"'
        yield b"x" * 256
        yield b'"}'

    async with AsyncClient(
        transport=ASGITransport(app=runtime.mounted_app),
        base_url="https://intercept.example",
    ) as client:
        response = await client.post("/register", content=oversized_body())

    assert response.status_code == 413
    assert response.json() == {
        "error": "invalid_client_metadata",
        "error_description": "MCP registration request body is too large",
    }


@pytest.mark.asyncio
async def test_direct_asgi_oauth_form_body_cap_rejects_chunked_payload() -> None:
    snapshot = replace(
        await load_mcp_auth_snapshot(_base_settings()),
        registration_policy=MCPRegistrationPolicy(max_body_bytes=128),
    )
    runtime = await build_mcp_runtime(
        snapshot=snapshot,
        database_url="postgresql+asyncpg://user:password@postgres/intercept",
        secret_key="application-secret",
        session_factory=lambda: None,
        local_provider_factory=_in_memory_provider_factory,
    )

    async def oversized_body():
        yield b"client_id="
        yield b"x" * 256

    async with AsyncClient(
        transport=ASGITransport(app=runtime.mounted_app),
        base_url="https://intercept.example",
    ) as client:
        for path in ("/token", "/token/", "/revoke", "/revoke/"):
            response = await client.post(path, content=oversized_body())

            assert response.status_code == 413
            assert response.json() == {
                "error": "invalid_request",
                "error_description": "MCP OAuth request body is too large",
            }


@pytest.mark.asyncio
async def test_local_runtime_installs_operational_and_root_discovery_routes() -> None:
    snapshot = await load_mcp_auth_snapshot(_base_settings())

    def provider_factory(_snapshot, _token_hash_key):
        return InMemoryOAuthProvider(
            base_url=_snapshot.oauth_base_url,
            resource_base_url=_snapshot.oauth_base_url,
            required_scopes=["mcp:access"],
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=["mcp:access"],
                default_scopes=["mcp:access"],
            ),
            revocation_options=RevocationOptions(enabled=True),
        )

    runtime = await build_mcp_runtime(
        snapshot=snapshot,
        database_url="postgresql+asyncpg://user:password@postgres/intercept",
        secret_key="application-secret",
        session_factory=lambda: None,
        local_provider_factory=provider_factory,
    )

    assert [route.path for route in runtime.well_known_routes] == [
        "/.well-known/oauth-authorization-server/mcp",
        "/.well-known/openid-configuration/mcp",
        "/.well-known/openid-configuration",
        "/.well-known/oauth-protected-resource/mcp/streamable",
    ]
    child_paths = [route.path for route in runtime.http_app.routes]
    assert child_paths == [
        "/authorize",
        "/token",
        "/register",
        "/revoke",
        "/streamable/",
    ]

    async with AsyncClient(
        transport=ASGITransport(app=runtime.mounted_app),
        base_url="https://intercept.example",
    ) as client:
        unauthorized = await client.post(
            "/streamable/",
            headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )

    assert unauthorized.status_code == 401
    assert (
        'resource_metadata="https://intercept.example/'
        '.well-known/oauth-protected-resource/mcp/streamable"'
        in unauthorized.headers["www-authenticate"]
    )
