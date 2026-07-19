"""Intercept identity bridge for FastMCP's native OIDC proxy."""

from __future__ import annotations

import hashlib
import logging
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.oidc_proxy import OIDCProxy
from key_value.aio.protocols import AsyncKeyValue
from mcp.server.auth.provider import (
    AuthorizationCode,
    OAuthClientInformationFull,
    OAuthToken,
    RefreshToken,
    TokenError,
)
from sqlalchemy import case, or_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from app.core.database import async_session_factory
from app.mcp.auth import MCP_ACCESS_SCOPE
from app.models.enums import UserStatus
from app.models.models import (
    MCPOAuthClient,
    MCPOAuthConsent,
    MCPOAuthProviderGrantReference,
    UserAccount,
)
from app.services.oidc_service import (
    OIDCAuthenticationError,
    OIDCIdentityPolicy,
    OIDCService,
    oidc_service,
)


CONNECTED_CLIENT_REFERENCE_COLLECTION = "intercept-mcp-client-references"
logger = logging.getLogger(__name__)


class OIDCIdentityError(RuntimeError):
    """Raised when the upstream OIDC response cannot identify a local user."""


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
    ) -> None:
        self._intercept_upstream_scopes = resolve_upstream_oidc_scopes(
            discovery_url=config_url,
            configured_scopes=configured_scopes,
        )
        self._intercept_session_factory = session_factory
        self._intercept_oidc_service = identity_service
        self._intercept_identity_policy = identity_policy

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
        self._install_exchange_tracking_store()

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

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        """Return native OAuth errors and remove orphaned upstream token sets."""

        self._install_exchange_tracking_store()
        persisted_token_ids: set[str] = set()
        context_token = self._intercept_exchange_token_ids.set(persisted_token_ids)
        try:
            return await super().exchange_authorization_code(
                client,
                authorization_code,
            )
        except (OIDCIdentityError, OIDCAuthenticationError) as exc:
            for token_id in persisted_token_ids:
                try:
                    await self._upstream_token_store.delete(key=token_id)
                except Exception:
                    logger.exception(
                        "Failed to remove rejected OIDC upstream token set %s",
                        token_id,
                    )
            raise TokenError(
                "invalid_grant",
                "The upstream OIDC identity could not be authorized",
            ) from exc
        finally:
            self._intercept_exchange_token_ids.reset(context_token)

    def _build_upstream_authorize_url(
        self,
        txn_id: str,
        transaction: dict[str, Any],
    ) -> str:
        upstream_transaction = transaction.copy()
        upstream_transaction["scopes"] = list(self._intercept_upstream_scopes)
        return super()._build_upstream_authorize_url(txn_id, upstream_transaction)

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
        id_token = idp_tokens.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise OIDCIdentityError("OIDC token response did not include an id_token")

        verified = await self._token_validator.verify_token(id_token)
        if verified is None:
            raise OIDCIdentityError("OIDC id_token validation failed")

        claims = verified.claims or {}
        issuer = str(self.oidc_config.issuer)
        async with self._intercept_session_factory() as db:
            user = await self._intercept_oidc_service.find_or_create_user(
                db,
                claims=claims,
                issuer=issuer,
                identity_policy=self._intercept_identity_policy,
            )
            await db.commit()

        return {
            "intercept_user_id": str(user.id),
            "auth_source": "oidc",
            "oidc_issuer": issuer,
            "oidc_subject": str(claims.get("sub") or ""),
        }

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Return a local reference-token principal after upstream validation."""

        validated = await super().load_access_token(token)
        if validated is None:
            return None

        token_payload = self.jwt_issuer.verify_token(token)
        local_claims = (validated.claims or {}).get("upstream_claims")
        if not isinstance(local_claims, dict):
            return None
        try:
            user_id = UUID(str(local_claims["intercept_user_id"]))
        except (KeyError, ValueError):
            return None

        async with self._intercept_session_factory() as db:
            user = await db.get(UserAccount, user_id)
            if user is None or user.status != UserStatus.ACTIVE:
                return None

        client_id = str(token_payload.get("client_id") or "")
        if not client_id:
            return None
        jti = str(token_payload.get("jti") or "")
        if not jti:
            return None

        jti_mapping = await self._jti_mapping_store.get(key=jti)
        if jti_mapping is None:
            return None
        upstream_tokens = await self._upstream_token_store.get(
            key=jti_mapping.upstream_token_id
        )
        if upstream_tokens is None:
            return None

        client_info = await self.get_client(client_id)
        reference_hash = hashlib.sha256(jti.encode("utf-8")).hexdigest()
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

        async with self._intercept_session_factory() as db:
            await self._record_connected_client_projection(
                db,
                user_id=user_id,
                client_id=client_id,
                client_info=client_info,
                reference_hash=reference_hash,
            )
            await db.commit()

        return validated.model_copy(
            update={
                # Keep the FastMCP reference token in request context. The upstream
                # token never leaves encrypted native storage.
                "token": token,
                "client_id": client_id,
                "scopes": [MCP_ACCESS_SCOPE],
                "resource": str(self._resource_url) if self._resource_url else None,
                "claims": dict(local_claims),
            }
        )

    async def _record_connected_client_projection(
        self,
        db: Any,
        *,
        user_id: UUID,
        client_id: str,
        client_info: Any,
        reference_hash: str,
    ) -> None:
        """Upsert user-facing metadata without copying native token material."""

        now = datetime.now(timezone.utc)

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
                "revoked_at": None,
            },
        ).returning(client_table.c.id)
        client_db_id = (await db.execute(client_upsert)).scalar_one()

        consent_table = MCPOAuthConsent.__table__
        consent_insert = postgresql_insert(consent_table).values(
            id=uuid4(),
            user_id=user_id,
            client_db_id=client_db_id,
            scope=MCP_ACCESS_SCOPE,
            provider_mode="oidc",
            provider_reference_hash=reference_hash,
            created_at=now,
            last_authorized_at=now,
            last_used_at=now,
            revoked_at=None,
        )
        reference_changed = or_(
            consent_table.c.provider_mode.is_distinct_from(
                consent_insert.excluded.provider_mode
            ),
            consent_table.c.provider_reference_hash.is_distinct_from(
                consent_insert.excluded.provider_reference_hash
            ),
        )
        consent_upsert = consent_insert.on_conflict_do_update(
            constraint="uq_mcp_oauth_consent_user_client_scope",
            set_={
                "provider_mode": consent_insert.excluded.provider_mode,
                "provider_reference_hash": (
                    consent_insert.excluded.provider_reference_hash
                ),
                "last_authorized_at": case(
                    (reference_changed, consent_insert.excluded.last_authorized_at),
                    else_=consent_table.c.last_authorized_at,
                ),
                "last_used_at": consent_insert.excluded.last_used_at,
                "revoked_at": None,
            },
        ).returning(consent_table.c.id)
        consent_id = (await db.execute(consent_upsert)).scalar_one()

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
                "consent_id": reference_insert.excluded.consent_id,
                "last_used_at": reference_insert.excluded.last_used_at,
                "revoked_at": None,
            },
        )
        await db.execute(reference_upsert)

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
    "InterceptOIDCProxy",
    "OIDCIdentityError",
    "oidc_authorize_parameters",
    "resolve_upstream_oidc_scopes",
]
