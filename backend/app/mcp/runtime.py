"""Startup snapshot and native storage construction for FastMCP."""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet
from fastmcp import FastMCP
from fastmcp.server.auth import AuthProvider, MultiAuth
from key_value.aio.errors.wrappers import DecryptionError
from key_value.aio.stores.postgresql import PostgreSQLStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from pydantic import AnyHttpUrl
from starlette.routing import BaseRoute, Route

from app.mcp.auth import (
    MCP_ACCESS_SCOPE,
    MCPConfigurationError,
    InterceptApiKeyVerifier,
    MCPRegistrationRequestMiddleware,
    XApiKeyToBearerMiddleware,
    derive_mcp_keys,
    validate_public_origin,
)
from app.mcp.oidc_provider import InterceptOIDCProxy
from app.mcp.server import create_mcp_server
from app.models.enums import UserRole
from app.services.oidc_service import (
    OIDCConfigurationError,
    OIDCIdentityPolicy,
    validate_oidc_discovery_url,
)
from app.services.mcp_registration_service import MCPRegistrationPolicy


class MCPAuthMode(str, Enum):
    API_KEY_ONLY = "api_key_only"
    OIDC_PROXY = "oidc_proxy"
    LOCAL_OAUTH = "local_oauth"


@dataclass(frozen=True, slots=True)
class OIDCAuthSnapshot:
    discovery_url: str
    client_id: str
    client_secret: str
    scopes: str
    provider_name: str
    jit_provisioning: bool
    default_role: str
    role_claim_path: str
    role_mapping: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MCPAuthSnapshot:
    mode: MCPAuthMode
    oauth_enabled: bool
    public_origin: str
    login_origin: str
    access_token_ttl_seconds: int
    refresh_token_ttl_days: int
    oidc: OIDCAuthSnapshot | None
    registration_policy: MCPRegistrationPolicy = field(
        default_factory=MCPRegistrationPolicy
    )

    @property
    def oauth_base_url(self) -> str:
        return f"{self.public_origin}/mcp"

    @property
    def resource_url(self) -> str:
        return f"{self.oauth_base_url}/streamable/"


@dataclass(frozen=True, slots=True)
class NativeOAuthStorage:
    postgres: PostgreSQLStore
    encrypted: FernetEncryptionWrapper


@dataclass(frozen=True, slots=True)
class MCPRuntime:
    snapshot: MCPAuthSnapshot
    provider: AuthProvider | None
    auth: MultiAuth
    server: FastMCP
    http_app: Any
    mounted_app: Any
    well_known_routes: tuple[BaseRoute, ...]
    storage: NativeOAuthStorage | None


_STORAGE_MARKER_COLLECTION = "intercept-fastmcp-system"
_STORAGE_MARKER_KEY = "encryption-key-check"
_STORAGE_MARKER_VALUE = {"format": 1, "purpose": "fastmcp-oauth-storage"}


def _align_protected_resource_metadata_routes(
    http_app: Any,
    routes: tuple[BaseRoute, ...],
    *,
    enabled: bool,
) -> tuple[BaseRoute, ...]:
    """Expose RFC 9728 metadata without FastMCP's transport trailing slash.

    FastMCP 3.4.4 derives the discovery path verbatim from the protected
    resource path. The MCP resource is intentionally slash-terminated, while
    Intercept's locked public discovery contract is not. Keep the native
    metadata handler and auth middleware, changing only the advertised/route
    URL at this pinned-version compatibility seam.
    """

    protected_prefix = "/.well-known/oauth-protected-resource/"
    normalized: list[BaseRoute] = []
    for route in routes:
        path = getattr(route, "path", "")
        if isinstance(route, Route) and path.startswith(protected_prefix):
            normalized.append(
                Route(
                    path=path.rstrip("/"),
                    endpoint=route.endpoint,
                    methods=route.methods,
                    name=route.name,
                    include_in_schema=route.include_in_schema,
                )
            )
        else:
            normalized.append(route)

    for route in http_app.router.routes:
        endpoint = getattr(route, "endpoint", None)
        metadata_url = getattr(endpoint, "resource_metadata_url", None)
        if metadata_url is not None:
            endpoint.resource_metadata_url = (
                AnyHttpUrl(str(metadata_url).rstrip("/")) if enabled else None
            )

    return tuple(normalized)


