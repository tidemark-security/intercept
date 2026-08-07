from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.oidc_proxy import OIDCConfiguration, OIDCProxy
from httpx import ASGITransport, AsyncClient
from mcp.server.auth.handlers.revoke import RevocationHandler
from mcp.server.auth.middleware.client_auth import ClientAuthenticator
from mcp.server.auth.provider import AuthorizeError, TokenError
from mcp.server.auth.routes import cors_middleware
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy import Select, func, select
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.mcp.auth import MCP_ACCESS_SCOPE
from app.mcp.oidc_provider import (
    CONNECTED_CLIENT_REFERENCE_COLLECTION,
    INTERCEPT_AUTHORIZATION_EPOCH_CLAIM,
    INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM,
    INTERCEPT_CREDENTIAL_VALIDATED_AT_CLAIM,
    InterceptOIDCProxy,
    OIDCIdentityError,
    VALIDATED_ID_TOKEN_MARKER,
    _AuthorizationCapacityStore,
    oidc_authorize_parameters,
    resolve_upstream_oidc_scopes,
)
from app.models.enums import UserRole, UserStatus
from app.models.models import (
    MCPOAuthClient,
    MCPOAuthConsent,
    MCPOAuthProviderGrantReference,
    UserAccount,
)
from app.services.oidc_service import (
    OIDCAuthenticationError,
    OIDCConfigurationError,
    OIDCIdentityPolicy,
)
from app.services.mcp_oauth_service import mcp_oauth_service
from app.services.mcp_registration_service import (
    MCPAuthorizationCapacityLimitError,
    MCPRegistrationExpiredError,
    MCPRegistrationPolicy,
    bind_authorization_request,
    reset_authorization_request,
)


def test_google_scope_translation_keeps_mcp_scope_local() -> None:
    scopes = resolve_upstream_oidc_scopes(
        discovery_url="https://accounts.google.com/.well-known/openid-configuration",
        configured_scopes="openid email profile",
    )

    assert scopes == ["openid", "email", "profile"]
    assert MCP_ACCESS_SCOPE not in scopes
    assert oidc_authorize_parameters(
        "https://accounts.google.com/.well-known/openid-configuration"
    ) == {"access_type": "offline", "prompt": "consent"}


def test_entra_scope_translation_adds_offline_access_once() -> None:
    scopes = resolve_upstream_oidc_scopes(
        discovery_url=(
            "https://login.microsoftonline.com/tenant/v2.0/"
            ".well-known/openid-configuration"
        ),
        configured_scopes="openid profile offline_access email offline_access",
    )

    assert scopes == ["openid", "profile", "offline_access", "email"]
    assert MCP_ACCESS_SCOPE not in scopes


def test_generic_scope_translation_uses_exact_configured_scopes() -> None:
    scopes = resolve_upstream_oidc_scopes(
        discovery_url="https://id.example/.well-known/openid-configuration",
        configured_scopes="openid custom.read email",
    )

    assert scopes == ["openid", "custom.read", "email"]
    assert oidc_authorize_parameters(
        "https://id.example/.well-known/openid-configuration"
    ) == {}


def test_proxy_scope_hooks_never_forward_mcp_access() -> None:
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._intercept_upstream_scopes = ["openid", "email", "profile"]

    assert proxy._prepare_scopes_for_token_exchange([MCP_ACCESS_SCOPE]) == [
        "openid",
        "email",
        "profile",
    ]
    assert proxy._prepare_scopes_for_upstream_refresh([MCP_ACCESS_SCOPE]) == [
        "openid",
        "email",
        "profile",
    ]
    assert proxy._translate_scopes_from_idp(["openid", "email"]) == [
        MCP_ACCESS_SCOPE
    ]


def _fastmcp_oidc_configuration(**overrides: object) -> OIDCConfiguration:
    metadata: dict[str, object] = {
        "strict": True,
        "issuer": "https://idp.example/tenant",
        "authorization_endpoint": "https://idp.example/authorize",
        "token_endpoint": "https://idp.example/token",
        "jwks_uri": "https://idp.example/jwks",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }
    metadata.update(overrides)
    return OIDCConfiguration.model_validate(metadata)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("issuer", "https://idp.example/tenant?query=forbidden"),
        ("authorization_endpoint", "http://idp.example/authorize"),
        ("token_endpoint", "http://169.254.169.254/token"),
        ("token_endpoint", "https://user:password@idp.example/token"),
        ("jwks_uri", "https://idp.example/jwks#fragment"),
    ],
)
def test_oidc_proxy_rejects_unsafe_discovery_metadata_before_endpoint_use(
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    value: str,
) -> None:
    discovered = _fastmcp_oidc_configuration(**{field_name: value})
    monkeypatch.setattr(
        OIDCProxy,
        "get_oidc_configuration",
        lambda *_args, **_kwargs: discovered,
    )
    proxy = object.__new__(InterceptOIDCProxy)

    with pytest.raises(OIDCConfigurationError, match=field_name):
        proxy.get_oidc_configuration(
            "https://idp.example/.well-known/openid-configuration",
            True,
            15,
        )


