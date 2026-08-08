from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import secrets
from typing import Any, Optional, cast

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.base64url_to_bytes import base64url_to_bytes
from webauthn.helpers.bytes_to_base64url import bytes_to_base64url
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorAttachment,
    AuthenticatorTransport,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.account_authentication import non_password_authentication_allowed
from app.core.authorization_lock import acquire_authorization_lock
from app.core.settings_registry import get_local
from app.models.models import PasskeyCredential, UserAccount, WebAuthnChallenge
from app.services.credential_invalidation import credential_was_issued_after_cutoff
from app.services.oidc_local_credential_policy import oidc_local_credential_policy
from app.services.passkey_challenge_request_service import (
    PasskeyChallengeRequestPolicy,
    passkey_challenge_request_service,
    passkey_source_fingerprint,
    passkey_user_fingerprint,
)
from app.services.password_login_request_service import password_login_request_service
from app.services.settings_service import SettingsService


@dataclass(slots=True)
class PasskeyConfig:
    rp_id: str
    rp_name: str
    expected_origins: list[str]
    timeout_ms: int
    challenge_ttl_seconds: int
    user_verification: UserVerificationRequirement
    resident_key: ResidentKeyRequirement
    attestation: AttestationConveyancePreference
    authenticator_attachment: Optional[AuthenticatorAttachment]


@dataclass(slots=True)
class PasskeyAuthenticationResult:
    user: UserAccount
    passkey: PasskeyCredential


class PasskeyChallengeNotFoundError(Exception):
    pass


class PasskeyConfigError(Exception):
    pass


class PasskeyCredentialNotFoundError(Exception):
    pass


class PasskeyOwnershipError(Exception):
    pass


class PasskeyPolicyError(Exception):
    """Raised when OIDC policy forbids local passkeys for an account."""


class PasskeyLimitError(Exception):
    """Raised when an account has reached its active passkey ceiling."""


_AUTHENTICATION_ADMISSION_TTL_SECONDS = 300
_MAX_AUTHENTICATION_USERNAME_LENGTH = 1024
_MAX_ACTIVE_PASSKEYS_PER_ACCOUNT = 10


