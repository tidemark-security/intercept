from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import logging
import secrets
from typing import Any, Optional, cast
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

import httpx
import jwt
from jwt.exceptions import ExpiredSignatureError, PyJWTError
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.account_authentication import non_password_authentication_allowed
from app.core.authorization_lock import acquire_authorization_lock
from app.core.oidc_policy_lock import acquire_oidc_policy_lock
from app.core.security import hash_opaque_token
from app.core.settings_registry import get_local
from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import OIDCAuthRequest, USERNAME_REGEX, UserAccount
from app.services import get_audit_service
from app.services.audit_service import AuditContext
from app.services.credential_invalidation import credential_was_issued_after_cutoff
from app.services.oidc_auth_request_service import (
    OIDCAuthRequestPolicy,
    oidc_auth_request_service,
    oidc_source_fingerprint,
)
from app.services.oidc_claim_contract import (
    OIDCClaimContractError,
    validate_oidc_claim_contract,
    validate_oidc_clock_skew,
)
from app.services.oidc_discovery_cache import OIDCDiscoveryCache
from app.services.oidc_local_credential_policy import (
    oidc_local_credential_policy,
)
from app.services.password_login_request_service import password_login_request_service
from app.services.settings_service import SettingsService


logger = logging.getLogger(__name__)
_EMAIL_ADAPTER = TypeAdapter(EmailStr)


class OIDCConfigurationError(Exception):
    pass


class OIDCAuthenticationError(Exception):
    pass


class OIDCConsumedStateError(OIDCAuthenticationError):
    """Authentication failed only after a valid OIDC state was consumed."""


class OIDCStateError(Exception):
    pass


def validate_oidc_redirect_uri(value: str) -> str:
    """Validate the exact externally registered OIDC callback URI."""

    redirect_uri = str(value or "").strip()
    parsed = urlparse(redirect_uri)
    try:
        parsed.port
    except ValueError as exc:
        raise OIDCConfigurationError("OIDC redirect URI has an invalid port") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise OIDCConfigurationError("OIDC redirect URI is invalid")

    is_loopback = parsed.hostname.lower() == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            is_loopback = False
    if parsed.scheme != "https" and not is_loopback:
        raise OIDCConfigurationError(
            "OIDC redirect URI must use HTTPS except for loopback hosts"
        )
    return redirect_uri


def oidc_redirect_origin(redirect_uri: str) -> str:
    """Return the canonical public origin for an exact callback URI."""

    parsed = urlparse(validate_oidc_redirect_uri(redirect_uri))
    return f"{parsed.scheme}://{parsed.netloc}"


def _validate_oidc_https_url(
    value: Any,
    *,
    field_name: str,
    allow_query: bool,
) -> str:
    """Require a discovery-provided URL that is safe for browser/server use."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise OIDCConfigurationError(f"OIDC {field_name} is invalid")
    if any(character.isspace() for character in value):
        raise OIDCConfigurationError(f"OIDC {field_name} is invalid")

    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise OIDCConfigurationError(
            f"OIDC {field_name} has an invalid port"
        ) from exc
    authority = parsed.netloc.rsplit("@", 1)[-1]
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or authority.endswith(":")
        or port == 0
        or parsed.fragment
        or (parsed.query and not allow_query)
    ):
        raise OIDCConfigurationError(
            f"OIDC {field_name} must be an absolute HTTPS URL"
        )
    return value


def validate_oidc_discovery_url(value: Any) -> str:
    """Validate the operator-configured OIDC discovery document URL.

    Query parameters are deliberately supported because some tenant-aware
    providers select policy at discovery time. Credentials and fragments are
    never meaningful for the outbound request and are rejected.
    """

    return _validate_oidc_https_url(
        value,
        field_name="discovery URL",
        allow_query=True,
    )


def validate_oidc_provider_metadata(
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Validate the security-sensitive URLs in an OIDC discovery document."""

    if not isinstance(metadata, dict):
        raise OIDCConfigurationError("OIDC discovery document must be a JSON object")

    validated = dict(metadata)
    validated["issuer"] = _validate_oidc_https_url(
        metadata.get("issuer"),
        field_name="issuer",
        allow_query=False,
    )
    for field_name in (
        "authorization_endpoint",
        "token_endpoint",
        "jwks_uri",
    ):
        validated[field_name] = _validate_oidc_https_url(
            metadata.get(field_name),
            field_name=field_name,
            allow_query=True,
        )
    return validated