def test_oidc_proxy_accepts_discovery_metadata_allowed_by_shared_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovered = _fastmcp_oidc_configuration(
        authorization_endpoint=(
            "https://idp.example/authorize?policy=interactive-signin"
        ),
    )
    monkeypatch.setattr(
        OIDCProxy,
        "get_oidc_configuration",
        lambda *_args, **_kwargs: discovered,
    )
    proxy = object.__new__(InterceptOIDCProxy)

    resolved = proxy.get_oidc_configuration(
        "https://idp.example/.well-known/openid-configuration",
        True,
        15,
    )

    assert resolved is discovered


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "requested_method",
    ["client_secret_post", "client_secret_basic", "private_key_jwt"],
)
async def test_oidc_proxy_dynamic_registration_never_returns_or_stores_secret(
    monkeypatch: pytest.MonkeyPatch,
    requested_method: str,
) -> None:
    captured: list[OAuthClientInformationFull] = []

    async def register(_proxy, client_info):
        captured.append(client_info.model_copy(deep=True))

    monkeypatch.setattr(OIDCProxy, "register_client", register)
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._registration_service = None
    client = OAuthClientInformationFull(
        client_id="dcr-client",
        client_secret="sdk-generated-secret",
        client_secret_expires_at=2_000_000_000,
        redirect_uris=["http://127.0.0.1:49152/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method=requested_method,
        scope=MCP_ACCESS_SCOPE,
    )

    await proxy.register_client(client)

    assert client.token_endpoint_auth_method == "none"
    assert client.client_secret is None
    assert client.client_secret_expires_at is None
    assert captured[0].token_endpoint_auth_method == "none"
    assert captured[0].client_secret is None


@pytest.mark.asyncio
async def test_sdk_resolved_oidc_cimd_client_bypasses_dcr_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delegated_authorize = AsyncMock(return_value="https://issuer.example/authorize")
    monkeypatch.setattr(OIDCProxy, "authorize", delegated_authorize)
    registration_service = SimpleNamespace(
        require_valid=AsyncMock(
            side_effect=AssertionError("CIMD client consulted DCR ledger")
        )
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._registration_service = registration_service
    proxy._cimd_manager = SimpleNamespace(
        is_cimd_client_id=lambda client_id: client_id.startswith("https://")
    )
    client = SimpleNamespace(
        client_id="https://mcp-client.example/.well-known/oauth-client.json"
    )
    params = SimpleNamespace(state="cimd-state")

    result = await proxy.authorize(client, params)

    assert result == "https://issuer.example/authorize"
    delegated_authorize.assert_awaited_once_with(client, params)
    registration_service.require_valid.assert_not_awaited()


@pytest.mark.asyncio
async def test_oidc_cimd_lookup_does_not_persist_unreserved_projection() -> None:
    client_id = "https://mcp-client.example/.well-known/oauth-client.json"
    cimd_client = SimpleNamespace(client_id=client_id, cimd_document=object())
    client_store = SimpleNamespace(
        get=AsyncMock(return_value=None),
        put=AsyncMock(),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._client_store = client_store
    proxy._cimd_manager = SimpleNamespace(
        is_cimd_client_id=lambda candidate: candidate == client_id,
        get_client=AsyncMock(return_value=cimd_client),
    )

    resolved = await proxy.get_client(client_id)

    assert resolved is cimd_client
    client_store.put.assert_not_awaited()


@pytest.mark.asyncio
async def test_oidc_cimd_fetch_is_admitted_before_network() -> None:
    client_id = "https://mcp-client.example/.well-known/oauth-client.json"
    capacity = SimpleNamespace(
        reserve=AsyncMock(
            side_effect=MCPAuthorizationCapacityLimitError("at capacity")
        )
    )
    cimd_manager = SimpleNamespace(
        is_cimd_client_id=lambda candidate: candidate == client_id,
        get_client=AsyncMock(),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._registration_policy = MCPRegistrationPolicy()
    proxy._authorization_capacity_service = capacity
    proxy._cimd_prefetch_reservation = ContextVar(
        "test_oidc_cimd_prefetch",
        default=None,
    )
    proxy._cimd_manager = cimd_manager
    token = bind_authorization_request()
    try:
        resolved = await proxy.get_client(client_id)
    finally:
        reset_authorization_request(token)

    assert resolved is None
    capacity.reserve.assert_awaited_once()
    cimd_manager.get_client.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ("success", "none", "error"))
async def test_oidc_non_authorization_cimd_fetch_releases_transient_capacity(
    outcome: str,
) -> None:
    client_id = "https://mcp-client.example/.well-known/oauth-client.json"
    cimd_client = SimpleNamespace(client_id=client_id, cimd_document=object())

    async def get_client(_client_id: str):
        if outcome == "error":
            raise RuntimeError("fetch failed")
        if outcome == "none":
            return None
        return cimd_client

    capacity = SimpleNamespace(
        reserve=AsyncMock(),
        release=AsyncMock(),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._registration_policy = MCPRegistrationPolicy()
    proxy._authorization_capacity_service = capacity
    proxy._cimd_prefetch_reservation = ContextVar(
        "test_oidc_transient_cimd_prefetch",
        default=None,
    )
    proxy._cimd_manager = SimpleNamespace(
        is_cimd_client_id=lambda candidate: candidate == client_id,
        get_client=AsyncMock(side_effect=get_client),
    )

    if outcome == "error":
        with pytest.raises(RuntimeError, match="fetch failed"):
            await proxy.get_client(client_id)
    else:
        resolved = await proxy.get_client(client_id)
        assert (resolved is not None) is (outcome == "success")

    capacity.reserve.assert_awaited_once()
    capacity.release.assert_awaited_once_with(
        capacity.reserve.await_args.kwargs["reservation_id"]
    )


@pytest.mark.asyncio
async def test_oidc_transaction_promotes_prefetch_and_releases_on_delete() -> None:
    delegate = SimpleNamespace(
        put=AsyncMock(return_value="stored"),
        delete=AsyncMock(return_value=True),
    )
    capacity = SimpleNamespace(
        promote=AsyncMock(),
        reserve=AsyncMock(),
        release=AsyncMock(),
    )
    prefetch = ContextVar(
        "test_oidc_transaction_prefetch",
        default=("fetch-reservation", "cimd-client"),
    )
    store = _AuthorizationCapacityStore(delegate, capacity, prefetch)
    transaction = SimpleNamespace(client_id="cimd-client")

    result = await store.put(key="transaction-id", value=transaction, ttl=900)
    await store.delete(key="transaction-id")

    assert result == "stored"
    capacity.promote.assert_awaited_once_with(
        reservation_id="fetch-reservation",
        pending_id="transaction-id",
        client_id="cimd-client",
        ttl_seconds=900,
    )
    capacity.reserve.assert_not_awaited()
    capacity.release.assert_awaited_once_with("transaction-id")


@pytest.mark.asyncio
async def test_repeated_oidc_cimd_lookup_preserves_prefetch_for_transaction() -> None:
    client_id = "https://mcp-client.example/.well-known/oauth-client.json"
    cimd_client = SimpleNamespace(client_id=client_id, cimd_document=object())
    fetcher = SimpleNamespace(_cache={})

    async def get_client(_client_id: str):
        fetcher._cache[client_id] = SimpleNamespace(
            must_revalidate=False,
            expires_at=datetime.now(timezone.utc).timestamp() + 60,
        )
        return cimd_client

    cimd_manager = SimpleNamespace(
        _fetcher=fetcher,
        is_cimd_client_id=lambda candidate: candidate == client_id,
        get_client=AsyncMock(side_effect=get_client),
    )
    capacity = SimpleNamespace(
        promote=AsyncMock(),
        reserve=AsyncMock(),
        release=AsyncMock(),
    )
    reservation = ContextVar(
        "test_repeated_oidc_cimd_prefetch",
        default=None,
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._registration_policy = MCPRegistrationPolicy()
    proxy._authorization_capacity_service = capacity
    proxy._cimd_prefetch_reservation = reservation
    proxy._cimd_manager = cimd_manager
    delegate = SimpleNamespace(put=AsyncMock(return_value="stored"))
    store = _AuthorizationCapacityStore(delegate, capacity, reservation)
    token = bind_authorization_request()
    try:
        first = await proxy.get_client(client_id)
        second = await proxy.get_client(client_id)
        result = await store.put(
            key="transaction-id",
            value=SimpleNamespace(client_id=client_id),
            ttl=900,
        )
    finally:
        reset_authorization_request(token)

    assert first is cimd_client
    assert second is cimd_client
    assert result == "stored"
    capacity.reserve.assert_awaited_once()
    capacity.release.assert_not_awaited()
    capacity.promote.assert_awaited_once_with(
        reservation_id=capacity.reserve.await_args.kwargs["reservation_id"],
        pending_id="transaction-id",
        client_id=client_id,
        ttl_seconds=900,
    )


@pytest.mark.asyncio
async def test_oidc_transaction_releases_prefetch_when_promotion_fails() -> None:
    capacity = SimpleNamespace(
        promote=AsyncMock(
            side_effect=MCPAuthorizationCapacityLimitError("reservation expired")
        ),
        reserve=AsyncMock(),
        release=AsyncMock(),
    )
    prefetch = ContextVar(
        "test_failed_oidc_transaction_prefetch",
        default=("fetch-reservation", "cimd-client"),
    )
    store = _AuthorizationCapacityStore(
        SimpleNamespace(put=AsyncMock()),
        capacity,
        prefetch,
    )

    with pytest.raises(
        MCPAuthorizationCapacityLimitError,
        match="reservation expired",
    ):
        await store.put(
            key="transaction-id",
            value=SimpleNamespace(client_id="cimd-client"),
            ttl=900,
        )

    assert [
        call.args[0] for call in capacity.release.await_args_list
    ] == ["transaction-id", "fetch-reservation"]
    assert prefetch.get() is None


@pytest.mark.asyncio
async def test_oidc_authorize_releases_unpromoted_prefetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject_authorize(*_args, **_kwargs):
        raise AuthorizeError("invalid_request", "authorization rejected")

    monkeypatch.setattr(OIDCProxy, "authorize", reject_authorize)
    capacity = SimpleNamespace(release=AsyncMock())
    prefetch = ContextVar(
        "test_rejected_oidc_authorize_prefetch",
        default=("fetch-reservation", "cimd-client"),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._registration_service = None
    proxy._authorization_capacity_service = capacity
    proxy._cimd_prefetch_reservation = prefetch
    client = OAuthClientInformationFull(
        client_id="cimd-client",
        redirect_uris=["http://127.0.0.1:49152/callback"],
        token_endpoint_auth_method="none",
    )

    with pytest.raises(AuthorizeError, match="authorization rejected"):
        await proxy.authorize(client, SimpleNamespace())  # type: ignore[arg-type]

    capacity.release.assert_awaited_once_with("fetch-reservation")
    assert prefetch.get() is None


@pytest.mark.asyncio
async def test_oidc_proxy_metadata_advertises_only_public_dcr_and_cimd_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def stale_metadata(_request):
        return JSONResponse({"token_endpoint_auth_methods_supported": ["secret"]})

    monkeypatch.setattr(
        OIDCProxy,
        "get_routes",
        lambda _proxy, _mcp_path=None: [
            Route(
                "/.well-known/oauth-authorization-server",
                stale_metadata,
                methods=["GET"],
            )
        ],
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy.base_url = "https://intercept.example/mcp"
    proxy.service_documentation_url = None
    proxy.client_registration_options = ClientRegistrationOptions(
        enabled=True,
        valid_scopes=[MCP_ACCESS_SCOPE],
        default_scopes=[MCP_ACCESS_SCOPE],
    )
    proxy.revocation_options = RevocationOptions(enabled=True)
    app = Starlette(routes=proxy.get_routes())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://intercept.example",
    ) as client:
        response = await client.get("/.well-known/oauth-authorization-server")

    assert response.status_code == 200
    metadata = response.json()
    assert metadata["token_endpoint_auth_methods_supported"] == [
        "none",
        "private_key_jwt",
    ]
    assert metadata["revocation_endpoint_auth_methods_supported"] == [
        "none",
        "private_key_jwt",
    ]
    assert metadata["client_id_metadata_document_supported"] is True


@pytest.mark.asyncio
async def test_oidc_revocation_handler_authenticates_private_key_cimd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = object.__new__(InterceptOIDCProxy)
    proxy.base_url = "https://intercept.example/mcp"
    proxy.service_documentation_url = None
    proxy.client_registration_options = None
    proxy.revocation_options = None
    private_client = OAuthClientInformationFull(
        client_id="https://client.example/oauth-client.json",
        redirect_uris=["http://127.0.0.1:49152/callback"],
        token_endpoint_auth_method="private_key_jwt",
    )
    proxy.get_client = AsyncMock(return_value=private_client)
    proxy.load_access_token = AsyncMock(return_value=None)
    proxy.load_refresh_token = AsyncMock(return_value=None)
    proxy.revoke_token = AsyncMock()
    proxy._cimd_manager = SimpleNamespace(
        validate_private_key_jwt=AsyncMock(return_value=True)
    )

    base_handler = RevocationHandler(
        provider=proxy,
        client_authenticator=ClientAuthenticator(proxy),
    )
    monkeypatch.setattr(
        OIDCProxy,
        "get_routes",
        lambda _proxy, _mcp_path=None: [
            Route(
                "/revoke",
                cors_middleware(base_handler.handle, ["POST", "OPTIONS"]),
                methods=["POST", "OPTIONS"],
            )
        ],
    )
    app = Starlette(routes=proxy.get_routes())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://intercept.example",
    ) as client:
        response = await client.post(
            "/revoke",
            data={
                "client_id": "https://client.example/oauth-client.json",
                "client_assertion_type": (
                    "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
                ),
                "client_assertion": "signed-client-assertion",
                "client_secret": "",
                "token": "unknown-token",
            },
        )
        proxy.get_client.return_value = OAuthClientInformationFull(
            client_id="public-client",
            redirect_uris=["http://127.0.0.1:49152/callback"],
            token_endpoint_auth_method="none",
        )
        public_response = await client.post(
            "/revoke",
            data={
                "client_id": "public-client",
                "client_secret": "",
                "token": "unknown-token",
            },
        )

    assert response.status_code == 200
    assert public_response.status_code == 200
    proxy._cimd_manager.validate_private_key_jwt.assert_awaited_once_with(
        assertion="signed-client-assertion",
        client=private_client,
        token_endpoint="https://intercept.example/mcp/token",
    )


class _Session:
    def __init__(self, user=None) -> None:
        self.user = user
        self.committed = False
        self.rolled_back = False

    async def get(self, _model, user_id):
        return self.user if self.user is not None and self.user.id == user_id else None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _session_factory(session: _Session):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


def _strict_id_token_claims(
    *,
    nonce: str = "server-nonce",
    subject: str = "provider-subject",
) -> dict[str, object]:
    now = int(datetime.now(timezone.utc).timestamp())
    return {
        "iss": "https://issuer.example",
        "aud": "intercept-oidc-client",
        "sub": subject,
        "exp": now + 300,
        "iat": now - 10,
        "nonce": nonce,
        "email": "person@example.com",
        "preferred_username": "person@example.com",
    }


def _configure_marker_crypto(proxy: InterceptOIDCProxy) -> None:
    proxy._jwt_signing_key = b"unit-test-marker-signing-key"
    proxy._upstream_client_id = "intercept-oidc-client"
    proxy._intercept_oidc_clock_skew_seconds = 30.0
    proxy.oidc_config = SimpleNamespace(issuer="https://issuer.example")


def _validated_idp_tokens(
    proxy: InterceptOIDCProxy,
    *,
    claims: dict[str, object],
    id_token: str = "id-token",
    validated_at: float | None = None,
    family_started_at: float | None = None,
    authorization_epoch: int = 101,
    nonce: str = "server-nonce",
) -> dict[str, object]:
    validation_epoch = validated_at or float(
        datetime.now(timezone.utc).timestamp()
    )
    family_epoch = family_started_at or validation_epoch - 30.0
    return {
        "id_token": id_token,
        VALIDATED_ID_TOKEN_MARKER: proxy._build_validated_id_token_marker(
            claims=claims,
            authorization_epoch=authorization_epoch,
            validated_at=validation_epoch,
            credential_family_started_at=family_epoch,
            nonce=nonce,
            id_token=id_token,
        ),
    }


@pytest.mark.asyncio
async def test_proxy_normalizes_verified_id_token_through_oidc_service() -> None:
    user = SimpleNamespace(
        id=uuid4(),
        username="person@example.com",
        role=SimpleNamespace(value="ANALYST"),
    )
    provider_claims = _strict_id_token_claims()
    validated_at = float(datetime.now(timezone.utc).timestamp())
    family_started_at = validated_at - 30.0
    session = _Session()
    oidc_service = SimpleNamespace(find_or_create_user=AsyncMock(return_value=user))
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._intercept_session_factory = _session_factory(session)
    proxy._intercept_oidc_service = oidc_service
    identity_policy = OIDCIdentityPolicy(
        jit_provisioning=False,
        default_role="AUDITOR",
        role_claim_path="groups",
        role_mapping={"security-auditors": "AUDITOR"},
    )
    proxy._intercept_identity_policy = identity_policy

    claims = await proxy._extract_upstream_claims(
        _validated_idp_tokens(
            proxy,
            claims=provider_claims,
            validated_at=validated_at,
            family_started_at=family_started_at,
        )
    )

    oidc_service.find_or_create_user.assert_awaited_once_with(
        session,
        claims=provider_claims,
        issuer="https://issuer.example",
        identity_policy=identity_policy,
    )
    assert claims == {
        "intercept_user_id": str(user.id),
        "auth_source": "oidc",
        "oidc_issuer": "https://issuer.example",
        "oidc_subject": "provider-subject",
        INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: 101,
        INTERCEPT_CREDENTIAL_VALIDATED_AT_CLAIM: validated_at,
        INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM: family_started_at,
    }
    assert session.committed is True


@pytest.mark.asyncio
async def test_proxy_rejects_token_response_without_validated_id_token() -> None:
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)

    with pytest.raises(OIDCIdentityError):
        await proxy._extract_upstream_claims({"id_token": "invalid"})


@pytest.mark.asyncio
async def test_proxy_rejects_forged_reserved_validation_marker() -> None:
    user = SimpleNamespace(id=uuid4(), credentials_invalidated_at=None)
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._intercept_session_factory = _session_factory(_Session())
    proxy._intercept_oidc_service = SimpleNamespace(
        find_or_create_user=AsyncMock(return_value=user)
    )
    proxy._intercept_identity_policy = OIDCIdentityPolicy(
        jit_provisioning=False,
        default_role="ANALYST",
        role_claim_path="",
        role_mapping={},
    )
    forged = {
        "id_token": "attacker-id-token",
        VALIDATED_ID_TOKEN_MARKER: {
            "claims": _strict_id_token_claims(),
            "authorization_epoch": 101,
            "validated_at": float(datetime.now(timezone.utc).timestamp()),
            "credential_family_started_at": float(
                datetime.now(timezone.utc).timestamp() - 30
            ),
            "nonce": "server-nonce",
            "mac": "attacker-controlled-mac",
        },
    }

    with pytest.raises(OIDCIdentityError, match="authentication"):
        await proxy._extract_upstream_claims(forged)


@pytest.mark.asyncio
async def test_callback_strips_idp_marker_and_authenticates_strict_claims() -> None:
    provider_claims = _strict_id_token_claims()
    verified = AccessToken(
        token="id-token",
        client_id="intercept-oidc-client",
        scopes=[],
        claims=provider_claims,
    )
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._token_validator = SimpleNamespace(
        verify_token=AsyncMock(return_value=verified)
    )
    family_started_at = float(datetime.now(timezone.utc).timestamp() - 60)
    context = proxy._callback_validation_context_var()
    context_token = context.set(
        SimpleNamespace(
            nonce="server-nonce",
            authorization_epoch=101,
            credential_family_started_at=family_started_at,
        )
    )
    try:
        validated = await proxy._validate_callback_token_response(
            {
                "access_token": "upstream-access-token",
                "id_token": "id-token",
                VALIDATED_ID_TOKEN_MARKER: {"mac": "idp-controlled"},
            }
        )
    finally:
        context.reset(context_token)

    marker = proxy._validated_id_token_marker(validated)
    assert marker["claims"] == provider_claims
    assert marker["authorization_epoch"] == 101
    assert marker["credential_family_started_at"] == family_started_at
    assert marker["nonce"] == "server-nonce"
    assert marker["mac"] != "idp-controlled"
    proxy._token_validator.verify_token.assert_awaited_once_with("id-token")

    tampered = dict(validated)
    tampered_marker = dict(marker)
    tampered_marker["claims"] = {
        **provider_claims,
        "sub": "attacker-subject",
    }
    tampered[VALIDATED_ID_TOKEN_MARKER] = tampered_marker
    with pytest.raises(OIDCIdentityError, match="authentication"):
        proxy._validated_id_token_marker(tampered)

    tampered_epoch = dict(validated)
    tampered_epoch_marker = dict(marker)
    tampered_epoch_marker["authorization_epoch"] = 102
    tampered_epoch[VALIDATED_ID_TOKEN_MARKER] = tampered_epoch_marker
    with pytest.raises(OIDCIdentityError, match="authentication"):
        proxy._validated_id_token_marker(tampered_epoch)


@pytest.mark.asyncio
async def test_callback_rejects_strict_nonce_mismatch_before_persistence() -> None:
    verified = AccessToken(
        token="id-token",
        client_id="intercept-oidc-client",
        scopes=[],
        claims=_strict_id_token_claims(nonce="different-transaction"),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._token_validator = SimpleNamespace(
        verify_token=AsyncMock(return_value=verified)
    )
    context = proxy._callback_validation_context_var()
    context_token = context.set(
        SimpleNamespace(
            nonce="server-nonce",
            authorization_epoch=101,
            credential_family_started_at=float(
                datetime.now(timezone.utc).timestamp() - 60
            ),
        )
    )
    try:
        with pytest.raises(OIDCIdentityError, match="claims"):
            await proxy._validate_callback_token_response(
                {"access_token": "access", "id_token": "id-token"}
            )
    finally:
        context.reset(context_token)


def test_upstream_authorize_url_replaces_static_nonce_with_transaction_hmac(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        OIDCProxy,
        "_build_upstream_authorize_url",
        lambda _proxy, _txn_id, _transaction: (
            "https://issuer.example/authorize?prompt=consent&nonce=static"
        ),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._jwt_signing_key = b"unit-test-marker-signing-key"
    proxy._intercept_upstream_scopes = ["openid", "email"]

    first = proxy._build_upstream_authorize_url("transaction-one", {})
    second = proxy._build_upstream_authorize_url("transaction-two", {})

    first_query = parse_qs(urlparse(first).query)
    second_query = parse_qs(urlparse(second).query)
    assert first_query["prompt"] == ["consent"]
    assert len(first_query["nonce"]) == 1
    assert first_query["nonce"] != ["static"]
    assert first_query["nonce"] != second_query["nonce"]


@pytest.mark.asyncio
async def test_callback_binds_server_owned_transaction_family_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[object] = []

    async def delegated_callback(proxy, _request):
        observed.append(proxy._callback_validation_context_var().get())
        return SimpleNamespace(status_code=302)

    monkeypatch.setattr(OIDCProxy, "_handle_idp_callback", delegated_callback)
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._jwt_signing_key = b"unit-test-marker-signing-key"
    proxy._transaction_store = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(created_at=123.0))
    )
    proxy._authorization_capacity_service = SimpleNamespace(
        require_authorization_epoch=AsyncMock(return_value=456)
    )
    request = SimpleNamespace(query_params={"state": "transaction-id"})

    response = await proxy._handle_idp_callback(request)

    assert response.status_code == 302
    assert len(observed) == 1
    assert observed[0].authorization_epoch == 456
    assert observed[0].credential_family_started_at == 123.0
    assert observed[0].nonce == proxy._derive_oidc_nonce("transaction-id")
    assert proxy._callback_validation_context_var().get() is None
    require_epoch = (
        proxy._authorization_capacity_service.require_authorization_epoch
    )
    require_epoch.assert_awaited_once_with("transaction-id")


@pytest.mark.asyncio
async def test_refresh_without_id_token_requires_new_authorization() -> None:
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    prior_tokens = _validated_idp_tokens(
        proxy,
        claims=_strict_id_token_claims(),
    )
    previous_marker = proxy._validated_id_token_marker(prior_tokens)
    context = proxy._refresh_marker_context_var()
    context_token = context.set(previous_marker)
    try:
        with pytest.raises(
            OIDCIdentityError,
            match="did not include a new ID token",
        ) as exc_info:
            await proxy._validate_refresh_token_response(
                {
                    "access_token": "new-upstream-access-secret",
                    "refresh_token": "new-upstream-refresh-secret",
                    VALIDATED_ID_TOKEN_MARKER: {"mac": "idp-controlled"},
                }
            )
    finally:
        context.reset(context_token)

    assert "new-upstream-access-secret" not in str(exc_info.value)
    assert "new-upstream-refresh-secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_refresh_without_new_id_token_returns_token_safe_invalid_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        status=UserStatus.ACTIVE,
        credentials_invalidated_at=None,
    )
    local_claims = {
        "intercept_user_id": str(user_id),
        "auth_source": "oidc",
        INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: 101,
        INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM: 100.0,
    }

    async def upstream_refresh(proxy, _client, _refresh_token, _scopes):
        refreshed = await proxy._validate_refresh_token_response(
            {
                "access_token": "new-upstream-access-secret",
                "refresh_token": "new-upstream-refresh-secret",
            }
        )
        return OAuthToken(
            access_token=refreshed["access_token"],
            refresh_token=refreshed["refresh_token"],
            token_type="Bearer",
            expires_in=3600,
            scope=MCP_ACCESS_SCOPE,
        )

    monkeypatch.setattr(OIDCProxy, "exchange_refresh_token", upstream_refresh)
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._registration_service = None
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token, *, expected_token_use: {
            "token_use": expected_token_use,
            "jti": "refresh-jti",
            "upstream_claims": local_claims,
        }
    )
    proxy._intercept_session_factory = _session_factory(_Session(user))
    proxy._require_active_provider_grant = AsyncMock()
    proxy._jti_mapping_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(upstream_token_id="upstream-family")
        )
    )
    proxy._upstream_token_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                raw_token_data=_validated_idp_tokens(
                    proxy,
                    claims=_strict_id_token_claims(),
                    validated_at=150.0,
                    family_started_at=100.0,
                )
            )
        )
    )

    with pytest.raises(TokenError) as exc_info:
        await proxy.exchange_refresh_token(
            SimpleNamespace(client_id="vscode-client"),
            SimpleNamespace(token="native-refresh-token"),
            [MCP_ACCESS_SCOPE],
        )

    assert exc_info.value.error == "invalid_grant"
    rendered_error = repr(exc_info.value)
    assert "new-upstream-access-secret" not in rendered_error
    assert "new-upstream-refresh-secret" not in rendered_error


