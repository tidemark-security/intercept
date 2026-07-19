"""OAuth 2.1 broker for the remote MCP server.

The implementation is intentionally scoped to public MCP clients using
authorization-code + PKCE. API keys remain the machine-to-machine path.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import secrets
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast
from urllib.parse import quote, urlencode, urlparse

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserStatus
from app.models.models import (
    MCPOAuthAuthorizationCode,
    MCPOAuthClient,
    MCPOAuthClientRead,
    MCPOAuthConsent,
    MCPOAuthToken,
    UserAccount,
)
from app.services.audit_service import AuditContext, get_audit_service
from app.services.settings_service import SettingsService


MCP_OAUTH_SCOPE = "mcp:access"
ACCESS_TOKEN_PREFIX = "tmoa_"
REFRESH_TOKEN_PREFIX = "tmor_"
AUTH_CODE_PREFIX = "tmoc_"
CODE_TTL_SECONDS = 300
CLIENT_ID_PREFIX = "mcp_client_"
MIN_CODE_VERIFIER_LENGTH = 43
MAX_CODE_VERIFIER_LENGTH = 128


@dataclass(slots=True)
class MCPOAuthSettings:
    enabled: bool
    public_base_url: str
    login_base_url: str
    access_token_ttl_seconds: int
    refresh_token_ttl_days: int


@dataclass(slots=True)
class OAuthTokenValidationResult:
    user: UserAccount
    token: MCPOAuthToken
    client: MCPOAuthClient


class MCPOAuthError(Exception):
    """Base OAuth service exception."""

    error = "invalid_request"
    description = "Invalid OAuth request"


class OAuthDisabledError(MCPOAuthError):
    error = "server_error"
    description = "MCP OAuth is not enabled"


class OAuthConfigurationError(MCPOAuthError):
    error = "server_error"
    description = "MCP OAuth is not configured correctly"

    def __init__(self, description: str | None = None) -> None:
        if description is not None:
            self.description = description
        super().__init__(self.description)


class OAuthInvalidRequestError(MCPOAuthError):
    error = "invalid_request"

    def __init__(self, description: str) -> None:
        super().__init__(description)
        self.description = description


class OAuthInvalidClientError(MCPOAuthError):
    error = "invalid_client"
    description = "Invalid OAuth client"


class OAuthInvalidGrantError(MCPOAuthError):
    error = "invalid_grant"

    def __init__(self, description: str = "Invalid grant") -> None:
        super().__init__(description)
        self.description = description


class OAuthInvalidTokenError(MCPOAuthError):
    error = "invalid_token"

    def __init__(self, description: str = "Invalid access token") -> None:
        super().__init__(description)
        self.description = description


class OAuthInactiveUserError(MCPOAuthError):
    error = "invalid_token"
    description = "User account is not active"


class MCPOAuthService:
    """Business logic for MCP OAuth registration, authorization, and tokens."""

    async def get_settings(self, db: AsyncSession) -> MCPOAuthSettings:
        settings = SettingsService(db)
        enabled = bool(await settings.get("mcp.oauth.enabled", default=False))
        public_base_url = str(await settings.get("mcp.oauth.public_base_url", default="") or "").rstrip("/")
        login_base_url = str(await settings.get("mcp.oauth.login_base_url", default="") or "").rstrip("/")
        access_ttl = int(await settings.get("mcp.oauth.access_token_ttl_seconds", default=3600))
        refresh_ttl_days = int(await settings.get("mcp.oauth.refresh_token_ttl_days", default=30))

        if enabled:
            self._validate_public_base_url(
                public_base_url,
                setting_name="MCP_OAUTH_PUBLIC_BASE_URL",
            )
            if not login_base_url:
                login_base_url = public_base_url
            self._validate_public_base_url(
                login_base_url,
                setting_name="MCP_OAUTH_LOGIN_BASE_URL",
            )
            if access_ttl <= 0:
                raise OAuthConfigurationError("MCP OAuth access token TTL must be positive")
            if refresh_ttl_days <= 0:
                raise OAuthConfigurationError("MCP OAuth refresh token TTL days must be positive")

        return MCPOAuthSettings(
            enabled=enabled,
            public_base_url=public_base_url,
            login_base_url=login_base_url,
            access_token_ttl_seconds=access_ttl,
            refresh_token_ttl_days=refresh_ttl_days,
        )

    async def get_enabled_settings(self, db: AsyncSession) -> MCPOAuthSettings:
        settings = await self.get_settings(db)
        if not settings.enabled:
            raise OAuthDisabledError()
        return settings

    def resource_url_for_path(self, settings: MCPOAuthSettings, path: str) -> str:
        if path.startswith("/mcp/streamable"):
            return f"{settings.public_base_url}/mcp/streamable/"
        return f"{settings.public_base_url}/mcp"

    def resource_metadata_url_for_path(self, settings: MCPOAuthSettings, path: str) -> str:
        if path.startswith("/mcp/streamable"):
            return f"{settings.public_base_url}/.well-known/oauth-protected-resource/mcp/streamable"
        return f"{settings.public_base_url}/.well-known/oauth-protected-resource/mcp"

    def allowed_resource_urls(self, settings: MCPOAuthSettings) -> set[str]:
        base = settings.public_base_url
        return {
            f"{base}/mcp",
            f"{base}/mcp/",
            f"{base}/mcp/streamable",
            f"{base}/mcp/streamable/",
        }

    async def protected_resource_metadata(self, db: AsyncSession, path: str) -> dict[str, Any]:
        settings = await self.get_enabled_settings(db)
        resource = self.resource_url_for_path(settings, path)
        return {
            "resource": resource,
            "authorization_servers": [settings.public_base_url],
            "scopes_supported": [MCP_OAUTH_SCOPE],
            "bearer_methods_supported": ["header"],
            "resource_name": "Tidemark Intercept MCP",
            "resource_documentation": f"{settings.public_base_url}/docs",
        }

    async def authorization_server_metadata(self, db: AsyncSession) -> dict[str, Any]:
        settings = await self.get_enabled_settings(db)
        base = settings.public_base_url
        return {
            "issuer": base,
            "authorization_endpoint": f"{base}/oauth/authorize",
            "token_endpoint": f"{base}/oauth/token",
            "registration_endpoint": f"{base}/oauth/register",
            "revocation_endpoint": f"{base}/oauth/revoke",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": [MCP_OAUTH_SCOPE],
        }

    async def register_dynamic_client(
        self,
        db: AsyncSession,
        *,
        payload: dict[str, Any],
        context: Optional[AuditContext] = None,
    ) -> MCPOAuthClient:
        await self.get_enabled_settings(db)
        client = await self._upsert_client_from_metadata(
            db,
            metadata=payload,
            client_id=f"{CLIENT_ID_PREFIX}{secrets.token_urlsafe(24)}",
        )
        await get_audit_service(db).log_event(
            event_type="auth.mcp_oauth.client_registered",
            entity_type="mcp_oauth_client",
            entity_id=str(client.id),
            description="MCP OAuth client registered",
            new_value={
                "client_id": client.client_id,
                "client_name": client.client_name,
                "redirect_uris": client.redirect_uris,
            },
            context=context,
        )
        return client

    async def resolve_client(self, db: AsyncSession, client_id: str) -> MCPOAuthClient:
        result = await db.execute(
            select(MCPOAuthClient).where(cast(Any, MCPOAuthClient.client_id == client_id))
        )
        client = result.scalar_one_or_none()
        if client and client.revoked_at is None:
            return client

        parsed = urlparse(client_id)
        if parsed.scheme == "https" and parsed.netloc:
            metadata = await self._fetch_client_metadata(client_id)
            if metadata.get("client_id") != client_id:
                raise OAuthInvalidClientError()
            return await self._upsert_client_from_metadata(db, metadata=metadata, client_id=client_id)

        raise OAuthInvalidClientError()

    async def create_authorization_code(
        self,
        db: AsyncSession,
        *,
        client: MCPOAuthClient,
        user: UserAccount,
        redirect_uri: str,
        code_challenge: str,
        code_challenge_method: str,
        scope: str,
        resource: str,
        context: Optional[AuditContext] = None,
    ) -> str:
        await self.get_enabled_settings(db)
        self._validate_authorization_request(
            client=client,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scope=scope,
            resource=resource,
            settings=await self.get_enabled_settings(db),
        )

        raw_code = f"{AUTH_CODE_PREFIX}{secrets.token_urlsafe(48)}"
        now = datetime.now(timezone.utc)
        auth_code = MCPOAuthAuthorizationCode(
            code_hash=self._hash_secret(raw_code),
            client_db_id=client.id,
            user_id=user.id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scope=scope,
            resource=resource,
            expires_at=now + timedelta(seconds=CODE_TTL_SECONDS),
        )
        db.add(auth_code)
        await self._remember_consent(db, user=user, client=client, scope=scope)
        await db.flush()

        await get_audit_service(db).log_event(
            event_type="auth.mcp_oauth.authorized",
            entity_type="mcp_oauth_client",
            entity_id=str(client.id),
            description="MCP OAuth client authorized",
            new_value={
                "client_id": client.client_id,
                "client_name": client.client_name,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "resource": resource,
            },
            performed_by=user.username,
            context=context,
        )
        return raw_code

    async def has_active_consent(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
        client: MCPOAuthClient,
        scope: str,
    ) -> bool:
        consent = await self._get_consent(db, user=user, client=client, scope=scope)
        return consent is not None and consent.revoked_at is None

    async def exchange_authorization_code(
        self,
        db: AsyncSession,
        *,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: str,
        resource: str,
        context: Optional[AuditContext] = None,
    ) -> dict[str, Any]:
        settings = await self.get_enabled_settings(db)
        if resource not in self.allowed_resource_urls(settings):
            raise OAuthInvalidGrantError("Invalid resource")

        client = await self.resolve_client(db, client_id)
        now = datetime.now(timezone.utc)
        code_result = await db.execute(
            select(MCPOAuthAuthorizationCode).where(
                cast(Any, MCPOAuthAuthorizationCode.code_hash == self._hash_secret(code))
            )
        )
        auth_code = code_result.scalar_one_or_none()
        if auth_code is None:
            raise OAuthInvalidGrantError("Invalid authorization code")
        if auth_code.consumed_at is not None:
            raise OAuthInvalidGrantError("Authorization code has already been used")
        if auth_code.expires_at <= now:
            raise OAuthInvalidGrantError("Authorization code has expired")
        if auth_code.client_db_id != client.id:
            raise OAuthInvalidGrantError("Authorization code was issued to a different client")
        if auth_code.redirect_uri != redirect_uri:
            raise OAuthInvalidGrantError("Redirect URI does not match authorization code")
        if auth_code.resource != resource:
            raise OAuthInvalidGrantError("Resource does not match authorization code")
        if not self._verify_pkce(code_verifier, auth_code.code_challenge):
            raise OAuthInvalidGrantError("PKCE verification failed")

        user = await db.get(UserAccount, auth_code.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise OAuthInactiveUserError()

        auth_code.consumed_at = now
        return await self._issue_token_pair(
            db,
            settings=settings,
            client=client,
            user=user,
            scope=auth_code.scope,
            resource=auth_code.resource,
            context=context,
            event_type="auth.mcp_oauth.token_issued",
        )

    async def refresh_access_token(
        self,
        db: AsyncSession,
        *,
        refresh_token: str,
        client_id: str,
        resource: str | None = None,
        context: Optional[AuditContext] = None,
    ) -> dict[str, Any]:
        settings = await self.get_enabled_settings(db)
        client = await self.resolve_client(db, client_id)
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(MCPOAuthToken).where(
                cast(Any, MCPOAuthToken.token_hash == self._hash_secret(refresh_token))
            )
        )
        old_refresh = result.scalar_one_or_none()
        if old_refresh is None or old_refresh.token_type != "refresh":
            raise OAuthInvalidGrantError("Invalid refresh token")
        if old_refresh.revoked_at is not None:
            raise OAuthInvalidGrantError("Refresh token has been revoked")
        if old_refresh.expires_at <= now:
            old_refresh.revoked_at = now
            raise OAuthInvalidGrantError("Refresh token has expired")
        if old_refresh.client_db_id != client.id:
            raise OAuthInvalidGrantError("Refresh token was issued to a different client")
        if resource and resource != old_refresh.resource:
            raise OAuthInvalidGrantError("Resource does not match refresh token")

        user = await db.get(UserAccount, old_refresh.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise OAuthInactiveUserError()

        old_refresh.revoked_at = now
        return await self._issue_token_pair(
            db,
            settings=settings,
            client=client,
            user=user,
            scope=old_refresh.scope,
            resource=old_refresh.resource,
            context=context,
            event_type="auth.mcp_oauth.token_refreshed",
            rotated_from_token_id=old_refresh.id,
        )

    async def validate_access_token(
        self,
        db: AsyncSession,
        *,
        token: str,
        request_path: str,
        context: Optional[AuditContext] = None,
    ) -> OAuthTokenValidationResult:
        settings = await self.get_enabled_settings(db)
        expected_resource = self.resource_url_for_path(settings, request_path)
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(MCPOAuthToken, UserAccount, MCPOAuthClient)
            .join(UserAccount, cast(Any, UserAccount.id == MCPOAuthToken.user_id))
            .join(MCPOAuthClient, cast(Any, MCPOAuthClient.id == MCPOAuthToken.client_db_id))
            .where(cast(Any, MCPOAuthToken.token_hash == self._hash_secret(token)))
        )
        row = result.first()
        if row is None:
            raise OAuthInvalidTokenError()

        oauth_token, user, client = row
        if oauth_token.token_type != "access":
            raise OAuthInvalidTokenError()
        if oauth_token.revoked_at is not None:
            raise OAuthInvalidTokenError("Access token has been revoked")
        if oauth_token.expires_at <= now:
            oauth_token.revoked_at = now
            raise OAuthInvalidTokenError("Access token has expired")
        if client.revoked_at is not None:
            raise OAuthInvalidClientError()
        if user.status != UserStatus.ACTIVE:
            raise OAuthInactiveUserError()
        if oauth_token.scope != MCP_OAUTH_SCOPE:
            raise OAuthInvalidTokenError("Access token is missing required scope")
        if oauth_token.resource.rstrip("/") != expected_resource.rstrip("/"):
            raise OAuthInvalidTokenError("Access token resource does not match MCP endpoint")

        oauth_token.last_used_at = now
        client.last_seen_at = now
        await get_audit_service(db).log_event(
            event_type="auth.mcp_oauth.mcp_request",
            entity_type="mcp_oauth_client",
            entity_id=str(client.id),
            description="MCP OAuth request authenticated",
            new_value={
                "client_id": client.client_id,
                "client_name": client.client_name,
                "path": request_path,
                "scope": oauth_token.scope,
            },
            performed_by=user.username,
            context=context,
        )
        return OAuthTokenValidationResult(user=user, token=oauth_token, client=client)

    async def revoke_token(
        self,
        db: AsyncSession,
        *,
        token: str,
        client_id: str | None = None,
        context: Optional[AuditContext] = None,
    ) -> None:
        await self.get_enabled_settings(db)
        token_hash = self._hash_secret(token)
        result = await db.execute(
            select(MCPOAuthToken).where(cast(Any, MCPOAuthToken.token_hash == token_hash))
        )
        oauth_token = result.scalar_one_or_none()
        if oauth_token is None:
            return
        if client_id:
            client = await self.resolve_client(db, client_id)
            if oauth_token.client_db_id != client.id:
                raise OAuthInvalidClientError()
        now = datetime.now(timezone.utc)
        oauth_token.revoked_at = now
        if oauth_token.token_type == "refresh":
            await self._revoke_refresh_family(db, refresh_token_id=oauth_token.id, now=now)
        await get_audit_service(db).log_event(
            event_type="auth.mcp_oauth.token_revoked",
            entity_type="mcp_oauth_token",
            entity_id=str(oauth_token.id),
            description="MCP OAuth token revoked",
            context=context,
        )

    async def list_connected_clients(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
    ) -> list[MCPOAuthClientRead]:
        result = await db.execute(
            select(MCPOAuthConsent, MCPOAuthClient)
            .join(MCPOAuthClient, cast(Any, MCPOAuthClient.id == MCPOAuthConsent.client_db_id))
            .where(cast(Any, MCPOAuthConsent.user_id == user.id))
            .where(cast(Any, MCPOAuthConsent.revoked_at == None))  # noqa: E711
            .where(cast(Any, MCPOAuthClient.revoked_at == None))  # noqa: E711
            .order_by(cast(Any, MCPOAuthConsent.last_authorized_at).desc())
        )
        rows = result.all()
        connected: list[MCPOAuthClientRead] = []
        for consent, client in rows:
            last_used = await self._last_used_at(db, user=user, client=client)
            connected.append(
                MCPOAuthClientRead(
                    id=consent.id,
                    client_id=client.client_id,
                    client_name=client.client_name,
                    client_uri=client.client_uri,
                    redirect_uris=client.redirect_uris,
                    scope=consent.scope,
                    created_at=consent.created_at,
                    last_authorized_at=consent.last_authorized_at,
                    last_used_at=last_used,
                )
            )
        return connected

    async def revoke_connected_client(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
        consent_id: Any,
        context: Optional[AuditContext] = None,
    ) -> None:
        result = await db.execute(
            select(MCPOAuthConsent, MCPOAuthClient)
            .join(MCPOAuthClient, cast(Any, MCPOAuthClient.id == MCPOAuthConsent.client_db_id))
            .where(cast(Any, MCPOAuthConsent.id == consent_id))
            .where(cast(Any, MCPOAuthConsent.user_id == user.id))
        )
        row = result.first()
        if row is None:
            raise OAuthInvalidRequestError("Connected MCP client not found")
        consent, client = row
        now = datetime.now(timezone.utc)
        consent.revoked_at = now
        await self._revoke_user_client_tokens(db, user=user, client=client, now=now)
        await get_audit_service(db).log_event(
            event_type="auth.mcp_oauth.client_revoked",
            entity_type="mcp_oauth_client",
            entity_id=str(client.id),
            description="MCP OAuth client access revoked",
            new_value={"client_id": client.client_id, "client_name": client.client_name},
            performed_by=user.username,
            context=context,
        )

    async def _issue_token_pair(
        self,
        db: AsyncSession,
        *,
        settings: MCPOAuthSettings,
        client: MCPOAuthClient,
        user: UserAccount,
        scope: str,
        resource: str,
        context: Optional[AuditContext],
        event_type: str,
        rotated_from_token_id: Any = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        access_token = f"{ACCESS_TOKEN_PREFIX}{secrets.token_urlsafe(48)}"
        refresh_token = f"{REFRESH_TOKEN_PREFIX}{secrets.token_urlsafe(48)}"
        refresh_row = MCPOAuthToken(
            token_hash=self._hash_secret(refresh_token),
            token_type="refresh",
            client_db_id=client.id,
            user_id=user.id,
            scope=scope,
            resource=resource,
            expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
            rotated_from_token_id=rotated_from_token_id,
        )
        db.add(refresh_row)
        await db.flush()
        access_row = MCPOAuthToken(
            token_hash=self._hash_secret(access_token),
            token_type="access",
            client_db_id=client.id,
            user_id=user.id,
            scope=scope,
            resource=resource,
            refresh_token_id=refresh_row.id,
            expires_at=now + timedelta(seconds=settings.access_token_ttl_seconds),
        )
        db.add(access_row)
        client.last_seen_at = now
        await db.flush()

        await get_audit_service(db).log_event(
            event_type=event_type,
            entity_type="mcp_oauth_client",
            entity_id=str(client.id),
            description="MCP OAuth token pair issued",
            new_value={
                "client_id": client.client_id,
                "client_name": client.client_name,
                "scope": scope,
                "resource": resource,
                "access_expires_at": access_row.expires_at,
                "refresh_expires_at": refresh_row.expires_at,
            },
            performed_by=user.username,
            context=context,
        )

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": settings.access_token_ttl_seconds,
            "refresh_token": refresh_token,
            "scope": scope,
        }

    async def _remember_consent(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
        client: MCPOAuthClient,
        scope: str,
    ) -> MCPOAuthConsent:
        now = datetime.now(timezone.utc)
        consent = await self._get_consent(db, user=user, client=client, scope=scope)
        if consent is None:
            consent = MCPOAuthConsent(
                user_id=user.id,
                client_db_id=client.id,
                scope=scope,
                last_authorized_at=now,
            )
            db.add(consent)
        else:
            consent.revoked_at = None
            consent.last_authorized_at = now
        return consent

    async def _get_consent(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
        client: MCPOAuthClient,
        scope: str,
    ) -> MCPOAuthConsent | None:
        result = await db.execute(
            select(MCPOAuthConsent)
            .where(cast(Any, MCPOAuthConsent.user_id == user.id))
            .where(cast(Any, MCPOAuthConsent.client_db_id == client.id))
            .where(cast(Any, MCPOAuthConsent.scope == scope))
        )
        return result.scalar_one_or_none()

    async def _last_used_at(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
        client: MCPOAuthClient,
    ) -> datetime | None:
        result = await db.execute(
            select(func.max(MCPOAuthToken.last_used_at))
            .where(cast(Any, MCPOAuthToken.user_id == user.id))
            .where(cast(Any, MCPOAuthToken.client_db_id == client.id))
        )
        return result.scalar_one_or_none()

    async def _revoke_refresh_family(
        self,
        db: AsyncSession,
        *,
        refresh_token_id: Any,
        now: datetime,
    ) -> None:
        result = await db.execute(
            select(MCPOAuthToken).where(cast(Any, MCPOAuthToken.refresh_token_id == refresh_token_id))
        )
        for token in result.scalars().all():
            token.revoked_at = now

    async def _revoke_user_client_tokens(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
        client: MCPOAuthClient,
        now: datetime,
    ) -> None:
        result = await db.execute(
            select(MCPOAuthToken)
            .where(cast(Any, MCPOAuthToken.user_id == user.id))
            .where(cast(Any, MCPOAuthToken.client_db_id == client.id))
            .where(cast(Any, MCPOAuthToken.revoked_at == None))  # noqa: E711
        )
        for token in result.scalars().all():
            token.revoked_at = now

    async def _upsert_client_from_metadata(
        self,
        db: AsyncSession,
        *,
        metadata: dict[str, Any],
        client_id: str,
    ) -> MCPOAuthClient:
        redirect_uris = metadata.get("redirect_uris")
        if not isinstance(redirect_uris, list) or not redirect_uris:
            raise OAuthInvalidClientError()
        normalized_redirect_uris = [self._validate_redirect_uri(uri) for uri in redirect_uris]
        token_auth_method = str(metadata.get("token_endpoint_auth_method") or "none")
        if token_auth_method != "none":
            raise OAuthInvalidClientError()

        result = await db.execute(
            select(MCPOAuthClient).where(cast(Any, MCPOAuthClient.client_id == client_id))
        )
        client = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if client is None:
            client = MCPOAuthClient(
                client_id=client_id,
                client_name=str(metadata.get("client_name") or "MCP Client")[:200],
                client_uri=self._optional_string(metadata.get("client_uri")),
                logo_uri=self._optional_string(metadata.get("logo_uri")),
                redirect_uris=normalized_redirect_uris,
                scope=MCP_OAUTH_SCOPE,
                grant_types=self._string_list(metadata.get("grant_types")) or ["authorization_code", "refresh_token"],
                response_types=self._string_list(metadata.get("response_types")) or ["code"],
                token_endpoint_auth_method="none",
                contacts=self._string_list(metadata.get("contacts")),
                jwks_uri=self._optional_string(metadata.get("jwks_uri")),
                client_metadata=metadata,
            )
            db.add(client)
        else:
            client.client_name = str(metadata.get("client_name") or client.client_name)[:200]
            client.client_uri = self._optional_string(metadata.get("client_uri"))
            client.logo_uri = self._optional_string(metadata.get("logo_uri"))
            client.redirect_uris = normalized_redirect_uris
            client.grant_types = self._string_list(metadata.get("grant_types")) or ["authorization_code", "refresh_token"]
            client.response_types = self._string_list(metadata.get("response_types")) or ["code"]
            client.token_endpoint_auth_method = "none"
            client.contacts = self._string_list(metadata.get("contacts"))
            client.jwks_uri = self._optional_string(metadata.get("jwks_uri"))
            client.client_metadata = metadata
            client.updated_at = now
            client.revoked_at = None
        await db.flush()
        return client

    async def _fetch_client_metadata(self, client_id: str) -> dict[str, Any]:
        parsed = urlparse(client_id)
        if parsed.scheme != "https" or not parsed.hostname:
            raise OAuthInvalidClientError()
        self._assert_public_hostname(parsed.hostname)

        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            response = await client.get(
                client_id,
                headers={"Accept": "application/json"},
            )
        if response.status_code != 200:
            raise OAuthInvalidClientError()
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type:
            raise OAuthInvalidClientError()
        if len(response.content) > 64_000:
            raise OAuthInvalidClientError()
        payload = response.json()
        if not isinstance(payload, dict):
            raise OAuthInvalidClientError()
        return payload

    def _validate_authorization_request(
        self,
        *,
        client: MCPOAuthClient,
        redirect_uri: str,
        code_challenge: str,
        code_challenge_method: str,
        scope: str,
        resource: str,
        settings: MCPOAuthSettings,
    ) -> None:
        normalized_redirect = self._validate_redirect_uri(redirect_uri)
        if normalized_redirect not in client.redirect_uris:
            raise OAuthInvalidRequestError("redirect_uri is not registered for this client")
        if code_challenge_method != "S256":
            raise OAuthInvalidRequestError("Only S256 PKCE code challenges are supported")
        if not code_challenge:
            raise OAuthInvalidRequestError("code_challenge is required")
        if scope != MCP_OAUTH_SCOPE:
            raise OAuthInvalidRequestError("Only the mcp:access scope is supported")
        if resource not in self.allowed_resource_urls(settings):
            raise OAuthInvalidRequestError("Invalid MCP resource")

    def _validate_public_base_url(self, public_base_url: str, *, setting_name: str) -> None:
        parsed = urlparse(public_base_url)
        if not parsed.scheme or not parsed.netloc:
            raise OAuthConfigurationError(f"{setting_name} is required when MCP OAuth is enabled")
        hostname = parsed.hostname or ""
        is_loopback = hostname in {"localhost"} or self._is_loopback_ip(hostname)
        if parsed.scheme != "https" and not (parsed.scheme == "http" and is_loopback):
            raise OAuthConfigurationError(f"{setting_name} must be HTTPS except localhost development")
        if parsed.path not in {"", "/"}:
            raise OAuthConfigurationError(f"{setting_name} must not include a path")

    def _validate_redirect_uri(self, redirect_uri: Any) -> str:
        if not isinstance(redirect_uri, str) or not redirect_uri:
            raise OAuthInvalidClientError()
        parsed = urlparse(redirect_uri)
        hostname = parsed.hostname or ""
        if parsed.scheme != "http":
            raise OAuthInvalidClientError()
        if hostname not in {"localhost"} and not self._is_loopback_ip(hostname):
            raise OAuthInvalidClientError()
        if not parsed.path:
            raise OAuthInvalidClientError()
        if parsed.fragment:
            raise OAuthInvalidClientError()
        return redirect_uri

    def _assert_public_hostname(self, hostname: str) -> None:
        try:
            addresses = socket.getaddrinfo(hostname, None)
        except socket.gaierror as exc:
            raise OAuthInvalidClientError() from exc
        for *_, sockaddr in addresses:
            ip_value = sockaddr[0]
            if not self._is_public_ip(ip_value):
                raise OAuthInvalidClientError()

    @staticmethod
    def _is_loopback_ip(hostname: str) -> bool:
        try:
            return ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            return False

    @staticmethod
    def _is_public_ip(value: str) -> bool:
        try:
            ip = ipaddress.ip_address(value)
        except ValueError:
            return False
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )

    @staticmethod
    def _hash_secret(secret: str) -> str:
        return hashlib.blake2b(secret.encode("utf-8"), digest_size=32).hexdigest()

    @staticmethod
    def _verify_pkce(code_verifier: str, code_challenge: str) -> bool:
        if not (
            MIN_CODE_VERIFIER_LENGTH <= len(code_verifier) <= MAX_CODE_VERIFIER_LENGTH
        ):
            return False
        try:
            verifier_bytes = code_verifier.encode("ascii")
        except UnicodeEncodeError:
            return False
        digest = hashlib.sha256(verifier_bytes).digest()
        expected = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return hmac.compare_digest(expected, code_challenge)

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if isinstance(item, str) and item.strip()]

    @staticmethod
    def build_redirect_uri(redirect_uri: str, params: dict[str, str | None]) -> str:
        filtered = {k: v for k, v in params.items() if v is not None}
        separator = "&" if "?" in redirect_uri else "?"
        return f"{redirect_uri}{separator}{urlencode(filtered)}"

    @staticmethod
    def login_redirect_for_authorize(public_base_url: str, authorize_url: str) -> str:
        return f"{public_base_url}/login?next={quote(authorize_url, safe='')}"


mcp_oauth_service = MCPOAuthService()


__all__ = [
    "ACCESS_TOKEN_PREFIX",
    "MCP_OAUTH_SCOPE",
    "OAuthConfigurationError",
    "OAuthDisabledError",
    "OAuthInactiveUserError",
    "OAuthInvalidClientError",
    "OAuthInvalidGrantError",
    "OAuthInvalidRequestError",
    "OAuthInvalidTokenError",
    "OAuthTokenValidationResult",
    "mcp_oauth_service",
]
