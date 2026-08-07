"""Native CIMD contract tests for Intercept's local OAuth provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastmcp.server.auth.cimd import CIMDClientManager, CIMDDocument
from fastmcp.server.auth.oauth_proxy.models import ProxyDCRClient
from pydantic import AnyUrl
from mcp.server.auth.provider import AuthorizationParams, AuthorizeError
from mcp.shared.auth import OAuthClientInformationFull
from sqlalchemy import select
from starlette.applications import Starlette

from app.mcp.local_oauth_provider import InterceptOAuthProvider, PendingAuthorization
from app.models.models import MCPOAuthClient
from app.services.mcp_registration_service import (
    MCPAuthorizationCapacityLimitError,
    MCPRegistrationPolicy,
    bind_authorization_request,
    reset_authorization_request,
)


CIMD_CLIENT_ID = "https://mcp-client.example/.well-known/oauth-client.json"
LOOPBACK_REDIRECT = "http://127.0.0.1:49152/callback"
JWT_BEARER_ASSERTION_TYPE = (
    "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
)


class UnusedPendingAuthorizations:
    pass


class UnexpectedDCRLedger:
    async def require_valid(self, client_id: str) -> bool:
        raise AssertionError(f"CIMD client consulted DCR ledger: {client_id}")

    async def activate(self, client_id: str) -> bool:
        raise AssertionError(f"CIMD client activated DCR lease: {client_id}")


@dataclass
class RecordingPendingAuthorizations:
    created: list[PendingAuthorization] = field(default_factory=list)

    async def create(self, pending: PendingAuthorization) -> None:
        self.created.append(pending)


@dataclass
class RecordingBackend:
    stored_client: OAuthClientInformationFull | None = None
    get_client_ids: list[str] = field(default_factory=list)
    registered_clients: list[OAuthClientInformationFull] = field(
        default_factory=list
    )

    async def get_client(
        self, client_id: str
    ) -> OAuthClientInformationFull | None:
        self.get_client_ids.append(client_id)
        return self.stored_client

    async def register_client(self, client: OAuthClientInformationFull) -> None:
        self.registered_clients.append(client)

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> None:
        return None

    async def load_access_token(self, token: str) -> None:
        return None

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> None:
        return None


@dataclass
class StubCIMDManager:
    client: ProxyDCRClient | None
    resolved_client_ids: list[str] = field(default_factory=list)
    validated_assertions: list[tuple[str, str, str]] = field(default_factory=list)

    def is_cimd_client_id(self, client_id: str) -> bool:
        return client_id.startswith("https://")

    async def get_client(self, client_id: str) -> ProxyDCRClient | None:
        self.resolved_client_ids.append(client_id)
        return self.client

    async def validate_private_key_jwt(
        self,
        assertion: str,
        client: ProxyDCRClient,
        token_endpoint: str,
    ) -> bool:
        self.validated_assertions.append(
            (assertion, str(client.client_id), token_endpoint)
        )
        return True


def _cimd_client(
    *,
    token_endpoint_auth_method: str = "none",
    redirect_uris: list[str] | None = None,
) -> ProxyDCRClient:
    document = CIMDDocument(
        client_id=CIMD_CLIENT_ID,
        client_name="Native CIMD Client",
        redirect_uris=redirect_uris or [LOOPBACK_REDIRECT],
        token_endpoint_auth_method=token_endpoint_auth_method,
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp:access",
        jwks={"keys": [{"kty": "OKP", "crv": "Ed25519", "x": "test"}]}
        if token_endpoint_auth_method == "private_key_jwt"
        else None,
    )
    return ProxyDCRClient(
        client_id=CIMD_CLIENT_ID,
        redirect_uris=None,
        token_endpoint_auth_method=document.token_endpoint_auth_method,
        grant_types=document.grant_types,
        response_types=document.response_types,
        scope=document.scope,
        client_name=document.client_name,
        cimd_document=document,
    )


@pytest.mark.asyncio
async def test_https_client_id_uses_native_cimd_before_relational_lookup() -> None:
    """A CIMD URL is validated before any relational grant projection."""
    backend = RecordingBackend()
    cimd_manager = StubCIMDManager(_cimd_client())
    provider = InterceptOAuthProvider(
        backend=backend,
        pending_authorizations=UnusedPendingAuthorizations(),
        public_base_url="http://localhost:8080",
        cimd_manager=cimd_manager,
    )

    resolved = await provider.get_client(CIMD_CLIENT_ID)

    assert resolved is cimd_manager.client
    assert cimd_manager.resolved_client_ids == [CIMD_CLIENT_ID]
    assert backend.get_client_ids == []
    assert backend.registered_clients == []


@pytest.mark.asyncio
async def test_non_url_client_id_preserves_dynamic_registration_lookup() -> None:
    registered = OAuthClientInformationFull(
        client_id="registered-public-client",
        redirect_uris=[LOOPBACK_REDIRECT],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp:access",
    )
    backend = RecordingBackend(stored_client=registered)
    cimd_manager = StubCIMDManager(None)
    provider = InterceptOAuthProvider(
        backend=backend,
        pending_authorizations=UnusedPendingAuthorizations(),
        public_base_url="http://localhost:8080",
        cimd_manager=cimd_manager,
    )

    resolved = await provider.get_client("registered-public-client")

    assert resolved is registered
    assert backend.get_client_ids == ["registered-public-client"]
    assert cimd_manager.resolved_client_ids == []


@pytest.mark.asyncio
async def test_private_key_cimd_client_is_projected_without_downgrade() -> None:
    """Lookup retains asymmetric metadata without persisting a projection."""
    backend = RecordingBackend()
    native_client = _cimd_client(token_endpoint_auth_method="private_key_jwt")
    provider = InterceptOAuthProvider(
        backend=backend,
        pending_authorizations=UnusedPendingAuthorizations(),
        public_base_url="http://localhost:8080",
        cimd_manager=StubCIMDManager(native_client),
    )

    resolved = await provider.get_client(CIMD_CLIENT_ID)

    assert resolved is native_client
    assert backend.registered_clients == []


@pytest.mark.asyncio
async def test_private_key_cimd_lookup_defers_relational_projection(
    session_maker,
) -> None:
    """The relational grant projection retains metadata needed for reconnects."""
    native_client = _cimd_client(token_endpoint_auth_method="private_key_jwt")
    provider = InterceptOAuthProvider(
        session_factory=session_maker,
        public_base_url="http://localhost:8080",
        cimd_manager=StubCIMDManager(native_client),
    )

    assert await provider.get_client(CIMD_CLIENT_ID) is native_client

    async with session_maker() as session:
        stored = (
            await session.execute(
                select(MCPOAuthClient).where(
                    MCPOAuthClient.client_id == CIMD_CLIENT_ID
                )
            )
        ).scalar_one_or_none()
    assert stored is None


@pytest.mark.asyncio
async def test_private_key_cimd_exact_redirect_reaches_local_consent() -> None:
    pending_authorizations = RecordingPendingAuthorizations()
    backend = RecordingBackend()
    native_client = _cimd_client(token_endpoint_auth_method="private_key_jwt")
    provider = InterceptOAuthProvider(
        backend=backend,
        pending_authorizations=pending_authorizations,
        public_base_url="http://localhost:8080",
        cimd_manager=StubCIMDManager(native_client),
        registration_service=UnexpectedDCRLedger(),
    )
    oauth_app = Starlette(routes=provider.get_routes("/streamable/"))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=oauth_app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as oauth_client:
        response = await oauth_client.get(
            "/authorize",
            params={
                "client_id": CIMD_CLIENT_ID,
                "redirect_uri": LOOPBACK_REDIRECT,
                "response_type": "code",
                "code_challenge": "a" * 43,
                "code_challenge_method": "S256",
                "scope": "mcp:access",
            },
        )

    assert response.status_code == 302
    assert response.headers["location"].startswith(
        "http://localhost:8080/api/v1/mcp/oauth/consent/"
    )
    assert len(pending_authorizations.created) == 1
    assert pending_authorizations.created[0].redirect_uri == LOOPBACK_REDIRECT
    assert (
        pending_authorizations.created[0].resource
        == "http://localhost:8080/mcp/streamable/"
    )
    assert len(backend.registered_clients) == 1
    projection = backend.registered_clients[0]
    assert projection.token_endpoint_auth_method == "private_key_jwt"
    assert projection.jwks == native_client.cimd_document.jwks


@pytest.mark.asyncio
async def test_cimd_fetch_is_rejected_before_network_when_capacity_is_full() -> None:
    class FullCapacity:
        async def reserve(self, **_kwargs: Any) -> None:
            raise MCPAuthorizationCapacityLimitError("full")

    manager = StubCIMDManager(_cimd_client())
    provider = InterceptOAuthProvider(
        backend=RecordingBackend(),
        pending_authorizations=UnusedPendingAuthorizations(),
        public_base_url="http://localhost:8080",
        cimd_manager=manager,
        registration_policy=MCPRegistrationPolicy(),
        authorization_capacity_service=FullCapacity(),  # type: ignore[arg-type]
    )
    token = bind_authorization_request()
    try:
        resolved = await provider.get_client(CIMD_CLIENT_ID)
    finally:
        reset_authorization_request(token)

    assert resolved is None
    assert manager.resolved_client_ids == []


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ("success", "none", "error"))
async def test_non_authorization_cimd_fetch_releases_transient_capacity(
    outcome: str,
) -> None:
    class OutcomeManager(StubCIMDManager):
        async def get_client(self, client_id: str) -> ProxyDCRClient | None:
            self.resolved_client_ids.append(client_id)
            if outcome == "error":
                raise RuntimeError("fetch failed")
            if outcome == "none":
                return None
            return self.client

    class RecordingCapacity:
        def __init__(self) -> None:
            self.reservations: list[dict[str, Any]] = []
            self.releases: list[str] = []

        async def reserve(self, **kwargs: Any) -> None:
            self.reservations.append(kwargs)

        async def release(self, reservation_id: str) -> None:
            self.releases.append(reservation_id)

    capacity = RecordingCapacity()
    provider = InterceptOAuthProvider(
        backend=RecordingBackend(),
        pending_authorizations=UnusedPendingAuthorizations(),
        public_base_url="http://localhost:8080",
        cimd_manager=OutcomeManager(_cimd_client()),
        registration_policy=MCPRegistrationPolicy(),
        authorization_capacity_service=capacity,  # type: ignore[arg-type]
    )

    if outcome == "error":
        with pytest.raises(RuntimeError, match="fetch failed"):
            await provider.get_client(CIMD_CLIENT_ID)
    else:
        resolved = await provider.get_client(CIMD_CLIENT_ID)
        assert (resolved is not None) is (outcome == "success")

    assert len(capacity.reservations) == 1
    assert capacity.releases == [
        capacity.reservations[0]["reservation_id"]
    ]


@pytest.mark.asyncio
async def test_repeated_cimd_lookup_preserves_prefetch_reservation_for_authorize() -> None:
    class CachingCIMDManager(StubCIMDManager):
        def __init__(self, client: ProxyDCRClient) -> None:
            super().__init__(client)
            self._fetcher = SimpleNamespace(_cache={})

        async def get_client(self, client_id: str) -> ProxyDCRClient | None:
            resolved = await super().get_client(client_id)
            self._fetcher._cache[client_id] = SimpleNamespace(
                must_revalidate=False,
                expires_at=datetime.now(timezone.utc).timestamp() + 60,
            )
            return resolved

    class RecordingCapacity:
        def __init__(self) -> None:
            self.reservations: list[dict[str, Any]] = []
            self.promotions: list[dict[str, Any]] = []
            self.releases: list[str] = []

        async def reserve(self, **kwargs: Any) -> None:
            self.reservations.append(kwargs)

        async def promote(self, **kwargs: Any) -> None:
            self.promotions.append(kwargs)

        async def release(self, reservation_id: str) -> None:
            self.releases.append(reservation_id)

    request_id = UUID("16ad90ad-4cf0-4c56-b4e2-9f39c44ca099")
    capacity = RecordingCapacity()
    pending = RecordingPendingAuthorizations()
    provider = InterceptOAuthProvider(
        backend=RecordingBackend(),
        pending_authorizations=pending,
        public_base_url="http://localhost:8080",
        cimd_manager=CachingCIMDManager(_cimd_client()),
        registration_policy=MCPRegistrationPolicy(),
        authorization_capacity_service=capacity,  # type: ignore[arg-type]
        request_id_factory=lambda: request_id,
    )
    token = bind_authorization_request()
    try:
        first = await provider.get_client(CIMD_CLIENT_ID)
        second = await provider.get_client(CIMD_CLIENT_ID)
        assert first is not None
        assert second is first
        assert capacity.releases == []
        await provider.authorize(
            second,
            AuthorizationParams(
                state="state",
                scopes=["mcp:access"],
                code_challenge="a" * 43,
                redirect_uri=AnyUrl(LOOPBACK_REDIRECT),
                redirect_uri_provided_explicitly=True,
                resource="http://localhost:8080/mcp/streamable/",
            ),
        )
    finally:
        reset_authorization_request(token)

    assert len(capacity.reservations) == 1
    assert capacity.releases == []
    assert capacity.promotions == [
        {
            "reservation_id": capacity.reservations[0]["reservation_id"],
            "pending_id": str(request_id),
            "client_id": CIMD_CLIENT_ID,
            "ttl_seconds": 300,
        }
    ]


@pytest.mark.asyncio
async def test_cimd_authorize_releases_prefetch_when_promotion_fails() -> None:
    class RecordingCapacity:
        def __init__(self) -> None:
            self.reservations: list[dict[str, Any]] = []
            self.releases: list[str] = []

        async def reserve(self, **kwargs: Any) -> None:
            self.reservations.append(kwargs)

        async def promote(self, **_kwargs: Any) -> None:
            raise MCPAuthorizationCapacityLimitError("reservation expired")

        async def release(self, reservation_id: str) -> None:
            self.releases.append(reservation_id)

    capacity = RecordingCapacity()
    provider = InterceptOAuthProvider(
        backend=RecordingBackend(),
        pending_authorizations=RecordingPendingAuthorizations(),
        public_base_url="http://localhost:8080",
        cimd_manager=StubCIMDManager(_cimd_client()),
        registration_policy=MCPRegistrationPolicy(),
        authorization_capacity_service=capacity,  # type: ignore[arg-type]
    )
    token = bind_authorization_request()
    try:
        client = await provider.get_client(CIMD_CLIENT_ID)
        assert client is not None
        assert capacity.releases == []
        with pytest.raises(AuthorizeError, match="reservation expired"):
            await provider.authorize(
                client,
                AuthorizationParams(
                    state="state",
                    scopes=["mcp:access"],
                    code_challenge="a" * 43,
                    redirect_uri=AnyUrl(LOOPBACK_REDIRECT),
                    redirect_uri_provided_explicitly=True,
                    resource="http://localhost:8080/mcp/streamable/",
                ),
            )
    finally:
        reset_authorization_request(token)

    assert len(capacity.reservations) == 1
    assert capacity.releases == [
        capacity.reservations[0]["reservation_id"]
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cimd_client", "reason"),
    [
        (
            _cimd_client(redirect_uris=["http://127.0.0.1:*/callback"]),
            "wildcard",
        ),
    ],
)
async def test_unsupported_cimd_forms_fail_closed_before_persistence(
    cimd_client: ProxyDCRClient,
    reason: str,
) -> None:
    """Relational local grants reject redirects they cannot bind exactly."""
    backend = RecordingBackend()
    provider = InterceptOAuthProvider(
        backend=backend,
        pending_authorizations=UnusedPendingAuthorizations(),
        public_base_url="http://localhost:8080",
        cimd_manager=StubCIMDManager(cimd_client),
    )

    assert await provider.get_client(CIMD_CLIENT_ID) is None, reason
    assert backend.registered_clients == []
    assert backend.get_client_ids == []


@pytest.mark.asyncio
async def test_metadata_advertises_native_cimd_authentication_contract() -> None:
    provider = InterceptOAuthProvider(
        backend=RecordingBackend(),
        pending_authorizations=UnusedPendingAuthorizations(),
        public_base_url="http://localhost:8080",
        cimd_manager=StubCIMDManager(None),
    )
    discovery = Starlette(
        routes=provider.get_well_known_routes("/streamable/")
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=discovery),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/.well-known/oauth-authorization-server/mcp"
        )

    assert response.status_code == 200
    metadata: dict[str, Any] = response.json()
    assert metadata["client_id_metadata_document_supported"] is True
    assert metadata["token_endpoint_auth_methods_supported"] == [
        "none",
        "private_key_jwt",
    ]
    assert metadata["revocation_endpoint_auth_methods_supported"] == [
        "none",
        "private_key_jwt",
    ]
    assert metadata["code_challenge_methods_supported"] == ["S256"]


@pytest.mark.asyncio
async def test_native_token_and_revocation_handlers_accept_public_clients() -> None:
    registered = OAuthClientInformationFull(
        client_id="registered-public-client",
        redirect_uris=[LOOPBACK_REDIRECT],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp:access",
    )
    provider = InterceptOAuthProvider(
        backend=RecordingBackend(stored_client=registered),
        pending_authorizations=UnusedPendingAuthorizations(),
        public_base_url="http://localhost:8080",
        cimd_manager=StubCIMDManager(None),
    )
    oauth_app = Starlette(routes=provider.get_routes("/streamable/"))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=oauth_app),
        base_url="http://testserver",
    ) as oauth_client:
        token_response = await oauth_client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": "unknown-code",
                "redirect_uri": LOOPBACK_REDIRECT,
                "client_id": "registered-public-client",
                "code_verifier": "a" * 43,
            },
        )
        revoke_response = await oauth_client.post(
            "/revoke",
            data={
                "token": "unknown-token",
                "client_id": "registered-public-client",
                "client_secret": "",
            },
        )

    # Reaching invalid_grant proves the public client passed native client auth.
    assert token_response.status_code == 401
    assert token_response.json()["error"] == "invalid_grant"
    assert revoke_response.status_code == 200


@pytest.mark.asyncio
async def test_native_token_and_revocation_handlers_authenticate_private_key_cimd() -> None:
    """Both native endpoints delegate CIMD assertions to FastMCP's manager."""
    cimd_manager = StubCIMDManager(
        _cimd_client(token_endpoint_auth_method="private_key_jwt")
    )
    provider = InterceptOAuthProvider(
        backend=RecordingBackend(),
        pending_authorizations=UnusedPendingAuthorizations(),
        public_base_url="http://localhost:8080",
        cimd_manager=cimd_manager,
    )
    oauth_app = Starlette(routes=provider.get_routes("/streamable/"))
    client_authentication = {
        "client_id": CIMD_CLIENT_ID,
        "client_assertion_type": JWT_BEARER_ASSERTION_TYPE,
        "client_assertion": "signed-client-assertion",
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=oauth_app),
        base_url="http://testserver",
    ) as oauth_client:
        token_response = await oauth_client.post(
            "/token",
            data={
                **client_authentication,
                "grant_type": "authorization_code",
                "code": "unknown-code",
                "redirect_uri": LOOPBACK_REDIRECT,
                "code_verifier": "a" * 43,
            },
        )
        revoke_response = await oauth_client.post(
            "/revoke",
            data={
                **client_authentication,
                "token": "unknown-token",
                # MCP SDK 1.24's native revocation request model requires the
                # nullable field to be present for every client auth method.
                "client_secret": "",
            },
        )

    assert token_response.status_code == 401
    assert token_response.json()["error"] == "invalid_grant"
    assert revoke_response.status_code == 200
    assert cimd_manager.validated_assertions == [
        (
            "signed-client-assertion",
            CIMD_CLIENT_ID,
            "http://localhost:8080/mcp/token",
        ),
        (
            "signed-client-assertion",
            CIMD_CLIENT_ID,
            "http://localhost:8080/mcp/token",
        ),
    ]


def test_native_cimd_manager_is_enabled_by_default() -> None:
    provider = InterceptOAuthProvider(
        backend=RecordingBackend(),
        pending_authorizations=UnusedPendingAuthorizations(),
        public_base_url="http://localhost:8080",
    )

    assert isinstance(provider._cimd_manager, CIMDClientManager)
    assert provider._cimd_manager.enabled is True