@pytest.mark.asyncio
async def test_refresh_id_token_is_revalidated_with_subject_continuity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    prior_tokens = _validated_idp_tokens(
        proxy,
        claims=_strict_id_token_claims(),
    )
    previous_marker = proxy._validated_id_token_marker(prior_tokens)
    new_validation_epoch = previous_marker["validated_at"] + 60.0
    monkeypatch.setattr(
        "app.mcp.oidc_provider.time.time",
        lambda: new_validation_epoch,
    )
    refreshed_claims = _strict_id_token_claims()
    refreshed_claims.pop("nonce")
    proxy._token_validator = SimpleNamespace(
        verify_token=AsyncMock(
            return_value=AccessToken(
                token="new-id-token",
                client_id="intercept-oidc-client",
                scopes=[],
                claims=refreshed_claims,
            )
        )
    )
    context = proxy._refresh_marker_context_var()
    context_token = context.set(previous_marker)
    try:
        refreshed = await proxy._validate_refresh_token_response(
            {"access_token": "new-access", "id_token": "new-id-token"}
        )
    finally:
        context.reset(context_token)

    marker = proxy._validated_id_token_marker(refreshed)
    assert marker["claims"] == refreshed_claims
    assert marker["authorization_epoch"] == previous_marker[
        "authorization_epoch"
    ]
    assert marker["validated_at"] == new_validation_epoch
    assert marker["credential_family_started_at"] == previous_marker[
        "credential_family_started_at"
    ]
    assert marker["nonce"] == previous_marker["nonce"]

    changed_subject_claims = {
        **refreshed_claims,
        "sub": "different-provider-subject",
    }
    proxy._token_validator.verify_token = AsyncMock(
        return_value=AccessToken(
            token="changed-subject-token",
            client_id="intercept-oidc-client",
            scopes=[],
            claims=changed_subject_claims,
        )
    )
    context_token = context.set(previous_marker)
    try:
        with pytest.raises(OIDCIdentityError, match="subject"):
            await proxy._validate_refresh_token_response(
                {
                    "access_token": "other-access",
                    "id_token": "changed-subject-token",
                }
            )
    finally:
        context.reset(context_token)


