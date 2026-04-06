from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
from typing import Any, Optional, cast
from urllib.parse import urlencode, urlparse

import httpx
import jwt
from jwt.exceptions import ExpiredSignatureError, PyJWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings_registry import get_local
from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import OIDCAuthRequest, USERNAME_REGEX, UserAccount
from app.services import get_audit_service
from app.services.auth_service import RequestMetadata
from app.services.settings_service import SettingsService


logger = logging.getLogger(__name__)


class OIDCConfigurationError(Exception):
    pass


class OIDCAuthenticationError(Exception):
    pass


class OIDCStateError(Exception):
    pass


@dataclass(slots=True)
class OIDCProviderConfiguration:
    discovery_url: str
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    client_id: str
    client_secret: Optional[str]
    scopes: str
    provider_name: str


class OIDCService:
    def __init__(self) -> None:
        pass

    async def get_public_config(self, db: AsyncSession) -> dict[str, Any]:
        settings = SettingsService(db)  # type: ignore[arg-type]
        enabled = bool(await settings.get("oidc.enabled", default=False))
        provider_name = str(await settings.get("oidc.provider_name", default="SSO"))
        return {"enabled": enabled, "providerName": provider_name}

    async def is_password_login_allowed(self, db: AsyncSession, *, user: UserAccount) -> bool:
        if user.role == UserRole.ADMIN:
            return True

        settings = SettingsService(db)  # type: ignore[arg-type]
        bypass_users = await settings.get("oidc.sso_bypass_users", default=[])
        if isinstance(bypass_users, str):
            bypass_users = [bypass_users]

        normalized = {str(item).strip().lower() for item in bypass_users if str(item).strip()}
        return user.username in normalized

    async def begin_login(
        self,
        db: AsyncSession,
        *,
        redirect_to: str,
        callback_url: str,
    ) -> tuple[str, datetime, str]:
        provider = await self._load_provider_configuration(db)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        browser_binding_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        auth_request = OIDCAuthRequest(
            state=state,
            nonce=nonce,
            browser_binding_hash=self._hash_browser_binding_token(browser_binding_token),
            redirect_to=redirect_to,
            expires_at=expires_at,
        )
        db.add(auth_request)
        await db.flush()

        params = {
            "client_id": provider.client_id,
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": provider.scopes,
            "state": state,
            "nonce": nonce,
        }
        return f"{provider.authorization_endpoint}?{urlencode(params)}", expires_at, browser_binding_token

    async def exchange_code(
        self,
        db: AsyncSession,
        *,
        code: str,
        state: str,
        callback_url: str,
        browser_binding_token: Optional[str],
    ) -> tuple[UserAccount, str, str, str]:
        auth_request = await self._consume_auth_request(
            db,
            state=state,
            browser_binding_token=browser_binding_token,
        )
        provider = await self._load_provider_configuration(db)

        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": callback_url,
            "client_id": provider.client_id,
        }
        auth: Optional[httpx.BasicAuth] = None
        if provider.client_secret:
            auth = httpx.BasicAuth(provider.client_id, provider.client_secret)

        async with httpx.AsyncClient(timeout=15.0) as client:
            if auth is not None:
                response = await client.post(provider.token_endpoint, data=token_data, auth=auth)
            else:
                response = await client.post(provider.token_endpoint, data=token_data)
            response.raise_for_status()
            token_payload = response.json()

            id_token = token_payload.get("id_token")
            if not isinstance(id_token, str) or not id_token:
                raise OIDCAuthenticationError("OIDC token response did not include an id_token")

            jwks_response = await client.get(provider.jwks_uri)
            jwks_response.raise_for_status()
            jwks = jwks_response.json()

        claims = self._validate_id_token(
            id_token=id_token,
            jwks=jwks,
            issuer=provider.issuer,
            audience=provider.client_id,
            expected_nonce=auth_request.nonce,
        )

        user = await self.find_or_create_user(db, claims=claims, issuer=provider.issuer)
        return user, provider.issuer, str(claims["sub"]), auth_request.redirect_to

    async def test_discovery(self, db: AsyncSession) -> dict[str, str | bool]:
        provider = await self._load_provider_configuration(db)
        return {
            "success": True,
            "message": (
                f"Discovery loaded for issuer {provider.issuer}. "
                "Authorization, token, and JWKS endpoints are available."
            ),
        }

    async def find_or_create_user(
        self,
        db: AsyncSession,
        *,
        claims: dict[str, Any],
        issuer: str,
        metadata: Optional[RequestMetadata] = None,
    ) -> UserAccount:
        subject = str(claims.get("sub") or "").strip()
        if not subject:
            raise OIDCAuthenticationError("OIDC claims did not include a subject")

        email = str(claims.get("email") or "").strip().lower()
        if not email:
            raise OIDCAuthenticationError("OIDC claims did not include an email address")

        result = await db.execute(
            select(UserAccount).where(
                cast(Any, UserAccount.oidc_issuer == issuer),
                cast(Any, UserAccount.oidc_subject == subject),
            )
        )
        user = result.scalar_one_or_none()
        if user is not None:
            if user.status != UserStatus.ACTIVE:
                raise OIDCAuthenticationError("OIDC-linked user account is not active")
            return user

        result = await db.execute(select(UserAccount).where(cast(Any, UserAccount.email == email)))
        user = result.scalar_one_or_none()
        if user is not None:
            if user.status != UserStatus.ACTIVE:
                raise OIDCAuthenticationError("OIDC-linked user account is not active")
            user.oidc_issuer = issuer
            user.oidc_subject = subject
            user.updated_at = datetime.now(timezone.utc)
            await get_audit_service(db).oidc_account_linked(
                user_id=user.id,
                username=user.username,
                oidc_issuer=issuer,
                oidc_subject=subject,
                context=metadata.to_audit_context() if metadata else None,
            )
            await db.flush()
            return user

        settings = SettingsService(db)  # type: ignore[arg-type]
        jit_enabled = bool(await settings.get("oidc.jit_provisioning", default=True))
        if not jit_enabled:
            raise OIDCAuthenticationError("OIDC sign-in is not enabled for unprovisioned users")

        username = self._derive_username(claims)
        if username is None:
            raise OIDCAuthenticationError("OIDC claims did not include a usable username")

        existing = await db.execute(select(UserAccount).where(cast(Any, UserAccount.username == username)))
        if existing.scalar_one_or_none() is not None:
            raise OIDCAuthenticationError("OIDC username collides with an existing account")

        role = await self.resolve_role(db, claims=claims)
        now = datetime.now(timezone.utc)
        user = UserAccount(
            username=username,
            email=email,
            role=role,
            status=UserStatus.ACTIVE,
            account_type=AccountType.HUMAN,
            password_hash=None,
            password_updated_at=None,
            must_change_password=False,
            failed_login_attempts=0,
            oidc_issuer=issuer,
            oidc_subject=subject,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        await db.flush()

        await get_audit_service(db).oidc_account_provisioned(
            user_id=user.id,
            username=user.username,
            role=user.role,
            oidc_issuer=issuer,
            oidc_subject=subject,
            context=metadata.to_audit_context() if metadata else None,
        )
        return user

    async def resolve_role(self, db: AsyncSession, *, claims: dict[str, Any]) -> UserRole:
        settings = SettingsService(db)  # type: ignore[arg-type]
        default_role = str(await settings.get("oidc.default_role", default=UserRole.ANALYST.value)).upper()
        role_claim_path = str(await settings.get("oidc.role_claim_path", default="")).strip()
        role_mapping = await settings.get("oidc.role_mapping", default={})
        if not isinstance(role_mapping, dict):
            role_mapping = {}

        if role_claim_path:
            claim_value = self._extract_claim_path(claims, role_claim_path)
            mapped_role = self._map_role(claim_value, role_mapping)
            if mapped_role is not None:
                return mapped_role

        try:
            return UserRole(default_role)
        except ValueError as exc:
            raise OIDCConfigurationError("OIDC default role is invalid") from exc

    async def _load_provider_configuration(self, db: AsyncSession) -> OIDCProviderConfiguration:
        settings = SettingsService(db)  # type: ignore[arg-type]
        discovery_url = await settings.get("oidc.discovery_url")
        client_id = await settings.get("oidc.client_id")
        client_secret = await settings.get("oidc.client_secret")
        scopes = str(await settings.get("oidc.scopes", default="openid email profile"))
        provider_name = str(await settings.get("oidc.provider_name", default="SSO"))

        if not discovery_url or not client_id:
            raise OIDCConfigurationError("OIDC discovery URL and client ID must be configured")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(str(discovery_url))
            response.raise_for_status()
            metadata = response.json()

        missing_fields = [
            field_name
            for field_name in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri")
            if not metadata.get(field_name)
        ]
        if missing_fields:
            raise OIDCConfigurationError(
                f"OIDC discovery document is missing required fields: {', '.join(missing_fields)}"
            )

        return OIDCProviderConfiguration(
            discovery_url=str(discovery_url),
            issuer=str(metadata["issuer"]),
            authorization_endpoint=str(metadata["authorization_endpoint"]),
            token_endpoint=str(metadata["token_endpoint"]),
            jwks_uri=str(metadata["jwks_uri"]),
            client_id=str(client_id),
            client_secret=str(client_secret) if client_secret else None,
            scopes=scopes,
            provider_name=provider_name,
        )

    async def _consume_auth_request(
        self,
        db: AsyncSession,
        *,
        state: str,
        browser_binding_token: Optional[str],
    ) -> OIDCAuthRequest:
        auth_request = await db.get(OIDCAuthRequest, state)
        now = datetime.now(timezone.utc)
        if auth_request is None or auth_request.consumed_at is not None or auth_request.expires_at <= now:
            raise OIDCStateError("OIDC state is invalid or expired")
        if not browser_binding_token:
            raise OIDCStateError("OIDC browser binding cookie is missing")
        if self._hash_browser_binding_token(browser_binding_token) != auth_request.browser_binding_hash:
            raise OIDCStateError("OIDC browser binding is invalid")

        auth_request.consumed_at = now
        await db.flush()
        return auth_request

    @staticmethod
    def _hash_browser_binding_token(token: str) -> str:
        return hashlib.blake2b(token.encode("utf-8"), digest_size=32).hexdigest()

    def _validate_id_token(
        self,
        *,
        id_token: str,
        jwks: dict[str, Any],
        issuer: str,
        audience: str,
        expected_nonce: str,
    ) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(id_token)
            jwk_data = self._select_jwk(jwks, header.get("kid"))
            key = jwt.PyJWK(jwk_data).key
            claims = jwt.decode(
                id_token,
                key,
                algorithms=[header.get("alg", "RS256")],
                issuer=issuer,
                audience=audience,
                options={"verify_at_hash": False},
            )
        except ExpiredSignatureError as exc:
            raise OIDCAuthenticationError("OIDC ID token has expired") from exc
        except PyJWTError as exc:
            raise OIDCAuthenticationError("OIDC ID token validation failed") from exc

        nonce = str(claims.get("nonce") or "")
        if nonce != expected_nonce:
            raise OIDCAuthenticationError("OIDC nonce validation failed")
        return claims

    @staticmethod
    def _select_jwk(jwks: dict[str, Any], kid: Optional[str]) -> dict[str, Any]:
        keys = jwks.get("keys")
        if not isinstance(keys, list) or not keys:
            raise OIDCAuthenticationError("OIDC provider returned no JWKS keys")
        if kid is None:
            return cast(dict[str, Any], keys[0])
        for key in keys:
            if isinstance(key, dict) and key.get("kid") == kid:
                return cast(dict[str, Any], key)
        raise OIDCAuthenticationError("OIDC signing key was not found in JWKS")

    @staticmethod
    def _extract_claim_path(claims: dict[str, Any], path: str) -> Any:
        current: Any = claims
        for part in path.split("."):
            if not part:
                return None
            if isinstance(current, dict):
                current = current.get(part)
                continue
            return None
        return current

    @staticmethod
    def _map_role(claim_value: Any, role_mapping: dict[str, Any]) -> Optional[UserRole]:
        if isinstance(claim_value, list):
            values = [str(item) for item in claim_value]
        elif claim_value is None:
            values = []
        else:
            values = [str(claim_value)]

        for value in values:
            mapped = role_mapping.get(value)
            if mapped is None:
                continue
            try:
                return UserRole(str(mapped).upper())
            except ValueError as exc:
                raise OIDCConfigurationError(f"OIDC role mapping contains invalid role {mapped!r}") from exc
        return None

    @staticmethod
    def _derive_username(claims: dict[str, Any]) -> Optional[str]:
        candidates = [claims.get("preferred_username"), claims.get("email")]
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            normalized = candidate.strip().lower()
            if USERNAME_REGEX.match(normalized):
                return normalized
        return None

    async def is_safe_redirect_target(self, db: AsyncSession, target: str) -> bool:
        if not target:
            return False
        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False

        settings = SettingsService(db)  # type: ignore[arg-type]
        allowed_origins_raw = await settings.get(
            "oidc.allowed_redirect_origins",
            default=get_local("oidc.allowed_redirect_origins"),
        )
        if isinstance(allowed_origins_raw, str):
            allowed_origins = [origin.strip() for origin in allowed_origins_raw.split(",") if origin.strip()]
        elif isinstance(allowed_origins_raw, list):
            allowed_origins = [str(origin).strip() for origin in allowed_origins_raw if str(origin).strip()]
        else:
            allowed_origins = []

        target_origin = f"{parsed.scheme}://{parsed.netloc}".lower()
        normalized_allowed = {origin.rstrip("/").lower() for origin in allowed_origins}
        return target_origin in normalized_allowed


oidc_service = OIDCService()


__all__ = [
    "OIDCAuthenticationError",
    "OIDCConfigurationError",
    "OIDCStateError",
    "OIDCService",
    "oidc_service",
]