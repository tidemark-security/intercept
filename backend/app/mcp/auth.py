"""FastMCP-native authentication primitives for Intercept."""

from __future__ import annotations

import base64
import ipaddress
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastmcp.server.auth import AccessToken, TokenVerifier

from app.services.api_key_service import (
    ApiKeyExpiredError,
    ApiKeyNotFoundError,
    ApiKeyRevokedError,
    UserInactiveError,
    api_key_service,
)


MCP_ACCESS_SCOPE = "mcp:access"


class MCPConfigurationError(RuntimeError):
    """Raised when MCP authentication cannot be assembled safely."""


@dataclass(frozen=True, slots=True)
class MCPDerivedKeys:
    """Domain-separated keys shared by every Intercept replica."""

    jwt_signing_key: bytes
    storage_fernet_key: bytes
    token_hash_key: bytes


def _derive_key(secret_key: str, *, info: bytes) -> bytes:
    if not secret_key:
        raise MCPConfigurationError("SECRET_KEY is required for MCP OAuth")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"tidemark-intercept-fastmcp-v1",
        info=info,
    ).derive(secret_key.encode("utf-8"))


def derive_mcp_keys(secret_key: str) -> MCPDerivedKeys:
    """Derive independent signing, storage, and opaque-secret hashing keys."""

    jwt_key = _derive_key(secret_key, info=b"jwt-signing")
    storage_key = base64.urlsafe_b64encode(
        _derive_key(secret_key, info=b"oauth-storage-encryption")
    )
    return MCPDerivedKeys(
        jwt_signing_key=jwt_key,
        storage_fernet_key=storage_key,
        token_hash_key=_derive_key(secret_key, info=b"opaque-token-hashing"),
    )


def _is_loopback(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def validate_public_origin(value: str) -> str:
    """Validate and normalize the externally reachable Intercept origin."""

    raw_value = str(value or "").strip()
    parsed = urlsplit(raw_value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise MCPConfigurationError(
            "MCP_OAUTH_PUBLIC_BASE_URL must be an absolute http(s) origin"
        )
    if parsed.username is not None or parsed.password is not None:
        raise MCPConfigurationError(
            "MCP_OAUTH_PUBLIC_BASE_URL must not contain credentials"
        )
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise MCPConfigurationError(
            "MCP_OAUTH_PUBLIC_BASE_URL must be an origin with no path, query, or fragment"
        )
    if parsed.scheme != "https" and not _is_loopback(parsed.hostname):
        raise MCPConfigurationError(
            "MCP_OAUTH_PUBLIC_BASE_URL must use HTTPS except for loopback development"
        )

    # Accessing .port also validates malformed/non-numeric ports.
    try:
        _ = parsed.port
    except ValueError as exc:
        raise MCPConfigurationError(
            "MCP_OAUTH_PUBLIC_BASE_URL contains an invalid port"
        ) from exc

    return f"{parsed.scheme}://{parsed.netloc}"


class XApiKeyToBearerMiddleware:
    """Normalize the legacy X-API-Key header for FastMCP's bearer middleware."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = list(scope.get("headers", []))
        has_authorization = any(name.lower() == b"authorization" for name, _ in headers)
        if not has_authorization:
            api_key = next(
                (
                    value.strip()
                    for name, value in headers
                    if name.lower() == b"x-api-key" and value.strip()
                ),
                None,
            )
            if api_key:
                headers.append((b"authorization", b"Bearer " + api_key))
                scope = {**scope, "headers": headers}

        await self.app(scope, receive, send)


class InterceptApiKeyVerifier(TokenVerifier):
    """Validate Intercept API keys through FastMCP's native verifier contract."""

    def __init__(
        self,
        *,
        session_factory: Callable[..., Any],
        resource_url: str,
        api_key_service: Any = api_key_service,
    ) -> None:
        super().__init__(
            base_url=resource_url,
            resource_base_url=resource_url,
            required_scopes=[MCP_ACCESS_SCOPE],
        )
        self._session_factory = session_factory
        self._api_key_service = api_key_service
        self._resource_url = resource_url

    async def verify_token(self, token: str) -> AccessToken | None:
        async with self._session_factory() as db:
            try:
                result = await self._api_key_service.validate_api_key(
                    db,
                    raw_key=token,
                    context=None,
                )
                await db.commit()
            except (
                ApiKeyExpiredError,
                ApiKeyNotFoundError,
                ApiKeyRevokedError,
                UserInactiveError,
            ):
                await db.rollback()
                return None

        return AccessToken(
            token=token,
            client_id=f"api-key:{result.api_key.id}",
            scopes=[MCP_ACCESS_SCOPE],
            resource=self._resource_url,
            claims={
                "intercept_user_id": str(result.user.id),
                "auth_source": "api_key",
                "api_key_id": str(result.api_key.id),
            },
        )


__all__ = [
    "MCP_ACCESS_SCOPE",
    "MCPConfigurationError",
    "MCPDerivedKeys",
    "InterceptApiKeyVerifier",
    "XApiKeyToBearerMiddleware",
    "derive_mcp_keys",
    "validate_public_origin",
]