@pytest.mark.asyncio
async def test_transparent_refresh_carries_authenticated_marker_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    raw_token_data = _validated_idp_tokens(
        proxy,
        claims=_strict_id_token_claims(),
    )
    upstream_token_set = SimpleNamespace(
        raw_token_data=raw_token_data,
        client_id="vscode-client",
        upstream_token_id="upstream-family",
    )
    observed: list[dict[str, object] | None] = []

    async def delegated_refresh(base_proxy, token_set):
        observed.append(base_proxy._refresh_marker_context_var().get())
        return token_set

    monkeypatch.setattr(
        OIDCProxy,
        "_try_transparent_refresh",
        delegated_refresh,
    )
    proxy._extract_upstream_claims = AsyncMock(
        return_value={
            "intercept_user_id": str(uuid4()),
            "auth_source": "oidc",
        }
    )
    proxy._require_active_provider_grant = AsyncMock()
    proxy._upstream_token_store = SimpleNamespace(delete=AsyncMock())

    refreshed = await proxy._try_transparent_refresh(upstream_token_set)

    assert refreshed is upstream_token_set
    assert observed == [proxy._validated_id_token_marker(raw_token_data)]
    proxy._extract_upstream_claims.assert_awaited_once_with(raw_token_data)
    proxy._require_active_provider_grant.assert_awaited_once()
    assert proxy._refresh_marker_context_var().get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity_error",
    [
        OIDCIdentityError("OIDC id_token validation failed"),
        OIDCAuthenticationError("OIDC-linked user account is not active"),
    ],
)
async def test_authorization_code_identity_failure_is_native_error_and_cleans_tokens(
    monkeypatch: pytest.MonkeyPatch,
    identity_error: Exception,
) -> None:
    upstream_store = SimpleNamespace(put=AsyncMock(), delete=AsyncMock())

    async def fastmcp_exchange(proxy, _client, _authorization_code):
        await proxy._upstream_token_store.put(
            key="persisted-before-identity-hook",
            value=SimpleNamespace(access_token="upstream-secret"),
            ttl=300,
        )
        raise identity_error

    monkeypatch.setattr(OIDCProxy, "exchange_authorization_code", fastmcp_exchange)
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._upstream_token_store = upstream_store

    with pytest.raises(TokenError) as exc_info:
        await proxy.exchange_authorization_code(
            SimpleNamespace(client_id="vscode-client"),
            SimpleNamespace(code="one-use-code"),
        )

    assert exc_info.value.error == "invalid_grant"
    assert "identity" in str(exc_info.value.error_description).lower()
    upstream_store.delete.assert_awaited_once_with(
        key="persisted-before-identity-hook"
    )


@pytest.mark.asyncio
async def test_oidc_authorization_code_predating_account_cutoff_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        status=UserStatus.ACTIVE,
        credentials_invalidated_at=datetime.fromtimestamp(200, tz=timezone.utc),
    )
    # The IdP token is issued after the cutoff, but the server-owned OAuth
    # transaction began before it. The credential family must stay invalid.
    provider_claims = _strict_id_token_claims()
    upstream_store = SimpleNamespace(put=AsyncMock(), delete=AsyncMock())

    async def fastmcp_exchange(proxy, _client, _authorization_code):
        await proxy._upstream_token_store.put(
            key="pre-disable-upstream-family",
            value=SimpleNamespace(access_token="upstream-secret"),
            ttl=300,
        )
        await proxy._extract_upstream_claims(
            _validated_idp_tokens(
                proxy,
                claims=provider_claims,
                validated_at=300.0,
                family_started_at=100.0,
            )
        )
        return OAuthToken(
            access_token="should-not-be-issued",
            token_type="Bearer",
            expires_in=3600,
            scope=MCP_ACCESS_SCOPE,
        )

    monkeypatch.setattr(OIDCProxy, "exchange_authorization_code", fastmcp_exchange)
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._upstream_token_store = upstream_store
    proxy._intercept_session_factory = _session_factory(_Session())
    proxy._intercept_oidc_service = SimpleNamespace(
        find_or_create_user=AsyncMock(return_value=user)
    )
    proxy._intercept_identity_policy = OIDCIdentityPolicy(
        jit_provisioning=False,
        default_role="ANALYST",
        role_claim_path="",
        role_mapping={},
    )

    with pytest.raises(TokenError) as exc_info:
        await proxy.exchange_authorization_code(
            SimpleNamespace(client_id="vscode-client"),
            SimpleNamespace(code="pre-disable-code"),
        )

    assert exc_info.value.error == "invalid_grant"
    upstream_store.delete.assert_awaited_once_with(
        key="pre-disable-upstream-family"
    )


