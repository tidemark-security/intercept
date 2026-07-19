"""Resolve FastMCP access tokens to current Intercept users."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from fastapi import HTTPException
from fastmcp.server.auth import AccessToken
from fastmcp.server.dependencies import get_access_token, get_http_request
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from app.core.database import async_session_factory
from app.mcp.auth import MCP_ACCESS_SCOPE
from app.models.enums import UserStatus
from app.models.models import UserAccount
from app.services.audit_service import AuditContext, get_audit_service


@dataclass(frozen=True, slots=True)
class MCPPrincipal:
    """Current local user plus the MCP credential that selected them."""

    user: UserAccount
    auth_source: str
    client_id: str
    scopes: frozenset[str]


_current_principal: ContextVar[MCPPrincipal | None] = ContextVar(
    "intercept_mcp_principal",
    default=None,
)


def get_current_mcp_principal() -> MCPPrincipal | None:
    """Return the principal bound around the current tool call, if any."""

    return _current_principal.get()


def _request_audit_context(request: Any | None) -> AuditContext:
    if request is None:
        return AuditContext()

    client = getattr(request, "client", None)
    ip_address = getattr(client, "host", None)
    if ip_address is None and isinstance(client, tuple) and client:
        ip_address = client[0]
    headers = getattr(request, "headers", {}) or {}
    return AuditContext(
        ip_address=ip_address,
        user_agent=headers.get("user-agent"),
        correlation_id=headers.get("x-request-id"),
    )


async def require_mcp_principal(
    *,
    access_token: AccessToken | None = None,
    request: Any | None = None,
    session_factory: Callable[..., Any] = async_session_factory,
    audit_service_factory: Callable[[Any], Any] = get_audit_service,
) -> MCPPrincipal:
    """Reload and validate the local user represented by a native access token."""

    if access_token is None:
        access_token = get_access_token()
    if access_token is None or MCP_ACCESS_SCOPE not in access_token.scopes:
        raise HTTPException(status_code=401, detail="MCP authentication required")

    claims = access_token.claims or {}
    raw_user_id = claims.get("intercept_user_id")
    auth_source = str(claims.get("auth_source") or "").strip()
    if not raw_user_id or auth_source not in {"api_key", "oauth", "oidc"}:
        raise HTTPException(status_code=401, detail="MCP identity is not bound to Intercept")
    try:
        user_id = UUID(str(raw_user_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail="MCP identity is not bound to Intercept",
        ) from exc

    if request is None:
        try:
            request = get_http_request()
        except RuntimeError:
            request = None

    async with session_factory() as db:
        user = await db.get(UserAccount, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="MCP user no longer exists")
        if user.status != UserStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="MCP user account is not active")

        principal = MCPPrincipal(
            user=user,
            auth_source=auth_source,
            client_id=access_token.client_id,
            scopes=frozenset(access_token.scopes),
        )
        await audit_service_factory(db).log_event(
            event_type="auth.mcp.access",
            entity_type="user",
            entity_id=str(user.id),
            description="MCP request authenticated",
            new_value={
                "auth_source": auth_source,
                "client_id": access_token.client_id,
                "scopes": sorted(access_token.scopes),
            },
            performed_by=user.username,
            context=_request_audit_context(request),
        )
        await db.commit()

    return principal


class MCPPrincipalMiddleware(Middleware):
    """Bind a freshly reloaded principal around every MCP protocol request."""

    def __init__(self, *, session_factory: Callable[..., Any] = async_session_factory) -> None:
        self._session_factory = session_factory

    async def on_request(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        principal = await require_mcp_principal(session_factory=self._session_factory)
        reset_token = _current_principal.set(principal)
        try:
            return await call_next(context)
        finally:
            _current_principal.reset(reset_token)


__all__ = [
    "MCPPrincipal",
    "MCPPrincipalMiddleware",
    "get_current_mcp_principal",
    "require_mcp_principal",
]
