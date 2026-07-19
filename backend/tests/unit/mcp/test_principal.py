from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastmcp.server.auth import AccessToken

from app.mcp.auth import MCP_ACCESS_SCOPE
from app.mcp.principal import (
    MCPPrincipal,
    MCPPrincipalMiddleware,
    get_current_mcp_principal,
    require_mcp_principal,
)
from app.models.enums import UserStatus


class _Session:
    def __init__(self, user) -> None:
        self.user = user
        self.committed = False

    async def get(self, model, user_id):
        return self.user if self.user is not None and self.user.id == user_id else None

    async def commit(self) -> None:
        self.committed = True


def _session_factory(session: _Session):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


@pytest.mark.asyncio
async def test_require_mcp_principal_reloads_user_and_audits_request_context() -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        username="analyst",
        status=UserStatus.ACTIVE,
    )
    session = _Session(user)
    audit = SimpleNamespace(log_event=AsyncMock())
    token = AccessToken(
        token="reference-token",
        client_id="vscode-client",
        scopes=[MCP_ACCESS_SCOPE],
        claims={"intercept_user_id": str(user_id), "auth_source": "oidc"},
    )
    request = SimpleNamespace(
        client=SimpleNamespace(host="203.0.113.10"),
        headers={"user-agent": "mcp-client", "x-request-id": "req-123"},
    )

    principal = await require_mcp_principal(
        access_token=token,
        request=request,
        session_factory=_session_factory(session),
        audit_service_factory=lambda _db: audit,
    )

    assert principal.user is user
    assert principal.auth_source == "oidc"
    assert principal.client_id == "vscode-client"
    assert principal.scopes == frozenset({MCP_ACCESS_SCOPE})
    audit.log_event.assert_awaited_once()
    audit_kwargs = audit.log_event.await_args.kwargs
    assert audit_kwargs["event_type"] == "auth.mcp.access"
    assert audit_kwargs["performed_by"] == "analyst"
    assert audit_kwargs["new_value"] == {
        "auth_source": "oidc",
        "client_id": "vscode-client",
        "scopes": [MCP_ACCESS_SCOPE],
    }
    assert audit_kwargs["context"].ip_address == "203.0.113.10"
    assert audit_kwargs["context"].user_agent == "mcp-client"
    assert audit_kwargs["context"].correlation_id == "req-123"
    assert session.committed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [UserStatus.DISABLED, UserStatus.LOCKED])
async def test_require_mcp_principal_rejects_inactive_users(status: UserStatus) -> None:
    user_id = uuid4()
    session = _Session(SimpleNamespace(id=user_id, status=status))
    token = AccessToken(
        token="reference-token",
        client_id="client",
        scopes=[MCP_ACCESS_SCOPE],
        claims={"intercept_user_id": str(user_id), "auth_source": "oauth"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_mcp_principal(
            access_token=token,
            request=None,
            session_factory=_session_factory(session),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_mcp_principal_rejects_deleted_or_unbound_identity() -> None:
    token = AccessToken(
        token="reference-token",
        client_id="client",
        scopes=[MCP_ACCESS_SCOPE],
        claims={"auth_source": "oauth"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_mcp_principal(
            access_token=token,
            request=None,
            session_factory=_session_factory(_Session(None)),
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_principal_middleware_binds_every_protocol_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=uuid4(), username="analyst")
    principal = MCPPrincipal(
        user=user,
        auth_source="oidc",
        client_id="vscode-client",
        scopes=frozenset({MCP_ACCESS_SCOPE}),
    )
    resolver = AsyncMock(return_value=principal)
    monkeypatch.setattr("app.mcp.principal.require_mcp_principal", resolver)
    middleware = MCPPrincipalMiddleware(session_factory=object())

    async def call_next(_context):
        assert get_current_mcp_principal() is principal
        return "listed"

    result = await middleware.on_request(SimpleNamespace(method="tools/list"), call_next)

    assert result == "listed"
    resolver.assert_awaited_once()
    assert get_current_mcp_principal() is None