def _required_text(value: Any) -> str:
    return str(value or "").strip()


async def load_mcp_auth_snapshot(settings: Any) -> MCPAuthSnapshot:
    """Resolve one immutable auth topology snapshot for the current worker."""

    oauth_enabled = bool(await settings.get("mcp.oauth.enabled", default=False))
    public_value = _required_text(
        await settings.get(
            "mcp.oauth.public_base_url",
            default="",
        )
    )
    if not oauth_enabled:
        # Treat this as a real recovery switch: stale interactive-auth values
        # must not prevent API-key-only startup. Keep a valid configured origin
        # when available so audit/resource claims remain useful, otherwise use
        # a harmless loopback identifier. No OAuth discovery routes are exposed
        # in this mode.
        try:
            public_origin = (
                validate_public_origin(public_value)
                if public_value
                else "http://localhost:8080"
            )
        except MCPConfigurationError:
            public_origin = "http://localhost:8080"
        return MCPAuthSnapshot(
            mode=MCPAuthMode.API_KEY_ONLY,
            oauth_enabled=False,
            public_origin=public_origin,
            login_origin=public_origin,
            access_token_ttl_seconds=3600,
            refresh_token_ttl_days=30,
            oidc=None,
        )

    if not public_value:
        raise MCPConfigurationError(
            "MCP_OAUTH_PUBLIC_BASE_URL is required when MCP OAuth is enabled"
        )
    public_origin = validate_public_origin(public_value)
    login_value = _required_text(
        await settings.get("mcp.oauth.login_base_url", default="")
    )
    login_origin = validate_public_origin(login_value) if login_value else public_origin

    access_ttl = int(
        await settings.get("mcp.oauth.access_token_ttl_seconds", default=3600)
    )
    refresh_ttl_days = int(
        await settings.get("mcp.oauth.refresh_token_ttl_days", default=30)
    )
    if access_ttl <= 0 or refresh_ttl_days <= 0:
        raise MCPConfigurationError("MCP OAuth token lifetimes must be positive")

    registration_policy = MCPRegistrationPolicy(
        max_body_bytes=int(
            await settings.get(
                "mcp.oauth.registration_max_body_bytes",
                default=64 * 1024,
            )
        ),
        pending_quota=int(
            await settings.get(
                "mcp.oauth.registration_pending_quota",
                default=1_000,
            )
        ),
        total_quota=int(
            await settings.get(
                "mcp.oauth.registration_total_quota",
                default=5_000,
            )
        ),
        per_ip_quota=int(
            await settings.get(
                "mcp.oauth.registration_per_ip_quota",
                default=600,
            )
        ),
        rate_window_seconds=int(
            await settings.get(
                "mcp.oauth.registration_rate_window_seconds",
                default=60 * 60,
            )
        ),
        abandoned_ttl_seconds=int(
            await settings.get(
                "mcp.oauth.registration_abandoned_ttl_seconds",
                default=60 * 60,
            )
        ),
        active_ttl_seconds=max(
            int(
                await settings.get(
                    "mcp.oauth.registration_active_ttl_seconds",
                    default=30 * 24 * 60 * 60,
                )
            ),
            access_ttl,
            refresh_ttl_days * 24 * 60 * 60,
        ),
        pending_authorization_global_quota=int(
            await settings.get(
                "mcp.oauth.pending_authorization_global_quota",
                default=1_000,
            )
        ),
        pending_authorization_per_client_quota=int(
            await settings.get(
                "mcp.oauth.pending_authorization_per_client_quota",
                default=10,
            )
        ),
        pending_authorization_per_source_quota=int(
            await settings.get(
                "mcp.oauth.pending_authorization_per_source_quota",
                default=50,
            )
        ),
        cimd_fetch_reservation_ttl_seconds=int(
            await settings.get(
                "mcp.oauth.cimd_fetch_reservation_ttl_seconds",
                default=60,
            )
        ),
        cimd_cache_max_entries=int(
            await settings.get(
                "mcp.oauth.cimd_cache_max_entries",
                default=256,
            )
        ),
        client_assertion_replay_global_quota=int(
            await settings.get(
                "mcp.oauth.client_assertion_replay_global_quota",
                default=100_000,
            )
        ),
        client_assertion_replay_per_client_quota=int(
            await settings.get(
                "mcp.oauth.client_assertion_replay_per_client_quota",
                default=10_000,
            )
        ),
    )
    if any(
        value <= 0
        for value in (
            registration_policy.max_body_bytes,
            registration_policy.pending_quota,
            registration_policy.total_quota,
            registration_policy.per_ip_quota,
            registration_policy.rate_window_seconds,
            registration_policy.abandoned_ttl_seconds,
            registration_policy.active_ttl_seconds,
            registration_policy.pending_authorization_global_quota,
            registration_policy.pending_authorization_per_client_quota,
            registration_policy.pending_authorization_per_source_quota,
            registration_policy.cimd_fetch_reservation_ttl_seconds,
            registration_policy.cimd_cache_max_entries,
            registration_policy.client_assertion_replay_global_quota,
            registration_policy.client_assertion_replay_per_client_quota,
        )
    ):
        raise MCPConfigurationError("MCP registration limits must be positive")
    if (
        registration_policy.client_assertion_replay_per_client_quota
        > registration_policy.client_assertion_replay_global_quota
    ):
        raise MCPConfigurationError(
            "MCP per-client assertion replay quota cannot exceed global quota"
        )
    if (
        registration_policy.abandoned_ttl_seconds
        < registration_policy.rate_window_seconds
    ):
        raise MCPConfigurationError(
            "MCP registration abandoned TTL must be at least the rate window"
        )

    oidc_enabled = bool(await settings.get("oidc.enabled", default=False))
    oidc_snapshot: OIDCAuthSnapshot | None = None
    if oidc_enabled:
        raw_discovery_url = await settings.get("oidc.discovery_url")
        discovery_url = _required_text(raw_discovery_url)
        client_id = _required_text(await settings.get("oidc.client_id"))
        client_secret = _required_text(await settings.get("oidc.client_secret"))
        if not discovery_url or not client_id or not client_secret:
            raise MCPConfigurationError(
                "OIDC is enabled, but discovery URL, client ID, and client secret are required"
            )
        try:
            discovery_url = validate_oidc_discovery_url(raw_discovery_url)
        except OIDCConfigurationError as exc:
            raise MCPConfigurationError(str(exc)) from exc

        role_mapping = await settings.get("oidc.role_mapping", default={})
        if not isinstance(role_mapping, dict):
            raise MCPConfigurationError("OIDC role mapping must be a JSON object")
        scopes = _required_text(
            await settings.get("oidc.scopes", default="openid email profile")
        )
        if "openid" not in scopes.split():
            raise MCPConfigurationError(
                "OIDC scopes must include openid for MCP ID-token verification"
            )
        default_role_value = _required_text(
            await settings.get("oidc.default_role", default="ANALYST")
        ).upper()
        try:
            default_role = UserRole(default_role_value).value
        except ValueError as exc:
            raise MCPConfigurationError("OIDC default role is invalid") from exc
        for mapped_role in role_mapping.values():
            try:
                UserRole(str(mapped_role).upper())
            except ValueError as exc:
                raise MCPConfigurationError(
                    f"OIDC role mapping contains invalid role {mapped_role!r}"
                ) from exc
        oidc_snapshot = OIDCAuthSnapshot(
            discovery_url=discovery_url,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
            provider_name=_required_text(
                await settings.get("oidc.provider_name", default="SSO")
            ),
            jit_provisioning=bool(
                await settings.get("oidc.jit_provisioning", default=False)
            ),
            default_role=default_role,
            role_claim_path=_required_text(
                await settings.get("oidc.role_claim_path", default="")
            ),
            role_mapping=dict(role_mapping),
        )

    if oidc_snapshot is not None:
        mode = MCPAuthMode.OIDC_PROXY
    else:
        mode = MCPAuthMode.LOCAL_OAUTH

    return MCPAuthSnapshot(
        mode=mode,
        oauth_enabled=oauth_enabled,
        public_origin=public_origin,
        login_origin=login_origin,
        access_token_ttl_seconds=access_ttl,
        refresh_token_ttl_days=refresh_ttl_days,
        oidc=oidc_snapshot,
        registration_policy=registration_policy,
    )