def _pkce_s256_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _authorization_url_with_params(
    authorization_endpoint: str,
    params: dict[str, str],
) -> str:
    """Merge required request parameters into a discovery endpoint query."""

    parsed = urlsplit(authorization_endpoint)
    generated_names = set(params)
    existing_params = [
        (name, value)
        for name, value in parse_qsl(parsed.query, keep_blank_values=True)
        if name not in generated_names
    ]
    query = urlencode([*existing_params, *params.items()])
    return urlunsplit(parsed._replace(query=query))


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
    redirect_uri: str

    def authorization_snapshot(self) -> tuple[str | None, ...]:
        """Return fields that affect protocol or identity authorization."""

        # provider_name is deliberately display-only and does not invalidate an
        # authentication already in progress.
        return (
            self.discovery_url,
            self.issuer,
            self.authorization_endpoint,
            self.token_endpoint,
            self.jwks_uri,
            self.client_id,
            self.client_secret,
            self.scopes,
            self.redirect_uri,
        )


@dataclass(frozen=True, slots=True)
class OIDCIdentityPolicy:
    """Identity behavior captured when an authentication topology is built.

    Web sign-in intentionally leaves this unset and continues resolving the
    current settings for each login. Long-lived protocols such as MCP pass the
    worker's startup snapshot so every request handled by that worker applies
    one coherent account-linking and provisioning policy.
    """

    jit_provisioning: bool
    default_role: str
    role_claim_path: str
    role_mapping: dict[str, Any]


