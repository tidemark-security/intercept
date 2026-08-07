"""Pre-parser request-body limits for security-sensitive HTTP routes."""

from __future__ import annotations

from collections.abc import Collection

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


PASSKEY_REQUEST_MAX_BODY_BYTES = 256 * 1024
PASSWORD_LOGIN_REQUEST_MAX_BODY_BYTES = 8 * 1024


class RequestBodyLimitMiddleware:
    """Reject selected request bodies before framework JSON parsing."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        paths: Collection[str],
    ) -> None:
        if max_body_bytes < 1:
            raise ValueError("Request body limit must be positive")
        self.app = app
        self.max_body_bytes = int(max_body_bytes)
        self.paths = frozenset(path.rstrip("/") or "/" for path in paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope.get("path") or "").rstrip("/") or "/"
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or path not in self.paths
        ):
            await self.app(scope, receive, send)
            return

        declared_lengths: list[int] = []
        for name, value in scope.get("headers", []):
            if name.lower() != b"content-length":
                continue
            try:
                declared_lengths.append(int(value))
            except (TypeError, ValueError):
                await self._reject(scope, receive, send)
                return
        if (
            any(length < 0 or length > self.max_body_bytes for length in declared_lengths)
            or len(set(declared_lengths)) > 1
        ):
            await self._reject(scope, receive, send)
            return

        buffered: list[Message] = []
        body_size = 0
        more_body = True
        while more_body:
            message = await receive()
            buffered.append(message)
            if message.get("type") != "http.request":
                break
            body_size += len(message.get("body", b""))
            if body_size > self.max_body_bytes:
                await self._reject(scope, receive, send)
                return
            more_body = bool(message.get("more_body", False))

        async def replay_receive() -> Message:
            if buffered:
                return buffered.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            {"message": "Request body too large.", "fields": []},
            status_code=413,
        )
        await response(scope, receive, send)


PASSKEY_REQUEST_PATHS = frozenset(
    {
        "/api/v1/auth/passkeys/register/options",
        "/api/v1/auth/passkeys/register/verify",
        "/api/v1/auth/passkeys/authenticate/options",
        "/api/v1/auth/passkeys/authenticate/verify",
    }
)

PASSWORD_LOGIN_REQUEST_PATHS = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/password/change",
        "/api/v1/auth/reset-password",
    }
)


__all__ = [
    "PASSKEY_REQUEST_MAX_BODY_BYTES",
    "PASSKEY_REQUEST_PATHS",
    "PASSWORD_LOGIN_REQUEST_MAX_BODY_BYTES",
    "PASSWORD_LOGIN_REQUEST_PATHS",
    "RequestBodyLimitMiddleware",
]
