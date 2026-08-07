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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast
from urllib.parse import quote, urlencode, urlparse

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.account_authentication import non_password_authentication_allowed
from app.core.settings_registry import get_local
from app.mcp.auth import derive_mcp_keys
from app.models.models import (
    MCPOAuthAuthorizationCode,
    MCPOAuthClient,
    MCPOAuthClientRead,
    MCPOAuthConsent,
    MCPOAuthProviderGrantReference,
    MCPOAuthToken,
    UserAccount,
)
from app.services.audit_service import AuditContext, get_audit_service
from app.services.credential_invalidation import credential_was_issued_after_cutoff
from app.services.mcp_oauth_epoch import next_mcp_oauth_grant_epoch
from app.services.settings_service import SettingsService


MCP_OAUTH_SCOPE = "mcp:access"
ACCESS_TOKEN_PREFIX = "tmoa_"
REFRESH_TOKEN_PREFIX = "tmor_"
AUTH_CODE_PREFIX = "tmoc_"
CODE_TTL_SECONDS = 300
MIN_CODE_VERIFIER_LENGTH = 43
MAX_CODE_VERIFIER_LENGTH = 128
SECRET_HASH_SCHEME = "hmac-sha256:v1"


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


@dataclass(slots=True)
class OAuthProviderGrantValidationResult:
    consent: MCPOAuthConsent
    reference: MCPOAuthProviderGrantReference | None
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


class OAuthPasswordChangeRequiredError(MCPOAuthError):
    error = "invalid_token"
    description = "Password change required"


