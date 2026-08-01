"""Integration tests for FastMCP-native local OAuth 2.1 + PKCE."""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import api_app, app, compose_http_app
from app.mcp.local_oauth_provider import create_local_oauth_provider
from app.mcp.runtime import (
    MCPAuthMode,
    MCPAuthSnapshot,
    build_mcp_runtime,
)
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


PUBLIC_BASE_URL = "http://localhost:8000"
LOGIN_BASE_URL = "http://localhost:5173"
REDIRECT_URI = "http://127.0.0.1:49152/callback"
RESOURCE = f"{PUBLIC_BASE_URL}/mcp/streamable/"
CODE_VERIFIER = "a" * 64


def _code_challenge(verifier: str = CODE_VERIFIER) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


@pytest_asyncio.fixture
async def local_oauth_client(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MCP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("MCP_OAUTH_PUBLIC_BASE_URL", PUBLIC_BASE_URL)
    monkeypatch.setenv("MCP_OAUTH_LOGIN_BASE_URL", LOGIN_BASE_URL)
    monkeypatch.setenv("MCP_OAUTH_REFRESH_TOKEN_TTL_DAYS", "7")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")

    previous_http_app = app._http_app
    previous_runtime = app.runtime
    runtime = await build_mcp_runtime(
        snapshot=MCPAuthSnapshot(
            mode=MCPAuthMode.LOCAL_OAUTH,
            oauth_enabled=True,
            public_origin=PUBLIC_BASE_URL,
            login_origin=LOGIN_BASE_URL,
            access_token_ttl_seconds=3600,
            refresh_token_ttl_days=7,
            oidc=None,
        ),
        database_url="postgresql://unused-in-local-mode",
        secret_key="test-fastmcp-local-oauth-secret",
        session_factory=session_maker,
        local_provider_factory=(
            lambda snapshot, token_hash_key: create_local_oauth_provider(
                snapshot=snapshot,
                session_factory=session_maker,
                token_hash_key=token_hash_key,
            )
        ),
    )
    app.install(compose_http_app(api_app, runtime), runtime)
    api_app.state.mcp_runtime = runtime
    try:
        yield client, runtime
    finally:
        app.install(previous_http_app, previous_runtime)
        api_app.state.mcp_runtime = previous_runtime


async def _register_client(client: AsyncClient) -> str:
    response = await client.post(
        "/mcp/register",
        json={
            "client_name": "Codex Test Client",
            "client_uri": "https://codex.example.test",
            "redirect_uris": [REDIRECT_URI],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "mcp:access",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["client_id"]


async def _login(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
):
    user = analyst_user_factory(
        username="mcp_oauth_user",
        email="mcp_oauth_user@example.test",
    )
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return user


def _authorize_params(client_id: str) -> dict[str, str]:
    return {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "code_challenge": _code_challenge(),
        "code_challenge_method": "S256",
        "scope": "mcp:access",
        "resource": RESOURCE,
        "state": "state-123",
    }


async def _begin_authorization(client: AsyncClient, client_id: str) -> str:
    response = await client.get(
        "/mcp/authorize",
        params=_authorize_params(client_id),
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.startswith(f"{LOGIN_BASE_URL}/api/v1/mcp/oauth/consent/")
    return urlparse(location).path


@pytest.mark.asyncio
async def test_native_discovery_and_challenge_use_external_streamable_resource(
    local_oauth_client,
) -> None:
    client, _runtime = local_oauth_client

    metadata = await client.get(
        "/.well-known/oauth-protected-resource/mcp/streamable"
    )
    assert metadata.status_code == 200
    assert metadata.json()["resource"] == RESOURCE
    assert "localhost:8000" in metadata.text

    challenge = await client.post(
        "/mcp/streamable/",
        headers={"Accept": "application/json, text/event-stream"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "challenge-test", "version": "1"},
            },
        },
    )
    assert challenge.status_code == 401
    assert "localhost:8000" in challenge.headers["www-authenticate"]
    assert "localhost:8080" not in challenge.headers["www-authenticate"]
    assert "/mcp/streamable\"" in challenge.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_native_local_oauth_pkce_flow_uses_intercept_session(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    client, runtime = local_oauth_client
    client_id = await _register_client(client)
    consent_path = await _begin_authorization(client, client_id)

    anonymous_consent = await client.get(consent_path, follow_redirects=False)
    assert anonymous_consent.status_code == 302
    assert anonymous_consent.headers["location"].startswith(
        f"{LOGIN_BASE_URL}/login?next="
    )

    user = await _login(client, session_maker, analyst_user_factory)
    consent = await client.get(consent_path)
    assert consent.status_code == 200
    assert "Authorize MCP access" in consent.text
    assert "Codex Test Client" in consent.text
    assert 'method="post"' in consent.text

    approval = await client.post(consent_path, json={"decision": "approve"})
    assert approval.status_code == 200
    callback_query = parse_qs(urlparse(approval.json()["redirect_to"]).query)
    auth_code = callback_query["code"][0]
    assert callback_query["state"] == ["state-123"]

    token_response = await client.post(
        "/mcp/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
            "resource": RESOURCE,
        },
    )
    assert token_response.status_code == 200, token_response.text
    token_payload = token_response.json()
    assert token_payload["access_token"]
    assert token_payload["refresh_token"]
    assert token_payload["scope"] == "mcp:access"

    access = await runtime.provider.load_access_token(token_payload["access_token"])
    assert access is not None
    assert access.claims["intercept_user_id"] == str(user.id)

    async with runtime.http_app.lifespan(runtime.http_app):
        initialized = await client.post(
            "/mcp/streamable/",
            headers={
                "Authorization": f"Bearer {token_payload['access_token']}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "oauth-test", "version": "1"},
                },
            },
        )
    assert initialized.status_code == 200, initialized.text

    connected = await client.get("/api/v1/mcp/oauth/clients")
    assert connected.status_code == 200
    clients = connected.json()
    assert len(clients) == 1
    assert clients[0]["client_name"] == "Codex Test Client"

    revoked = await client.delete(f"/api/v1/mcp/oauth/clients/{clients[0]['id']}")
    assert revoked.status_code == 204
    assert await runtime.provider.load_access_token(token_payload["access_token"]) is None


@pytest.mark.asyncio
async def test_native_token_endpoint_rejects_invalid_pkce_verifier(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    client, _runtime = local_oauth_client
    client_id = await _register_client(client)
    consent_path = await _begin_authorization(client, client_id)
    await _login(client, session_maker, analyst_user_factory)
    approval = await client.post(consent_path, json={"decision": "approve"})
    auth_code = parse_qs(urlparse(approval.json()["redirect_to"]).query)["code"][0]

    response = await client.post(
        "/mcp/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": "b" * 64,
            "resource": RESOURCE,
        },
    )

    # FastMCP intentionally maps invalid_grant to 401 for the MCP token contract.
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_legacy_oauth_and_sse_routes_are_not_aliased(local_oauth_client) -> None:
    client, _runtime = local_oauth_client

    responses = [
        await client.post("/oauth/register", json={}),
        await client.get("/oauth/authorize"),
        await client.post("/oauth/token"),
        await client.post("/oauth/revoke"),
        await client.get("/mcp/sse"),
        await client.post("/mcp/messages"),
    ]
    assert all(response.status_code in {404, 405} for response in responses)