@pytest.mark.asyncio
async def test_oidc_authorization_code_crossing_account_cutoff_is_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        status=UserStatus.ACTIVE,
        credentials_invalidated_at=None,
    )
    local_claims = {
        "intercept_user_id": str(user_id),
        "auth_source": "oidc",
        INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: 101,
        INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM: 100.0,
    }
    issued = OAuthToken(
        access_token="must-be-removed-access",
        refresh_token="must-be-removed-refresh",
        token_type="Bearer",
        expires_in=3600,
        scope=MCP_ACCESS_SCOPE,
    )

    async def exchange_after_disable(*_args: object, **_kwargs: object):
        user.credentials_invalidated_at = datetime.fromtimestamp(
            200,
            tz=timezone.utc,
        )
        return issued

    monkeypatch.setattr(
        OIDCProxy,
        "exchange_authorization_code",
        AsyncMock(side_effect=exchange_after_disable),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._registration_service = None
    proxy._upstream_token_store = SimpleNamespace()
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token, *, expected_token_use: {
            "token_use": expected_token_use,
            "upstream_claims": local_claims,
        }
    )
    proxy._intercept_session_factory = _session_factory(_Session(user))
    proxy._remove_issued_token_state = AsyncMock()

    with pytest.raises(TokenError) as exc_info:
        await proxy.exchange_authorization_code(
            SimpleNamespace(client_id="vscode-client"),
            SimpleNamespace(code="crossing-code"),
        )

    assert exc_info.value.error == "invalid_grant"
    proxy._remove_issued_token_state.assert_awaited_once_with(issued, set())


@pytest.mark.asyncio
async def test_successful_oidc_exchange_claims_durable_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = OAuthToken(
        access_token="fastmcp-access",
        token_type="Bearer",
        expires_in=3600,
        scope=MCP_ACCESS_SCOPE,
    )
    monkeypatch.setattr(
        OIDCProxy,
        "exchange_authorization_code",
        AsyncMock(return_value=issued),
    )
    registration_service = SimpleNamespace(
        require_valid=AsyncMock(return_value=True),
        activate=AsyncMock(return_value=True),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._upstream_token_store = SimpleNamespace()
    proxy._registration_service = registration_service
    client = SimpleNamespace(client_id="public-dcr-client")

    result = await proxy.exchange_authorization_code(
        client,
        SimpleNamespace(code="one-use-code"),
    )

    assert result == issued
    registration_service.require_valid.assert_awaited_once_with(
        "public-dcr-client"
    )
    registration_service.activate.assert_awaited_once_with("public-dcr-client")


@pytest.mark.asyncio
async def test_successful_oidc_refresh_extends_registration_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = OAuthToken(
        access_token="rotated-fastmcp-access",
        token_type="Bearer",
        expires_in=3600,
        scope=MCP_ACCESS_SCOPE,
    )
    base_exchange = AsyncMock(return_value=issued)
    monkeypatch.setattr(OIDCProxy, "exchange_refresh_token", base_exchange)
    registration_service = SimpleNamespace(
        require_valid=AsyncMock(return_value=True),
        activate=AsyncMock(return_value=True),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._registration_service = registration_service
    client = SimpleNamespace(client_id="public-dcr-client")
    refresh = SimpleNamespace(token="native-refresh")

    result = await proxy.exchange_refresh_token(
        client,
        refresh,
        [MCP_ACCESS_SCOPE],
    )

    assert result == issued
    base_exchange.assert_awaited_once_with(client, refresh, [MCP_ACCESS_SCOPE])
    registration_service.require_valid.assert_awaited_once_with(
        "public-dcr-client"
    )
    registration_service.activate.assert_awaited_once_with("public-dcr-client")


@pytest.mark.asyncio
async def test_oidc_refresh_fails_closed_for_unmarked_legacy_token_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        status=UserStatus.ACTIVE,
        credentials_invalidated_at=None,
    )
    local_claims = {
        "intercept_user_id": str(user_id),
        "auth_source": "oidc",
        INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: 101,
        INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM: 100.0,
    }
    base_exchange = AsyncMock()
    monkeypatch.setattr(OIDCProxy, "exchange_refresh_token", base_exchange)
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._registration_service = None
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token, *, expected_token_use: {
            "token_use": expected_token_use,
            "jti": "legacy-refresh-jti",
            "upstream_claims": local_claims,
        }
    )
    proxy._intercept_session_factory = _session_factory(_Session(user))
    proxy._jti_mapping_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(upstream_token_id="legacy-upstream")
        )
    )
    proxy._upstream_token_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                raw_token_data={"id_token": "legacy-id-token"}
            )
        )
    )

    with pytest.raises(TokenError) as exc_info:
        await proxy.exchange_refresh_token(
            SimpleNamespace(client_id="vscode-client"),
            SimpleNamespace(token="legacy-refresh"),
            [MCP_ACCESS_SCOPE],
        )

    assert exc_info.value.error == "invalid_grant"
    base_exchange.assert_not_awaited()


@pytest.mark.asyncio
async def test_oidc_refresh_predating_account_cutoff_is_rejected_before_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        status=UserStatus.ACTIVE,
        credentials_invalidated_at=datetime.fromtimestamp(200, tz=timezone.utc),
    )
    local_claims = {
        "intercept_user_id": str(user_id),
        "auth_source": "oidc",
        INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: 101,
        INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM: 100.0,
    }
    base_exchange = AsyncMock(
        return_value=OAuthToken(
            access_token="should-not-be-issued",
            token_type="Bearer",
            expires_in=3600,
            scope=MCP_ACCESS_SCOPE,
        )
    )
    monkeypatch.setattr(OIDCProxy, "exchange_refresh_token", base_exchange)
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._registration_service = None
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token, *, expected_token_use: {
            "token_use": expected_token_use,
            "upstream_claims": local_claims,
        }
    )
    proxy._intercept_session_factory = _session_factory(_Session(user))
    refresh = SimpleNamespace(token="pre-disable-refresh", scopes=[MCP_ACCESS_SCOPE])

    with pytest.raises(TokenError) as exc_info:
        await proxy.exchange_refresh_token(
            SimpleNamespace(client_id="vscode-client"),
            refresh,
            [MCP_ACCESS_SCOPE],
        )

    assert exc_info.value.error == "invalid_grant"
    base_exchange.assert_not_awaited()


@pytest.mark.asyncio
async def test_oidc_refresh_crossing_account_cutoff_removes_issued_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        status=UserStatus.ACTIVE,
        credentials_invalidated_at=None,
    )
    local_claims = {
        "intercept_user_id": str(user_id),
        "auth_source": "oidc",
        INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: 101,
        INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM: 100.0,
    }
    issued = OAuthToken(
        access_token="must-be-removed-access",
        refresh_token="must-be-removed-refresh",
        token_type="Bearer",
        expires_in=3600,
        scope=MCP_ACCESS_SCOPE,
    )

    async def exchange_after_disable(*_args, **_kwargs):
        user.credentials_invalidated_at = datetime.fromtimestamp(
            200,
            tz=timezone.utc,
        )
        return issued

    base_exchange = AsyncMock(side_effect=exchange_after_disable)
    monkeypatch.setattr(OIDCProxy, "exchange_refresh_token", base_exchange)
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._registration_service = None
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token, *, expected_token_use: {
            "token_use": expected_token_use,
            "jti": "crossing-refresh-jti",
            "upstream_claims": local_claims,
        }
    )
    proxy._intercept_session_factory = _session_factory(_Session(user))
    proxy._require_active_provider_grant = AsyncMock()
    proxy._jti_mapping_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(upstream_token_id="crossing-upstream")
        )
    )
    proxy._upstream_token_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                raw_token_data=_validated_idp_tokens(
                    proxy,
                    claims=_strict_id_token_claims(),
                    validated_at=150.0,
                    family_started_at=100.0,
                )
            )
        )
    )
    proxy._remove_issued_token_state = AsyncMock()

    with pytest.raises(TokenError) as exc_info:
        await proxy.exchange_refresh_token(
            SimpleNamespace(client_id="vscode-client"),
            SimpleNamespace(token="crossing-refresh"),
            [MCP_ACCESS_SCOPE],
        )

    assert exc_info.value.error == "invalid_grant"
    base_exchange.assert_awaited_once()
    proxy._remove_issued_token_state.assert_awaited_once_with(issued)


