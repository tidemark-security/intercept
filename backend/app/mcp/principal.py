"""Resolve FastMCP access tokens to current Intercept users."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import logging
from typing import Any, Callable
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException
from fastmcp.server.auth import AccessToken
from fastmcp.server.dependencies import get_access_token, get_http_request
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from app.core.account_authentication import non_password_authentication_allowed
from app.core.client_address import request_client_address
from app.core.database import async_session_factory
from app.core.authorization_lock import (
    AuthorizationConcurrencyError,
    acquire_authorization_lock,
)
from app.mcp.auth import MCP_ACCESS_SCOPE
from app.models.models import UserAccount
from app.services.api_key_service import (
    ApiKeyExpiredError,
    ApiKeyNotFoundError,
    ApiKeyPolicyError,
    ApiKeyRevokedError,
    ApiKeyScopeError,
    UserInactiveError,
    api_key_service,
)
from app.services.audit_service import AuditContext, get_audit_service
from app.services.mcp_oauth_service import MCPOAuthError, mcp_oauth_service

logger = logging.getLogger(__name__)


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

    if hasattr(request, "scope"):
        ip_address = request_client_address(request)
    else:
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
    db: Any | None = None,
    commit: bool = True,
    revalidate_source_credential: bool = False,
    skip_locked: bool = False,
    shared_lock: bool = False,
) -> MCPPrincipal:
    """Reload and validate the local user represented by a native access token.

    Tool middleware supplies its own session with ``commit=False`` so user and
    source-credential locks remain held through tool execution. Direct callers
    retain the existing self-contained transaction behavior.
    """

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

    async def load_principal(active_db: Any) -> MCPPrincipal:
        authorization_acquired = await acquire_authorization_lock(
            active_db,
            user_id=user_id,
            shared=True,
            wait=not skip_locked,
        )
        if not authorization_acquired:
            raise HTTPException(
                status_code=503,
                detail="MCP authorization state is busy; retry the request",
            )
        user = None
        if auth_source == "api_key" and revalidate_source_credential:
            try:
                api_key_result = await api_key_service.validate_api_key(
                    active_db,
                    raw_key=access_token.token,
                    required_scopes={MCP_ACCESS_SCOPE},
                    context=None,
                    audit_success=False,
                    skip_locked=skip_locked,
                    shared_lock=shared_lock,
                )
            except (
                AuthorizationConcurrencyError,
                ApiKeyExpiredError,
                ApiKeyNotFoundError,
                ApiKeyRevokedError,
            ) as exc:
                raise HTTPException(
                    status_code=401,
                    detail="MCP API key is no longer valid",
                ) from exc
            except (
                ApiKeyPolicyError,
                ApiKeyScopeError,
                UserInactiveError,
            ) as exc:
                raise HTTPException(
                    status_code=403,
                    detail="MCP API key is no longer authorized",
                ) from exc

            claimed_api_key_id = str(claims.get("api_key_id") or "")
            if (
                api_key_result.user.id != user_id
                or claimed_api_key_id != str(api_key_result.api_key.id)
            ):
                raise HTTPException(
                    status_code=401,
                    detail="MCP identity is not bound to Intercept",
                )
            user = api_key_result.user

        if auth_source == "oauth" and revalidate_source_credential:
            resource_path = urlsplit(str(access_token.resource or "")).path
            if not resource_path:
                resource_path = "/mcp/streamable/"
            try:
                oauth_result = await mcp_oauth_service.validate_access_token(
                    active_db,
                    token=access_token.token,
                    request_path=resource_path,
                    context=None,
                    for_update=True,
                    skip_locked=skip_locked,
                    audit_success=False,
                )
            except MCPOAuthError as exc:
                raise HTTPException(
                    status_code=401,
                    detail="MCP OAuth token is no longer valid",
                ) from exc
            if (
                oauth_result.user.id != user_id
                or oauth_result.client.client_id != access_token.client_id
            ):
                raise HTTPException(
                    status_code=401,
                    detail="MCP identity is not bound to Intercept",
                )
            user = oauth_result.user

        if auth_source == "oidc" and revalidate_source_credential:
            provider_reference_hash = str(
                claims.get("oidc_grant_reference_hash") or ""
            )
            if not provider_reference_hash:
                raise HTTPException(
                    status_code=401,
                    detail="MCP OIDC grant is no longer valid",
                )
            candidate_user = await active_db.get(UserAccount, user_id)
            if candidate_user is None:
                raise HTTPException(
                    status_code=401,
                    detail="MCP user no longer exists",
                )
            user = await active_db.get(
                UserAccount,
                user_id,
                populate_existing=True,
                with_for_update={
                    "read": shared_lock,
                    "skip_locked": skip_locked,
                },
            )
            if user is None:
                raise HTTPException(
                    status_code=503 if skip_locked else 401,
                    detail=(
                        "MCP authorization state is busy; retry the request"
                        if skip_locked
                        else "MCP user no longer exists"
                    ),
                )
            try:
                await mcp_oauth_service.validate_provider_grant_reference(
                    active_db,
                    user_id=user_id,
                    client_id=access_token.client_id,
                    provider_reference_hash=provider_reference_hash,
                    for_update=True,
                    skip_locked=skip_locked,
                )
            except MCPOAuthError as exc:
                raise HTTPException(
                    status_code=401,
                    detail="MCP OIDC grant is no longer valid",
                ) from exc

        if user is None:
            candidate_user = await active_db.get(UserAccount, user_id)
            if candidate_user is None:
                raise HTTPException(
                    status_code=401,
                    detail="MCP user no longer exists",
                )
            user = await active_db.get(
                UserAccount,
                user_id,
                populate_existing=True,
                with_for_update={
                    "read": shared_lock,
                    "skip_locked": skip_locked,
                },
            )
        if user is None:
            if skip_locked:
                raise HTTPException(
                    status_code=503,
                    detail="MCP authorization state is busy; retry the request",
                )
            raise HTTPException(status_code=401, detail="MCP user no longer exists")
        if not non_password_authentication_allowed(user):
            raise HTTPException(status_code=403, detail="MCP user account is not active")
        if user.must_change_password:
            raise HTTPException(status_code=403, detail="Password change required")

        principal = MCPPrincipal(
            user=user,
            auth_source=auth_source,
            client_id=access_token.client_id,
            scopes=frozenset(access_token.scopes),
        )
        await audit_service_factory(active_db).log_event(
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
        return principal

    if db is not None:
        principal = await load_principal(db)
        if commit:
            await db.commit()
        return principal

    async with session_factory() as owned_db:
        principal = await load_principal(owned_db)
        await owned_db.commit()
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
        # Tool calls are authorized by on_call_tool below, where the same
        # transaction and row lock can remain live through tool execution.
        if context.method == "tools/call":
            return await call_next(context)

        principal = await require_mcp_principal(
            session_factory=self._session_factory,
            skip_locked=True,
            shared_lock=True,
        )
        reset_token = _current_principal.set(principal)
        try:
            return await call_next(context)
        finally:
            _current_principal.reset(reset_token)

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        async with self._session_factory() as db:
            principal = await require_mcp_principal(
                session_factory=self._session_factory,
                db=db,
                commit=False,
                revalidate_source_credential=True,
                skip_locked=True,
            )
            reset_token = _current_principal.set(principal)
            try:
                response = await call_next(context)
            except Exception:
                # Authentication succeeded, so preserve its audit record even
                # when the downstream tool reports a controlled failure.
                try:
                    await db.commit()
                except Exception:
                    await db.rollback()
                    logger.exception("Failed to persist MCP access audit event")
                raise
            else:
                await db.commit()
                return response
            finally:
                _current_principal.reset(reset_token)


__all__ = [
    "MCPPrincipal",
    "MCPPrincipalMiddleware",
    "get_current_mcp_principal",
    "require_mcp_principal",
]