class PasskeyService:
    def __init__(
        self,
        *,
        challenge_request_policy: PasskeyChallengeRequestPolicy | None = None,
    ) -> None:
        self._challenge_request_policy = (
            challenge_request_policy or PasskeyChallengeRequestPolicy()
        )

    @staticmethod
    async def _lock_user(
        db: AsyncSession,
        *,
        user_id: Any,
        shared_authorization: bool,
    ) -> UserAccount | None:
        await acquire_authorization_lock(
            db,
            user_id=user_id,
            shared=shared_authorization,
        )
        return await db.get(
            UserAccount,
            user_id,
            populate_existing=True,
            with_for_update=True,
        )

    @staticmethod
    async def _require_passkey_allowed(
        db: AsyncSession,
        *,
        user: UserAccount,
    ) -> None:
        capabilities = (
            await oidc_local_credential_policy.revoke_impermissible_credentials(
                db,
                user=user,
            )
        )
        if not capabilities.passkey_allowed:
            raise PasskeyPolicyError(
                "Local passkeys are disabled for this OIDC-linked account"
            )

    async def begin_registration(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
        user_display_name: Optional[str] = None,
    ) -> dict[str, Any]:
        locked_user = await self._lock_user(
            db,
            user_id=user.id,
            shared_authorization=False,
        )
        if locked_user is None or not non_password_authentication_allowed(
            locked_user
        ):
            raise PasskeyPolicyError("Passkey registration is unavailable")
        user = locked_user
        await self._require_passkey_allowed(db, user=user)
        config = await self._load_config(db)
        existing = await self.list_user_passkeys(db, user_id=user.id, include_revoked=False)
        if len(existing) >= _MAX_ACTIVE_PASSKEYS_PER_ACCOUNT:
            raise PasskeyLimitError()

        exclude_credentials = [
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(credential.credential_id),
                transports=self._to_transport_enums(credential.transports),
            )
            for credential in existing
        ]

        authenticator_selection = AuthenticatorSelectionCriteria(
            authenticator_attachment=config.authenticator_attachment,
            resident_key=config.resident_key,
            user_verification=config.user_verification,
            require_resident_key=(config.resident_key == ResidentKeyRequirement.REQUIRED),
        )

        options = generate_registration_options(
            rp_id=config.rp_id,
            rp_name=config.rp_name,
            user_id=str(user.id).encode("utf-8"),
            user_name=user.username,
            user_display_name=user_display_name or user.username,
            timeout=config.timeout_ms,
            attestation=config.attestation,
            authenticator_selection=authenticator_selection,
            exclude_credentials=exclude_credentials,
        )
        options_dict = self._parse_options_json(options)
        challenge = options_dict["challenge"]

        await self._create_challenge(
            db,
            challenge=challenge,
            flow_type="registration",
            user_id=user.id,
            username=user.username,
            ttl_seconds=config.challenge_ttl_seconds,
            metadata={"rp_id": config.rp_id},
        )

        return {
            "challenge": challenge,
            "options": options_dict,
        }

    async def finish_registration(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
        challenge: str,
        credential: dict[str, Any],
        name: str,
    ) -> PasskeyCredential:
        challenge_record = await self._consume_challenge(
            db,
            challenge=challenge,
            flow_type="registration",
            user_id=user.id,
        )
        await self._require_passkey_allowed(db, user=user)
        active_count = await db.scalar(
            select(func.count())
            .select_from(PasskeyCredential)
            .where(
                cast(Any, PasskeyCredential.user_id == user.id),
                cast(Any, PasskeyCredential.revoked_at == None),  # noqa: E711
            )
        )
        if int(active_count or 0) >= _MAX_ACTIVE_PASSKEYS_PER_ACCOUNT:
            raise PasskeyLimitError()
        config = await self._load_config(db)

        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge_record.challenge),
            expected_rp_id=config.rp_id,
            expected_origin=config.expected_origins,
            require_user_verification=(config.user_verification == UserVerificationRequirement.REQUIRED),
        )

        # The first active passkey disables password login for non-admin users.
        # Clear any failure that completed while this transaction held the
        # account gate so it cannot reappear if passkey posture changes later.
        await password_login_request_service.clear_pending_failures(
            db,
            user_id=user.id,
        )

        stored = PasskeyCredential(
            user_id=user.id,
            name=name.strip(),
            credential_id=bytes_to_base64url(verified.credential_id),
            credential_public_key=bytes_to_base64url(verified.credential_public_key),
            sign_count=verified.sign_count,
            transports=self._extract_transports(credential),
            aaguid=str(verified.aaguid) if verified.aaguid else None,
            is_backup_eligible=(verified.credential_device_type == "multi_device"),
            is_backed_up=bool(verified.credential_backed_up),
            last_used_at=None,
        )
        db.add(stored)
        await db.flush()
        return stored

    async def begin_authentication(
        self,
        db: AsyncSession,
        *,
        username: str,
        source_address: str | None = None,
    ) -> tuple[dict[str, Any], Optional[UserAccount]]:
        normalized_username = username.strip().lower()
        if (
            not normalized_username
            or len(username) > _MAX_AUTHENTICATION_USERNAME_LENGTH
            or len(normalized_username) > _MAX_AUTHENTICATION_USERNAME_LENGTH
        ):
            raise PasskeyPolicyError("Passkey sign-in is unavailable")

        admission_id = await self._reserve_authentication_admission(
            db,
            normalized_username=normalized_username,
            source_address=source_address,
        )
        config = await self._load_config(db)

        options = generate_authentication_options(
            rp_id=config.rp_id,
            timeout=config.timeout_ms,
            # An empty allow-list invokes WebAuthn's discoverable-credential
            # flow. This removes username-specific identifiers and database
            # work from the public initiation response.
            allow_credentials=[],
            user_verification=config.user_verification,
        )
        options_dict = self._parse_options_json(options)
        challenge = options_dict["challenge"]

        await self._finalize_authentication_admission(
            db,
            admission_id=admission_id,
            challenge=challenge,
            user_id=None,
            ttl_seconds=config.challenge_ttl_seconds,
            metadata={"rp_id": config.rp_id},
        )

        return {
            "challenge": challenge,
            "options": options_dict,
        }, None

    async def _reserve_authentication_admission(
        self,
        db: AsyncSession,
        *,
        normalized_username: str,
        source_address: str | None,
    ) -> Any:
        now = datetime.now(timezone.utc)
        reservation = WebAuthnChallenge(
            challenge=secrets.token_urlsafe(32),
            flow_type="authentication",
            user_id=None,
            username=None,
            source_fingerprint=passkey_source_fingerprint(source_address),
            user_fingerprint=passkey_user_fingerprint(normalized_username),
            expires_at=now
            + timedelta(seconds=_AUTHENTICATION_ADMISSION_TTL_SECONDS),
            challenge_metadata={"state": "admitted"},
        )
        await passkey_challenge_request_service.reserve_durably(
            db,
            challenge=reservation,
            policy=self._challenge_request_policy,
        )
        return reservation.id

    @staticmethod
    async def _finalize_authentication_admission(
        db: AsyncSession,
        *,
        admission_id: Any,
        challenge: str,
        ttl_seconds: int,
        user_id: Any = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> WebAuthnChallenge:
        reservation = await db.get(
            WebAuthnChallenge,
            admission_id,
            populate_existing=True,
            with_for_update=True,
        )
        if reservation is None:
            raise PasskeyChallengeNotFoundError()
        reservation.challenge = challenge
        reservation.user_id = user_id
        reservation.expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=ttl_seconds
        )
        reservation.challenge_metadata = metadata or {}
        await db.flush()
        return reservation

    async def finish_authentication(
        self,
        db: AsyncSession,
        *,
        challenge: str,
        credential: dict[str, Any],
    ) -> PasskeyAuthenticationResult:
        challenge_record = await self._consume_challenge(
            db,
            challenge=challenge,
            flow_type="authentication",
            shared_authorization=True,
        )

        credential_id = credential.get("id")
        if not credential_id:
            raise PasskeyCredentialNotFoundError()

        owner_result = await db.execute(
            select(PasskeyCredential.user_id).where(
                cast(Any, PasskeyCredential.credential_id == credential_id),
                cast(Any, PasskeyCredential.revoked_at == None),  # noqa: E711
            )
        )
        owner_id = owner_result.scalar_one_or_none()
        if owner_id is None:
            raise PasskeyCredentialNotFoundError()

        user = await self._lock_user(
            db,
            user_id=owner_id,
            shared_authorization=True,
        )
        if user is None or not non_password_authentication_allowed(user):
            raise PasskeyCredentialNotFoundError()

        result = await db.execute(
            select(PasskeyCredential)
            .where(
                cast(Any, PasskeyCredential.credential_id == credential_id),
                cast(Any, PasskeyCredential.user_id == owner_id),
                cast(Any, PasskeyCredential.revoked_at == None),  # noqa: E711
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        passkey = result.scalar_one_or_none()
        if passkey is None:
            raise PasskeyCredentialNotFoundError()

        if challenge_record.user_id and passkey.user_id != challenge_record.user_id:
            raise PasskeyOwnershipError()

        if not credential_was_issued_after_cutoff(
            user,
            issued_at=passkey.created_at,
        ):
            passkey.revoked_at = datetime.now(timezone.utc)
            passkey.updated_at = passkey.revoked_at
            raise PasskeyCredentialNotFoundError()

        await self._require_passkey_allowed(db, user=user)

        config = await self._load_config(db)
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge_record.challenge),
            expected_rp_id=config.rp_id,
            expected_origin=config.expected_origins,
            credential_public_key=base64url_to_bytes(passkey.credential_public_key),
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=(config.user_verification == UserVerificationRequirement.REQUIRED),
        )

        now = datetime.now(timezone.utc)
        passkey.sign_count = verified.new_sign_count
        passkey.last_used_at = now
        passkey.is_backed_up = bool(verified.credential_backed_up)
        passkey.updated_at = now

        return PasskeyAuthenticationResult(user=user, passkey=passkey)

    async def list_user_passkeys(
        self,
        db: AsyncSession,
        *,
        user_id,
        include_revoked: bool = False,
    ) -> list[PasskeyCredential]:
        query = select(PasskeyCredential).where(cast(Any, PasskeyCredential.user_id == user_id))
        if not include_revoked:
            query = query.where(cast(Any, PasskeyCredential.revoked_at == None))  # noqa: E711
        query = query.order_by(cast(Any, PasskeyCredential.created_at).desc())
        result = await db.execute(query)
        return list(result.scalars().all())

    async def rename_passkey(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
        passkey_id,
        name: str,
    ) -> PasskeyCredential:
        await self._require_passkey_allowed(db, user=user)

        passkey = await db.get(PasskeyCredential, passkey_id)
        if passkey is None:
            raise PasskeyCredentialNotFoundError()
        if passkey.user_id != user.id:
            raise PasskeyOwnershipError()

        existing_transports = list(passkey.transports or [])
        passkey.name = name.strip()
        passkey.updated_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(passkey)

        if existing_transports and not passkey.transports:
            passkey.transports = existing_transports
            await db.flush()
            await db.refresh(passkey)

        return passkey

    async def revoke_passkey(
        self,
        db: AsyncSession,
        *,
        passkey_id,
        user_id=None,
        revoked_by_admin_id=None,
    ) -> PasskeyCredential:
        effective_user_id = user_id
        if effective_user_id is None:
            owner_result = await db.execute(
                select(PasskeyCredential.user_id).where(
                    cast(Any, PasskeyCredential.id == passkey_id)
                )
            )
            effective_user_id = owner_result.scalar_one_or_none()
        if effective_user_id is None:
            raise PasskeyCredentialNotFoundError()

        locked_user = await self._lock_user(
            db,
            user_id=effective_user_id,
            shared_authorization=False,
        )
        if locked_user is None:
            raise PasskeyCredentialNotFoundError()

        result = await db.execute(
            select(PasskeyCredential)
            .where(cast(Any, PasskeyCredential.id == passkey_id))
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        passkey = result.scalar_one_or_none()
        if passkey is None:
            raise PasskeyCredentialNotFoundError()
        if user_id is not None and passkey.user_id != user_id:
            raise PasskeyOwnershipError()

        # Revoking the final passkey can re-enable password login. Linearize the
        # transition with invalid guesses that could not enter the account gate.
        await password_login_request_service.clear_pending_failures(
            db,
            user_id=passkey.user_id,
        )

        now = datetime.now(timezone.utc)
        passkey.revoked_at = now
        passkey.revoked_by_admin_id = revoked_by_admin_id
        passkey.updated_at = now
        return passkey

    async def user_has_active_passkeys(self, db: AsyncSession, *, user_id) -> bool:
        query = (
            select(PasskeyCredential.id)
            .where(
                cast(Any, PasskeyCredential.user_id == user_id),
                cast(Any, PasskeyCredential.revoked_at == None),  # noqa: E711
            )
            .limit(1)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None

    async def _create_challenge(
        self,
        db: AsyncSession,
        *,
        challenge: str,
        flow_type: str,
        ttl_seconds: int,
        user_id=None,
        username: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        source_fingerprint: Optional[str] = None,
        user_fingerprint: Optional[str] = None,
        enforce_authentication_quotas: bool = False,
    ) -> WebAuthnChallenge:
        now = datetime.now(timezone.utc)
        challenge_row = WebAuthnChallenge(
            challenge=challenge,
            flow_type=flow_type,
            user_id=user_id,
            username=username,
            source_fingerprint=source_fingerprint,
            user_fingerprint=user_fingerprint,
            expires_at=now + timedelta(seconds=ttl_seconds),
            challenge_metadata=metadata or {},
        )

        if flow_type == "registration":
            await passkey_challenge_request_service.reserve_registration(
                db,
                challenge=challenge_row,
                policy=self._challenge_request_policy,
            )
            return challenge_row

        if enforce_authentication_quotas:
            await passkey_challenge_request_service.reserve(
                db,
                challenge=challenge_row,
                policy=self._challenge_request_policy,
            )
            return challenge_row

        db.add(challenge_row)
        await db.flush()

        # Opportunistic cleanup
        history_cutoff = now - timedelta(
            seconds=self._challenge_request_policy.rate_window_seconds
        )
        await db.execute(
            delete(WebAuthnChallenge).where(
                cast(Any, WebAuthnChallenge.expires_at < now),
                or_(
                    cast(Any, WebAuthnChallenge.source_fingerprint == None),  # noqa: E711
                    cast(Any, WebAuthnChallenge.user_fingerprint == None),  # noqa: E711
                    cast(Any, WebAuthnChallenge.created_at <= history_cutoff),
                ),
            )
        )
        return challenge_row

    async def _consume_challenge(
        self,
        db: AsyncSession,
        *,
        challenge: str,
        flow_type: str,
        user_id=None,
        shared_authorization: bool = False,
    ) -> WebAuthnChallenge:
        now = datetime.now(timezone.utc)
        query = select(WebAuthnChallenge).where(
            cast(Any, WebAuthnChallenge.challenge == challenge),
            cast(Any, WebAuthnChallenge.flow_type == flow_type),
            cast(Any, WebAuthnChallenge.consumed_at == None),  # noqa: E711
            cast(Any, WebAuthnChallenge.expires_at > now),
        )
        if user_id is not None:
            query = query.where(cast(Any, WebAuthnChallenge.user_id == user_id))
        query = query.order_by(cast(Any, WebAuthnChallenge.created_at).desc())

        candidate_result = await db.execute(query)
        candidate = candidate_result.scalar_one_or_none()
        if candidate is None:
            raise PasskeyChallengeNotFoundError()

        locked_user = None
        if candidate.user_id is not None:
            locked_user = await self._lock_user(
                db,
                user_id=candidate.user_id,
                shared_authorization=shared_authorization,
            )

        now = datetime.now(timezone.utc)
        result = await db.execute(
            query.where(
                WebAuthnChallenge.id == candidate.id,
                WebAuthnChallenge.expires_at > now,
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        challenge_row = result.scalar_one_or_none()
        if challenge_row is None:
            raise PasskeyChallengeNotFoundError()

        challenge_row.consumed_at = now
        if challenge_row.user_id is None:
            if flow_type != "authentication" or user_id is not None:
                raise PasskeyChallengeNotFoundError()
            return challenge_row

        if locked_user is None or not non_password_authentication_allowed(
            locked_user
        ):
            raise PasskeyChallengeNotFoundError()
        if not credential_was_issued_after_cutoff(
            locked_user,
            issued_at=challenge_row.created_at,
        ):
            raise PasskeyChallengeNotFoundError()
        return challenge_row

    async def _load_config(self, db: AsyncSession) -> PasskeyConfig:
        settings_service = SettingsService(db)  # type: ignore[arg-type]

        rp_id = await settings_service.get(
            "auth.passkeys.rp_id",
            default=(get_local("auth.session.cookie_domain") or "localhost"),
        )
        rp_name = await settings_service.get(
            "auth.passkeys.rp_name",
            default="Tidemark Intercept",
        )
        cors_origins_fallback = get_local("cors_origins", default=[])
        expected_origins_raw = await settings_service.get(
            "auth.passkeys.expected_origins",
            default=cors_origins_fallback,
        )
        timeout_ms = await settings_service.get("auth.passkeys.timeout_ms", default=60000)
        challenge_ttl_seconds = await settings_service.get(
            "auth.passkeys.challenge_ttl_seconds",
            default=300,
        )
        user_verification_raw = await settings_service.get(
            "auth.passkeys.user_verification",
            default="required",
        )
        resident_key_raw = await settings_service.get(
            "auth.passkeys.resident_key",
            default="required",
        )
        attestation_raw = await settings_service.get(
            "auth.passkeys.attestation",
            default="none",
        )
        attachment_raw = await settings_service.get(
            "auth.passkeys.authenticator_attachment",
            default=None,
        )

        if isinstance(expected_origins_raw, str):
            parsed_json = None
            try:
                parsed_json = json.loads(expected_origins_raw)
            except json.JSONDecodeError:
                parsed_json = None

            if isinstance(parsed_json, list):
                expected_origins = [
                    str(origin).strip()
                    for origin in parsed_json
                    if str(origin).strip()
                ]
            else:
                expected_origins = [
                    origin.strip()
                    for origin in expected_origins_raw.split(",")
                    if origin.strip()
                ]
        elif isinstance(expected_origins_raw, list):
            expected_origins = [
                str(origin).strip()
                for origin in expected_origins_raw
                if str(origin).strip()
            ]
        else:
            expected_origins = [
                str(origin).strip()
                for origin in cors_origins_fallback
                if str(origin).strip()
            ]

        if not expected_origins:
            raise PasskeyConfigError("No expected WebAuthn origins configured")

        try:
            user_verification = UserVerificationRequirement(str(user_verification_raw).lower())
        except (TypeError, ValueError):
            user_verification = UserVerificationRequirement.REQUIRED

        # Public authentication is deliberately usernameless and therefore
        # supports discoverable credentials only. Treat older configurable
        # values as legacy input, but never mint another non-discoverable key.
        _ = resident_key_raw
        resident_key = ResidentKeyRequirement.REQUIRED

        try:
            attestation = AttestationConveyancePreference(str(attestation_raw).lower())
        except (TypeError, ValueError):
            attestation = AttestationConveyancePreference.NONE

        attachment: Optional[AuthenticatorAttachment] = None
        if attachment_raw:
            try:
                attachment = AuthenticatorAttachment(str(attachment_raw).lower())
            except (TypeError, ValueError):
                attachment = None

        return PasskeyConfig(
            rp_id=str(rp_id),
            rp_name=str(rp_name),
            expected_origins=expected_origins,
            timeout_ms=int(timeout_ms),
            challenge_ttl_seconds=int(challenge_ttl_seconds),
            user_verification=user_verification,
            resident_key=resident_key,
            attestation=attestation,
            authenticator_attachment=attachment,
        )

    @staticmethod
    def _parse_options_json(options: Any) -> dict[str, Any]:
        return json.loads(options_to_json(options))

    @staticmethod
    def _extract_transports(credential: dict[str, Any]) -> list[str]:
        known_transports = {"usb", "nfc", "ble", "hybrid", "internal"}

        response_payload = credential.get("response")
        response_transports = (
            response_payload.get("transports")
            if isinstance(response_payload, dict)
            else None
        )
        top_level_transports = credential.get("transports")

        normalized: list[str] = []
        for source in (response_transports, top_level_transports):
            if not isinstance(source, list):
                continue

            for transport in source:
                value = str(transport).strip().lower()
                if value and value in known_transports and value not in normalized:
                    normalized.append(value)

        if normalized:
            return normalized

        attachment = credential.get("authenticatorAttachment")
        if isinstance(attachment, str) and attachment.strip().lower() == "platform":
            return ["internal"]

        return []

    @staticmethod
    def _to_transport_enums(transports: list[str]) -> list[AuthenticatorTransport]:
        values: list[AuthenticatorTransport] = []
        for transport in transports:
            try:
                values.append(AuthenticatorTransport(str(transport).lower()))
            except (TypeError, ValueError):
                continue
        return values


passkey_service = PasskeyService()

__all__ = [
    "PasskeyService",
    "PasskeyConfig",
    "PasskeyAuthenticationResult",
    "PasskeyChallengeNotFoundError",
    "PasskeyConfigError",
    "PasskeyCredentialNotFoundError",
    "PasskeyLimitError",
    "PasskeyOwnershipError",
    "PasskeyPolicyError",
    "passkey_service",
]
