"""Bounded FastMCP Client ID Metadata Document resolution."""

from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Awaitable, Callable

import jwt
from fastmcp.server.auth.cimd import CIMDClientManager
from jwt.exceptions import PyJWTError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.services.mcp_client_assertion_replay_service import (
    MAX_CLIENT_ASSERTION_JTI_BYTES,
    MAX_MCP_CLIENT_ID_BYTES,
    MCPClientAssertionReplayError,
    MCPClientAssertionReplayService,
    MCPClientAssertionReplayStoreError,
)


CLIENT_ASSERTION_CLOCK_SKEW_SECONDS = 30
CLIENT_ASSERTION_DB_CLOCK_MARGIN_SECONDS = 30
CLIENT_ASSERTION_REPLAY_MARGIN_SECONDS = (
    CLIENT_ASSERTION_CLOCK_SKEW_SECONDS
    + CLIENT_ASSERTION_DB_CLOCK_MARGIN_SECONDS
)
CLIENT_ASSERTION_REPLAY_UNAVAILABLE_DESCRIPTION = (
    "Client assertion replay protection is temporarily unavailable"
)


def client_assertion_replay_error_boundary(
    endpoint: Callable[[Request], Awaitable[Response]],
) -> Callable[[Request], Awaitable[Response]]:
    """Map a fail-closed replay-ledger outage to a stable OAuth response."""

    @wraps(endpoint)
    async def wrapped(request: Request) -> Response:
        try:
            return await endpoint(request)
        except MCPClientAssertionReplayStoreError:
            return JSONResponse(
                {
                    "error": "server_error",
                    "error_description": (
                        CLIENT_ASSERTION_REPLAY_UNAVAILABLE_DESCRIPTION
                    ),
                },
                status_code=503,
                headers={
                    "Cache-Control": "no-store",
                    "Pragma": "no-cache",
                    "Retry-After": "1",
                },
            )

    return wrapped


def trim_cimd_cache(manager: Any, *, max_entries: int) -> None:
    """Enforce a hard FIFO bound on FastMCP's otherwise-unbounded cache."""

    fetcher = getattr(manager, "_fetcher", None)
    cache = getattr(fetcher, "_cache", None)
    if not isinstance(cache, dict):
        return
    while len(cache) > max_entries:
        cache.pop(next(iter(cache)))


def cimd_fetch_requires_network(manager: Any, client_id: str) -> bool:
    """Return whether resolving this client can perform outbound network I/O."""

    fetcher = getattr(manager, "_fetcher", None)
    cache = getattr(fetcher, "_cache", None)
    if not isinstance(cache, dict):
        return True
    entry = cache.get(client_id)
    if entry is None:
        return True
    try:
        expires_at = float(getattr(entry, "expires_at", 0))
    except (TypeError, ValueError):
        return True
    return bool(getattr(entry, "must_revalidate", False)) or time.time() >= expires_at


class BoundedCIMDClientManager(CIMDClientManager):
    """Bound CIMD documents and claim validated assertion JTIs durably."""

    def __init__(
        self,
        *,
        max_cache_entries: int,
        assertion_replay_service: MCPClientAssertionReplayService | None = None,
        **kwargs: Any,
    ) -> None:
        if max_cache_entries <= 0:
            raise ValueError("CIMD cache capacity must be positive")
        super().__init__(**kwargs)
        self.max_cache_entries = max_cache_entries
        self._assertion_replay_service = assertion_replay_service

    async def get_client(self, client_id_url: str):
        try:
            return await super().get_client(client_id_url)
        finally:
            trim_cimd_cache(self, max_entries=self.max_cache_entries)

    @staticmethod
    def _unverified_assertion_claims(assertion: str) -> tuple[str, float]:
        """Extract bounded replay fields; signature validation still belongs to FastMCP."""

        try:
            claims = jwt.decode(
                assertion,
                options={
                    "verify_signature": False,
                    "verify_exp": False,
                    "verify_aud": False,
                    "verify_iss": False,
                },
            )
        except PyJWTError as exc:
            raise ValueError("Client assertion is not a valid JWT") from exc

        jti = claims.get("jti")
        if not isinstance(jti, str) or not jti.strip():
            raise ValueError("Client assertion jti must be a non-empty string")
        if len(jti.encode("utf-8")) > MAX_CLIENT_ASSERTION_JTI_BYTES:
            raise ValueError("Client assertion jti is too long")

        exp = claims.get("exp")
        if isinstance(exp, bool) or not isinstance(exp, (int, float)):
            raise ValueError("Client assertion exp must be numeric")
        numeric_exp = float(exp)
        if not math.isfinite(numeric_exp):
            raise ValueError("Client assertion exp must be finite")
        return jti, numeric_exp

    def _discard_process_local_jti(self, jti: str) -> None:
        """Make PostgreSQL, rather than FastMCP's raw-JTI cache, authoritative."""

        validator = getattr(self, "_assertion_validator", None)
        cache = getattr(validator, "_jti_cache", None)
        if isinstance(cache, dict):
            cache.pop(jti, None)

    async def validate_private_key_jwt(
        self,
        assertion: str,
        client: Any,
        token_endpoint: str,
    ) -> bool:
        """Validate with FastMCP, then atomically reserve ``(client_id, jti)``."""

        replay_service = self._assertion_replay_service
        if replay_service is None:
            raise ValueError("Client assertion replay protection is unavailable")

        client_id_value = getattr(client, "client_id", None)
        if client_id_value is None:
            raise ValueError("Client assertion client_id is missing")
        client_id = str(client_id_value)
        if not client_id or len(client_id.encode("utf-8")) > MAX_MCP_CLIENT_ID_BYTES:
            raise ValueError("Client assertion client_id is invalid")

        jti, numeric_exp = self._unverified_assertion_claims(assertion)
        try:
            validated = await super().validate_private_key_jwt(
                assertion=assertion,
                client=client,
                token_endpoint=token_endpoint,
            )
        except ValueError as exc:
            if "Assertion replay detected" in str(exc):
                raise ValueError("Client assertion replay detected") from exc
            raise
        finally:
            # FastMCP's cache is keyed only by raw JTI. PostgreSQL remains
            # authoritative even when validation is cancelled or raises.
            self._discard_process_local_jti(jti)

        if not validated:
            raise ValueError("Client assertion validation failed")

        try:
            assertion_expiry = datetime.fromtimestamp(numeric_exp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise ValueError("Client assertion exp is outside the supported range") from exc
        replay_until = assertion_expiry + timedelta(
            seconds=CLIENT_ASSERTION_REPLAY_MARGIN_SECONDS
        )
        try:
            await replay_service.reserve(
                client_id=client_id,
                jti=jti,
                expires_at=replay_until,
            )
        except MCPClientAssertionReplayError as exc:
            raise ValueError("Client assertion replay detected") from exc
        return validated


__all__ = [
    "BoundedCIMDClientManager",
    "CLIENT_ASSERTION_CLOCK_SKEW_SECONDS",
    "CLIENT_ASSERTION_DB_CLOCK_MARGIN_SECONDS",
    "CLIENT_ASSERTION_REPLAY_MARGIN_SECONDS",
    "CLIENT_ASSERTION_REPLAY_UNAVAILABLE_DESCRIPTION",
    "client_assertion_replay_error_boundary",
    "cimd_fetch_requires_network",
    "trim_cimd_cache",
]