def normalize_asyncpg_url(database_url: str) -> str:
    """Convert SQLAlchemy's asyncpg URL to the unmasked asyncpg DSN form."""

    value = str(database_url)
    sqlalchemy_prefix = "postgresql+asyncpg://"
    if value.startswith(sqlalchemy_prefix):
        return "postgresql://" + value[len(sqlalchemy_prefix) :]
    if value.startswith(("postgresql://", "postgres://")):
        return value
    raise MCPConfigurationError(
        "FastMCP native PostgreSQL storage requires a PostgreSQL database URL"
    )


def build_native_oauth_storage(
    *,
    database_url: str,
    fernet_key: bytes,
) -> NativeOAuthStorage:
    """Build the exact native py-key-value PostgreSQL/encryption stack."""

    postgres = PostgreSQLStore(
        url=normalize_asyncpg_url(database_url),
        table_name="fastmcp_oauth_kv",
        auto_create=False,
    )
    encrypted = FernetEncryptionWrapper(
        key_value=postgres,
        fernet=Fernet(fernet_key),
    )
    return NativeOAuthStorage(postgres=postgres, encrypted=encrypted)


def create_native_mcp_lifespan(
    storage: NativeOAuthStorage | None,
) -> Callable[[FastMCP], Any]:
    """Own native storage and MCP-only HTTP resources for one worker."""

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        async with AsyncExitStack() as stack:
            if storage is not None:
                await stack.enter_async_context(storage.postgres)
                try:
                    marker = await storage.encrypted.get(
                        _STORAGE_MARKER_KEY,
                        collection=_STORAGE_MARKER_COLLECTION,
                    )
                except DecryptionError as exc:
                    raise MCPConfigurationError(
                        "FastMCP OAuth storage encryption key does not match existing data"
                    ) from exc
                if marker is None:
                    await storage.encrypted.put(
                        _STORAGE_MARKER_KEY,
                        _STORAGE_MARKER_VALUE,
                        collection=_STORAGE_MARKER_COLLECTION,
                    )
                elif marker != _STORAGE_MARKER_VALUE:
                    raise MCPConfigurationError(
                        "FastMCP OAuth storage encryption marker is invalid"
                    )
            oidc_http_client = await stack.enter_async_context(
                httpx.AsyncClient(timeout=15.0)
            )
            yield {
                "oauth_storage": storage.encrypted if storage is not None else None,
                "postgres_store": storage.postgres if storage is not None else None,
                "oidc_http_client": oidc_http_client,
            }

    return lifespan


