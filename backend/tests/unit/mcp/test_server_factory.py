from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from fastmcp.server.auth import AccessToken, TokenVerifier

from app.mcp.server import create_mcp_server


class _Verifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        return None


@pytest.mark.asyncio
async def test_server_factory_binds_auth_lifespan_and_explicit_tools() -> None:
    entered: list[str] = []

    @asynccontextmanager
    async def lifespan(_server):
        entered.append("entered")
        yield {"shared": "resource"}
        entered.append("closed")

    verifier = _Verifier(required_scopes=["mcp:access"])
    server = create_mcp_server(auth=verifier, lifespan=lifespan)

    assert server.auth is verifier
    # Factory inspection is intentionally outside a protocol request. FastMCP
    # 3.4 runs middleware for direct ``list_tools()`` calls by default, so skip
    # request middleware here rather than manufacturing an authenticated user.
    tools = await server.list_tools(run_middleware=False)
    assert {tool.name for tool in tools} == {
        "get_summary",
        "list_work",
        "find_related",
        "search_case_runbooks",
        "get_case_runbook",
        "record_triage_decision",
        "add_timeline_item",
        "get_item",
        "validate_mermaid",
    }

    async with server._lifespan_manager():
        assert entered == ["entered"]
    assert entered == ["entered", "closed"]
