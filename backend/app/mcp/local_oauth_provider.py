"""FastMCP-native OAuth provider for Intercept's local authentication mode."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, AsyncIterator, Callable, Protocol
from uuid import UUID, uuid4

from fastmcp.server.auth import AccessToken, OAuthProvider
from fastmcp.server.auth.auth import (
    PrivateKeyJWTClientAuthenticator,
    TokenHandler,
)
from fastmcp.server.auth.cimd import CIMDClientManager, CIMDDocument
from mcp.server.auth.handlers.metadata import MetadataHandler
from mcp.server.auth.handlers.revoke import RevocationHandler
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.routes import build_metadata, cors_middleware
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.routing import Route

from app.models.enums import UserStatus
from app.models.models import (
    MCPOAuthClient,
    MCPOAuthPendingAuthorization,
    MCPOAuthToken,
    UserAccount,
)
from app.services.mcp_oauth_service import (
    MCP_OAUTH_SCOPE,
    MCPOAuthSettings,
    MCPOAuthError,
    MCPOAuthService,
    OAuthDisabledError,
    OAuthInvalidClientError,
    OAuthInvalidGrantError,
    mcp_oauth_service,
)

if TYPE_CHECKING:
    from app.services.audit_service import AuditContext


DEFAULT_PENDING_AUTHORIZATION_TTL_SECONDS = 300
logger = logging.getLogger(__name__)


class SnapshotMCPOAuthService(MCPOAuthService):
    """Existing OAuth persistence with immutable worker-startup settings."""

    def __init__(self, settings: MCPOAuthSettings, *, token_hash_key: bytes) -> None:
        super().__init__(token_hash_key=token_hash_key)
        self.settings = settings

    async def get_settings(self, _db: AsyncSession) -> MCPOAuthSettings:
        return self.settings

    async def get_enabled_settings(self, _db: AsyncSession) -> MCPOAuthSettings:
        if not self.settings.enabled:
            raise OAuthDisabledError()
        return self.settings


@dataclass(frozen=True, slots=True)
class PendingAuthorization:
    """Browser authorization request awaiting an Intercept user decision."""

    id: UUID
    client_id: str
    state: str | None
    scopes: list[str]
    code_challenge: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    resource: str | None
    created_at: datetime
    expires_at: datetime


class PendingAuthorizationStore(Protocol):
    """Persistence seam used by the consent route and OAuth provider."""

    async def create(self, pending: PendingAuthorization) -> None:
        pass

    async def get(self, request_id: UUID) -> PendingAuthorization | None:
        pass

    async def consume(self, request_id: UUID) -> PendingAuthorization | None:
        pass


class LocalOAuthBackend(Protocol):
    """Database operations needed by the FastMCP provider."""

    async def create_authorization_code(
        self,
        pending: PendingAuthorization,
        user: UserAccount,
        *,
        context: AuditContext | None = None,
    ) -> str:
        pass

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        pass

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        pass

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        pass

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        pass

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        pass

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        pass

    async def load_access_token(self, token: str) -> AccessToken | None:
        pass

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        pass


class PendingAuthorizationUnavailableError(Exception):
    """The browser authorization request is missing, consumed, or expired."""


class InterceptRefreshToken(RefreshToken):
    """FastMCP refresh token carrying its RFC 8707 resource binding."""

    resource: str | None = None


class SQLAlchemyPendingAuthorizationStore:
    """PostgreSQL-backed one-use browser authorization handoffs."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        service: MCPOAuthService = mcp_oauth_service,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.service = service
        self._now = now or (lambda: datetime.now(timezone.utc))

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def create(self, pending: PendingAuthorization) -> None:
        async with self._session() as session:
            client = await self.service.resolve_client(session, pending.client_id)
            session.add(
                MCPOAuthPendingAuthorization(
                    id=pending.id,
                    client_db_id=client.id,
                    state=pending.state,
                    scopes=pending.scopes,
                    code_challenge=pending.code_challenge,
                    redirect_uri=pending.redirect_uri,
                    redirect_uri_provided_explicitly=(
                        pending.redirect_uri_provided_explicitly
                    ),
                    resource=pending.resource,
                    created_at=pending.created_at,
                    expires_at=pending.expires_at,
                )
            )

    async def get(self, request_id: UUID) -> PendingAuthorization | None:
        async with self._session() as session:
            row = await self._load(session, request_id=request_id, for_update=False)
            return self._to_pending(row) if row is not None else None

    async def consume(self, request_id: UUID) -> PendingAuthorization | None:
        async with self._session() as session:
            row = await self._load(session, request_id=request_id, for_update=True)
            if row is None:
                return None
            pending_row, _ = row
            pending = self._to_pending(row)
            pending_row.consumed_at = self._now()
            return pending

    async def _load(
        self,
        session: AsyncSession,
        *,
        request_id: UUID,
        for_update: bool,
    ) -> tuple[MCPOAuthPendingAuthorization, MCPOAuthClient] | None:
        statement = (
            select(MCPOAuthPendingAuthorization, MCPOAuthClient)
            .join(
                MCPOAuthClient,
                MCPOAuthClient.id
                == MCPOAuthPendingAuthorization.client_db_id,
            )
            .where(MCPOAuthPendingAuthorization.id == request_id)
        )
        if for_update:
            statement = statement.with_for_update(of=MCPOAuthPendingAuthorization)
        result = await session.execute(statement)
        row = result.first()
        if row is None:
            return None
        pending, client = row
        if pending.consumed_at is not None or pending.expires_at <= self._now():
            return None
        return pending, client

    @staticmethod
    def _to_pending(
        row: tuple[MCPOAuthPendingAuthorization, MCPOAuthClient],
    ) -> PendingAuthorization:
        pending, client = row
        return PendingAuthorization(
            id=pending.id,
            client_id=client.client_id,
            state=pending.state,
            scopes=list(pending.scopes),
            code_challenge=pending.code_challenge,
            redirect_uri=pending.redirect_uri,
            redirect_uri_provided_explicitly=(
                pending.redirect_uri_provided_explicitly
            ),
            resource=pending.resource,
            created_at=pending.created_at,
            expires_at=pending.expires_at,
        )