@pytest.mark.asyncio
async def test_oidc_refresh_crossing_connected_client_revocation_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    session_maker,
) -> None:
    """A refresh that returns after durable family revocation cannot issue tokens."""

    user = UserAccount(
        username="oidc.refresh.revocation.race@example.com",
        email="oidc.refresh.revocation.race@example.com",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        oidc_issuer="https://issuer.example",
        oidc_subject="oidc-refresh-revocation-race",
    )
    client_row = MCPOAuthClient(
        client_id="vscode-revocation-race",
        client_name="VS Code revocation race",
    )
    upstream_family_id = "upstream-family-revoked-during-refresh"
    reference_hash = hashlib.sha256(upstream_family_id.encode("utf-8")).hexdigest()
    async with session_maker() as db:
        db.add_all([user, client_row])
        await db.flush()
        consent = MCPOAuthConsent(
            user_id=user.id,
            client_db_id=client_row.id,
            provider_mode="oidc",
            provider_reference_hash=reference_hash,
        )
        db.add(consent)
        await db.flush()
        db.add(
            MCPOAuthProviderGrantReference(
                consent_id=consent.id,
                provider_reference_hash=reference_hash,
            )
        )
        await db.commit()

    local_claims = {
        "intercept_user_id": str(user.id),
        "auth_source": "oidc",
        INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: 101,
        INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM: 100.0,
    }
    issued = OAuthToken(
        access_token="must-be-removed-access",
        refresh_token="must-be-removed-refresh",
        token_type="Bearer",
        expires_in=3600,
        scope=MCP_ACCESS_SCOPE,
    )
    upstream_started = asyncio.Event()
    release_upstream = asyncio.Event()

    async def upstream_exchange(*_args, **_kwargs):
        upstream_started.set()
        await release_upstream.wait()
        return issued

    monkeypatch.setattr(OIDCProxy, "exchange_refresh_token", upstream_exchange)
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._registration_service = None
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token, *, expected_token_use: {
            "token_use": expected_token_use,
            "jti": "refresh-jti",
            "upstream_claims": local_claims,
        }
    )
    proxy._intercept_session_factory = session_maker
    proxy._jti_mapping_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(upstream_token_id=upstream_family_id)
        )
    )
    proxy._upstream_token_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                raw_token_data=_validated_idp_tokens(
                    proxy,
                    claims=_strict_id_token_claims(),
                    validated_at=150.0,
                    family_started_at=100.0,
                )
            )
        )
    )
    proxy._remove_issued_token_state = AsyncMock()

    refresh_task = asyncio.create_task(
        proxy.exchange_refresh_token(
            SimpleNamespace(client_id=client_row.client_id),
            SimpleNamespace(token="refresh-raced-by-revocation"),
            [MCP_ACCESS_SCOPE],
        )
    )
    await asyncio.wait_for(upstream_started.wait(), timeout=2)
    async with session_maker() as revocation_db:
        await mcp_oauth_service.revoke_connected_client(
            revocation_db,
            user=user,
            consent_id=consent.id,
        )
        await revocation_db.commit()
    release_upstream.set()

    with pytest.raises(TokenError) as exc_info:
        await asyncio.wait_for(refresh_task, timeout=2)

    assert exc_info.value.error == "invalid_grant"
    proxy._remove_issued_token_state.assert_awaited_once()
    assert proxy._remove_issued_token_state.await_args.args[0] is issued


@pytest.mark.asyncio
async def test_oidc_access_cannot_reactivate_a_revoked_token_family(
    monkeypatch: pytest.MonkeyPatch,
    session_maker,
) -> None:
    """Ordinary access never clears a durable connected-client tombstone."""

    user = UserAccount(
        username="oidc.revoked.access@example.com",
        email="oidc.revoked.access@example.com",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        oidc_issuer="https://issuer.example",
        oidc_subject="oidc-revoked-access",
    )
    client_row = MCPOAuthClient(
        client_id="vscode-revoked-access",
        client_name="VS Code revoked access",
    )
    upstream_family_id = "revoked-upstream-family"
    reference_hash = hashlib.sha256(upstream_family_id.encode("utf-8")).hexdigest()
    revoked_at = datetime.now(timezone.utc)
    async with session_maker() as db:
        db.add_all([user, client_row])
        await db.flush()
        consent = MCPOAuthConsent(
            user_id=user.id,
            client_db_id=client_row.id,
            provider_mode="oidc",
            provider_reference_hash=reference_hash,
            revoked_at=revoked_at,
        )
        db.add(consent)
        await db.flush()
        reference = MCPOAuthProviderGrantReference(
            consent_id=consent.id,
            provider_reference_hash=reference_hash,
            revoked_at=revoked_at,
        )
        db.add(reference)
        await db.commit()

    local_claims = {
        "intercept_user_id": str(user.id),
        "auth_source": "oidc",
        INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: 101,
        INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM: 100.0,
    }
    monkeypatch.setattr(
        OIDCProxy,
        "load_access_token",
        AsyncMock(
            return_value=AccessToken(
                token="upstream-provider-secret",
                client_id=client_row.client_id,
                scopes=["openid"],
                claims={"upstream_claims": local_claims},
            )
        ),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token: {
            "client_id": client_row.client_id,
            "jti": "revoked-access-jti",
            "exp": 2_000_000_000,
            "upstream_claims": local_claims,
        }
    )
    proxy._resource_url = "https://intercept.example/mcp/streamable/"
    proxy._intercept_session_factory = session_maker
    proxy._jti_mapping_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(upstream_token_id=upstream_family_id)
        ),
        delete=AsyncMock(),
    )
    proxy._upstream_token_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                upstream_token_id=upstream_family_id,
                expires_at=2_000_000_000,
                refresh_token_expires_at=2_100_000_000,
                raw_token_data=_validated_idp_tokens(
                    proxy,
                    claims=_strict_id_token_claims(),
                    validated_at=150.0,
                    family_started_at=100.0,
                ),
            )
        ),
        delete=AsyncMock(),
    )
    proxy._client_storage = SimpleNamespace(put=AsyncMock(), delete=AsyncMock())
    proxy.get_client = AsyncMock(return_value=None)

    assert await proxy.load_access_token("revoked-fastmcp-reference") is None

    async with session_maker() as db:
        persisted_consent = await db.get(MCPOAuthConsent, consent.id)
        persisted_reference = await db.get(
            MCPOAuthProviderGrantReference,
            reference.id,
        )
    assert persisted_consent is not None and persisted_consent.revoked_at == revoked_at
    assert persisted_reference is not None and persisted_reference.revoked_at == revoked_at
    proxy._client_storage.put.assert_not_awaited()