class OIDCService:
    def __init__(
        self,
        *,
        discovery_cache: OIDCDiscoveryCache | None = None,
        auth_request_policy: OIDCAuthRequestPolicy | None = None,
    ) -> None:
        self._discovery_cache = discovery_cache or OIDCDiscoveryCache()
        self._auth_request_policy = auth_request_policy or OIDCAuthRequestPolicy()
        self._auth_request_service = oidc_auth_request_service

    def canonical_origin(self) -> str:
        return oidc_redirect_origin(str(get_local("oidc.redirect_uri")))

    async def get_public_config(self, db: AsyncSession) -> dict[str, Any]:
        settings = SettingsService(db)  # type: ignore[arg-type]
        enabled = bool(await settings.get("oidc.enabled", default=False))
        provider_name = str(await settings.get("oidc.provider_name", default="SSO"))
        return {"enabled": enabled, "providerName": provider_name}

    async def is_password_login_allowed(self, db: AsyncSession, *, user: UserAccount) -> bool:
        capabilities = await oidc_local_credential_policy.capabilities_for(
            db,
            user=user,
        )
        return capabilities.password_login_allowed

    async def begin_login(
        self,
        db: AsyncSession,
        *,
        redirect_to: str,
        source_address: str | None = None,
    ) -> tuple[str, datetime, str]:
        provider = await self._load_provider_configuration(db)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        browser_binding_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        auth_request = OIDCAuthRequest(
            state=state,
            nonce=nonce,
            browser_binding_hash=hash_opaque_token(browser_binding_token),
            source_fingerprint=oidc_source_fingerprint(source_address),
            redirect_to=redirect_to,
            expires_at=expires_at,
        )
        await self._auth_request_service.reserve(
            db,
            auth_request=auth_request,
            policy=self._auth_request_policy,
        )

        params = {
            "client_id": provider.client_id,
            "redirect_uri": provider.redirect_uri,
            "response_type": "code",
            "scope": provider.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": _pkce_s256_challenge(browser_binding_token),
            "code_challenge_method": "S256",
        }
        return (
            _authorization_url_with_params(provider.authorization_endpoint, params),
            expires_at,
            browser_binding_token,
        )

    async def exchange_code(
        self,
        db: AsyncSession,
        *,
        code: str,
        state: str,
        browser_binding_token: Optional[str],
    ) -> tuple[UserAccount, str, str, str]:
        auth_request = await self._consume_auth_request(
            db,
            state=state,
            browser_binding_token=browser_binding_token,
        )
        try:
            return await self._exchange_consumed_code(
                db,
                code=code,
                browser_binding_token=browser_binding_token,
                auth_request=auth_request,
            )
        except OIDCConsumedStateError:
            raise
        except (OIDCConfigurationError, OIDCAuthenticationError) as exc:
            raise OIDCConsumedStateError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise OIDCConsumedStateError(
                "OIDC provider token validation failed"
            ) from exc
        except (AttributeError, TypeError, ValueError) as exc:
            raise OIDCConsumedStateError(
                "OIDC provider returned an invalid token response"
            ) from exc

    async def consume_authorization_error(
        self,
        db: AsyncSession,
        *,
        state: str,
        browser_binding_token: Optional[str],
    ) -> None:
        """Consume a browser-bound request after an IdP authorization error."""

        await self._consume_auth_request(
            db,
            state=state,
            browser_binding_token=browser_binding_token,
        )

    async def _exchange_consumed_code(
        self,
        db: AsyncSession,
        *,
        code: str,
        browser_binding_token: Optional[str],
        auth_request: OIDCAuthRequest,
    ) -> tuple[UserAccount, str, str, str]:
        """Finish a flow whose durable state has already been consumed."""

        provider = await self._load_provider_configuration(db)

        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": provider.redirect_uri,
            "client_id": provider.client_id,
            "code_verifier": browser_binding_token,
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

        claims = self.validate_id_token(
            id_token=id_token,
            jwks=jwks,
            issuer=provider.issuer,
            audience=provider.client_id,
            expected_nonce=auth_request.nonce,
        )

        # Linearize callback authorization against oidc.enabled writers before
        # taking any account lock or provisioning a JIT identity.  This shared
        # transaction lock remains held while the route creates and commits the
        # application session.  Settings writers take the exclusive form
        # through reconciliation and commit.
        await acquire_oidc_policy_lock(db, shared=True)
        if not await SettingsService(db).get("oidc.enabled", default=False):
            raise OIDCAuthenticationError(
                "OIDC sign-in was disabled before authentication completed"
            )

        # Settings may have changed while the remote token/JWKS requests were
        # in flight. Reload after taking the policy gate (the normal unchanged
        # path reuses the warmed discovery cache) and reject a mixed-provider
        # exchange rather than combining old cryptographic validation with new
        # provisioning policy.
        current_provider = await self._load_provider_configuration(db)
        if (
            current_provider.authorization_snapshot()
            != provider.authorization_snapshot()
        ):
            raise OIDCAuthenticationError(
                "OIDC provider configuration changed during authentication"
            )
        if not await self.is_safe_redirect_target(db, auth_request.redirect_to):
            raise OIDCAuthenticationError(
                "OIDC return target is no longer allowed"
            )

        user = await self.find_or_create_user(db, claims=claims, issuer=provider.issuer)
        if not credential_was_issued_after_cutoff(
            user,
            issued_at=auth_request.created_at,
        ):
            raise OIDCAuthenticationError(
                "OIDC credential predates account credential invalidation"
            )
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
        metadata: Optional[AuditContext] = None,
        identity_policy: OIDCIdentityPolicy | None = None,
    ) -> UserAccount:
        subject_claim = claims.get("sub")
        if not isinstance(subject_claim, str) or not subject_claim.strip():
            raise OIDCAuthenticationError("OIDC claims did not include a subject")
        subject = subject_claim

        identity_filters = (
            cast(Any, UserAccount.oidc_issuer == issuer),
            cast(Any, UserAccount.oidc_subject == subject),
        )
        candidate_result = await db.execute(
            select(UserAccount.id).where(*identity_filters)
        )
        candidate_user_id = candidate_result.scalar_one_or_none()
        user = None
        if candidate_user_id is not None:
            # IdP role reconciliation is an authorization writer. Queue it
            # ahead of later authenticated readers so downgrades cannot be
            # starved by a continuous request stream.
            await acquire_authorization_lock(
                db,
                user_id=candidate_user_id,
                shared=False,
            )
            result = await db.execute(
                select(UserAccount)
                .where(*identity_filters)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            user = result.scalar_one_or_none()
        if user is not None:
            if not non_password_authentication_allowed(user):
                raise OIDCAuthenticationError("OIDC-linked user account is not active")

            resolved_role = await self.resolve_role(
                db,
                claims=claims,
                identity_policy=identity_policy,
            )
            if user.role != resolved_role:
                old_role = user.role
                await password_login_request_service.clear_pending_failures(
                    db,
                    user_id=user.id,
                )
                user.role = resolved_role
                user.updated_at = datetime.now(timezone.utc)
                await get_audit_service(db).oidc_role_changed(
                    user_id=user.id,
                    username=user.username,
                    old_role=old_role,
                    new_role=resolved_role,
                    context=metadata,
                )
                await db.flush()
            await oidc_local_credential_policy.revoke_impermissible_credentials(
                db,
                user=user,
            )
            return user

        if identity_policy is None:
            settings = SettingsService(db)  # type: ignore[arg-type]
            jit_enabled = bool(
                await settings.get("oidc.jit_provisioning", default=False)
            )
        else:
            jit_enabled = identity_policy.jit_provisioning
        if not jit_enabled:
            raise OIDCAuthenticationError("OIDC sign-in is not enabled for unprovisioned users")

        email_claim = claims.get("email")
        try:
            email = str(_EMAIL_ADAPTER.validate_python(email_claim)).lower()
        except (ValidationError, TypeError, ValueError):
            raise OIDCAuthenticationError("OIDC claims did not include an email address")

        result = await db.execute(select(UserAccount).where(cast(Any, UserAccount.email == email)))
        user = result.scalar_one_or_none()
        if user is not None:
            raise OIDCAuthenticationError("OIDC email collides with an existing account")

        username = self._derive_username(claims)
        if username is None:
            raise OIDCAuthenticationError("OIDC claims did not include a usable username")

        existing = await db.execute(select(UserAccount).where(cast(Any, UserAccount.username == username)))
        if existing.scalar_one_or_none() is not None:
            raise OIDCAuthenticationError("OIDC username collides with an existing account")

        role = await self.resolve_role(
            db,
            claims=claims,
            identity_policy=identity_policy,
        )
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
            context=metadata,
        )
        await oidc_local_credential_policy.revoke_impermissible_credentials(
            db,
            user=user,
        )
        return user

    async def resolve_role(
        self,
        db: AsyncSession,
        *,
        claims: dict[str, Any],
        identity_policy: OIDCIdentityPolicy | None = None,
    ) -> UserRole:
        if identity_policy is None:
            settings = SettingsService(db)  # type: ignore[arg-type]
            default_role = str(
                await settings.get(
                    "oidc.default_role", default=UserRole.ANALYST.value
                )
            ).upper()
            role_claim_path = str(
                await settings.get("oidc.role_claim_path", default="")
            ).strip()
            role_mapping = await settings.get("oidc.role_mapping", default={})
            if not isinstance(role_mapping, dict):
                role_mapping = {}
        else:
            default_role = identity_policy.default_role.upper()
            role_claim_path = identity_policy.role_claim_path.strip()
            role_mapping = identity_policy.role_mapping

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
        redirect_uri = validate_oidc_redirect_uri(
            str(get_local("oidc.redirect_uri"))
        )

        if not discovery_url or not client_id:
            raise OIDCConfigurationError("OIDC discovery URL and client ID must be configured")
        validated_discovery_url = validate_oidc_discovery_url(discovery_url)

        async def load_validated_metadata() -> dict[str, object]:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(validated_discovery_url)
                response.raise_for_status()
                raw_metadata = response.json()
            return validate_oidc_provider_metadata(raw_metadata)

        metadata = await self._discovery_cache.get(
            validated_discovery_url,
            load_validated_metadata,
        )

        return OIDCProviderConfiguration(
            discovery_url=validated_discovery_url,
            issuer=str(metadata["issuer"]),
            authorization_endpoint=str(metadata["authorization_endpoint"]),
            token_endpoint=str(metadata["token_endpoint"]),
            jwks_uri=str(metadata["jwks_uri"]),
            client_id=str(client_id),
            client_secret=str(client_secret) if client_secret else None,
            scopes=scopes,
            provider_name=provider_name,
            redirect_uri=redirect_uri,
        )

    async def _consume_auth_request(
        self,
        db: AsyncSession,
        *,
        state: str,
        browser_binding_token: Optional[str],
    ) -> OIDCAuthRequest:
        result = await db.execute(
            select(OIDCAuthRequest)
            .where(cast(Any, OIDCAuthRequest.state == state))
            .with_for_update()
        )
        auth_request = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if auth_request is None or auth_request.consumed_at is not None or auth_request.expires_at <= now:
            raise OIDCStateError("OIDC state is invalid or expired")
        if not browser_binding_token:
            raise OIDCStateError("OIDC browser binding cookie is missing")
        if not secrets.compare_digest(
            hash_opaque_token(browser_binding_token),
            auth_request.browser_binding_hash,
        ):
            raise OIDCStateError("OIDC browser binding is invalid")

        auth_request.consumed_at = now
        await db.flush()
        await db.commit()
        return auth_request

    def validate_id_token(
        self,
        *,
        id_token: str,
        jwks: dict[str, Any],
        issuer: str,
        audience: str,
        expected_nonce: str,
    ) -> dict[str, Any]:
        try:
            clock_skew_seconds = validate_oidc_clock_skew(
                get_local("oidc.clock_skew_seconds")
            )
        except ValueError as exc:
            raise OIDCConfigurationError(str(exc)) from exc

        try:
            header = jwt.get_unverified_header(id_token)
            alg = str(header.get("alg") or "")
            if alg not in {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}:
                raise OIDCAuthenticationError("OIDC ID token uses an unsupported signing algorithm")
            jwk_data = self._select_jwk(jwks, header.get("kid"), alg)
            key = jwt.PyJWK(jwk_data).key
            claims = jwt.decode(
                id_token,
                key,
                algorithms=[alg],
                issuer=issuer,
                audience=audience,
                leeway=clock_skew_seconds,
                options={
                    "verify_at_hash": False,
                    "require": ["iss", "aud", "exp", "iat", "sub", "nonce"],
                },
            )
        except ExpiredSignatureError as exc:
            raise OIDCAuthenticationError("OIDC ID token has expired") from exc
        except PyJWTError as exc:
            raise OIDCAuthenticationError("OIDC ID token validation failed") from exc

        try:
            return validate_oidc_claim_contract(
                claims,
                issuer=issuer,
                audience=audience,
                expected_nonce=expected_nonce,
                require_nonce=True,
                clock_skew_seconds=clock_skew_seconds,
            )
        except OIDCClaimContractError as exc:
            raise OIDCAuthenticationError(str(exc)) from exc

    # Retain the former internal seam for downstream extensions while new code
    # and tests use the public protocol-contract validator above.
    _validate_id_token = validate_id_token

    @staticmethod
    def _select_jwk(jwks: dict[str, Any], kid: Optional[str], alg: str) -> dict[str, Any]:
        keys = jwks.get("keys")
        if not isinstance(keys, list) or not keys:
            raise OIDCAuthenticationError("OIDC provider returned no JWKS keys")
        if kid is None:
            raise OIDCAuthenticationError("OIDC ID token did not include a key ID")
        for key in keys:
            if (
                isinstance(key, dict)
                and key.get("kid") == kid
                and key.get("use", "sig") == "sig"
                and key.get("alg", alg) == alg
            ):
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
    "OIDCConsumedStateError",
    "OIDCIdentityPolicy",
    "OIDCStateError",
    "OIDCService",
    "oidc_redirect_origin",
    "oidc_service",
    "validate_oidc_discovery_url",
    "validate_oidc_provider_metadata",
    "validate_oidc_redirect_uri",
]
