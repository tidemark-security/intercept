from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
from mcp.server.auth.provider import AuthorizationParams, AuthorizeError, TokenError
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.mcp.local_oauth_provider import (
    InterceptOAuthProvider,
    PendingAuthorization,
    PendingAuthorizationUnavailableError,
    SQLAlchemyPendingAuthorizationStore,
    create_local_oauth_provider,
)
from app.services.mcp_oauth_service import mcp_oauth_service


FIXED_NOW = datetime(2026, 7, 19, 3, 0, tzinfo=timezone.utc)
FIXED_REQUEST_ID = UUID("16ad90ad-4cf0-4c56-b4e2-9f39c44ca001")
REDIRECT_URI = "http://127.0.0.1:49152/callback"
RESOURCE = "http://localhost:8080/mcp/streamable/"


@pytest.mark.asyncio
async def test_factory_freezes_token_and_origin_settings_from_startup_snapshot() -> None:
    provider = create_local_oauth_provider(
        snapshot=SimpleNamespace(
            public_origin="https://intercept.example",
            login_origin="https://login.intercept.example",
            access_token_ttl_seconds=1234,
            refresh_token_ttl_days=17,
        ),
        session_factory=object(),
    )

    settings = await provider._backend.service.get_enabled_settings(None)

    assert settings.public_base_url == "https://intercept.example"
    assert settings.login_base_url == "https://login.intercept.example"
    assert settings.access_token_ttl_seconds == 1234
    assert settings.refresh_token_ttl_days == 17


class RecordingPendingAuthorizations:
    def __init__(self) -> None:
        self.records: dict[UUID, PendingAuthorization] = {}

    async def create(self, pending: PendingAuthorization) -> None:
        self.records[pending.id] = pending

    async def get(self, request_id: UUID) -> PendingAuthorization | None:
        return self.records.get(request_id)

    async def consume(self, request_id: UUID) -> PendingAuthorization | None:
        return self.records.pop(request_id, None)


class UnusedBackend:
    pass


class RecordingBackend:
    def __init__(self) -> None:
        self.created_codes: list[tuple[PendingAuthorization, object]] = []

    async def create_authorization_code(
        self,
        pending: PendingAuthorization,
        user: object,
        *,
        context: object | None = None,
    ) -> str:
        self.created_codes.append((pending, user))
        return "native-authorization-code"


def _client() -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id="native-mcp-client-id",
        redirect_uris=[AnyUrl(REDIRECT_URI)],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp:access",
        client_name="VS Code",
        client_id_issued_at=1_753_000_000,
    )