class MCPOAuthDatabaseBackend:
    """Bridge FastMCP's provider contract to Intercept's OAuth persistence."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        service: MCPOAuthService = mcp_oauth_service,
        request_path: str = "/mcp/streamable/",
    ) -> None:
        self.session_factory = session_factory
        self.service = service
        self.request_path = request_path

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with self._session() as session:
            try:
                client = await self.service.resolve_client(session, client_id)
            except OAuthInvalidClientError:
                return None
            return self._client_information(client)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if client_info.client_id is None:
            raise RegistrationError(
                error="invalid_client_metadata",
                error_description="FastMCP client registration did not include client_id",
            )
        if client_info.token_endpoint_auth_method not in {
            "none",
            "private_key_jwt",
        }:
            raise RegistrationError(
                error="invalid_client_metadata",
                error_description=(
                    "Intercept supports public PKCE and CIMD private_key_jwt "
                    "clients only"
                ),
            )

        metadata = client_info.model_dump(mode="json", exclude_none=True)
        try:
            async with self._session() as session:
                # The existing public registration method generates its own ID. FastMCP
                # already generated the ID returned to the client, so use the service's
                # validated upsert primitive to persist that exact identifier.
                await self.service._upsert_client_from_metadata(  # noqa: SLF001
                    session,
                    metadata=metadata,
                    client_id=client_info.client_id,
                )
        except OAuthInvalidClientError as exc:
            raise RegistrationError(
                error="invalid_client_metadata",
                error_description="Invalid MCP OAuth client metadata",
            ) from exc

    async def create_authorization_code(
        self,
        pending: PendingAuthorization,
        user: UserAccount,
        *,
        context: AuditContext | None = None,
    ) -> str:
        async with self._session() as session:
            client = await self.service.resolve_client(session, pending.client_id)
            return await self.service.create_authorization_code(
                session,
                client=client,
                user=user,
                redirect_uri=pending.redirect_uri,
                code_challenge=pending.code_challenge,
                code_challenge_method="S256",
                scope=" ".join(pending.scopes),
                resource=pending.resource or "",
                context=context,
            )

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        if client.client_id is None:
            return None
        async with self._session() as session:
            try:
                stored_client = await self.service.resolve_client(
                    session, client.client_id
                )
            except OAuthInvalidClientError:
                return None
            stored = await self.service._load_authorization_code(  # noqa: SLF001
                session,
                code=authorization_code,
            )
            if (
                stored is None
                or stored.client_db_id != stored_client.id
                or stored.consumed_at is not None
            ):
                return None
            return AuthorizationCode(
                code=authorization_code,
                scopes=stored.scope.split(),
                expires_at=stored.expires_at.timestamp(),
                client_id=client.client_id,
                code_challenge=stored.code_challenge,
                redirect_uri=stored.redirect_uri,
                redirect_uri_provided_explicitly=True,
                resource=stored.resource,
            )

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        if client.client_id is None:
            raise TokenError("invalid_client", "OAuth client_id is required")
        now = datetime.now(timezone.utc)
        try:
            async with self._session() as session:
                stored_client = await self.service.resolve_client(
                    session, client.client_id
                )
                stored = await self.service._load_authorization_code(  # noqa: SLF001
                    session,
                    code=authorization_code.code,
                    for_update=True,
                )
                if (
                    stored is None
                    or stored.client_db_id != stored_client.id
                    or stored.consumed_at is not None
                    or stored.expires_at <= now
                ):
                    raise OAuthInvalidGrantError(
                        "Authorization code is invalid or expired"
                    )
                user = await session.get(UserAccount, stored.user_id)
                if user is None or user.status != UserStatus.ACTIVE:
                    raise OAuthInvalidGrantError("Intercept user is not active")

                stored.consumed_at = now
                settings = await self.service.get_enabled_settings(session)
                payload = await self.service._issue_token_pair(  # noqa: SLF001
                    session,
                    settings=settings,
                    client=stored_client,
                    user=user,
                    scope=stored.scope,
                    resource=stored.resource,
                    context=None,
                    event_type="auth.mcp_oauth.token_issued",
                )
                return OAuthToken.model_validate(payload)
        except MCPOAuthError as exc:
            raise TokenError("invalid_grant", exc.description) from exc

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        now = datetime.now(timezone.utc)
        async with self._session() as session:
            stored = await self.service._load_token(  # noqa: SLF001
                session,
                token=token.token,
                for_update=True,
            )
            if stored is None:
                return

            await self.service.revoke_token(
                session,
                token=token.token,
                client_id=token.client_id,
            )
            stored.revoked_at = now
            refresh_id = (
                stored.id if stored.token_type == "refresh" else stored.refresh_token_id
            )
            if refresh_id is not None:
                refresh = await session.get(MCPOAuthToken, refresh_id)
                if refresh is not None:
                    refresh.revoked_at = now
                await self.service._revoke_refresh_family(  # noqa: SLF001
                    session,
                    refresh_token_id=refresh_id,
                    now=now,
                )

    async def load_access_token(self, token: str) -> AccessToken | None:
        try:
            async with self._session() as session:
                validation = await self.service.validate_access_token(
                    session,
                    token=token,
                    request_path=self.request_path,
                )
                return AccessToken(
                    token=token,
                    client_id=validation.client.client_id,
                    scopes=validation.token.scope.split(),
                    expires_at=int(validation.token.expires_at.timestamp()),
                    resource=validation.token.resource,
                    claims={
                        "intercept_user_id": str(validation.user.id),
                        "auth_source": "oauth",
                        "client_id": validation.client.client_id,
                    },
                )
        except MCPOAuthError:
            return None

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        if client.client_id is None:
            return None
        now = datetime.now(timezone.utc)
        async with self._session() as session:
            try:
                stored_client = await self.service.resolve_client(
                    session, client.client_id
                )
            except OAuthInvalidClientError:
                return None
            stored = await self.service._load_token(  # noqa: SLF001
                session,
                token=refresh_token,
                for_update=True,
            )
            if (
                stored is None
                or stored.token_type != "refresh"
                or stored.client_db_id != stored_client.id
            ):
                return None
            if stored.revoked_at is not None or stored.expires_at <= now:
                stored.revoked_at = stored.revoked_at or now
                await self.service._revoke_refresh_family(  # noqa: SLF001
                    session,
                    refresh_token_id=stored.id,
                    now=now,
                )
                return None
            return InterceptRefreshToken(
                token=refresh_token,
                client_id=client.client_id,
                scopes=stored.scope.split(),
                expires_at=int(stored.expires_at.timestamp()),
                resource=stored.resource,
            )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        if client.client_id is None:
            raise TokenError("invalid_client", "OAuth client_id is required")
        if not set(scopes).issubset(refresh_token.scopes):
            raise TokenError(
                "invalid_scope", "Requested scopes exceed the refresh token grant"
            )
        resource = getattr(refresh_token, "resource", None)
        failure_description: str | None = None
        try:
            async with self._session() as session:
                stored_client = await self.service.resolve_client(
                    session, client.client_id
                )
                stored = await self.service._load_token(  # noqa: SLF001
                    session,
                    token=refresh_token.token,
                    for_update=True,
                )
                if (
                    stored is None
                    or stored.token_type != "refresh"
                    or stored.client_db_id != stored_client.id
                    or (resource is not None and stored.resource != resource)
                ):
                    failure_description = "Refresh token is invalid"
                elif (
                    stored.revoked_at is not None
                    or stored.expires_at <= datetime.now(timezone.utc)
                ):
                    replayed_at = datetime.now(timezone.utc)
                    stored.revoked_at = stored.revoked_at or replayed_at
                    await self.service._revoke_refresh_family(  # noqa: SLF001
                        session,
                        refresh_token_id=stored.id,
                        now=replayed_at,
                    )
                    failure_description = "Refresh token is invalid or already used"
                else:
                    payload = await self.service.refresh_access_token(
                        session,
                        refresh_token=refresh_token.token,
                        client_id=client.client_id,
                        resource=resource,
                    )
                    return OAuthToken.model_validate(payload)
        except MCPOAuthError as exc:
            raise TokenError("invalid_grant", exc.description) from exc
        raise TokenError(
            "invalid_grant",
            failure_description or "Refresh token is invalid",
        )

    @staticmethod
    def _client_information(client: object) -> OAuthClientInformationFull:
        metadata = dict(getattr(client, "client_metadata", {}) or {})
        metadata.update(
            {
                "client_id": getattr(client, "client_id"),
                "client_name": getattr(client, "client_name"),
                "client_uri": getattr(client, "client_uri"),
                "logo_uri": getattr(client, "logo_uri"),
                "redirect_uris": getattr(client, "redirect_uris"),
                "scope": getattr(client, "scope"),
                "grant_types": getattr(client, "grant_types"),
                "response_types": getattr(client, "response_types"),
                "token_endpoint_auth_method": getattr(
                    client, "token_endpoint_auth_method"
                ),
                "contacts": metadata.get("contacts"),
                "jwks_uri": getattr(client, "jwks_uri"),
            }
        )
        return OAuthClientInformationFull.model_validate(metadata)


class InterceptOAuthProvider(OAuthProvider):
    """FastMCP authorization server backed by Intercept's local accounts."""

    def __init__(
        self,
        *,
        public_base_url: str,
        pending_authorizations: PendingAuthorizationStore | None = None,
        backend: LocalOAuthBackend | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        service: MCPOAuthService = mcp_oauth_service,
        consent_base_url: str | None = None,
        pending_ttl_seconds: int = DEFAULT_PENDING_AUTHORIZATION_TTL_SECONDS,
        now: Callable[[], datetime] | None = None,
        request_id_factory: Callable[[], UUID] = uuid4,
        cimd_manager: CIMDClientManager | None = None,
    ) -> None:
        public_origin = public_base_url.rstrip("/")
        oauth_base_url = f"{public_origin}/mcp"
        super().__init__(
            base_url=oauth_base_url,
            resource_base_url=oauth_base_url,
            issuer_url=oauth_base_url,
            required_scopes=[MCP_OAUTH_SCOPE],
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=[MCP_OAUTH_SCOPE],
                default_scopes=[MCP_OAUTH_SCOPE],
            ),
            revocation_options=RevocationOptions(enabled=True),
        )
        if backend is None:
            if session_factory is None:
                raise TypeError("session_factory is required when backend is not provided")
            backend = MCPOAuthDatabaseBackend(
                session_factory=session_factory,
                service=service,
            )
        if pending_authorizations is None:
            if session_factory is None:
                raise TypeError(
                    "session_factory is required when pending_authorizations is not provided"
                )
            pending_authorizations = SQLAlchemyPendingAuthorizationStore(
                session_factory=session_factory,
                service=service,
                now=now,
            )
        self._backend = backend
        self.pending_authorizations = pending_authorizations
        self.consent_base_url = (
            consent_base_url or f"{public_origin}/api/v1/mcp/oauth/consent"
        ).rstrip("/")
        self.pending_ttl = timedelta(seconds=pending_ttl_seconds)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._request_id_factory = request_id_factory
        self._canonical_resource_url = f"{oauth_base_url}/streamable/"
        # FastMCP owns CIMD URL detection, SSRF-safe fetching, schema validation,
        # and HTTP caching. The relational grant store is only a projection used
        # by the local authorization-code and consent flows.
        self._cimd_manager = cimd_manager or CIMDClientManager(
            enable_cimd=True,
            default_scope=MCP_OAUTH_SCOPE,
        )

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        """Persist the OAuth request and hand the browser to Intercept consent."""
        if client.client_id is None:  # pragma: no cover - SDK always supplies it
            raise ValueError("OAuth client_id is required")

        requested_resource = str(params.resource) if params.resource else None
        if (
            requested_resource is not None
            and requested_resource.rstrip("/")
            != self._canonical_resource_url.rstrip("/")
        ):
            # mcp 1.24 (pinned through FastMCP 3.4.4) does not yet include
            # RFC 8707's invalid_target in AuthorizationErrorCode. Use its
            # native error type with invalid_request so the handler returns a
            # standards-shaped response instead of turning this into a 500.
            raise AuthorizeError(
                "invalid_request",
                "The requested resource is not this MCP server",
            )

        created_at = self._now()
        request_id = self._request_id_factory()
        pending = PendingAuthorization(
            id=request_id,
            client_id=client.client_id,
            state=params.state,
            scopes=list(params.scopes or [MCP_OAUTH_SCOPE]),
            code_challenge=params.code_challenge,
            redirect_uri=str(params.redirect_uri),
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=self._canonical_resource_url,
            created_at=created_at,
            expires_at=created_at + self.pending_ttl,
        )
        await self.pending_authorizations.create(pending)
        return f"{self.consent_base_url}/{request_id}"

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        if self._cimd_manager.is_cimd_client_id(client_id):
            return await self._get_cimd_client(client_id)
        return await self._backend.get_client(client_id)

    async def _get_cimd_client(
        self, client_id: str
    ) -> OAuthClientInformationFull | None:
        """Resolve and project exact-redirect native CIMD client metadata.

        ``CIMDClientManager`` performs the untrusted network fetch and all SSRF and
        document validation. Intercept persists a token-free projection for local
        consent and grant ownership. Wildcard redirect documents fail closed because
        the exact URI must survive the pending-consent and authorization-code flow.
        """
        client = await self._cimd_manager.get_client(client_id)
        if client is None:
            return None

        document = getattr(client, "cimd_document", None)
        if not isinstance(document, CIMDDocument):
            logger.warning("FastMCP returned a CIMD client without its document")
            return None
        if str(document.client_id).rstrip("/") != client_id.rstrip("/"):
            logger.warning("FastMCP CIMD client_id did not match the requested URL")
            return None
        if any("*" in redirect_uri for redirect_uri in document.redirect_uris):
            logger.warning(
                "Local OAuth rejected CIMD client %s: wildcard redirects are not "
                "supported by the relational authorization-code store",
                client_id,
            )
            return None

        scope = document.scope or MCP_OAUTH_SCOPE
        if set(scope.split()) != {MCP_OAUTH_SCOPE}:
            logger.warning(
                "Local OAuth rejected CIMD client %s: unsupported scope set",
                client_id,
            )
            return None
        if "authorization_code" not in document.grant_types:
            logger.warning(
                "Local OAuth rejected CIMD client %s: authorization_code is required",
                client_id,
            )
            return None
        if "code" not in document.response_types:
            logger.warning(
                "Local OAuth rejected CIMD client %s: code response type is required",
                client_id,
            )
            return None

        projection = OAuthClientInformationFull(
            client_id=client_id,
            redirect_uris=document.redirect_uris,
            token_endpoint_auth_method=document.token_endpoint_auth_method,
            grant_types=document.grant_types,
            response_types=document.response_types,
            scope=scope,
            client_name=document.client_name,
            client_uri=document.client_uri,
            logo_uri=document.logo_uri,
            contacts=document.contacts,
            tos_uri=document.tos_uri,
            policy_uri=document.policy_uri,
            jwks_uri=document.jwks_uri,
            jwks=document.jwks,
            software_id=document.software_id,
            software_version=document.software_version,
        )
        try:
            await self._backend.register_client(projection)
        except RegistrationError as exc:
            logger.warning(
                "Local OAuth could not persist native CIMD client %s: %s",
                client_id,
                exc.error_description or exc.error,
            )
            return None
        return client

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        """Expose FastMCP's native CIMD client-authentication contract.

        FastMCP's ``PrivateKeyJWTClientAuthenticator`` delegates assertion
        validation to ``CIMDClientManager`` while retaining the SDK's public-client
        path. The same authenticator protects token issuance and revocation, so
        discovery advertises exactly the two methods these handlers accept.
        """
        routes = super().get_routes(mcp_path)
        assert self.base_url is not None
        token_endpoint_url = f"{str(self.base_url).rstrip('/')}/token"
        client_authenticator = PrivateKeyJWTClientAuthenticator(
            provider=self,
            cimd_manager=self._cimd_manager,
            token_endpoint_url=token_endpoint_url,
        )

        metadata = build_metadata(
            self.base_url,
            self.service_documentation_url,
            self.client_registration_options or ClientRegistrationOptions(),
            self.revocation_options or RevocationOptions(),
        )
        metadata.client_id_metadata_document_supported = True
        metadata.token_endpoint_auth_methods_supported = [
            "none",
            "private_key_jwt",
        ]
        metadata.revocation_endpoint_auth_methods_supported = [
            "none",
            "private_key_jwt",
        ]
        metadata_handler = MetadataHandler(metadata)

        result: list[Route] = []
        for route in routes:
            if route.path == "/token" and route.methods and "POST" in route.methods:
                token_handler = TokenHandler(
                    provider=self,
                    client_authenticator=client_authenticator,
                )
                result.append(
                    Route(
                        path=route.path,
                        endpoint=cors_middleware(
                            token_handler.handle,
                            ["POST", "OPTIONS"],
                        ),
                        methods=["POST", "OPTIONS"],
                        name=route.name,
                        include_in_schema=route.include_in_schema,
                    )
                )
            elif route.path == "/revoke" and route.methods and "POST" in route.methods:
                revocation_handler = RevocationHandler(
                    provider=self,
                    client_authenticator=client_authenticator,
                )
                result.append(
                    Route(
                        path=route.path,
                        endpoint=cors_middleware(
                            revocation_handler.handle,
                            ["POST", "OPTIONS"],
                        ),
                        methods=["POST", "OPTIONS"],
                        name=route.name,
                        include_in_schema=route.include_in_schema,
                    )
                )
            elif route.path.startswith("/.well-known/oauth-authorization-server"):
                result.append(
                    Route(
                        path=route.path,
                        endpoint=cors_middleware(
                            metadata_handler.handle,
                            ["GET", "OPTIONS"],
                        ),
                        methods=route.methods or ["GET", "OPTIONS"],
                        name=route.name,
                        include_in_schema=route.include_in_schema,
                    )
                )
            else:
                result.append(route)
        return result

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        await self._backend.register_client(client_info)

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        return await self._backend.load_authorization_code(client, authorization_code)

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        return await self._backend.exchange_authorization_code(
            client, authorization_code
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        return await self._backend.load_access_token(token)

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        return await self._backend.load_refresh_token(client, refresh_token)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        return await self._backend.exchange_refresh_token(
            client, refresh_token, scopes
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        await self._backend.revoke_token(token)

    async def complete_authorization(
        self,
        request_id: UUID,
        *,
        user: UserAccount | None,
        approved: bool,
        context: AuditContext | None = None,
    ) -> str:
        """Consume a browser decision and return the MCP client's callback URL."""
        pending = await self.pending_authorizations.consume(request_id)
        if pending is None or pending.expires_at <= self._now():
            raise PendingAuthorizationUnavailableError(
                "OAuth authorization request is missing, expired, or already used"
            )

        if not approved:
            return construct_redirect_uri(
                pending.redirect_uri,
                error="access_denied",
                state=pending.state,
            )
        if user is None:
            raise PendingAuthorizationUnavailableError(
                "An authenticated Intercept user is required to approve MCP access"
            )

        code = await self._backend.create_authorization_code(
            pending,
            user,
            context=context,
        )
        return construct_redirect_uri(
            pending.redirect_uri,
            code=code,
            state=pending.state,
        )

    async def get_pending_authorization(
        self, request_id: UUID
    ) -> PendingAuthorization | None:
        """Load an unexpired browser request for the consent page."""
        return await self.pending_authorizations.get(request_id)


def create_local_oauth_provider(
    *,
    snapshot: object,
    session_factory: async_sessionmaker[AsyncSession],
    token_hash_key: bytes,
) -> InterceptOAuthProvider:
    """Create the startup-snapshotted local provider used by MCP runtime wiring."""
    public_origin = str(getattr(snapshot, "public_origin"))
    login_origin = str(getattr(snapshot, "login_origin", public_origin))
    snapshot_service = SnapshotMCPOAuthService(
        MCPOAuthSettings(
            enabled=True,
            public_base_url=public_origin,
            login_base_url=login_origin,
            access_token_ttl_seconds=int(
                getattr(snapshot, "access_token_ttl_seconds")
            ),
            refresh_token_ttl_days=int(getattr(snapshot, "refresh_token_ttl_days")),
        ),
        token_hash_key=token_hash_key,
    )
    return InterceptOAuthProvider(
        session_factory=session_factory,
        service=snapshot_service,
        public_base_url=public_origin,
        consent_base_url=f"{login_origin.rstrip('/')}/api/v1/mcp/oauth/consent",
    )


__all__ = [
    "DEFAULT_PENDING_AUTHORIZATION_TTL_SECONDS",
    "InterceptOAuthProvider",
    "LocalOAuthBackend",
    "MCPOAuthDatabaseBackend",
    "PendingAuthorization",
    "PendingAuthorizationStore",
    "PendingAuthorizationUnavailableError",
    "SQLAlchemyPendingAuthorizationStore",
    "SnapshotMCPOAuthService",
    "create_local_oauth_provider",
]
