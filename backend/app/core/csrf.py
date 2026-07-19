from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Any

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.request_context import get_correlation_id
from app.core.settings_registry import get_local
from app.services.api_key_service import (
    ApiKeyExpiredError,
    ApiKeyNotFoundError,
    ApiKeyRevokedError,
    UserInactiveError,
    api_key_service,
)
from app.services.audit_service import AuditContext


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
API_KEY_AUTH_RESULT_SCOPE_KEY = "api_key_auth_result"


def extract_api_key(headers: Headers) -> str | None:
    """Extract a bearer or X-API-Key credential from request headers."""
    auth_header = headers.get("authorization")
    if auth_header:
        scheme, _, credential = auth_header.partition(" ")
        if scheme.lower() == "bearer" and credential.strip():
            return credential.strip()

    api_key = headers.get("x-api-key")
    if api_key and api_key.strip():
        return api_key.strip()

    return None


class CSRFMiddleware:
    """Enforce CSRF protection for unsafe requests authenticated by session cookie."""

    def __init__(
        self,
        app,
        *,
        session_factory_provider: Callable[[], Any] | None = None,
    ):
        self.app = app
        self.session_factory_provider = session_factory_provider

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not get_local("auth.csrf.enabled"):
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "")).upper()
        if method not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request = Request(scope, receive=receive)
        session_cookie_name = get_local("auth.session.cookie_name")
        csrf_cookie_name = get_local("auth.csrf.cookie_name")
        csrf_header_name = get_local("auth.csrf.header_name")

        session_token = request.cookies.get(session_cookie_name)
        if not session_token:
            await self.app(scope, receive, send)
            return

        api_key = extract_api_key(headers)
        if api_key and await self._authenticate_api_key(scope, headers, api_key):
            await self.app(scope, receive, send)
            return

        csrf_cookie = request.cookies.get(csrf_cookie_name)
        csrf_header = headers.get(csrf_header_name)
        if csrf_cookie and csrf_header and secrets.compare_digest(csrf_cookie, csrf_header):
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            status_code=403,
            content={
                "detail": {
                    "message": "CSRF validation failed",
                    "fields": [],
                }
            },
        )
        await response(scope, receive, send)

    async def _authenticate_api_key(
        self,
        scope: dict[str, Any],
        headers: Headers,
        api_key: str,
    ) -> bool:
        """Return True only when the presented API key is a real credential."""
        if self.session_factory_provider is None:
            return False

        session_factory = self.session_factory_provider()
        client_host = None
        if scope.get("client"):
            client_host = scope["client"][0]

        audit_context = AuditContext(
            ip_address=client_host,
            user_agent=headers.get("user-agent"),
            correlation_id=get_correlation_id(headers),
        )

        try:
            async with session_factory() as db:
                result = await api_key_service.validate_api_key(
                    db,
                    raw_key=api_key,
                    context=audit_context,
                )
                await db.commit()
        except (
            ApiKeyExpiredError,
            ApiKeyNotFoundError,
            ApiKeyRevokedError,
            UserInactiveError,
        ):
            return False

        scope[API_KEY_AUTH_RESULT_SCOPE_KEY] = result
        return True
