from __future__ import annotations

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
        "oidc.trusted_auto_link_issuers": [],
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
async def test_local_runtime_installs_operational_and_root_discovery_routes() -> None:
    snapshot = await load_mcp_auth_snapshot(_base_settings())

    def provider_factory(_snapshot):
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