@pytest.mark.asyncio
async def test_authorize_persists_pkce_request_before_redirecting_to_intercept() -> None:
    pending_store = RecordingPendingAuthorizations()
    provider = InterceptOAuthProvider(
        backend=UnusedBackend(),
        pending_authorizations=pending_store,
        public_base_url="http://localhost:8080",
        now=lambda: FIXED_NOW,
        request_id_factory=lambda: FIXED_REQUEST_ID,
    )

    redirect = await provider.authorize(
        _client(),
        AuthorizationParams(
            state="client-state",
            scopes=["mcp:access"],
            code_challenge="pkce-challenge",
            redirect_uri=AnyUrl(REDIRECT_URI),
            redirect_uri_provided_explicitly=True,
            resource=RESOURCE,
        ),
    )

    assert redirect == (
        "http://localhost:8080/api/v1/mcp/oauth/consent/"
        "16ad90ad-4cf0-4c56-b4e2-9f39c44ca001"
    )
    assert pending_store.records[FIXED_REQUEST_ID] == PendingAuthorization(
        id=FIXED_REQUEST_ID,
        client_id="native-mcp-client-id",
        state="client-state",
        scopes=["mcp:access"],
        code_challenge="pkce-challenge",
        redirect_uri=REDIRECT_URI,
        redirect_uri_provided_explicitly=True,
        resource=RESOURCE,
        created_at=FIXED_NOW,
        expires_at=datetime(2026, 7, 19, 3, 5, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_authorize_defaults_missing_resource_to_canonical_streamable_url() -> None:
    pending_store = RecordingPendingAuthorizations()
    provider = InterceptOAuthProvider(
        backend=UnusedBackend(),
        pending_authorizations=pending_store,
        public_base_url="http://localhost:8080",
        now=lambda: FIXED_NOW,
        request_id_factory=lambda: FIXED_REQUEST_ID,
    )

    await provider.authorize(
        _client(),
        AuthorizationParams(
            state="client-state",
            scopes=["mcp:access"],
            code_challenge="pkce-challenge",
            redirect_uri=AnyUrl(REDIRECT_URI),
            redirect_uri_provided_explicitly=True,
            resource=None,
        ),
    )

    assert pending_store.records[FIXED_REQUEST_ID].resource == RESOURCE


@pytest.mark.asyncio
async def test_authorize_rejects_noncanonical_resource_before_persisting() -> None:
    pending_store = RecordingPendingAuthorizations()
    provider = InterceptOAuthProvider(
        backend=UnusedBackend(),
        pending_authorizations=pending_store,
        public_base_url="http://localhost:8080",
        now=lambda: FIXED_NOW,
        request_id_factory=lambda: FIXED_REQUEST_ID,
    )

    with pytest.raises(AuthorizeError) as raised:
        await provider.authorize(
            _client(),
            AuthorizationParams(
                state="client-state",
                scopes=["mcp:access"],
                code_challenge="pkce-challenge",
                redirect_uri=AnyUrl(REDIRECT_URI),
                redirect_uri_provided_explicitly=True,
                resource="https://attacker.example/mcp/streamable/",
            ),
        )

    assert raised.value.error == "invalid_request"
    assert pending_store.records == {}


@pytest.mark.asyncio
async def test_approved_consent_consumes_request_and_returns_client_callback() -> None:
    pending_store = RecordingPendingAuthorizations()
    backend = RecordingBackend()
    provider = InterceptOAuthProvider(
        backend=backend,
        pending_authorizations=pending_store,
        public_base_url="http://localhost:8080",
        now=lambda: FIXED_NOW,
        request_id_factory=lambda: FIXED_REQUEST_ID,
    )
    user = object()
    await provider.authorize(
        _client(),
        AuthorizationParams(
            state="client-state",
            scopes=["mcp:access"],
            code_challenge="pkce-challenge",
            redirect_uri=AnyUrl(REDIRECT_URI),
            redirect_uri_provided_explicitly=True,
            resource=RESOURCE,
        ),
    )

    redirect = await provider.complete_authorization(
        FIXED_REQUEST_ID,
        user=user,
        approved=True,
    )

    assert redirect == (
        "http://127.0.0.1:49152/callback?"
        "code=native-authorization-code&state=client-state"
    )
    assert len(backend.created_codes) == 1
    created_pending, created_for_user = backend.created_codes[0]
    assert created_pending.id == FIXED_REQUEST_ID
    assert created_for_user is user
    assert await pending_store.get(FIXED_REQUEST_ID) is None
    with pytest.raises(PendingAuthorizationUnavailableError):
        await provider.complete_authorization(
            FIXED_REQUEST_ID,
            user=user,
            approved=True,
        )


@pytest.mark.asyncio
async def test_registered_native_client_id_is_retrievable(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("MCP_OAUTH_PUBLIC_BASE_URL", "http://localhost:8080")
    provider = InterceptOAuthProvider(
        session_factory=session_maker,
        pending_authorizations=RecordingPendingAuthorizations(),
        public_base_url="http://localhost:8080",
    )
    client = _client()

    await provider.register_client(client)
    loaded = await provider.get_client("native-mcp-client-id")

    assert loaded == client


@pytest.mark.asyncio
async def test_authorization_code_exchange_returns_native_identity_claims(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("MCP_OAUTH_PUBLIC_BASE_URL", "http://localhost:8080")
    pending_store = RecordingPendingAuthorizations()
    provider = InterceptOAuthProvider(
        session_factory=session_maker,
        pending_authorizations=pending_store,
        public_base_url="http://localhost:8080",
    )
    client = _client()
    user = analyst_user_factory()
    async with session_maker() as session:
        session.add(user)
        await session.commit()
    await provider.register_client(client)
    await provider.authorize(
        client,
        AuthorizationParams(
            state="client-state",
            scopes=["mcp:access"],
            code_challenge="pkce-challenge",
            redirect_uri=AnyUrl(REDIRECT_URI),
            redirect_uri_provided_explicitly=True,
            resource=RESOURCE,
        ),
    )
    request_id = next(iter(pending_store.records))

    callback = await provider.complete_authorization(
        request_id,
        user=user,
        approved=True,
    )
    raw_code = parse_qs(urlparse(callback).query)["code"][0]
    authorization_code = await provider.load_authorization_code(client, raw_code)
    assert authorization_code is not None

    token_pair = await provider.exchange_authorization_code(client, authorization_code)
    access_token = await provider.verify_token(token_pair.access_token)

    assert access_token is not None
    assert access_token.client_id == "native-mcp-client-id"
    assert access_token.scopes == ["mcp:access"]
    assert access_token.resource == RESOURCE
    assert access_token.claims == {
        "intercept_user_id": str(user.id),
        "auth_source": "oauth",
        "client_id": "native-mcp-client-id",
    }


@pytest.mark.asyncio
async def test_refresh_exchange_rotates_once_under_concurrency(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("MCP_OAUTH_PUBLIC_BASE_URL", "http://localhost:8080")
    pending_store = RecordingPendingAuthorizations()
    provider = InterceptOAuthProvider(
        session_factory=session_maker,
        pending_authorizations=pending_store,
        public_base_url="http://localhost:8080",
    )
    client = _client()
    user = analyst_user_factory()
    async with session_maker() as session:
        session.add(user)
        await session.commit()
    await provider.register_client(client)
    await provider.authorize(
        client,
        AuthorizationParams(
            state=None,
            scopes=["mcp:access"],
            code_challenge="pkce-challenge",
            redirect_uri=AnyUrl(REDIRECT_URI),
            redirect_uri_provided_explicitly=True,
            resource=RESOURCE,
        ),
    )
    request_id = next(iter(pending_store.records))
    callback = await provider.complete_authorization(
        request_id, user=user, approved=True
    )
    raw_code = parse_qs(urlparse(callback).query)["code"][0]
    authorization_code = await provider.load_authorization_code(client, raw_code)
    assert authorization_code is not None
    original = await provider.exchange_authorization_code(client, authorization_code)
    assert original.refresh_token is not None

    loaded_refresh = await provider.load_refresh_token(
        client, original.refresh_token
    )
    assert loaded_refresh is not None
    outcomes = await asyncio.gather(
        provider.exchange_refresh_token(client, loaded_refresh, ["mcp:access"]),
        provider.exchange_refresh_token(client, loaded_refresh, ["mcp:access"]),
        return_exceptions=True,
    )
    successful = [outcome for outcome in outcomes if isinstance(outcome, OAuthToken)]
    rejected = [outcome for outcome in outcomes if isinstance(outcome, TokenError)]

    assert len(successful) == 1
    assert len(rejected) == 1, outcomes
    rotated = successful[0]

    assert rotated.access_token != original.access_token
    assert rotated.refresh_token is not None
    assert rotated.refresh_token != original.refresh_token
    assert await provider.load_refresh_token(client, original.refresh_token) is None
    rotated_access = await provider.load_access_token(rotated.access_token)
    assert rotated_access is None
    assert await provider.load_refresh_token(client, rotated.refresh_token) is None


@pytest.mark.asyncio
async def test_revoking_rotated_refresh_token_revokes_descendant_family(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("MCP_OAUTH_PUBLIC_BASE_URL", "http://localhost:8080")
    pending_store = RecordingPendingAuthorizations()
    provider = InterceptOAuthProvider(
        session_factory=session_maker,
        pending_authorizations=pending_store,
        public_base_url="http://localhost:8080",
    )
    client = _client()
    user = analyst_user_factory()
    async with session_maker() as session:
        session.add(user)
        await session.commit()
    await provider.register_client(client)
    await provider.authorize(
        client,
        AuthorizationParams(
            state=None,
            scopes=["mcp:access"],
            code_challenge="pkce-challenge",
            redirect_uri=AnyUrl(REDIRECT_URI),
            redirect_uri_provided_explicitly=True,
            resource=RESOURCE,
        ),
    )
    request_id = next(iter(pending_store.records))
    callback = await provider.complete_authorization(
        request_id, user=user, approved=True
    )
    raw_code = parse_qs(urlparse(callback).query)["code"][0]
    authorization_code = await provider.load_authorization_code(client, raw_code)
    assert authorization_code is not None
    original = await provider.exchange_authorization_code(client, authorization_code)
    assert original.refresh_token is not None
    original_refresh = await provider.load_refresh_token(
        client, original.refresh_token
    )
    assert original_refresh is not None

    rotated = await provider.exchange_refresh_token(
        client, original_refresh, ["mcp:access"]
    )
    assert rotated.refresh_token is not None
    assert await provider.load_access_token(rotated.access_token) is not None
    assert await provider.load_refresh_token(client, rotated.refresh_token) is not None

    async with session_maker() as session:
        await mcp_oauth_service.revoke_token(
            session,
            token=original.refresh_token,
            client_id=client.client_id,
        )
        await session.commit()

    assert await provider.load_access_token(rotated.access_token) is None
    assert await provider.load_refresh_token(client, rotated.refresh_token) is None


@pytest.mark.asyncio
async def test_revoking_access_token_revokes_ancestors_and_descendants(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("MCP_OAUTH_PUBLIC_BASE_URL", "http://localhost:8080")
    pending_store = RecordingPendingAuthorizations()
    provider = InterceptOAuthProvider(
        session_factory=session_maker,
        pending_authorizations=pending_store,
        public_base_url="http://localhost:8080",
    )
    client = _client()
    user = analyst_user_factory()
    async with session_maker() as session:
        session.add(user)
        await session.commit()
    await provider.register_client(client)
    await provider.authorize(
        client,
        AuthorizationParams(
            state=None,
            scopes=["mcp:access"],
            code_challenge="pkce-challenge",
            redirect_uri=AnyUrl(REDIRECT_URI),
            redirect_uri_provided_explicitly=True,
            resource=RESOURCE,
        ),
    )
    request_id = next(iter(pending_store.records))
    callback = await provider.complete_authorization(
        request_id, user=user, approved=True
    )
    raw_code = parse_qs(urlparse(callback).query)["code"][0]
    authorization_code = await provider.load_authorization_code(client, raw_code)
    assert authorization_code is not None
    original = await provider.exchange_authorization_code(client, authorization_code)
    assert original.refresh_token is not None
    original_refresh = await provider.load_refresh_token(
        client, original.refresh_token
    )
    assert original_refresh is not None
    first_rotation = await provider.exchange_refresh_token(
        client, original_refresh, ["mcp:access"]
    )
    assert first_rotation.refresh_token is not None
    first_rotated_refresh = await provider.load_refresh_token(
        client, first_rotation.refresh_token
    )
    assert first_rotated_refresh is not None
    second_rotation = await provider.exchange_refresh_token(
        client, first_rotated_refresh, ["mcp:access"]
    )
    assert second_rotation.refresh_token is not None

    async with session_maker() as session:
        await mcp_oauth_service.revoke_token(
            session,
            token=first_rotation.access_token,
            client_id=client.client_id,
        )
        await session.commit()

    assert await provider.load_access_token(original.access_token) is None
    assert await provider.load_access_token(first_rotation.access_token) is None
    assert await provider.load_access_token(second_rotation.access_token) is None
    assert (
        await provider.load_refresh_token(client, second_rotation.refresh_token)
        is None
    )
    assert (
        await provider.load_refresh_token(client, first_rotation.refresh_token)
        is None
    )
    assert await provider.load_refresh_token(client, original.refresh_token) is None


@pytest.mark.asyncio
async def test_pending_authorization_is_durable_and_one_use(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("MCP_OAUTH_PUBLIC_BASE_URL", "http://localhost:8080")
    first_store = SQLAlchemyPendingAuthorizationStore(
        session_factory=session_maker,
        now=lambda: FIXED_NOW,
    )
    provider = InterceptOAuthProvider(
        session_factory=session_maker,
        pending_authorizations=first_store,
        public_base_url="http://localhost:8080",
        now=lambda: FIXED_NOW,
        request_id_factory=lambda: FIXED_REQUEST_ID,
    )
    client = _client()
    await provider.register_client(client)
    await provider.authorize(
        client,
        AuthorizationParams(
            state="durable-state",
            scopes=["mcp:access"],
            code_challenge="durable-challenge",
            redirect_uri=AnyUrl(REDIRECT_URI),
            redirect_uri_provided_explicitly=True,
            resource=RESOURCE,
        ),
    )
    second_store = SQLAlchemyPendingAuthorizationStore(
        session_factory=session_maker,
        now=lambda: FIXED_NOW,
    )

    loaded = await second_store.get(FIXED_REQUEST_ID)
    consumed = await second_store.consume(FIXED_REQUEST_ID)

    assert loaded is not None
    assert loaded.state == "durable-state"
    assert consumed == loaded
    assert await first_store.get(FIXED_REQUEST_ID) is None
    assert await first_store.consume(FIXED_REQUEST_ID) is None