@pytest.mark.asyncio
async def test_clock_skew_cannot_make_pre_revocation_oidc_authorization_fresh(
    session_maker,
) -> None:
    user = UserAccount(
        username="oidc.stale.code@example.com",
        email="oidc.stale.code@example.com",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        oidc_issuer="https://issuer.example",
        oidc_subject="oidc-stale-code",
    )
    client_row = MCPOAuthClient(
        client_id="vscode-stale-code",
        client_name="VS Code stale code",
    )
    revoked_at = datetime.now(timezone.utc)
    skewed_authorization_time = revoked_at + timedelta(days=365)
    async with session_maker() as db:
        db.add_all([user, client_row])
        await db.flush()
        consent = MCPOAuthConsent(
            user_id=user.id,
            client_db_id=client_row.id,
            provider_mode="oidc",
            last_authorized_at=revoked_at - timedelta(minutes=2),
            last_authorization_epoch=40,
            revoked_at=revoked_at,
            revocation_epoch=42,
        )
        db.add(consent)
        await db.commit()

    proxy = object.__new__(InterceptOIDCProxy)
    client_info = SimpleNamespace(
        client_name="VS Code stale code",
        client_uri=None,
        logo_uri=None,
        redirect_uris=["http://127.0.0.1:4567/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        contacts=[],
        jwks_uri=None,
        cimd_document=None,
    )
    async with session_maker() as db:
        with pytest.raises(OIDCIdentityError, match="revoked"):
            await proxy._record_connected_client_projection(
                db,
                user_id=user.id,
                client_id=client_row.client_id,
                client_info=client_info,
                reference_hash="stale-code-family",
                reauthorize=True,
                authorization_epoch=41,
                authorization_started_at=skewed_authorization_time,
            )
        await db.rollback()

    async with session_maker() as db:
        persisted = await db.get(MCPOAuthConsent, consent.id)
    assert persisted is not None
    assert persisted.revoked_at == revoked_at
    assert persisted.revocation_epoch == 42
    assert persisted.last_authorization_epoch == 40
    assert persisted.last_authorized_at == revoked_at - timedelta(minutes=2)


@pytest.mark.asyncio
async def test_oidc_provider_rejects_code_from_revoked_authorization_epoch(
    monkeypatch: pytest.MonkeyPatch,
    session_maker,
) -> None:
    user = UserAccount(
        username="oidc.revoked.exchange@example.com",
        email="oidc.revoked.exchange@example.com",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        oidc_issuer="https://issuer.example",
        oidc_subject="oidc-revoked-exchange",
    )
    client_row = MCPOAuthClient(
        client_id="vscode-revoked-exchange",
        client_name="VS Code revoked exchange",
    )
    revoked_at = datetime.now(timezone.utc)
    authorization_epoch = 41
    skewed_authorization_time = revoked_at + timedelta(days=365)
    async with session_maker() as db:
        db.add_all([user, client_row])
        await db.flush()
        db.add(
            MCPOAuthConsent(
                user_id=user.id,
                client_db_id=client_row.id,
                provider_mode="oidc",
                last_authorized_at=revoked_at - timedelta(minutes=2),
                last_authorization_epoch=40,
                revoked_at=revoked_at,
                revocation_epoch=42,
            )
        )
        await db.commit()

    issued = OAuthToken(
        access_token="stale-fastmcp-access",
        refresh_token="stale-fastmcp-refresh",
        token_type="Bearer",
        expires_in=3600,
        scope=MCP_ACCESS_SCOPE,
    )
    monkeypatch.setattr(
        OIDCProxy,
        "exchange_authorization_code",
        AsyncMock(return_value=issued),
    )
    local_claims = {
        "intercept_user_id": str(user.id),
        "auth_source": "oidc",
        INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: authorization_epoch,
        INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM: (
            skewed_authorization_time.timestamp()
        ),
    }
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._registration_service = None
    proxy._intercept_session_factory = session_maker
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token, *, expected_token_use: {
            "jti": "stale-access-jti",
            "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
            "upstream_claims": local_claims,
            "token_use": expected_token_use,
        }
    )
    proxy._jti_mapping_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                upstream_token_id="stale-upstream-family"
            )
        )
    )
    proxy._upstream_token_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                expires_at=int(datetime.now(timezone.utc).timestamp()) + 3600,
                refresh_token_expires_at=(
                    int(datetime.now(timezone.utc).timestamp()) + 7200
                ),
                raw_token_data=_validated_idp_tokens(
                    proxy,
                    claims=_strict_id_token_claims(),
                    authorization_epoch=authorization_epoch,
                    validated_at=skewed_authorization_time.timestamp(),
                    family_started_at=skewed_authorization_time.timestamp(),
                ),
            )
        )
    )
    proxy._client_storage = SimpleNamespace(put=AsyncMock())
    proxy._remove_issued_token_state = AsyncMock()
    client_info = SimpleNamespace(
        client_id=client_row.client_id,
        client_name=client_row.client_name,
        client_uri=None,
        logo_uri=None,
        redirect_uris=["http://127.0.0.1:4567/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        contacts=[],
        jwks_uri=None,
        cimd_document=None,
    )

    with pytest.raises(TokenError) as exc_info:
        await proxy.exchange_authorization_code(
            client_info,
            SimpleNamespace(code="pre-revocation-code"),
        )

    assert exc_info.value.error == "invalid_grant"
    proxy._remove_issued_token_state.assert_awaited_once_with(issued, set())
    proxy._client_storage.put.assert_not_awaited()


@pytest.mark.asyncio
async def test_fresh_database_epoch_reopens_despite_reverse_clock_skew(
    session_maker,
) -> None:
    user = UserAccount(
        username="oidc.fresh.code@example.com",
        email="oidc.fresh.code@example.com",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        oidc_issuer="https://issuer.example",
        oidc_subject="oidc-fresh-code",
    )
    client_row = MCPOAuthClient(
        client_id="vscode-fresh-code",
        client_name="VS Code fresh code",
    )
    revoked_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    authorization_started_at = revoked_at - timedelta(days=365)
    async with session_maker() as db:
        db.add_all([user, client_row])
        await db.flush()
        consent = MCPOAuthConsent(
            user_id=user.id,
            client_db_id=client_row.id,
            provider_mode="oidc",
            last_authorized_at=revoked_at - timedelta(minutes=1),
            last_authorization_epoch=40,
            revoked_at=revoked_at,
            revocation_epoch=42,
        )
        db.add(consent)
        await db.commit()

    proxy = object.__new__(InterceptOIDCProxy)
    client_info = SimpleNamespace(
        client_name="VS Code fresh code",
        client_uri=None,
        logo_uri=None,
        redirect_uris=["http://127.0.0.1:4567/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        contacts=[],
        jwks_uri=None,
        cimd_document=None,
    )
    async with session_maker() as db:
        await proxy._record_connected_client_projection(
            db,
            user_id=user.id,
            client_id=client_row.client_id,
            client_info=client_info,
            reference_hash="fresh-code-family",
            reauthorize=True,
            authorization_epoch=43,
            authorization_started_at=authorization_started_at,
        )
        await db.commit()

    async with session_maker() as db:
        persisted = await db.get(MCPOAuthConsent, consent.id)
        reference = await db.scalar(
            select(MCPOAuthProviderGrantReference).where(
                MCPOAuthProviderGrantReference.provider_reference_hash
                == "fresh-code-family"
            )
        )
    assert persisted is not None
    assert persisted.revoked_at is None
    assert persisted.revocation_epoch is None
    assert persisted.last_authorization_epoch == 43
    assert persisted.last_authorized_at == authorization_started_at
    assert reference is not None and reference.revoked_at is None


@pytest.mark.asyncio
async def test_oidc_post_exchange_expiry_removes_partially_issued_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = OAuthToken(
        access_token="fastmcp-access",
        refresh_token="fastmcp-refresh",
        token_type="Bearer",
        expires_in=3600,
        scope=MCP_ACCESS_SCOPE,
    )
    monkeypatch.setattr(
        OIDCProxy,
        "exchange_authorization_code",
        AsyncMock(return_value=issued),
    )
    registration_service = SimpleNamespace(
        require_valid=AsyncMock(return_value=True),
        activate=AsyncMock(
            side_effect=MCPRegistrationExpiredError("expired during exchange")
        ),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._upstream_token_store = SimpleNamespace()
    proxy._registration_service = registration_service
    proxy._remove_issued_token_state = AsyncMock()

    with pytest.raises(TokenError, match="expired"):
        await proxy.exchange_authorization_code(
            SimpleNamespace(client_id="public-dcr-client"),
            SimpleNamespace(code="one-use-code"),
        )

    proxy._remove_issued_token_state.assert_awaited_once()
    assert proxy._remove_issued_token_state.await_args.args[0] == issued


@pytest.mark.asyncio
async def test_oidc_rejected_grant_cleanup_deletes_every_native_reference() -> None:
    jti_mapping_store = SimpleNamespace(
        get=AsyncMock(
            side_effect=[
                SimpleNamespace(upstream_token_id="upstream-family"),
                SimpleNamespace(upstream_token_id="upstream-family"),
            ]
        ),
        delete=AsyncMock(),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token, *, expected_token_use: {
            "jti": f"{expected_token_use}-jti"
        }
    )
    proxy._jti_mapping_store = jti_mapping_store
    proxy._refresh_token_store = SimpleNamespace(delete=AsyncMock())
    proxy._upstream_token_store = SimpleNamespace(delete=AsyncMock())
    issued = OAuthToken(
        access_token="fastmcp-access",
        refresh_token="fastmcp-refresh",
        token_type="Bearer",
        expires_in=3600,
        scope=MCP_ACCESS_SCOPE,
    )

    await proxy._remove_issued_token_state(issued)

    assert [call.kwargs["key"] for call in jti_mapping_store.delete.await_args_list] == [
        "access-jti",
        "refresh-jti",
    ]
    proxy._refresh_token_store.delete.assert_awaited_once_with(
        key=hashlib.sha256(b"fastmcp-refresh").hexdigest()
    )
    proxy._upstream_token_store.delete.assert_awaited_once_with(
        key="upstream-family"
    )


@pytest.mark.asyncio
async def test_proxy_returns_reference_token_with_local_identity_not_upstream_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(id=user_id, status=UserStatus.ACTIVE)
    session = _Session(user)
    upstream_result = AccessToken(
        token="upstream-provider-secret",
        client_id="intercept-oidc-app",
        scopes=["openid", "email"],
        claims={
            "upstream_claims": {
                "intercept_user_id": str(user_id),
                "auth_source": "oidc",
                "oidc_issuer": "https://issuer.example",
                "oidc_subject": "provider-subject",
                INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: 101,
                INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM: 100.0,
            }
        },
    )
    monkeypatch.setattr(
        OIDCProxy,
        "load_access_token",
        AsyncMock(return_value=upstream_result),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token: {
            "client_id": "vscode-client",
            "jti": "reference-id",
            "upstream_claims": upstream_result.claims["upstream_claims"],
        }
    )
    proxy._resource_url = "https://intercept.example/mcp/streamable/"
    proxy._intercept_session_factory = _session_factory(session)
    proxy._jti_mapping_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(upstream_token_id="upstream-set-id")
        )
    )
    proxy._upstream_token_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                expires_at=2_000_000_000,
                refresh_token_expires_at=2_100_000_000,
                raw_token_data=_validated_idp_tokens(
                    proxy,
                    claims=_strict_id_token_claims(),
                ),
            )
        )
    )
    proxy._client_storage = SimpleNamespace(put=AsyncMock())
    proxy.get_client = AsyncMock(return_value=None)
    proxy._record_connected_client_projection = AsyncMock()

    result = await proxy.load_access_token("fastmcp-reference-token")

    assert result is not None
    assert result.token == "fastmcp-reference-token"
    assert result.client_id == "vscode-client"
    assert result.scopes == [MCP_ACCESS_SCOPE]
    assert result.resource == "https://intercept.example/mcp/streamable/"
    assert result.claims["intercept_user_id"] == str(user_id)
    assert result.claims["auth_source"] == "oidc"
    assert "upstream-provider-secret" not in repr(result)


@pytest.mark.asyncio
async def test_validated_reference_updates_token_free_connected_client_projection(
    monkeypatch: pytest.MonkeyPatch,
    session_maker,
) -> None:
    user = UserAccount(
        username="projected.oidc@example.com",
        email="projected.oidc@example.com",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        oidc_issuer="https://issuer.example",
        oidc_subject="projected-provider-subject",
    )
    async with session_maker() as db:
        db.add(user)
        await db.commit()
    user_id = user.id
    upstream_result = AccessToken(
        token="upstream-provider-secret",
        client_id="intercept-oidc-app",
        scopes=["openid", "email"],
        claims={
            "upstream_claims": {
                "intercept_user_id": str(user_id),
                "auth_source": "oidc",
                INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: 101,
                INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM: 100.0,
            }
        },
    )
    monkeypatch.setattr(
        OIDCProxy,
        "load_access_token",
        AsyncMock(return_value=upstream_result),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token: {
            "client_id": "vscode-client",
            "jti": "reference-id",
            "exp": 2_000_000_000,
            "upstream_claims": upstream_result.claims["upstream_claims"],
        }
    )
    proxy._resource_url = "https://intercept.example/mcp/streamable/"
    proxy._intercept_session_factory = session_maker
    proxy.get_client = AsyncMock(
        return_value=SimpleNamespace(
            client_id="vscode-client",
            client_name="VS Code",
            client_uri="https://code.visualstudio.com",
            logo_uri=None,
            redirect_uris=["http://127.0.0.1:4567/callback"],
            scope=MCP_ACCESS_SCOPE,
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
            contacts=None,
            jwks_uri=None,
            cimd_document=None,
        )
    )
    proxy._jti_mapping_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(upstream_token_id="upstream-set-id")
        )
    )
    proxy._upstream_token_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                expires_at=2_000_000_000,
                refresh_token_expires_at=2_100_000_000,
                raw_token_data=_validated_idp_tokens(
                    proxy,
                    claims=_strict_id_token_claims(),
                ),
            )
        )
    )
    proxy._client_storage = SimpleNamespace(put=AsyncMock())
    monkeypatch.setattr("app.mcp.oidc_provider.time.time", lambda: 1_900_000_000)

    result = await proxy.load_access_token("fastmcp-reference-token")

    assert result is not None
    async with session_maker() as db:
        client = (await db.execute(select(MCPOAuthClient))).scalar_one()
        consent = (await db.execute(select(MCPOAuthConsent))).scalar_one()
        grant_reference = (
            await db.execute(select(MCPOAuthProviderGrantReference))
        ).scalar_one()
    assert client.client_name == "VS Code"
    assert client.client_metadata == {"registration_source": "dcr"}
    assert consent.user_id == user_id
    assert consent.provider_mode == "oidc"
    assert (
        consent.provider_reference_hash
        == "e343ce8b4aa002fd7dd1abac7cd4e4099d8532aaabd55e815caf4d3da0316894"
    )
    assert consent.last_used_at is not None
    assert grant_reference.consent_id == consent.id
    assert grant_reference.provider_reference_hash == consent.provider_reference_hash
    assert grant_reference.last_used_at is not None
    assert "upstream-provider-secret" not in repr(client)
    assert "upstream-provider-secret" not in repr(consent)
    assert "upstream-provider-secret" not in repr(grant_reference)
    proxy._client_storage.put.assert_awaited_once()
    native_write = proxy._client_storage.put.await_args.kwargs
    assert native_write["collection"] == CONNECTED_CLIENT_REFERENCE_COLLECTION
    assert native_write["value"] == {
        "user_id": str(user_id),
        "client_id": "vscode-client",
        "jti": "reference-id",
        "upstream_token_id": "upstream-set-id",
    }
    assert native_write["ttl"] == 200_000_000


