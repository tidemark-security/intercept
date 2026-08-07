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
from mcp.shared.auth import OAuthClientInformationFull
from starlette.responses import JSONResponse

from app.core.client_address import (
    ClientAddressResolver,
    client_address_resolver as default_client_address_resolver,
)
from app.core.authorization_lock import AuthorizationConcurrencyError
from app.services.mcp_registration_service import (
    bind_authorization_request,
    bind_registration_source_ip,
    reset_authorization_request,
    reset_registration_source_ip,
)

from app.core.api_key_scopes import MCP_ACCESS_SCOPE
from app.services.api_key_service import (
    ApiKeyExpiredError,
    ApiKeyNotFoundError,
    ApiKeyPolicyError,
    ApiKeyRevokedError,
    ApiKeyScopeError,
    UserInactiveError,
    api_key_service,
)


class MCPConfigurationError(RuntimeError):
    """Raised when MCP authentication cannot be assembled safely."""


def normalize_public_dcr_client(
    client_info: OAuthClientInformationFull,
) -> OAuthClientInformationFull:
    """Make dynamic registrations match Intercept's public-client contract.

    The MCP SDK creates a secret when the auth method is omitted or requests a
    confidential-client method. Intercept does not validate or retain those
    secrets, so returning one would misrepresent the token endpoint contract.
    CIMD clients do not pass through this DCR-only normalization seam.
    """

    client_info.token_endpoint_auth_method = "none"
    client_info.client_secret = None
    client_info.client_secret_expires_at = None
    return client_info


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


class MCPRegistrationRequestMiddleware:
    """Apply trusted source context and bound public OAuth request bodies."""

    def __init__(
        self,
        app: Any,
        *,
        max_body_bytes: int,
        client_address_resolver: ClientAddressResolver = default_client_address_resolver,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.client_address_resolver = client_address_resolver

    @staticmethod
    def _is_registration(scope: dict[str, Any]) -> bool:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            return False
        path = str(scope.get("path") or "").rstrip("/")
        return path in {"/register", "/mcp/register"}

    @staticmethod
    def _is_authorization(scope: dict[str, Any]) -> bool:
        if scope.get("type") != "http" or scope.get("method") not in {"GET", "POST"}:
            return False
        path = str(scope.get("path") or "").rstrip("/")
        return path in {"/authorize", "/mcp/authorize"}

    @staticmethod
    def _is_oauth_form_request(scope: dict[str, Any]) -> bool:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            return False
        path = str(scope.get("path") or "").rstrip("/")
        return path in {
            "/consent",
            "/mcp/consent",
            "/token",
            "/mcp/token",
            "/revoke",
            "/mcp/revoke",
        }

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        is_registration = self._is_registration(scope)
        is_authorization = self._is_authorization(scope)
        is_oauth_form_request = self._is_oauth_form_request(scope)
        replay_receive = receive
        if is_registration or (
            is_authorization and scope.get("method") == "POST"
        ) or is_oauth_form_request:
            if is_registration:
                error = "invalid_client_metadata"
                description = "MCP registration request body is too large"
            elif is_authorization:
                error = "invalid_request"
                description = "MCP authorization request body is too large"
            else:
                error = "invalid_request"
                description = "MCP OAuth request body is too large"
            bounded_receive = await self._bounded_receive(
                scope,
                receive,
                send,
                error=error,
                description=description,
            )
            if bounded_receive is None:
                return
            replay_receive = bounded_receive

        # Token authentication and access-token revalidation can resolve CIMD
        # metadata too, so every MCP HTTP request needs trusted source attribution.
        source_ip = self.client_address_resolver.resolve_scope(scope) or "unknown"
        source_token = bind_registration_source_ip(source_ip)
        authorization_token = (
            bind_authorization_request() if is_authorization else None
        )
        try:
            await self.app(scope, replay_receive, send)
        finally:
            if authorization_token is not None:
                reset_authorization_request(authorization_token)
            reset_registration_source_ip(source_token)

    async def _bounded_receive(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
        *,
        error: str,
        description: str,
    ) -> Callable[[], Any] | None:
        """Buffer one public request body and return a bounded replay callable."""

        for name, value in scope.get("headers", []):
            if name.lower() != b"content-length":
                continue
            try:
                declared_size = int(value)
            except (TypeError, ValueError):
                break
            if declared_size > self.max_body_bytes:
                await self._reject(
                    scope,
                    receive,
                    send,
                    error=error,
                    description=description,
                )
                return None
            break

        buffered: list[dict[str, Any]] = []
        body_size = 0
        more_body = True
        while more_body:
            message = await receive()
            buffered.append(message)
            if message.get("type") == "http.request":
                body_size += len(message.get("body", b""))
                if body_size > self.max_body_bytes:
                    await self._reject(
                        scope,
                        receive,
                        send,
                        error=error,
                        description=description,
                    )
                    return None
                more_body = bool(message.get("more_body", False))
            else:
                more_body = False

        async def replay_receive() -> dict[str, Any]:
            if buffered:
                return buffered.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        return replay_receive

    @staticmethod
    async def _reject(
        scope: Any,
        receive: Any,
        send: Any,
        *,
        error: str,
        description: str,
    ) -> None:
        response = JSONResponse(
            {
                "error": error,
                "error_description": description,
            },
            status_code=413,
        )
        await response(scope, receive, send)


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
                    required_scopes={MCP_ACCESS_SCOPE},
                    context=None,
                    skip_locked=True,
                )
                await db.commit()
            except (
                AuthorizationConcurrencyError,
                ApiKeyExpiredError,
                ApiKeyNotFoundError,
                ApiKeyPolicyError,
                ApiKeyRevokedError,
                ApiKeyScopeError,
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
    "MCPRegistrationRequestMiddleware",
    "XApiKeyToBearerMiddleware",
    "derive_mcp_keys",
    "normalize_public_dcr_client",
    "validate_public_origin",
]
