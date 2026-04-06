from __future__ import annotations

import secrets

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.settings_registry import get_local


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class CSRFMiddleware:
    """Enforce CSRF protection for unsafe requests authenticated by session cookie."""

    def __init__(self, app):
        self.app = app

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
        if headers.get("authorization") or headers.get("x-api-key"):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        session_cookie_name = get_local("auth.session.cookie_name")
        csrf_cookie_name = get_local("auth.csrf.cookie_name")
        csrf_header_name = get_local("auth.csrf.header_name")

        session_token = request.cookies.get(session_cookie_name)
        if not session_token:
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