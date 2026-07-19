"""Integration tests for MCP transport endpoint behavior."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import AccountType, UserRole, UserStatus
from app.main import app as intercept_app
from app.models.models import UserAccount
from app.services.api_key_service import api_key_service


@pytest.fixture
async def mcp_api_key(session_maker: async_sessionmaker[AsyncSession]) -> str:
    async with session_maker() as session:
        user = UserAccount(
            username="mcp_tool_user",
            email="mcp_tool@test.com",
            role=UserRole.ANALYST,
            status=UserStatus.ACTIVE,
            account_type=AccountType.NHI,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        api_key_result = await api_key_service.create_api_key(
            session,
            user_id=user.id,
            name="MCP tool transport key",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        _, raw_key = api_key_result
        await session.commit()
        return raw_key


@pytest.mark.asyncio
async def test_mcp_namespace_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/mcp/streamable/",
        headers={"Accept": "application/json, text/event-stream"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "unauthenticated-test", "version": "1"},
            },
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_legacy_tool_call_endpoint_removed(
    client: AsyncClient,
    mcp_api_key: str,
) -> None:
    response = await client.post(
        "/mcp/v1/tools/call",
        headers={"Authorization": f"Bearer {mcp_api_key}"},
        json={"name": "get_cases_api_v1_cases_get", "arguments": {"limit": 10}},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_legacy_tool_list_endpoint_removed(
    client: AsyncClient,
    mcp_api_key: str,
) -> None:
    response = await client.post(
        "/mcp/v1/tools/list",
        headers={"Authorization": f"Bearer {mcp_api_key}"},
    )
    assert response.status_code == 404


def _streamable_payload(response) -> dict:
    if "application/json" in response.headers.get("content-type", ""):
        return response.json()
    for line in response.text.splitlines():
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: "))
    raise AssertionError(f"No JSON-RPC payload in response: {response.text}")


@pytest.mark.asyncio
async def test_real_streamable_initialize_and_tool_listing(
    client: AsyncClient,
    mcp_api_key: str,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.mcp.tools.async_session_factory", session_maker)
    runtime = intercept_app.runtime
    assert runtime is not None
    headers = {
        "Authorization": f"Bearer {mcp_api_key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    # Enter in the test task so AnyIO's session-manager cancel scope is also
    # closed by the same task (matching production lifespan behavior).
    async with runtime.http_app.lifespan(runtime.http_app):
        initialized = await client.post(
            "/mcp/streamable/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "integration-test", "version": "1"},
                },
            },
        )
        assert initialized.status_code == 200, initialized.text
        assert _streamable_payload(initialized)["result"]["serverInfo"]["name"]
        session_id = initialized.headers["mcp-session-id"]

        session_headers = {
            **headers,
            "MCP-Session-Id": session_id,
            "MCP-Protocol-Version": "2025-06-18",
        }
        notification = await client.post(
            "/mcp/streamable/",
            headers=session_headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        assert notification.status_code in {200, 202}

        listed = await client.post(
            "/mcp/streamable/",
            headers=session_headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert listed.status_code == 200, listed.text
        tool_names = {
            tool["name"] for tool in _streamable_payload(listed)["result"]["tools"]
        }
        assert {"get_summary", "list_work", "record_triage_decision"} <= tool_names

        invoked = await client.post(
            "/mcp/streamable/",
            headers=session_headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "list_work",
                    "arguments": {"kind": "alert", "limit": 1},
                },
            },
        )
        assert invoked.status_code == 200, invoked.text
        assert _streamable_payload(invoked)["result"].get("isError") is not True