@pytest.mark.asyncio
async def test_connected_client_projection_is_idempotent_across_workers(
    session_maker,
) -> None:
    user = UserAccount(
        username="oidc.projection@example.com",
        email="oidc.projection@example.com",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        oidc_issuer="https://issuer.example",
        oidc_subject="provider-subject",
    )
    async with session_maker() as db:
        db.add(user)
        await db.commit()

    client_info = SimpleNamespace(
        client_name="VS Code",
        client_uri="https://code.visualstudio.com",
        logo_uri=None,
        redirect_uris=["http://127.0.0.1:4567/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        contacts=[],
        jwks_uri=None,
        cimd_document=None,
    )
    proxy = object.__new__(InterceptOIDCProxy)

    class _SelectBarrier:
        def __init__(self) -> None:
            self.arrivals = 0
            self.ready = asyncio.Event()

        async def wait(self) -> None:
            self.arrivals += 1
            if self.arrivals == 2:
                self.ready.set()
            await self.ready.wait()

    class _WorkerSession:
        def __init__(self, db, barrier: _SelectBarrier) -> None:
            self._db = db
            self._barrier = barrier
            self._synchronized = False

        async def execute(self, statement):
            result = await self._db.execute(statement)
            if isinstance(statement, Select) and not self._synchronized:
                self._synchronized = True
                await self._barrier.wait()
            return result

        def __getattr__(self, name):
            return getattr(self._db, name)

    barrier = _SelectBarrier()

    async def record_from_worker() -> None:
        async with session_maker() as db:
            await proxy._record_connected_client_projection(
                _WorkerSession(db, barrier),
                user_id=user.id,
                client_id="vscode-client",
                client_info=client_info,
                reference_hash="same-native-token-family",
                authorization_epoch=101,
            )
            await db.commit()

    await asyncio.wait_for(
        asyncio.gather(record_from_worker(), record_from_worker()),
        timeout=5,
    )

    async with session_maker() as db:
        assert await db.scalar(select(func.count()).select_from(MCPOAuthClient)) == 1
        assert await db.scalar(select(func.count()).select_from(MCPOAuthConsent)) == 1
        assert (
            await db.scalar(
                select(func.count()).select_from(MCPOAuthProviderGrantReference)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_revoke_projected_client_invalidates_native_token_family() -> None:
    user_id = uuid4()
    reference_hash = (
        "1b7e95116aff9dc9c89bcf5b02e1ed2d8596841a7cd7e14c5edb55c3259cd901"
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._client_storage = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "user_id": str(user_id),
                "client_id": "vscode-client",
                "jti": "reference-id",
                "upstream_token_id": "upstream-set-id",
            }
        ),
        delete=AsyncMock(return_value=True),
    )
    proxy._jti_mapping_store = SimpleNamespace(delete=AsyncMock(return_value=True))
    proxy._upstream_token_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                access_token="upstream-access-secret",
                refresh_token="upstream-refresh-secret",
                client_id="vscode-client",
                scope="openid email",
            )
        ),
        delete=AsyncMock(return_value=True),
    )
    proxy.revoke_token = AsyncMock()

    revoked = await proxy.revoke_projected_client(
        user_id=user_id,
        provider_reference_hash=reference_hash,
    )

    assert revoked is True
    assert [
        call.args[0].token for call in proxy.revoke_token.await_args_list
    ] == ["upstream-access-secret", "upstream-refresh-secret"]
    proxy._jti_mapping_store.delete.assert_awaited_once_with(key="reference-id")
    proxy._upstream_token_store.delete.assert_awaited_once_with(
        key="upstream-set-id"
    )
    proxy._client_storage.delete.assert_awaited_once_with(
        key=reference_hash,
        collection=CONNECTED_CLIENT_REFERENCE_COLLECTION,
    )


@pytest.mark.asyncio
async def test_revoke_projected_client_rejects_another_users_reference() -> None:
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._client_storage = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "user_id": str(uuid4()),
                "client_id": "vscode-client",
                "jti": "reference-id",
                "upstream_token_id": "upstream-set-id",
            }
        ),
        delete=AsyncMock(),
    )
    proxy._upstream_token_store = SimpleNamespace(delete=AsyncMock())
    proxy._jti_mapping_store = SimpleNamespace(delete=AsyncMock())

    revoked = await proxy.revoke_projected_client(
        user_id=uuid4(),
        provider_reference_hash="reference-hash",
    )

    assert revoked is False
    proxy._upstream_token_store.delete.assert_not_awaited()
    proxy._jti_mapping_store.delete.assert_not_awaited()
    proxy._client_storage.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_proxy_rejects_reference_when_local_user_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    session = _Session(SimpleNamespace(id=user_id, status=UserStatus.DISABLED))
    upstream_result = AccessToken(
        token="upstream-provider-secret",
        client_id="intercept-oidc-app",
        scopes=[],
        claims={
            "upstream_claims": {
                "intercept_user_id": str(user_id),
                "auth_source": "oidc",
                INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: 101,
            }
        },
    )
    monkeypatch.setattr(
        OIDCProxy,
        "load_access_token",
        AsyncMock(return_value=upstream_result),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token: {
            "client_id": "vscode-client",
            "jti": "reference-id",
            "upstream_claims": {
                "intercept_user_id": str(user_id),
                "auth_source": "oidc",
                INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: 101,
            },
        }
    )
    proxy._resource_url = "https://intercept.example/mcp/streamable/"
    proxy._intercept_session_factory = _session_factory(session)

    assert await proxy.load_access_token("fastmcp-reference-token") is None


@pytest.mark.asyncio
async def test_proxy_rejects_unmarked_legacy_access_token_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        status=UserStatus.ACTIVE,
        credentials_invalidated_at=None,
    )
    local_claims = {
        "intercept_user_id": str(user_id),
        "auth_source": "oidc",
        INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: 101,
        INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM: 100.0,
    }
    base_load = AsyncMock()
    monkeypatch.setattr(OIDCProxy, "load_access_token", base_load)
    proxy = object.__new__(InterceptOIDCProxy)
    _configure_marker_crypto(proxy)
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token: {
            "client_id": "vscode-client",
            "jti": "legacy-reference-id",
            "upstream_claims": local_claims,
        }
    )
    proxy._intercept_session_factory = _session_factory(_Session(user))
    proxy._jti_mapping_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(upstream_token_id="legacy-upstream")
        )
    )
    proxy._upstream_token_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                raw_token_data={"id_token": "legacy-id-token"}
            )
        )
    )

    assert await proxy.load_access_token("legacy-fastmcp-token") is None
    base_load.assert_not_awaited()


@pytest.mark.asyncio
async def test_proxy_rejects_pre_cutoff_reference_after_user_reenabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        status=UserStatus.ACTIVE,
        credentials_invalidated_at=datetime.fromtimestamp(200, tz=timezone.utc),
    )
    local_claims = {
        "intercept_user_id": str(user_id),
        "auth_source": "oidc",
        INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: 101,
        INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM: 100.0,
    }
    upstream_result = AccessToken(
        token="upstream-provider-secret",
        client_id="intercept-oidc-app",
        scopes=[],
        claims={"upstream_claims": local_claims},
    )
    base_load = AsyncMock(return_value=upstream_result)
    monkeypatch.setattr(OIDCProxy, "load_access_token", base_load)

    proxy = object.__new__(InterceptOIDCProxy)
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token: {
            "client_id": "vscode-client",
            "jti": "pre-disable-reference-id",
            "upstream_claims": local_claims,
        }
    )
    proxy._resource_url = "https://intercept.example/mcp/streamable/"
    proxy._intercept_session_factory = _session_factory(_Session(user))
    proxy._jti_mapping_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(upstream_token_id="upstream-set-id")
        )
    )
    proxy._upstream_token_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                expires_at=2_000_000_000,
                refresh_token_expires_at=2_100_000_000,
            )
        )
    )
    proxy._client_storage = SimpleNamespace(put=AsyncMock())
    proxy.get_client = AsyncMock(return_value=None)
    proxy._record_connected_client_projection = AsyncMock()

    assert await proxy.load_access_token("pre-disable-fastmcp-token") is None
    base_load.assert_not_awaited()
