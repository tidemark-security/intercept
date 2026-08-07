"""Intercept identity bridge for FastMCP's native OIDC proxy."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.auth import PrivateKeyJWTClientAuthenticator
from fastmcp.server.auth.oidc_proxy import OIDCProxy
from key_value.aio.protocols import AsyncKeyValue
from mcp.server.auth.handlers.metadata import MetadataHandler
from mcp.server.auth.handlers.revoke import RevocationHandler
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthClientInformationFull,
    OAuthToken,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.server.auth.routes import build_metadata, cors_middleware
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from app.core.account_authentication import non_password_authentication_allowed
from app.core.database import async_session_factory
from app.core.settings_registry import get_local
from app.mcp.auth import MCP_ACCESS_SCOPE, normalize_public_dcr_client
from app.mcp.cimd import (
    BoundedCIMDClientManager,
    cimd_fetch_requires_network,
    trim_cimd_cache,
)
from app.models.models import (
    MCPOAuthClient,
    MCPOAuthConsent,
    MCPOAuthProviderGrantReference,
    UserAccount,
)
from app.services.credential_invalidation import credential_was_issued_after_cutoff
from app.services.oidc_claim_contract import (
    OIDCClaimContractError,
    validate_oidc_claim_contract,
    validate_oidc_clock_skew,
)
from app.services.oidc_service import (
    OIDCAuthenticationError,
    OIDCConfigurationError,
    OIDCIdentityPolicy,
    OIDCService,
    oidc_service,
    validate_oidc_provider_metadata,
)
from app.services.mcp_registration_service import (
    MCPAuthorizationCapacityLimitError,
    MCPDCRRegistrationService,
    MCPOAuthAuthorizationCapacityService,
    MCPRegistrationExpiredError,
    MCPRegistrationLimitError,
    MCPRegistrationPolicy,
    authorization_request_active,
)
from app.services.mcp_oauth_service import (
    MCPOAuthError,
    mcp_oauth_service,
)


CONNECTED_CLIENT_REFERENCE_COLLECTION = "intercept-mcp-client-references"
INTERCEPT_AUTHORIZATION_EPOCH_CLAIM = "intercept_authorization_epoch"
INTERCEPT_CREDENTIAL_VALIDATED_AT_CLAIM = "intercept_credentials_validated_at"
INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM = (
    "intercept_credential_family_started_at"
)
OIDC_GRANT_REFERENCE_HASH_CLAIM = "oidc_grant_reference_hash"
VALIDATED_ID_TOKEN_MARKER = "_intercept_validated_id_token"
_MARKER_FIELDS = frozenset(
    {
        "claims",
        "authorization_epoch",
        "validated_at",
        "credential_family_started_at",
        "nonce",
        "mac",
    }
)
logger = logging.getLogger(__name__)


class OIDCIdentityError(RuntimeError):
    """Raised when the upstream OIDC response cannot identify a local user."""


def _provider_reference_hash(upstream_token_id: str) -> str:
    """Return the durable identifier for one native upstream token family."""

    return hashlib.sha256(upstream_token_id.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class _OIDCCallbackValidationContext:
    nonce: str
    authorization_epoch: int
    credential_family_started_at: float


class _OIDCValidatingClient:
    """Validate OIDC token responses before the SDK can persist client code."""

    def __init__(self, delegate: Any, owner: "InterceptOIDCProxy") -> None:
        self._delegate = delegate
        self._owner = owner

    async def fetch_token(self, **kwargs: Any) -> dict[str, Any]:
        response = await self._delegate.fetch_token(**kwargs)
        return await self._owner._validate_callback_token_response(response)

    async def refresh_token(self, **kwargs: Any) -> dict[str, Any]:
        response = await self._delegate.refresh_token(**kwargs)
        return await self._owner._validate_refresh_token_response(response)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class _ExchangeTrackingStore:
    """Track native upstream-token writes in the current exchange task."""

    def __init__(
        self,
        delegate: Any,
        active_keys: ContextVar[set[str] | None],
    ) -> None:
        self._delegate = delegate
        self._active_keys = active_keys

    async def put(self, *, key: str, value: Any, **kwargs: Any) -> Any:
        result = await self._delegate.put(key=key, value=value, **kwargs)
        keys = self._active_keys.get()
        if keys is not None:
            keys.add(key)
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class _AuthorizationCapacityStore:
    """Bind native OIDC transactions to durable authorization capacity."""

    def __init__(
        self,
        delegate: Any,
        capacity: MCPOAuthAuthorizationCapacityService,
        prefetch_reservation: ContextVar[tuple[str, str] | None],
    ) -> None:
        self._delegate = delegate
        self._capacity = capacity
        self._prefetch_reservation = prefetch_reservation

    async def put(self, *, key: str, value: Any, **kwargs: Any) -> Any:
        client_id = str(value.client_id)
        ttl_seconds = max(int(kwargs.get("ttl") or 15 * 60), 1)
        prefetch = self._prefetch_reservation.get()
        cleanup_ids = [key]
        if prefetch is not None and prefetch[1] == client_id:
            cleanup_ids.append(prefetch[0])
        try:
            if prefetch is not None and prefetch[1] == client_id:
                await self._capacity.promote(
                    reservation_id=prefetch[0],
                    pending_id=key,
                    client_id=client_id,
                    ttl_seconds=ttl_seconds,
                )
            else:
                await self._capacity.reserve(
                    reservation_id=key,
                    client_id=client_id,
                    provider_mode="oidc",
                    ttl_seconds=ttl_seconds,
                )
            return await self._delegate.put(key=key, value=value, **kwargs)
        except Exception:
            for reservation_id in dict.fromkeys(cleanup_ids):
                await self._capacity.release(reservation_id)
            raise
        finally:
            self._prefetch_reservation.set(None)

    async def delete(self, *, key: str, **kwargs: Any) -> Any:
        result = await self._delegate.delete(key=key, **kwargs)
        await self._capacity.release(key)
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


def _provider_kind(discovery_url: str) -> str:
    hostname = (urlsplit(discovery_url).hostname or "").lower()
    if hostname == "accounts.google.com" or hostname.endswith(".google.com"):
        return "google"
    if hostname == "login.microsoftonline.com" or hostname.endswith(
        ".microsoftonline.com"
    ):
        return "entra"
    return "generic"


def _deduplicate_scopes(scopes: list[str]) -> list[str]:
    return list(dict.fromkeys(scope for scope in scopes if scope))


def resolve_upstream_oidc_scopes(
    *,
    discovery_url: str,
    configured_scopes: str,
) -> list[str]:
    """Resolve IdP wire scopes while keeping ``mcp:access`` client-facing."""

    scopes = _deduplicate_scopes(str(configured_scopes or "").split())
    scopes = [scope for scope in scopes if scope != MCP_ACCESS_SCOPE]
    if _provider_kind(discovery_url) == "entra":
        scopes = _deduplicate_scopes([*scopes, "offline_access"])
    return scopes


def oidc_authorize_parameters(discovery_url: str) -> dict[str, str]:
    """Return provider-specific parameters needed for durable user sessions."""

    if _provider_kind(discovery_url) == "google":
        return {"access_type": "offline", "prompt": "consent"}
    return {}


class InterceptOIDCProxy(OIDCProxy):
    """OIDCProxy that translates scopes and binds validated users to Intercept."""

    def get_oidc_configuration(
        self,
        config_url: Any,
        strict: bool | None,
        timeout_seconds: int | None,
    ) -> Any:
        """Apply Intercept's discovery-metadata contract before endpoint use."""

        configuration = super().get_oidc_configuration(
            config_url,
            strict,
            timeout_seconds,
        )
        validate_oidc_provider_metadata(configuration.model_dump(mode="json"))
        return configuration

    def __init__(
        self,
        *,
        config_url: str,
        client_id: str,
        client_secret: str,
        configured_scopes: str,
        base_url: str,
        resource_base_url: str,
        client_storage: AsyncKeyValue,
        jwt_signing_key: bytes,
        identity_policy: OIDCIdentityPolicy,
        session_factory: Callable[..., Any] = async_session_factory,
        identity_service: OIDCService = oidc_service,
        fastmcp_access_token_expiry_seconds: int | None = None,
        fallback_access_token_expiry_seconds: int | None = None,
        fallback_refresh_token_expiry_seconds: int | None = None,
        registration_policy: MCPRegistrationPolicy | None = None,
        registration_service: MCPDCRRegistrationService | None = None,
        authorization_capacity_service: (
            MCPOAuthAuthorizationCapacityService | None
        ) = None,
    ) -> None:
        self._intercept_upstream_scopes = resolve_upstream_oidc_scopes(
            discovery_url=config_url,
            configured_scopes=configured_scopes,
        )
        self._intercept_session_factory = session_factory
        self._intercept_oidc_service = identity_service
        self._intercept_identity_policy = identity_policy
        self._registration_policy = registration_policy or MCPRegistrationPolicy()
        self._registration_service = registration_service
        if self._registration_service is None and registration_policy is not None:
            self._registration_service = MCPDCRRegistrationService(
                session_factory=session_factory,
                policy=registration_policy,
            )
        self._authorization_capacity_service = authorization_capacity_service
        if self._authorization_capacity_service is None and registration_policy is not None:
            self._authorization_capacity_service = MCPOAuthAuthorizationCapacityService(
                session_factory=session_factory,
                policy=registration_policy,
            )
        self._cimd_prefetch_reservation: ContextVar[
            tuple[str, str] | None
        ] = ContextVar(
            f"intercept_oidc_cimd_prefetch_reservation_{id(self)}",
            default=None,
        )

        super().__init__(
            config_url=config_url,
            strict=True,
            client_id=client_id,
            client_secret=client_secret,
            required_scopes=[MCP_ACCESS_SCOPE],
            verify_id_token=True,
            base_url=base_url,
            resource_base_url=resource_base_url,
            issuer_url=base_url,
            redirect_path="/auth/callback",
            client_storage=client_storage,
            jwt_signing_key=jwt_signing_key,
            require_authorization_consent="remember",
            forward_resource=False,
            extra_authorize_params=oidc_authorize_parameters(config_url),
            fastmcp_access_token_expiry_seconds=fastmcp_access_token_expiry_seconds,
            fallback_access_token_expiry_seconds=(
                fallback_access_token_expiry_seconds
            ),
            fallback_refresh_token_expiry_seconds=(
                fallback_refresh_token_expiry_seconds
            ),
            enable_cimd=True,
        )
        try:
            self._intercept_oidc_clock_skew_seconds = validate_oidc_clock_skew(
                get_local("oidc.clock_skew_seconds")
            )
        except ValueError as exc:
            raise OIDCConfigurationError(str(exc)) from exc
        self._oidc_callback_validation_context: ContextVar[
            _OIDCCallbackValidationContext | None
        ] = ContextVar(
            f"intercept_oidc_callback_validation_{id(self)}",
            default=None,
        )
        self._oidc_refresh_marker_context: ContextVar[
            dict[str, Any] | None
        ] = ContextVar(
            f"intercept_oidc_refresh_marker_{id(self)}",
            default=None,
        )
        self._cimd_manager = BoundedCIMDClientManager(
            enable_cimd=True,
            default_scope=self._default_scope_str,
            allowed_redirect_uri_patterns=self._allowed_client_redirect_uris,
            max_cache_entries=self._registration_policy.cimd_cache_max_entries,
        )
        if self._authorization_capacity_service is not None:
            self._transaction_store = _AuthorizationCapacityStore(
                self._transaction_store,
                self._authorization_capacity_service,
                self._cimd_prefetch_reservation,
            )
        self._install_exchange_tracking_store()

    def _uses_dcr_lease(self, client_id: str) -> bool:
        """Return whether this SDK-resolved client is governed by DCR limits."""

        cimd_manager = getattr(self, "_cimd_manager", None)
        return cimd_manager is None or not cimd_manager.is_cimd_client_id(client_id)

    def _install_exchange_tracking_store(self) -> None:
        if isinstance(self._upstream_token_store, _ExchangeTrackingStore):
            return
        active_keys = getattr(self, "_intercept_exchange_token_ids", None)
        if active_keys is None:
            active_keys = ContextVar(
                f"intercept_oidc_exchange_token_ids_{id(self)}",
                default=None,
            )
            self._intercept_exchange_token_ids = active_keys
        self._upstream_token_store = _ExchangeTrackingStore(
            self._upstream_token_store,
            active_keys,
        )

    async def get_client(
        self,
        client_id: str,
    ) -> OAuthClientInformationFull | None:
        """Resolve CIMD without creating an unbounded native client projection."""

        cimd_manager = getattr(self, "_cimd_manager", None)
        if cimd_manager is None or not cimd_manager.is_cimd_client_id(client_id):
            return await super().get_client(client_id)

        capacity = getattr(self, "_authorization_capacity_service", None)
        policy = getattr(self, "_registration_policy", MCPRegistrationPolicy())
        reservation_context = getattr(self, "_cimd_prefetch_reservation", None)
        authorization_active = authorization_request_active()
        existing_reservation = (
            reservation_context.get() if reservation_context is not None else None
        )
        if not (
            authorization_active
            and existing_reservation is not None
            and existing_reservation[1] == client_id
        ) and reservation_context is not None:
            reservation_context.set(None)
            if existing_reservation is not None and capacity is not None:
                await capacity.release(existing_reservation[0])
            existing_reservation = None
        reservation_id = (
            existing_reservation[0] if existing_reservation is not None else None
        )
        # A cold lookup owns only a transient fetch slot. An actual authorize
        # request may transfer that slot into the transaction-store prefetch.
        created_reservation_id: str | None = None
        if (
            capacity is not None
            and cimd_fetch_requires_network(cimd_manager, client_id)
            and reservation_id is None
        ):
            reservation_id = uuid4().hex
            try:
                await capacity.reserve(
                    reservation_id=reservation_id,
                    client_id=client_id,
                    provider_mode="oidc-cimd-fetch",
                    ttl_seconds=policy.cimd_fetch_reservation_ttl_seconds,
                )
                created_reservation_id = reservation_id
            except MCPAuthorizationCapacityLimitError:
                logger.warning("OIDC proxy rejected CIMD fetch at capacity")
                return None

        retain_created_reservation = False
        try:
            client = await cimd_manager.get_client(client_id)
            if (
                client is not None
                and reservation_context is not None
                and authorization_active
            ):
                reservation_context.set(
                    (reservation_id, client_id) if reservation_id else None
                )
                retain_created_reservation = created_reservation_id is not None
            return client
        finally:
            try:
                trim_cimd_cache(
                    cimd_manager,
                    max_entries=policy.cimd_cache_max_entries,
                )
            finally:
                if (
                    created_reservation_id is not None
                    and not retain_created_reservation
                    and capacity is not None
                ):
                    await capacity.release(created_reservation_id)

    async def register_client(
        self,
        client_info: OAuthClientInformationFull,
    ) -> None:
        """Register a public DCR client and never return a phantom secret."""

        normalized = normalize_public_dcr_client(client_info)
        client_id = normalized.client_id
        if client_id is None:  # pragma: no cover - SDK registration guarantees this
            raise RegistrationError(
                error="invalid_client_metadata",
                error_description="MCP registration did not include client_id",
            )

        reservation = None
        if self._registration_service is not None:
            try:
                reservation = await self._registration_service.reserve(
                    client_id=client_id,
                    provider_mode="oidc",
                )
            except MCPRegistrationLimitError as exc:
                raise RegistrationError(
                    error="invalid_client_metadata",
                    error_description=str(exc),
                ) from exc
        try:
            if reservation is not None:
                for expired_client_id in reservation.expired_client_ids:
                    await self._client_store.delete(key=expired_client_id)
                await self._registration_service.finalize_expired(
                    reservation.expired_client_ids
                )
            await super().register_client(normalized)
        except Exception:
            if self._registration_service is not None:
                await self._registration_service.release(client_id)
            raise

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        """Reject expired DCR clients before starting upstream consent."""

        if (
            self._registration_service is not None
            and client.client_id is not None
            and self._uses_dcr_lease(client.client_id)
        ):
            try:
                await self._registration_service.require_valid(client.client_id)
            except MCPRegistrationExpiredError as exc:
                raise AuthorizeError(
                    "invalid_request",
                    "The MCP client registration has expired",
                ) from exc
        try:
            return await super().authorize(client, params)
        except MCPAuthorizationCapacityLimitError as exc:
            raise AuthorizeError("invalid_request", str(exc)) from exc
        finally:
            reservation_context = getattr(
                self,
                "_cimd_prefetch_reservation",
                None,
            )
            if reservation_context is not None:
                prefetch = reservation_context.get()
                reservation_context.set(None)
                capacity = getattr(
                    self,
                    "_authorization_capacity_service",
                    None,
                )
                if prefetch is not None and capacity is not None:
                    await capacity.release(prefetch[0])

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        """Advertise exactly the authentication methods our handlers support."""

        routes = super().get_routes(mcp_path)
        cimd_manager = getattr(self, "_cimd_manager", None)
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
        if metadata.revocation_endpoint is not None:
            metadata.revocation_endpoint_auth_methods_supported = [
                "none",
                "private_key_jwt",
            ]
        metadata_handler = MetadataHandler(metadata)

        result: list[Route] = []
        for route in routes:
            if (
                cimd_manager is not None
                and route.path == "/revoke"
                and route.methods
                and "POST" in route.methods
            ):
                client_authenticator = PrivateKeyJWTClientAuthenticator(
                    provider=self,
                    cimd_manager=cimd_manager,
                    token_endpoint_url=(
                        f"{str(self.base_url).rstrip('/')}/token"
                    ),
                )
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

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        """Return native OAuth errors and remove orphaned upstream token sets."""

        self._install_exchange_tracking_store()
        registration_service = getattr(self, "_registration_service", None)
        persisted_token_ids: set[str] = set()
        context_token = self._intercept_exchange_token_ids.set(persisted_token_ids)
        try:
            current_user: UserAccount | None = None
            authorization_epoch: int | None = None
            authorization_started_at: datetime | None = None
            if (
                registration_service is not None
                and client.client_id is not None
                and self._uses_dcr_lease(client.client_id)
            ):
                try:
                    await registration_service.require_valid(client.client_id)
                except MCPRegistrationExpiredError as exc:
                    raise TokenError(
                        "invalid_grant",
                        "The MCP client registration has expired",
                    ) from exc
            try:
                token = await super().exchange_authorization_code(
                    client,
                    authorization_code,
                )
            except (OIDCIdentityError, OIDCAuthenticationError) as exc:
                await self._remove_issued_token_state(None, persisted_token_ids)
                raise TokenError(
                    "invalid_grant",
                    "The upstream OIDC identity could not be authorized",
                ) from exc

            # The upstream exchange and local token persistence can span an
            # administrator's disable or credential-invalidation action. Re-read
            # the account after the SDK has issued the signed local token, and
            # remove every persisted reference if the credential family is no
            # longer current.
            jwt_issuer = getattr(self, "jwt_issuer", None)
            if jwt_issuer is not None:
                try:
                    access_payload = jwt_issuer.verify_token(
                        token.access_token,
                        expected_token_use="access",
                    )
                    local_claims = access_payload.get("upstream_claims")
                    if isinstance(local_claims, dict):
                        authorization_epoch = self._authorization_epoch(
                            local_claims.get(INTERCEPT_AUTHORIZATION_EPOCH_CLAIM)
                        )
                        authorization_started_at = datetime.fromtimestamp(
                            self._server_epoch(
                                local_claims.get(
                                    INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM
                                ),
                                field_name="credential-family-start",
                            ),
                            tz=timezone.utc,
                        )
                    current_user = (
                        await self._current_local_user(local_claims)
                        if isinstance(local_claims, dict)
                        else None
                    )
                except Exception as exc:
                    await self._remove_issued_token_state(
                        token,
                        persisted_token_ids,
                    )
                    raise TokenError(
                        "invalid_grant",
                        "The upstream OIDC identity could not be authorized",
                    ) from exc
                if current_user is None:
                    await self._remove_issued_token_state(
                        token,
                        persisted_token_ids,
                    )
                    raise TokenError(
                        "invalid_grant",
                        "The upstream OIDC identity could not be authorized",
                    )
            if (
                registration_service is not None
                and client.client_id is not None
                and self._uses_dcr_lease(client.client_id)
            ):
                try:
                    await registration_service.activate(client.client_id)
                except MCPRegistrationExpiredError as exc:
                    await self._remove_issued_token_state(token, persisted_token_ids)
                    raise TokenError(
                        "invalid_grant",
                        "The MCP client registration has expired",
                    ) from exc
                except Exception as exc:
                    await self._remove_issued_token_state(token, persisted_token_ids)
                    raise TokenError(
                        "server_error",
                        "The MCP client lease could not be persisted",
                    ) from exc
            if (
                jwt_issuer is not None
                and current_user is not None
                and authorization_epoch is not None
                and authorization_started_at is not None
            ):
                try:
                    await self._project_issued_authorization(
                        client=client,
                        token=token,
                        user=current_user,
                        authorization_epoch=authorization_epoch,
                        authorization_started_at=authorization_started_at,
                    )
                except Exception as exc:
                    await self._remove_issued_token_state(
                        token,
                        persisted_token_ids,
                    )
                    raise TokenError(
                        "invalid_grant",
                        "The OIDC connected-client grant could not be persisted",
                    ) from exc
            return token
        finally:
            self._intercept_exchange_token_ids.reset(context_token)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        """Rotate a native refresh token and extend the DCR inactivity lease."""

        jwt_issuer = getattr(self, "jwt_issuer", None)
        local_claims: dict[str, Any] | None = None
        upstream_token_id: str | None = None
        refresh_context_token = None
        if jwt_issuer is not None:
            try:
                refresh_payload = jwt_issuer.verify_token(
                    refresh_token.token,
                    expected_token_use="refresh",
                )
            except Exception as exc:
                raise TokenError("invalid_grant", "Invalid refresh token") from exc
            local_claims = refresh_payload.get("upstream_claims")
            if (
                not isinstance(local_claims, dict)
                or await self._current_local_user(local_claims) is None
            ):
                raise TokenError(
                    "invalid_grant",
                    "Refresh token predates account credential invalidation",
                )
            try:
                refresh_jti = refresh_payload.get("jti")
                if not isinstance(refresh_jti, str) or not refresh_jti:
                    raise OIDCIdentityError("OIDC refresh mapping is missing")
                mapping = await self._jti_mapping_store.get(key=refresh_jti)
                if mapping is None:
                    raise OIDCIdentityError("OIDC refresh mapping is missing")
                upstream_token_id = str(mapping.upstream_token_id or "")
                if not upstream_token_id:
                    raise OIDCIdentityError("OIDC upstream token family is missing")
                upstream_tokens = await self._upstream_token_store.get(
                    key=upstream_token_id
                )
                if upstream_tokens is None:
                    raise OIDCIdentityError("OIDC upstream token family is missing")
                previous_marker = self._validated_id_token_marker(
                    upstream_tokens.raw_token_data
                )
                if previous_marker["authorization_epoch"] != (
                    self._authorization_epoch(
                        local_claims.get(INTERCEPT_AUTHORIZATION_EPOCH_CLAIM)
                    )
                ):
                    raise OIDCIdentityError(
                        "OIDC authorization epoch does not match"
                    )
            except (AttributeError, OIDCIdentityError) as exc:
                raise TokenError(
                    "invalid_grant",
                    "Refresh token does not reference a validated OIDC family",
                ) from exc
            refresh_context_token = self._refresh_marker_context_var().set(
                previous_marker
            )
            try:
                await self._require_active_provider_grant(
                    local_claims=local_claims,
                    client_id=str(client.client_id or ""),
                    upstream_token_id=upstream_token_id,
                    allow_unprojected=True,
                )
            except (MCPOAuthError, ValueError) as exc:
                raise TokenError(
                    "invalid_grant",
                    "The OIDC connected-client grant has been revoked",
                ) from exc

        try:
            registration_service = getattr(self, "_registration_service", None)
            if (
                registration_service is not None
                and client.client_id is not None
                and self._uses_dcr_lease(client.client_id)
            ):
                try:
                    await registration_service.require_valid(client.client_id)
                except MCPRegistrationExpiredError as exc:
                    raise TokenError(
                        "invalid_grant",
                        "The MCP client registration has expired",
                    ) from exc
            try:
                token = await super().exchange_refresh_token(
                    client,
                    refresh_token,
                    scopes,
                )
            except (OIDCIdentityError, OIDCAuthenticationError) as exc:
                raise TokenError(
                    "invalid_grant",
                    "The upstream OIDC identity could not be refreshed",
                ) from exc

            # The upstream round trip can span an administrator's disable and
            # re-enable action. Re-read the account after that work, using the
            # immutable family-start marker from the signed refresh token.
            if (
                local_claims is not None
                and await self._current_local_user(local_claims) is None
            ):
                await self._remove_issued_token_state(token)
                raise TokenError(
                    "invalid_grant",
                    "Refresh token predates account credential invalidation",
                )

            if local_claims is not None and upstream_token_id is not None:
                try:
                    await self._require_active_provider_grant(
                        local_claims=local_claims,
                        client_id=str(client.client_id or ""),
                        upstream_token_id=upstream_token_id,
                        allow_unprojected=True,
                    )
                except (MCPOAuthError, ValueError) as exc:
                    await self._remove_issued_token_state(
                        token,
                        {upstream_token_id},
                    )
                    raise TokenError(
                        "invalid_grant",
                        "The OIDC connected-client grant has been revoked",
                    ) from exc

            if (
                registration_service is not None
                and client.client_id is not None
                and self._uses_dcr_lease(client.client_id)
            ):
                try:
                    await registration_service.activate(client.client_id)
                except MCPRegistrationExpiredError as exc:
                    await self._remove_issued_token_state(token)
                    raise TokenError(
                        "invalid_grant",
                        "The MCP client registration has expired",
                    ) from exc
                except Exception as exc:
                    await self._remove_issued_token_state(token)
                    raise TokenError(
                        "server_error",
                        "The MCP client lease could not be persisted",
                    ) from exc
            return token
        finally:
            if refresh_context_token is not None:
                self._refresh_marker_context_var().reset(refresh_context_token)

    async def _remove_issued_token_state(
        self,
        token: OAuthToken | None,
        upstream_token_ids: set[str] | None = None,
    ) -> None:
        """Fail closed by removing every local reference to a rejected grant."""

        upstream_ids = set(upstream_token_ids or ())
        if token is not None:
            raw_tokens = [(token.access_token, "access")]
            if token.refresh_token:
                raw_tokens.append((token.refresh_token, "refresh"))
            for raw_token, token_use in raw_tokens:
                try:
                    payload = self.jwt_issuer.verify_token(
                        raw_token,
                        expected_token_use=token_use,
                    )
                    jti = str(payload["jti"])
                    mapping = await self._jti_mapping_store.get(key=jti)
                    if mapping is not None:
                        upstream_ids.add(mapping.upstream_token_id)
                    await self._jti_mapping_store.delete(key=jti)
                    if token_use == "refresh":
                        await self._refresh_token_store.delete(
                            key=hashlib.sha256(raw_token.encode()).hexdigest()
                        )
                except Exception:
                    logger.exception("Failed to remove rejected OIDC %s token", token_use)
        for token_id in upstream_ids:
            try:
                await self._upstream_token_store.delete(key=token_id)
            except Exception:
                logger.exception(
                    "Failed to remove rejected OIDC upstream token set %s",
                    token_id,
                )

    async def _project_issued_authorization(
        self,
        *,
        client: OAuthClientInformationFull,
        token: OAuthToken,
        user: UserAccount,
        authorization_epoch: int,
        authorization_started_at: datetime,
    ) -> str:
        """Persist a fresh authorization before returning its token family."""

        client_id = str(client.client_id or "")
        if not client_id:
            raise OIDCIdentityError("OIDC client identity is missing")
        access_payload = self.jwt_issuer.verify_token(
            token.access_token,
            expected_token_use="access",
        )
        jti = str(access_payload.get("jti") or "")
        if not jti:
            raise OIDCIdentityError("OIDC access mapping is missing")
        mapping = await self._jti_mapping_store.get(key=jti)
        if mapping is None:
            raise OIDCIdentityError("OIDC access mapping is missing")
        upstream_token_id = str(mapping.upstream_token_id or "")
        upstream_tokens = await self._upstream_token_store.get(
            key=upstream_token_id
        )
        if upstream_tokens is None:
            raise OIDCIdentityError("OIDC upstream token family is missing")
        marker = self._validated_id_token_marker(upstream_tokens.raw_token_data)
        if marker["authorization_epoch"] != authorization_epoch:
            raise OIDCIdentityError("OIDC authorization epoch does not match")

        reference_hash = _provider_reference_hash(upstream_token_id)
        family_expiries = [
            value
            for value in (
                access_payload.get("exp"),
                upstream_tokens.expires_at,
                upstream_tokens.refresh_token_expires_at,
            )
            if isinstance(value, (int, float))
        ]
        ttl = (
            max(int(max(family_expiries)) - int(time.time()), 1)
            if family_expiries
            else None
        )
        async with self._intercept_session_factory() as db:
            try:
                await self._record_connected_client_projection(
                    db,
                    user_id=user.id,
                    client_id=client_id,
                    client_info=client,
                    reference_hash=reference_hash,
                    reauthorize=True,
                    authorization_epoch=authorization_epoch,
                    authorization_started_at=authorization_started_at,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        await self._client_storage.put(
            key=reference_hash,
            value={
                "user_id": str(user.id),
                "client_id": client_id,
                "jti": jti,
                "upstream_token_id": upstream_token_id,
            },
            collection=CONNECTED_CLIENT_REFERENCE_COLLECTION,
            ttl=ttl,
        )
        return reference_hash

    async def _require_active_provider_grant(
        self,
        *,
        local_claims: dict[str, Any],
        client_id: str,
        upstream_token_id: str,
        allow_unprojected: bool,
    ) -> None:
        """Serialize token acceptance with durable OIDC family revocation."""

        try:
            user_id = UUID(str(local_claims["intercept_user_id"]))
        except (KeyError, ValueError) as exc:
            raise OIDCIdentityError("OIDC local identity is missing") from exc
        if not client_id or not upstream_token_id:
            raise OIDCIdentityError("OIDC token family identity is missing")

        async with self._intercept_session_factory() as db:
            try:
                await mcp_oauth_service.validate_provider_grant_reference(
                    db,
                    user_id=user_id,
                    client_id=client_id,
                    provider_reference_hash=_provider_reference_hash(
                        upstream_token_id
                    ),
                    allow_unprojected=allow_unprojected,
                    for_update=True,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    def _callback_validation_context_var(
        self,
    ) -> ContextVar[_OIDCCallbackValidationContext | None]:
        context = getattr(self, "_oidc_callback_validation_context", None)
        if context is None:
            context = ContextVar(
                f"intercept_oidc_callback_validation_{id(self)}",
                default=None,
            )
            self._oidc_callback_validation_context = context
        return context

    def _refresh_marker_context_var(
        self,
    ) -> ContextVar[dict[str, Any] | None]:
        context = getattr(self, "_oidc_refresh_marker_context", None)
        if context is None:
            context = ContextVar(
                f"intercept_oidc_refresh_marker_{id(self)}",
                default=None,
            )
            self._oidc_refresh_marker_context = context
        return context

    def _clock_skew_seconds(self) -> float:
        configured = getattr(
            self,
            "_intercept_oidc_clock_skew_seconds",
            None,
        )
        if configured is not None:
            return validate_oidc_clock_skew(configured)
        try:
            return validate_oidc_clock_skew(get_local("oidc.clock_skew_seconds"))
        except ValueError as exc:
            raise OIDCConfigurationError(str(exc)) from exc

    def _derive_oidc_nonce(self, txn_id: str) -> str:
        if not isinstance(txn_id, str) or not txn_id:
            raise OIDCIdentityError("OIDC transaction is invalid")
        digest = hmac.new(
            self._jwt_signing_key,
            b"intercept-fastmcp-oidc-nonce-v1\0" + txn_id.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def _marker_mac(
        self,
        marker: dict[str, Any],
        *,
        id_token: str,
    ) -> str:
        signed_payload = {
            "audience": self._upstream_client_id,
            "id_token_sha256": hashlib.sha256(
                id_token.encode("utf-8")
            ).hexdigest(),
            "issuer": str(self.oidc_config.issuer),
            **marker,
        }
        try:
            serialized = json.dumps(
                signed_payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise OIDCIdentityError("OIDC validated marker is malformed") from exc
        marker_key = hmac.new(
            self._jwt_signing_key,
            b"intercept-fastmcp-oidc-marker-key-v1",
            hashlib.sha256,
        ).digest()
        digest = hmac.new(
            marker_key,
            b"intercept-fastmcp-oidc-marker-v1\0" + serialized,
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    @staticmethod
    def _server_epoch(value: Any, *, field_name: str) -> float:
        if (
            not isinstance(value, float)
            or not math.isfinite(value)
            or value < 0
        ):
            raise OIDCIdentityError(f"OIDC {field_name} marker is invalid")
        return value

    @staticmethod
    def _authorization_epoch(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise OIDCIdentityError("OIDC authorization epoch is invalid")
        return value

    def _build_validated_id_token_marker(
        self,
        *,
        claims: dict[str, Any],
        authorization_epoch: int,
        validated_at: float,
        credential_family_started_at: float,
        nonce: str,
        id_token: str,
    ) -> dict[str, Any]:
        causal_epoch = self._authorization_epoch(authorization_epoch)
        validated_epoch = self._server_epoch(
            validated_at,
            field_name="validated-at",
        )
        family_epoch = self._server_epoch(
            credential_family_started_at,
            field_name="credential-family-start",
        )
        if family_epoch > validated_epoch + self._clock_skew_seconds():
            raise OIDCIdentityError("OIDC credential family marker is invalid")
        if not isinstance(nonce, str) or not nonce:
            raise OIDCIdentityError("OIDC nonce marker is invalid")
        if not isinstance(id_token, str) or not id_token:
            raise OIDCIdentityError("OIDC ID token marker is invalid")

        marker: dict[str, Any] = {
            "claims": dict(claims),
            "authorization_epoch": causal_epoch,
            "validated_at": validated_epoch,
            "credential_family_started_at": family_epoch,
            "nonce": nonce,
        }
        marker["mac"] = self._marker_mac(marker, id_token=id_token)
        return marker

    def _validated_id_token_marker(
        self,
        idp_tokens: dict[str, Any],
    ) -> dict[str, Any]:
        id_token = idp_tokens.get("id_token")
        raw_marker = idp_tokens.get(VALIDATED_ID_TOKEN_MARKER)
        if (
            not isinstance(id_token, str)
            or not id_token
            or not isinstance(raw_marker, dict)
            or set(raw_marker) != _MARKER_FIELDS
            or not isinstance(raw_marker.get("claims"), dict)
            or not isinstance(raw_marker.get("nonce"), str)
            or not raw_marker.get("nonce")
            or not isinstance(raw_marker.get("mac"), str)
            or not raw_marker.get("mac")
        ):
            raise OIDCIdentityError("OIDC token response was not server validated")

        marker = {
            "claims": dict(raw_marker["claims"]),
            "authorization_epoch": self._authorization_epoch(
                raw_marker.get("authorization_epoch")
            ),
            "validated_at": self._server_epoch(
                raw_marker.get("validated_at"),
                field_name="validated-at",
            ),
            "credential_family_started_at": self._server_epoch(
                raw_marker.get("credential_family_started_at"),
                field_name="credential-family-start",
            ),
            "nonce": raw_marker["nonce"],
        }
        expected_mac = self._marker_mac(marker, id_token=id_token)
        if not hmac.compare_digest(raw_marker["mac"], expected_mac):
            raise OIDCIdentityError("OIDC validated marker authentication failed")
        if (
            marker["credential_family_started_at"]
            > marker["validated_at"] + self._clock_skew_seconds()
        ):
            raise OIDCIdentityError("OIDC credential family marker is invalid")
        marker["mac"] = raw_marker["mac"]
        return marker

    async def _strictly_validate_id_token(
        self,
        id_token: str,
        *,
        expected_nonce: str,
        require_nonce: bool,
    ) -> dict[str, Any]:
        verified = await self._token_validator.verify_token(id_token)
        if verified is None:
            raise OIDCIdentityError("OIDC ID token validation failed")
        try:
            return validate_oidc_claim_contract(
                verified.claims,
                issuer=str(self.oidc_config.issuer),
                audience=self._upstream_client_id,
                expected_nonce=expected_nonce,
                require_nonce=require_nonce,
                clock_skew_seconds=self._clock_skew_seconds(),
            )
        except OIDCClaimContractError as exc:
            raise OIDCIdentityError("OIDC ID token claims are invalid") from exc

    async def _validate_callback_token_response(
        self,
        token_response: dict[str, Any],
    ) -> dict[str, Any]:
        context = self._callback_validation_context_var().get()
        if context is None:
            raise OIDCIdentityError("OIDC callback validation context is missing")

        sanitized = dict(token_response)
        sanitized.pop(VALIDATED_ID_TOKEN_MARKER, None)
        id_token = sanitized.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise OIDCIdentityError(
                "OIDC token response did not include an ID token"
            )
        claims = await self._strictly_validate_id_token(
            id_token,
            expected_nonce=context.nonce,
            require_nonce=True,
        )
        sanitized[VALIDATED_ID_TOKEN_MARKER] = (
            self._build_validated_id_token_marker(
                claims=claims,
                authorization_epoch=context.authorization_epoch,
                validated_at=float(time.time()),
                credential_family_started_at=(
                    context.credential_family_started_at
                ),
                nonce=context.nonce,
                id_token=id_token,
            )
        )
        return sanitized

    async def _validate_refresh_token_response(
        self,
        token_response: dict[str, Any],
    ) -> dict[str, Any]:
        previous_marker = self._refresh_marker_context_var().get()
        if previous_marker is None:
            raise OIDCIdentityError("OIDC refresh validation context is missing")

        sanitized = dict(token_response)
        sanitized.pop(VALIDATED_ID_TOKEN_MARKER, None)
        if "id_token" not in sanitized:
            raise OIDCIdentityError(
                "OIDC refresh response did not include a new ID token"
            )

        id_token = sanitized.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise OIDCIdentityError("OIDC refreshed ID token is invalid")
        claims = await self._strictly_validate_id_token(
            id_token,
            expected_nonce=str(previous_marker["nonce"]),
            require_nonce=False,
        )
        previous_subject = previous_marker["claims"].get("sub")
        current_subject = claims.get("sub")
        if (
            not isinstance(previous_subject, str)
            or not isinstance(current_subject, str)
            or not hmac.compare_digest(previous_subject, current_subject)
        ):
            raise OIDCIdentityError("OIDC refreshed subject changed")

        sanitized[VALIDATED_ID_TOKEN_MARKER] = (
            self._build_validated_id_token_marker(
                claims=claims,
                authorization_epoch=previous_marker["authorization_epoch"],
                validated_at=float(time.time()),
                credential_family_started_at=previous_marker[
                    "credential_family_started_at"
                ],
                nonce=previous_marker["nonce"],
                id_token=id_token,
            )
        )
        return sanitized

    @asynccontextmanager
    async def _upstream_oauth_client(self) -> AsyncIterator[Any]:
        async with super()._upstream_oauth_client() as oauth_client:
            yield _OIDCValidatingClient(oauth_client, self)

    async def _try_transparent_refresh(self, upstream_token_set: Any) -> Any:
        previous_marker = self._validated_id_token_marker(
            upstream_token_set.raw_token_data
        )
        context = self._refresh_marker_context_var()
        context_token = context.set(previous_marker)
        try:
            refreshed = await super()._try_transparent_refresh(upstream_token_set)
            try:
                self._validated_id_token_marker(refreshed.raw_token_data)
                local_claims = await self._extract_upstream_claims(
                    refreshed.raw_token_data
                )
                await self._require_active_provider_grant(
                    local_claims=local_claims,
                    client_id=str(refreshed.client_id or ""),
                    upstream_token_id=str(refreshed.upstream_token_id or ""),
                    allow_unprojected=True,
                )
                return refreshed
            except Exception:
                try:
                    await self._upstream_token_store.delete(
                        key=refreshed.upstream_token_id
                    )
                except Exception:
                    logger.exception(
                        "Failed to remove rejected transparent OIDC refresh"
                    )
                raise
        finally:
            context.reset(context_token)

    async def _handle_idp_callback(
        self,
        request: Request,
    ) -> HTMLResponse | RedirectResponse:
        context = self._callback_validation_context_var()
        context_token = None
        txn_id = request.query_params.get("state")
        if txn_id:
            try:
                transaction = await self._transaction_store.get(key=txn_id)
                capacity = getattr(
                    self,
                    "_authorization_capacity_service",
                    None,
                )
                if transaction is not None and capacity is not None:
                    authorization_epoch = (
                        await capacity.require_authorization_epoch(txn_id)
                    )
                    family_started_at = self._server_epoch(
                        transaction.created_at,
                        field_name="credential-family-start",
                    )
                    context_token = context.set(
                        _OIDCCallbackValidationContext(
                            nonce=self._derive_oidc_nonce(txn_id),
                            authorization_epoch=authorization_epoch,
                            credential_family_started_at=family_started_at,
                        )
                    )
            except Exception:
                logger.exception("Unable to bind OIDC callback validation context")
        try:
            return await super()._handle_idp_callback(request)
        finally:
            if context_token is not None:
                context.reset(context_token)

    def _build_upstream_authorize_url(
        self,
        txn_id: str,
        transaction: dict[str, Any],
    ) -> str:
        upstream_transaction = transaction.copy()
        upstream_transaction["scopes"] = list(self._intercept_upstream_scopes)
        upstream_url = super()._build_upstream_authorize_url(
            txn_id,
            upstream_transaction,
        )
        parsed = urlsplit(upstream_url)
        query = [
            (key, value)
            for key, value in parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )
            if key != "nonce"
        ]
        query.append(("nonce", self._derive_oidc_nonce(txn_id)))
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(query),
                parsed.fragment,
            )
        )

    def _prepare_scopes_for_token_exchange(self, scopes: list[str]) -> list[str]:
        _ = scopes
        return list(self._intercept_upstream_scopes)

    def _prepare_scopes_for_upstream_refresh(self, scopes: list[str]) -> list[str]:
        _ = scopes
        return list(self._intercept_upstream_scopes)

    def _translate_scopes_from_idp(self, scopes: list[str]) -> list[str]:
        _ = scopes
        return [MCP_ACCESS_SCOPE]

    async def _extract_upstream_claims(
        self,
        idp_tokens: dict[str, Any],
    ) -> dict[str, Any]:
        marker = self._validated_id_token_marker(idp_tokens)
        claims = marker["claims"]
        authorization_epoch = marker["authorization_epoch"]
        family_started_at = marker["credential_family_started_at"]
        issuer = str(self.oidc_config.issuer)
        async with self._intercept_session_factory() as db:
            user = await self._intercept_oidc_service.find_or_create_user(
                db,
                claims=claims,
                issuer=issuer,
                identity_policy=self._intercept_identity_policy,
            )
            if not credential_was_issued_after_cutoff(
                user,
                issued_at=family_started_at,
            ):
                raise OIDCAuthenticationError(
                    "OIDC credential predates account credential invalidation"
                )
            await db.commit()

        local_claims = {
            "intercept_user_id": str(user.id),
            "auth_source": "oidc",
            "oidc_issuer": issuer,
            "oidc_subject": str(claims.get("sub") or ""),
            INTERCEPT_AUTHORIZATION_EPOCH_CLAIM: authorization_epoch,
            INTERCEPT_CREDENTIAL_VALIDATED_AT_CLAIM: marker["validated_at"],
            INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM: family_started_at,
        }
        return local_claims

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Return a local reference-token principal after upstream validation."""

        try:
            token_payload = self.jwt_issuer.verify_token(token)
        except Exception:
            return None

        embedded_claims = token_payload.get("upstream_claims")
        if not isinstance(embedded_claims, dict):
            return None
        try:
            authorization_epoch = self._authorization_epoch(
                embedded_claims.get(INTERCEPT_AUTHORIZATION_EPOCH_CLAIM)
            )
        except OIDCIdentityError:
            return None
        if await self._current_local_user(embedded_claims) is None:
            return None

        client_id = str(token_payload.get("client_id") or "")
        jti = str(token_payload.get("jti") or "")
        if not client_id or not jti:
            return None
        jti_mapping = await self._jti_mapping_store.get(key=jti)
        if jti_mapping is None:
            return None
        upstream_tokens = await self._upstream_token_store.get(
            key=jti_mapping.upstream_token_id
        )
        if upstream_tokens is None:
            return None
        try:
            marker = self._validated_id_token_marker(
                upstream_tokens.raw_token_data
            )
            if marker["authorization_epoch"] != authorization_epoch:
                return None
        except (AttributeError, OIDCIdentityError):
            return None

        validated = await super().load_access_token(token)
        if validated is None:
            return None

        local_claims = (validated.claims or {}).get("upstream_claims")
        if not isinstance(local_claims, dict):
            return None
        try:
            authorization_epoch = self._authorization_epoch(
                local_claims.get(INTERCEPT_AUTHORIZATION_EPOCH_CLAIM)
            )
        except OIDCIdentityError:
            return None
        user = await self._current_local_user(local_claims)
        if user is None:
            return None
        user_id = user.id

        # Transparent refresh can replace the stored family during validation.
        # Re-read and authenticate the marker before projecting the grant.
        upstream_tokens = await self._upstream_token_store.get(
            key=jti_mapping.upstream_token_id
        )
        if upstream_tokens is None:
            return None
        try:
            marker = self._validated_id_token_marker(
                upstream_tokens.raw_token_data
            )
            if marker["authorization_epoch"] != authorization_epoch:
                return None
        except (AttributeError, OIDCIdentityError):
            return None

        client_info = await self.get_client(client_id)
        reference_hash = _provider_reference_hash(
            jti_mapping.upstream_token_id
        )
        family_expiries = [
            value
            for value in (
                token_payload.get("exp"),
                upstream_tokens.expires_at,
                upstream_tokens.refresh_token_expires_at,
            )
            if isinstance(value, (int, float))
        ]
        ttl = (
            max(int(max(family_expiries)) - int(time.time()), 1)
            if family_expiries
            else None
        )
        async with self._intercept_session_factory() as db:
            try:
                await self._record_connected_client_projection(
                    db,
                    user_id=user_id,
                    client_id=client_id,
                    client_info=client_info,
                    reference_hash=reference_hash,
                    reauthorize=False,
                    authorization_epoch=authorization_epoch,
                )
                await db.commit()
            except OIDCIdentityError:
                await db.rollback()
                await self._jti_mapping_store.delete(key=jti)
                await self._upstream_token_store.delete(
                    key=jti_mapping.upstream_token_id
                )
                return None

        await self._client_storage.put(
            key=reference_hash,
            value={
                "user_id": str(user_id),
                "client_id": client_id,
                "jti": jti,
                "upstream_token_id": jti_mapping.upstream_token_id,
            },
            collection=CONNECTED_CLIENT_REFERENCE_COLLECTION,
            ttl=ttl,
        )

        return validated.model_copy(
            update={
                # Keep the FastMCP reference token in request context. The upstream
                # token never leaves encrypted native storage.
                "token": token,
                "client_id": client_id,
                "scopes": [MCP_ACCESS_SCOPE],
                "resource": str(self._resource_url) if self._resource_url else None,
                "claims": {
                    **local_claims,
                    OIDC_GRANT_REFERENCE_HASH_CLAIM: reference_hash,
                },
            }
        )

    async def _current_local_user(
        self,
        local_claims: dict[str, Any],
    ) -> UserAccount | None:
        """Resolve an active local user whose credential marker is current."""

        try:
            user_id = UUID(str(local_claims["intercept_user_id"]))
        except (KeyError, ValueError):
            return None

        async with self._intercept_session_factory() as db:
            user = await db.get(UserAccount, user_id)
            if user is None or not non_password_authentication_allowed(user):
                return None
            if not credential_was_issued_after_cutoff(
                user,
                issued_at=local_claims.get(
                    INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM
                ),
            ):
                return None
            return user

    async def _record_connected_client_projection(
        self,
        db: Any,
        *,
        user_id: UUID,
        client_id: str,
        client_info: Any,
        reference_hash: str,
        reauthorize: bool = False,
        authorization_epoch: int | None = None,
        authorization_started_at: datetime | None = None,
    ) -> None:
        """Upsert token-free metadata without reviving a revoked family.

        A completed authorization-code exchange is the sole caller allowed to
        reopen consent. Ordinary token access may create a missing legacy
        projection, but may never clear an existing revocation tombstone.
        """

        now = datetime.now(timezone.utc)
        causal_epoch = self._authorization_epoch(authorization_epoch)
        authorized_at = authorization_started_at or now

        def string_value(name: str, *, limit: int = 2048) -> str | None:
            value = getattr(client_info, name, None) if client_info is not None else None
            if value is None:
                return None
            normalized = str(value).strip()
            return normalized[:limit] if normalized else None

        def string_list(name: str) -> list[str]:
            values = getattr(client_info, name, None) if client_info is not None else None
            return [str(value) for value in (values or [])]

        source = (
            "cimd"
            if client_info is not None
            and getattr(client_info, "cimd_document", None) is not None
            else "dcr"
        )
        metadata = {"registration_source": source}
        client_table = MCPOAuthClient.__table__
        client_insert = postgresql_insert(client_table).values(
            id=uuid4(),
            client_id=client_id,
            client_name=(string_value("client_name", limit=200) or "MCP Client"),
            client_uri=string_value("client_uri"),
            logo_uri=string_value("logo_uri"),
            redirect_uris=string_list("redirect_uris"),
            scope=MCP_ACCESS_SCOPE,
            grant_types=string_list("grant_types")
            or ["authorization_code", "refresh_token"],
            response_types=string_list("response_types") or ["code"],
            token_endpoint_auth_method="none",
            contacts=string_list("contacts"),
            jwks_uri=string_value("jwks_uri"),
            metadata=metadata,
            created_at=now,
            updated_at=now,
            last_seen_at=now,
            revoked_at=None,
        )
        client_upsert = client_insert.on_conflict_do_update(
            index_elements=[client_table.c.client_id],
            set_={
                "client_name": client_insert.excluded.client_name,
                "client_uri": client_insert.excluded.client_uri,
                "logo_uri": client_insert.excluded.logo_uri,
                "redirect_uris": client_insert.excluded.redirect_uris,
                "scope": client_insert.excluded.scope,
                "grant_types": client_insert.excluded.grant_types,
                "response_types": client_insert.excluded.response_types,
                "token_endpoint_auth_method": (
                    client_insert.excluded.token_endpoint_auth_method
                ),
                "contacts": client_insert.excluded.contacts,
                "jwks_uri": client_insert.excluded.jwks_uri,
                "metadata": client_insert.excluded.metadata,
                "updated_at": now,
                "last_seen_at": now,
            },
            where=client_table.c.revoked_at.is_(None),
        ).returning(client_table.c.id, client_table.c.revoked_at)
        client_row = (await db.execute(client_upsert)).first()
        if client_row is None or client_row.revoked_at is not None:
            raise OIDCIdentityError("OIDC client registration has been revoked")
        client_db_id = client_row.id

        consent_table = MCPOAuthConsent.__table__
        consent_insert = postgresql_insert(consent_table).values(
            id=uuid4(),
            user_id=user_id,
            client_db_id=client_db_id,
            scope=MCP_ACCESS_SCOPE,
            provider_mode="oidc",
            provider_reference_hash=reference_hash,
            created_at=now,
            last_authorized_at=authorized_at,
            last_authorization_epoch=causal_epoch,
            last_used_at=now,
            revoked_at=None,
            revocation_epoch=None,
        )
        consent_updates: dict[str, Any] = {
            "provider_mode": consent_insert.excluded.provider_mode,
            "provider_reference_hash": (
                consent_insert.excluded.provider_reference_hash
            ),
            "last_used_at": consent_insert.excluded.last_used_at,
        }
        if reauthorize:
            consent_updates.update(
                {
                    "last_authorized_at": (
                        consent_insert.excluded.last_authorized_at
                    ),
                    "last_authorization_epoch": (
                        consent_insert.excluded.last_authorization_epoch
                    ),
                    "revoked_at": None,
                    "revocation_epoch": None,
                }
            )
        consent_upsert = consent_insert.on_conflict_do_update(
            constraint="uq_mcp_oauth_consent_user_client_scope",
            set_=consent_updates,
            where=(
                (
                    (
                        consent_table.c.last_authorization_epoch
                        <= causal_epoch
                    )
                    & (
                        consent_table.c.revocation_epoch.is_(None)
                        | (consent_table.c.revocation_epoch < causal_epoch)
                    )
                )
                if reauthorize
                else consent_table.c.revoked_at.is_(None)
            ),
        ).returning(consent_table.c.id, consent_table.c.revoked_at)
        consent_row = (await db.execute(consent_upsert)).first()
        if consent_row is None or consent_row.revoked_at is not None:
            raise OIDCIdentityError("OIDC connected-client grant has been revoked")
        consent_id = consent_row.id

        reference_table = MCPOAuthProviderGrantReference.__table__
        reference_insert = postgresql_insert(reference_table).values(
            id=uuid4(),
            consent_id=consent_id,
            provider_reference_hash=reference_hash,
            created_at=now,
            last_used_at=now,
            revoked_at=None,
        )
        reference_upsert = reference_insert.on_conflict_do_update(
            constraint="uq_mcp_oauth_provider_grant_reference_hash",
            set_={
                "last_used_at": reference_insert.excluded.last_used_at,
            },
            where=(
                reference_table.c.consent_id
                == reference_insert.excluded.consent_id
            )
            & reference_table.c.revoked_at.is_(None),
        ).returning(reference_table.c.id, reference_table.c.revoked_at)
        reference_row = (await db.execute(reference_upsert)).first()
        if reference_row is None or reference_row.revoked_at is not None:
            raise OIDCIdentityError("OIDC token family has been revoked")

    async def revoke_projected_client(
        self,
        *,
        user_id: UUID,
        provider_reference_hash: str,
    ) -> bool:
        """Revoke a projected grant through FastMCP's encrypted native stores.

        Deleting the upstream token set invalidates every access and refresh JTI
        in that native token family. Individual stale JTI mappings are left for
        their native TTL cleanup because ``AsyncKeyValue`` intentionally has no
        collection-scanning API.
        """

        reference = await self._client_storage.get(
            key=provider_reference_hash,
            collection=CONNECTED_CLIENT_REFERENCE_COLLECTION,
        )
        if not isinstance(reference, dict):
            return False
        if str(reference.get("user_id") or "") != str(user_id):
            return False

        jti = str(reference.get("jti") or "")
        upstream_token_id = str(reference.get("upstream_token_id") or "")
        client_id = str(reference.get("client_id") or "")
        if not jti or not upstream_token_id or not client_id:
            return False

        upstream_tokens = await self._upstream_token_store.get(key=upstream_token_id)
        if upstream_tokens is not None:
            scopes = str(upstream_tokens.scope or "").split()
            await self.revoke_token(
                AccessToken(
                    token=upstream_tokens.access_token,
                    client_id=client_id,
                    scopes=scopes,
                )
            )
            if upstream_tokens.refresh_token:
                await self.revoke_token(
                    RefreshToken(
                        token=upstream_tokens.refresh_token,
                        client_id=client_id,
                        scopes=scopes,
                    )
                )

        await self._jti_mapping_store.delete(key=jti)
        await self._upstream_token_store.delete(key=upstream_token_id)
        await self._client_storage.delete(
            key=provider_reference_hash,
            collection=CONNECTED_CLIENT_REFERENCE_COLLECTION,
        )
        return True


__all__ = [
    "CONNECTED_CLIENT_REFERENCE_COLLECTION",
    "INTERCEPT_AUTHORIZATION_EPOCH_CLAIM",
    "INTERCEPT_CREDENTIAL_FAMILY_STARTED_AT_CLAIM",
    "INTERCEPT_CREDENTIAL_VALIDATED_AT_CLAIM",
    "InterceptOIDCProxy",
    "OIDCIdentityError",
    "VALIDATED_ID_TOKEN_MARKER",
    "oidc_authorize_parameters",
    "resolve_upstream_oidc_scopes",
]