class MCPOAuthService:
    """Business logic for MCP OAuth registration, authorization, and tokens."""

    def __init__(self, *, token_hash_key: bytes | None = None) -> None:
        if token_hash_key is not None and len(token_hash_key) < 32:
            raise OAuthConfigurationError(
                "MCP OAuth token hashing key must be at least 32 bytes"
            )
        self._token_hash_key = token_hash_key

    @staticmethod
    def require_eligible_user(user: UserAccount | None) -> UserAccount:
        """Require a current user that may exercise an MCP OAuth grant."""
        if user is None or not non_password_authentication_allowed(user):
            raise OAuthInactiveUserError()
        if user.must_change_password:
            raise OAuthPasswordChangeRequiredError()
        return user

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

    def allowed_resource_urls(self, settings: MCPOAuthSettings) -> set[str]:
        base = settings.public_base_url
        return {
            f"{base}/mcp",
            f"{base}/mcp/",
            f"{base}/mcp/streamable",
            f"{base}/mcp/streamable/",
        }

    async def resolve_client(self, db: AsyncSession, client_id: str) -> MCPOAuthClient:
        result = await db.execute(
            select(MCPOAuthClient).where(cast(Any, MCPOAuthClient.client_id == client_id))
        )
        client = result.scalar_one_or_none()
        if client and client.revoked_at is None:
            return client
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
        user = self.require_eligible_user(
            await db.get(
                UserAccount,
                user.id,
                populate_existing=True,
                with_for_update=True,
            )
        )
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
            created_at=now,
        )
        db.add(auth_code)
        await self._remember_consent(
            db,
            user=user,
            client=client,
            scope=scope,
            authorized_at=now,
        )
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
        user_id = await self._authorization_code_user_id(db, code=code)
        if user_id is None:
            raise OAuthInvalidGrantError("Invalid authorization code")
        user = self.require_eligible_user(
            await db.get(
                UserAccount,
                user_id,
                populate_existing=True,
                with_for_update=True,
            )
        )
        consent = await self._get_consent(
            db,
            user=user,
            client=client,
            scope=MCP_OAUTH_SCOPE,
            for_update=True,
        )
        auth_code = await self._load_authorization_code(
            db,
            code=code,
            for_update=True,
        )
        if auth_code is None:
            raise OAuthInvalidGrantError("Invalid authorization code")
        now = datetime.now(timezone.utc)
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
        if auth_code.user_id != user.id:
            raise OAuthInvalidGrantError("Invalid authorization code")
        self._require_current_authorization_epoch(
            consent=consent,
            issued_at=auth_code.created_at,
        )
        if not credential_was_issued_after_cutoff(
            user,
            issued_at=auth_code.created_at,
        ):
            raise OAuthInvalidGrantError(
                "Authorization code predates account credential invalidation"
            )

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
        user_id = await self._token_user_id(db, token=refresh_token)
        if user_id is None:
            raise OAuthInvalidGrantError("Invalid refresh token")
        user = self.require_eligible_user(
            await db.get(
                UserAccount,
                user_id,
                populate_existing=True,
                with_for_update=True,
            )
        )
        old_refresh = await self._load_token(
            db,
            token=refresh_token,
            for_update=True,
        )
        if old_refresh is None or old_refresh.token_type != "refresh":
            raise OAuthInvalidGrantError("Invalid refresh token")
        now = datetime.now(timezone.utc)
        if old_refresh.revoked_at is not None:
            await self._revoke_refresh_family(
                db,
                refresh_token_id=old_refresh.id,
                now=now,
            )
            raise OAuthInvalidGrantError("Refresh token has been revoked")
        if old_refresh.expires_at <= now:
            old_refresh.revoked_at = now
            await self._revoke_refresh_family(
                db,
                refresh_token_id=old_refresh.id,
                now=now,
            )
            raise OAuthInvalidGrantError("Refresh token has expired")
        if old_refresh.client_db_id != client.id:
            raise OAuthInvalidGrantError("Refresh token was issued to a different client")
        if resource and resource != old_refresh.resource:
            raise OAuthInvalidGrantError("Resource does not match refresh token")

        if old_refresh.user_id != user.id:
            raise OAuthInvalidGrantError("Invalid refresh token")
        if not credential_was_issued_after_cutoff(
            user,
            issued_at=old_refresh.created_at,
        ):
            raise OAuthInvalidGrantError(
                "Refresh token predates account credential invalidation"
            )

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
        for_update: bool = False,
        skip_locked: bool = False,
        audit_success: bool = True,
    ) -> OAuthTokenValidationResult:
        settings = await self.get_enabled_settings(db)
        expected_resource = self.resource_url_for_path(settings, request_path)
        now = datetime.now(timezone.utc)
        oauth_token = await self._load_token(
            db,
            token=token,
            for_update=for_update,
            skip_locked=skip_locked,
        )
        if oauth_token is None:
            raise OAuthInvalidTokenError()

        user = await db.get(UserAccount, oauth_token.user_id)
        client = await db.get(MCPOAuthClient, oauth_token.client_db_id)
        if user is None or client is None:
            raise OAuthInvalidTokenError()
        if oauth_token.token_type != "access":
            raise OAuthInvalidTokenError()
        if oauth_token.revoked_at is not None:
            raise OAuthInvalidTokenError("Access token has been revoked")
        if oauth_token.expires_at <= now:
            oauth_token.revoked_at = now
            raise OAuthInvalidTokenError("Access token has expired")
        if client.revoked_at is not None:
            raise OAuthInvalidClientError()
        self.require_eligible_user(user)
        if not credential_was_issued_after_cutoff(
            user,
            issued_at=oauth_token.created_at,
        ):
            raise OAuthInvalidTokenError(
                "Access token predates account credential invalidation"
            )
        if oauth_token.scope != MCP_OAUTH_SCOPE:
            raise OAuthInvalidTokenError("Access token is missing required scope")
        if oauth_token.resource.rstrip("/") != expected_resource.rstrip("/"):
            raise OAuthInvalidTokenError("Access token resource does not match MCP endpoint")

        oauth_token.last_used_at = now
        client.last_seen_at = now
        if audit_success:
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

    async def validate_provider_grant_reference(
        self,
        db: AsyncSession,
        *,
        user_id: Any,
        client_id: str,
        provider_reference_hash: str,
        allow_unprojected: bool = False,
        for_update: bool = False,
        skip_locked: bool = False,
    ) -> OAuthProviderGrantValidationResult | None:
        """Validate one OIDC token family against its durable revocation state.

        ``allow_unprojected`` exists only for token families created before the
        durable projection was introduced. A revoked consent or any revoked
        family reference still fails closed. Tool execution always requires an
        exact projected reference and holds that row lock until completion.
        """

        consent_result = await db.execute(
            select(MCPOAuthConsent, MCPOAuthClient)
            .join(
                MCPOAuthClient,
                cast(Any, MCPOAuthClient.id == MCPOAuthConsent.client_db_id),
            )
            .where(cast(Any, MCPOAuthConsent.user_id == user_id))
            .where(cast(Any, MCPOAuthConsent.scope == MCP_OAUTH_SCOPE))
            .where(cast(Any, MCPOAuthClient.client_id == client_id))
        )
        consent_row = consent_result.first()
        if consent_row is None:
            if allow_unprojected:
                return None
            raise OAuthInvalidTokenError("OIDC grant is not projected")

        consent, client = consent_row
        if (
            consent.provider_mode != "oidc"
            or consent.revoked_at is not None
            or client.revoked_at is not None
        ):
            raise OAuthInvalidTokenError("OIDC grant has been revoked")

        reference_statement = select(MCPOAuthProviderGrantReference).where(
            cast(
                Any,
                MCPOAuthProviderGrantReference.consent_id == consent.id,
            ),
            cast(
                Any,
                MCPOAuthProviderGrantReference.provider_reference_hash
                == provider_reference_hash,
            ),
        )
        if for_update:
            reference_statement = reference_statement.execution_options(
                populate_existing=True
            ).with_for_update(
                of=MCPOAuthProviderGrantReference,
                skip_locked=skip_locked,
            )
        reference_result = await db.execute(reference_statement)
        reference = reference_result.scalar_one_or_none()
        if reference is None:
            if allow_unprojected:
                revoked_reference = await db.scalar(
                    select(MCPOAuthProviderGrantReference.id)
                    .where(
                        cast(
                            Any,
                            MCPOAuthProviderGrantReference.consent_id
                            == consent.id,
                        ),
                        cast(
                            Any,
                            MCPOAuthProviderGrantReference.revoked_at != None,  # noqa: E711
                        ),
                    )
                    .limit(1)
                )
                if revoked_reference is None:
                    return OAuthProviderGrantValidationResult(
                        consent=consent,
                        reference=None,
                        client=client,
                    )
            raise OAuthInvalidTokenError("OIDC grant reference is not active")
        if reference.revoked_at is not None:
            raise OAuthInvalidTokenError("OIDC grant reference has been revoked")
        return OAuthProviderGrantValidationResult(
            consent=consent,
            reference=reference,
            client=client,
        )

    async def revoke_token(
        self,
        db: AsyncSession,
        *,
        token: str,
        client_id: str | None = None,
        context: Optional[AuditContext] = None,
    ) -> None:
        await self.get_enabled_settings(db)
        oauth_token = await self._load_token(
            db,
            token=token,
            for_update=True,
        )
        if oauth_token is None:
            return
        if client_id:
            client = await self.resolve_client(db, client_id)
            if oauth_token.client_db_id != client.id:
                raise OAuthInvalidClientError()
        now = datetime.now(timezone.utc)
        oauth_token.revoked_at = now
        refresh_token_id = (
            oauth_token.id
            if oauth_token.token_type == "refresh"
            else oauth_token.refresh_token_id
        )
        if refresh_token_id is not None:
            await self._revoke_refresh_family(
                db,
                refresh_token_id=refresh_token_id,
                now=now,
            )
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
            last_used = (
                consent.last_used_at
                if consent.provider_mode == "oidc"
                else await self._last_used_at(db, user=user, client=client)
            )
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
        locked_user = await db.get(
            UserAccount,
            user.id,
            populate_existing=True,
            with_for_update=True,
        )
        if locked_user is None:
            raise OAuthInvalidRequestError("Connected MCP client not found")
        consent, client = await self.resolve_connected_client(
            db,
            user=locked_user,
            consent_id=consent_id,
            for_update=True,
        )
        now = datetime.now(timezone.utc)
        revocation_epoch = await next_mcp_oauth_grant_epoch(db)
        consent.revoked_at = now
        consent.revocation_epoch = revocation_epoch
        await db.execute(
            update(MCPOAuthAuthorizationCode)
            .where(
                cast(Any, MCPOAuthAuthorizationCode.user_id == locked_user.id),
                cast(Any, MCPOAuthAuthorizationCode.client_db_id == client.id),
                cast(Any, MCPOAuthAuthorizationCode.consumed_at == None),  # noqa: E711
            )
            .values(consumed_at=now)
        )
        if consent.provider_mode == "local":
            await self._revoke_user_client_tokens(
                db,
                user=locked_user,
                client=client,
                now=now,
            )
        else:
            references = await self.list_active_provider_grant_references(
                db,
                consent_id=consent.id,
            )
            for reference in references:
                reference.revoked_at = now
        await get_audit_service(db).log_event(
            event_type="auth.mcp_oauth.client_revoked",
            entity_type="mcp_oauth_client",
            entity_id=str(client.id),
            description="MCP OAuth client access revoked",
            new_value={"client_id": client.client_id, "client_name": client.client_name},
            performed_by=locked_user.username,
            context=context,
        )

    async def invalidate_user_grants(
        self,
        db: AsyncSession,
        *,
        user_id: Any,
        invalidated_at: datetime,
    ) -> None:
        """Permanently invalidate persisted MCP grants for one account."""

        revocation_epoch = await next_mcp_oauth_grant_epoch(db)

        await db.execute(
            update(MCPOAuthAuthorizationCode)
            .where(
                cast(Any, MCPOAuthAuthorizationCode.user_id == user_id),
                cast(Any, MCPOAuthAuthorizationCode.consumed_at == None),  # noqa: E711
            )
            .values(consumed_at=invalidated_at)
        )
        await db.execute(
            update(MCPOAuthToken)
            .where(
                cast(Any, MCPOAuthToken.user_id == user_id),
                cast(Any, MCPOAuthToken.revoked_at == None),  # noqa: E711
            )
            .values(revoked_at=invalidated_at)
        )
        consent_ids = select(MCPOAuthConsent.id).where(
            cast(Any, MCPOAuthConsent.user_id == user_id)
        )
        await db.execute(
            update(MCPOAuthProviderGrantReference)
            .where(
                cast(
                    Any,
                    MCPOAuthProviderGrantReference.consent_id.in_(consent_ids),
                ),
                cast(
                    Any,
                    MCPOAuthProviderGrantReference.revoked_at == None,  # noqa: E711
                ),
            )
            .values(revoked_at=invalidated_at)
        )
        await db.execute(
            update(MCPOAuthConsent)
            .where(cast(Any, MCPOAuthConsent.user_id == user_id))
            .values(
                revoked_at=func.coalesce(
                    MCPOAuthConsent.revoked_at,
                    invalidated_at,
                ),
                revocation_epoch=revocation_epoch,
            )
        )

    async def resolve_connected_client(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
        consent_id: Any,
        for_update: bool = False,
    ) -> tuple[MCPOAuthConsent, MCPOAuthClient]:
        """Load a user-owned connected-client projection for provider actions."""

        statement = (
            select(MCPOAuthConsent, MCPOAuthClient)
            .join(MCPOAuthClient, cast(Any, MCPOAuthClient.id == MCPOAuthConsent.client_db_id))
            .where(cast(Any, MCPOAuthConsent.id == consent_id))
            .where(cast(Any, MCPOAuthConsent.user_id == user.id))
        )
        if for_update:
            statement = statement.execution_options(
                populate_existing=True
            ).with_for_update(of=MCPOAuthConsent)
        result = await db.execute(statement)
        row = result.first()
        if row is None:
            raise OAuthInvalidRequestError("Connected MCP client not found")
        return row[0], row[1]

    async def list_active_provider_grant_references(
        self,
        db: AsyncSession,
        *,
        consent_id: Any,
    ) -> list[MCPOAuthProviderGrantReference]:
        """Lock active native-provider family references for user revocation."""

        result = await db.execute(
            select(MCPOAuthProviderGrantReference)
            .where(
                cast(
                    Any,
                    MCPOAuthProviderGrantReference.consent_id == consent_id,
                )
            )
            .where(
                cast(
                    Any,
                    MCPOAuthProviderGrantReference.revoked_at == None,  # noqa: E711
                )
            )
            .order_by(cast(Any, MCPOAuthProviderGrantReference.created_at))
            .with_for_update()
        )
        return list(result.scalars().all())

    async def lock_active_provider_grant_reference(
        self,
        db: AsyncSession,
        *,
        consent_id: Any,
        reference_id: Any,
    ) -> MCPOAuthProviderGrantReference | None:
        """Reacquire one family lock after a prior progress commit."""

        result = await db.execute(
            select(MCPOAuthProviderGrantReference)
            .where(
                cast(
                    Any,
                    MCPOAuthProviderGrantReference.id == reference_id,
                ),
                cast(
                    Any,
                    MCPOAuthProviderGrantReference.consent_id == consent_id,
                ),
                cast(
                    Any,
                    MCPOAuthProviderGrantReference.revoked_at == None,  # noqa: E711
                ),
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        return result.scalar_one_or_none()

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
        self.require_eligible_user(user)
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
        authorized_at: datetime | None = None,
    ) -> MCPOAuthConsent:
        now = authorized_at or datetime.now(timezone.utc)
        authorization_epoch = await next_mcp_oauth_grant_epoch(db)
        consent = await self._get_consent(
            db,
            user=user,
            client=client,
            scope=scope,
            for_update=True,
        )
        if consent is None:
            consent = MCPOAuthConsent(
                user_id=user.id,
                client_db_id=client.id,
                scope=scope,
                last_authorized_at=now,
                last_authorization_epoch=authorization_epoch,
            )
            db.add(consent)
        else:
            consent.revoked_at = None
            consent.revocation_epoch = None
            consent.last_authorized_at = now
            consent.last_authorization_epoch = authorization_epoch
            consent.provider_mode = "local"
            consent.provider_reference_hash = None
            references = await self.list_active_provider_grant_references(
                db,
                consent_id=consent.id,
            )
            for reference in references:
                reference.revoked_at = now
        return consent

    async def _get_consent(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
        client: MCPOAuthClient,
        scope: str,
        for_update: bool = False,
    ) -> MCPOAuthConsent | None:
        statement = (
            select(MCPOAuthConsent)
            .where(cast(Any, MCPOAuthConsent.user_id == user.id))
            .where(cast(Any, MCPOAuthConsent.client_db_id == client.id))
            .where(cast(Any, MCPOAuthConsent.scope == scope))
        )
        if for_update:
            statement = statement.execution_options(
                populate_existing=True
            ).with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    def _require_current_authorization_epoch(
        *,
        consent: MCPOAuthConsent | None,
        issued_at: datetime,
    ) -> None:
        """Reject a code that does not belong to the active consent epoch."""

        if (
            consent is None
            or consent.revoked_at is not None
            or issued_at < consent.last_authorized_at
        ):
            raise OAuthInvalidGrantError(
                "Authorization code predates connected-client authorization"
            )

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
        """Revoke a complete rotated refresh-token family and its access tokens."""

        result = await db.execute(
            select(MCPOAuthToken)
            .where(cast(Any, MCPOAuthToken.id == refresh_token_id))
            .with_for_update()
        )
        refresh = result.scalar_one_or_none()
        if refresh is None or refresh.token_type != "refresh":
            return

        family_ids = {refresh.id}
        ancestor = refresh
        while (
            ancestor.rotated_from_token_id is not None
            and ancestor.rotated_from_token_id not in family_ids
        ):
            result = await db.execute(
                select(MCPOAuthToken)
                .where(
                    cast(
                        Any,
                        MCPOAuthToken.id == ancestor.rotated_from_token_id,
                    )
                )
                .with_for_update()
            )
            parent = result.scalar_one_or_none()
            if parent is None or parent.token_type != "refresh":
                break
            family_ids.add(parent.id)
            ancestor = parent

        frontier = set(family_ids)
        while frontier:
            result = await db.execute(
                select(MCPOAuthToken)
                .where(cast(Any, MCPOAuthToken.token_type == "refresh"))
                .where(
                    cast(
                        Any,
                        MCPOAuthToken.rotated_from_token_id.in_(frontier),
                    )
                )
                .with_for_update()
            )
            descendants = [
                token
                for token in result.scalars().all()
                if token.id not in family_ids
            ]
            frontier = {token.id for token in descendants}
            family_ids.update(frontier)

        result = await db.execute(
            select(MCPOAuthToken)
            .where(
                cast(
                    Any,
                    or_(
                        MCPOAuthToken.id.in_(family_ids),
                        MCPOAuthToken.refresh_token_id.in_(family_ids),
                    ),
                )
            )
            .with_for_update()
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
        if token_auth_method not in {"none", "private_key_jwt"}:
            raise OAuthInvalidClientError()
        if token_auth_method == "private_key_jwt":
            parsed_client_id = urlparse(client_id)
            has_embedded_jwks = isinstance(metadata.get("jwks"), dict)
            has_jwks_uri = bool(self._optional_string(metadata.get("jwks_uri")))
            if (
                parsed_client_id.scheme != "https"
                or not parsed_client_id.netloc
                or not (has_embedded_jwks or has_jwks_uri)
            ):
                raise OAuthInvalidClientError()

        if any("*" in uri for uri in normalized_redirect_uris):
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
                grant_types=self._string_list(metadata.get("grant_types"))
                or ["authorization_code", "refresh_token"],
                response_types=self._string_list(metadata.get("response_types")) or ["code"],
                token_endpoint_auth_method=token_auth_method,
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
            client.grant_types = self._string_list(metadata.get("grant_types")) or [
                "authorization_code",
                "refresh_token",
            ]
            client.response_types = self._string_list(metadata.get("response_types")) or ["code"]
            client.token_endpoint_auth_method = token_auth_method
            client.contacts = self._string_list(metadata.get("contacts"))
            client.jwks_uri = self._optional_string(metadata.get("jwks_uri"))
            client.client_metadata = metadata
            client.updated_at = now
            client.revoked_at = None
        await db.flush()
        return client

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
        if not parsed.netloc or parsed.username is not None or parsed.password is not None:
            raise OAuthInvalidClientError()
        is_loopback = hostname == "localhost" or self._is_loopback_ip(hostname)
        if parsed.scheme != "https" and not (parsed.scheme == "http" and is_loopback):
            raise OAuthInvalidClientError()
        if not parsed.path:
            raise OAuthInvalidClientError()
        if parsed.fragment:
            raise OAuthInvalidClientError()
        try:
            _ = parsed.port
        except ValueError as exc:
            raise OAuthInvalidClientError() from exc
        return redirect_uri

    @staticmethod
    def _is_loopback_ip(hostname: str) -> bool:
        try:
            return ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            return False

    def _hash_secret(self, secret: str) -> str:
        """Return the current keyed, deterministic lookup digest."""
        if self._token_hash_key is None:
            raise OAuthConfigurationError(
                "MCP OAuth token hashing key is not configured"
            )
        digest = hmac.digest(
            self._token_hash_key,
            secret.encode("utf-8"),
            "sha256",
        ).hex()
        return f"{SECRET_HASH_SCHEME}:{digest}"

    @staticmethod
    def _legacy_hash_secret(secret: str) -> str:
        """Reproduce pre-HMAC indexes solely for an opportunistic data upgrade."""
        # These are 384-bit generated OAuth secrets, not human passwords. Retain
        # the old digest only for dual-read migration; all new writes use HMAC.
        return hashlib.blake2b(  # lgtm[py/weak-sensitive-data-hashing]
            secret.encode("utf-8"),
            digest_size=32,
        ).hexdigest()

    def _secret_hashes_for_lookup(self, secret: str) -> tuple[str, str]:
        return self._hash_secret(secret), self._legacy_hash_secret(secret)

    async def _load_authorization_code(
        self,
        db: AsyncSession,
        *,
        code: str,
        for_update: bool = False,
    ) -> MCPOAuthAuthorizationCode | None:
        current_hash, legacy_hash = self._secret_hashes_for_lookup(code)
        statement = select(MCPOAuthAuthorizationCode).where(
            cast(
                Any,
                MCPOAuthAuthorizationCode.code_hash.in_(
                    (current_hash, legacy_hash)
                ),
            )
        )
        if for_update:
            statement = statement.execution_options(
                populate_existing=True
            ).with_for_update()
        result = await db.execute(statement)
        authorization_code = result.scalar_one_or_none()
        if (
            authorization_code is not None
            and authorization_code.code_hash == legacy_hash
        ):
            authorization_code.code_hash = current_hash
        return authorization_code

    async def _authorization_code_user_id(
        self,
        db: AsyncSession,
        *,
        code: str,
    ) -> Any | None:
        """Resolve a code owner without mutating or locking the grant row."""

        current_hash, legacy_hash = self._secret_hashes_for_lookup(code)
        result = await db.execute(
            select(MCPOAuthAuthorizationCode.user_id).where(
                cast(
                    Any,
                    MCPOAuthAuthorizationCode.code_hash.in_(
                        (current_hash, legacy_hash)
                    ),
                )
            )
        )
        return result.scalar_one_or_none()

    async def _load_token(
        self,
        db: AsyncSession,
        *,
        token: str,
        for_update: bool = False,
        skip_locked: bool = False,
    ) -> MCPOAuthToken | None:
        current_hash, legacy_hash = self._secret_hashes_for_lookup(token)
        statement = select(MCPOAuthToken).where(
            cast(
                Any,
                MCPOAuthToken.token_hash.in_(
                    (current_hash, legacy_hash)
                ),
            )
        )
        if for_update:
            statement = statement.execution_options(
                populate_existing=True
            ).with_for_update(skip_locked=skip_locked)
        result = await db.execute(statement)
        oauth_token = result.scalar_one_or_none()
        if oauth_token is not None and oauth_token.token_hash == legacy_hash:
            oauth_token.token_hash = current_hash
        return oauth_token

    async def _token_user_id(
        self,
        db: AsyncSession,
        *,
        token: str,
    ) -> Any | None:
        """Resolve a token owner without mutating or locking the grant row."""

        current_hash, legacy_hash = self._secret_hashes_for_lookup(token)
        result = await db.execute(
            select(MCPOAuthToken.user_id).where(
                cast(
                    Any,
                    MCPOAuthToken.token_hash.in_((current_hash, legacy_hash)),
                )
            )
        )
        return result.scalar_one_or_none()

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


mcp_oauth_service = MCPOAuthService(
    token_hash_key=derive_mcp_keys(str(get_local("secret_key"))).token_hash_key
)


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
    "OAuthPasswordChangeRequiredError",
    "OAuthProviderGrantValidationResult",
    "OAuthTokenValidationResult",
    "mcp_oauth_service",
]
