"""Integration tests for MCP OAuth 2.1 authorization-code + PKCE."""
from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


PUBLIC_BASE_URL = "http://localhost:8000"
LOGIN_BASE_URL = "http://localhost:5173"
REDIRECT_URI = "http://127.0.0.1:49152/callback"
RESOURCE = f"{PUBLIC_BASE_URL}/mcp"
CODE_VERIFIER = "a" * 64


def _code_challenge(verifier: str = CODE_VERIFIER) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


async def _register_client(client: AsyncClient) -> str:
    response = await client.post(
        "/oauth/register",
        json={
            "client_name": "Codex Test Client",
            "client_uri": "https://codex.example.test",
            "redirect_uris": [REDIRECT_URI],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    assert response.status_code == 201
    return response.json()["client_id"]


async def _login(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory(username="mcp_oauth_user", email="mcp_oauth_user@example.test")
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200


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


@pytest.mark.asyncio
async def test_mcp_missing_credential_advertises_oauth_metadata(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("MCP_OAUTH_PUBLIC_BASE_URL", PUBLIC_BASE_URL)

    response = await client.get("/mcp/does-not-exist")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == (
        'Bearer resource_metadata="http://localhost:8000/.well-known/oauth-protected-resource/mcp", '
        'scope="mcp:access"'
    )


@pytest.mark.asyncio
async def test_mcp_oauth_pkce_flow_uses_local_intercept_session(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("MCP_OAUTH_PUBLIC_BASE_URL", PUBLIC_BASE_URL)
    monkeypatch.setenv("MCP_OAUTH_LOGIN_BASE_URL", LOGIN_BASE_URL)
    monkeypatch.setenv("MCP_OAUTH_REFRESH_TOKEN_TTL_DAYS", "7")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")

    client_id = await _register_client(client)

    login_redirect_response = await client.get(
        "/oauth/authorize",
        params=_authorize_params(client_id),
        follow_redirects=False,
    )
    assert login_redirect_response.status_code == 302
    login_location = login_redirect_response.headers["location"]
    assert login_location.startswith(f"{LOGIN_BASE_URL}/login?")
    next_values = parse_qs(urlparse(login_location).query)["next"]
    parsed_next = urlparse(next_values[0])
    assert f"{parsed_next.scheme}://{parsed_next.netloc}" == PUBLIC_BASE_URL
    assert parsed_next.path == "/oauth/authorize"
    assert parse_qs(parsed_next.query) == {
        key: [value] for key, value in _authorize_params(client_id).items()
    }

    await _login(client, session_maker, analyst_user_factory)

    consent_response = await client.get("/oauth/authorize", params=_authorize_params(client_id))
    assert consent_response.status_code == 200
    assert "Authorize MCP access" in consent_response.text
    assert "You can close this tab once the agent confirms the connection is complete." in consent_response.text

    approve_response = await client.get(
        "/oauth/authorize",
        params={**_authorize_params(client_id), "approve": "1"},
        follow_redirects=False,
    )
    assert approve_response.status_code == 302
    callback_location = approve_response.headers["location"]
    callback_query = parse_qs(urlparse(callback_location).query)
    auth_code = callback_query["code"][0]
    assert callback_query["state"] == ["state-123"]

    token_response = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
            "resource": RESOURCE,
        },
    )
    assert token_response.status_code == 200
    token_payload = token_response.json()
    assert token_payload["access_token"].startswith("tmoa_")
    assert token_payload["refresh_token"].startswith("tmor_")
    assert token_payload["scope"] == "mcp:access"

    mcp_response = await client.get(
        "/mcp/does-not-exist",
        headers={"Authorization": f"Bearer {token_payload['access_token']}"},
    )
    assert mcp_response.status_code == 404

    connected_response = await client.get("/api/v1/mcp/oauth/clients")
    assert connected_response.status_code == 200
    connected_clients = connected_response.json()
    assert len(connected_clients) == 1
    assert connected_clients[0]["client_name"] == "Codex Test Client"

    revoke_response = await client.delete(f"/api/v1/mcp/oauth/clients/{connected_clients[0]['id']}")
    assert revoke_response.status_code == 204

    revoked_mcp_response = await client.get(
        "/mcp/does-not-exist",
        headers={"Authorization": f"Bearer {token_payload['access_token']}"},
    )
    assert revoked_mcp_response.status_code == 401


@pytest.mark.asyncio
async def test_mcp_oauth_rejects_invalid_pkce_verifier(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("MCP_OAUTH_PUBLIC_BASE_URL", PUBLIC_BASE_URL)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")

    client_id = await _register_client(client)
    await _login(client, session_maker, analyst_user_factory)

    approve_response = await client.get(
        "/oauth/authorize",
        params={**_authorize_params(client_id), "approve": "1"},
        follow_redirects=False,
    )
    assert approve_response.status_code == 302
    auth_code = parse_qs(urlparse(approve_response.headers["location"]).query)["code"][0]

    token_response = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": "b" * 64,
            "resource": RESOURCE,
        },
    )

    assert token_response.status_code == 400
    assert token_response.json()["error"] == "invalid_grant"