async def build_mcp_runtime(
    *,
    snapshot: MCPAuthSnapshot,
    database_url: str,
    secret_key: str,
    session_factory: Callable[..., Any],
    local_provider_factory: (
        Callable[[MCPAuthSnapshot, bytes], AuthProvider] | None
    ) = None,
) -> MCPRuntime:
    """Assemble auth, routes, server, and transport before startup yields."""

    keys = derive_mcp_keys(secret_key)
    storage: NativeOAuthStorage | None = None
    provider: AuthProvider | None = None

    if snapshot.mode is MCPAuthMode.OIDC_PROXY:
        if snapshot.oidc is None:  # defensive: load_mcp_auth_snapshot guarantees this
            raise MCPConfigurationError("OIDC proxy mode is missing its OIDC snapshot")
        storage = build_native_oauth_storage(
            database_url=database_url,
            fernet_key=keys.storage_fernet_key,
        )
        provider = InterceptOIDCProxy(
            config_url=snapshot.oidc.discovery_url,
            client_id=snapshot.oidc.client_id,
            client_secret=snapshot.oidc.client_secret,
            configured_scopes=snapshot.oidc.scopes,
            base_url=snapshot.oauth_base_url,
            resource_base_url=snapshot.oauth_base_url,
            client_storage=storage.encrypted,
            jwt_signing_key=keys.jwt_signing_key,
            session_factory=session_factory,
            identity_policy=OIDCIdentityPolicy(
                jit_provisioning=snapshot.oidc.jit_provisioning,
                default_role=snapshot.oidc.default_role,
                role_claim_path=snapshot.oidc.role_claim_path,
                role_mapping=dict(snapshot.oidc.role_mapping),
            ),
            fastmcp_access_token_expiry_seconds=snapshot.access_token_ttl_seconds,
            fallback_access_token_expiry_seconds=snapshot.access_token_ttl_seconds,
            fallback_refresh_token_expiry_seconds=(
                snapshot.refresh_token_ttl_days * 24 * 60 * 60
            ),
            registration_policy=snapshot.registration_policy,
        )
    elif snapshot.mode is MCPAuthMode.LOCAL_OAUTH:
        if local_provider_factory is None:
            raise MCPConfigurationError("Local MCP OAuth provider is not configured")
        provider = local_provider_factory(snapshot, keys.token_hash_key)

    api_key_verifier = InterceptApiKeyVerifier(
        session_factory=session_factory,
        resource_url=snapshot.resource_url,
    )
    auth = MultiAuth(
        server=provider,
        verifiers=[api_key_verifier],
        base_url=snapshot.oauth_base_url,
        resource_base_url=snapshot.oauth_base_url,
        required_scopes=[MCP_ACCESS_SCOPE],
    )
    server = create_mcp_server(
        auth=auth,
        lifespan=create_native_mcp_lifespan(storage),
        session_factory=session_factory,
    )
    http_app = server.http_app(
        path="/streamable/",
        transport="streamable-http",
        host_origin_protection=True if snapshot.oauth_enabled else "auto",
        allowed_hosts=(
            [urlsplit(snapshot.public_origin).netloc]
            if snapshot.oauth_enabled
            else None
        ),
        allowed_origins=(
            [snapshot.public_origin] if snapshot.oauth_enabled else None
        ),
    )
    well_known_routes = _align_protected_resource_metadata_routes(
        http_app,
        tuple(auth.get_well_known_routes("/streamable/")),
        enabled=provider is not None,
    )

    # Discovery is installed at the public root by the outer application. Do
    # not leave shadow copies beneath /mcp.
    http_app.router.routes[:] = [
        route
        for route in http_app.router.routes
        if not getattr(route, "path", "").startswith("/.well-known/")
    ]
    mounted_app = MCPRegistrationRequestMiddleware(
        XApiKeyToBearerMiddleware(http_app),
        max_body_bytes=snapshot.registration_policy.max_body_bytes,
    )
    return MCPRuntime(
        snapshot=snapshot,
        provider=provider,
        auth=auth,
        server=server,
        http_app=http_app,
        mounted_app=mounted_app,
        well_known_routes=well_known_routes,
        storage=storage,
    )


__all__ = [
    "MCPAuthMode",
    "MCPAuthSnapshot",
    "MCPRuntime",
    "NativeOAuthStorage",
    "OIDCAuthSnapshot",
    "build_native_oauth_storage",
    "build_mcp_runtime",
    "create_native_mcp_lifespan",
    "load_mcp_auth_snapshot",
    "normalize_asyncpg_url",
]
