from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

from sqlalchemy import select
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

from app.core.config import settings
from app.models.enums import AccountType
from app.models.models import AppSetting, PasskeyCredential, UserAccount, WebAuthnChallenge
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


class PasskeyService:
    async def begin_registration(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
        user_display_name: Optional[str] = None,
    ) -> dict[str, Any]:
        config = await self._load_config(db)
        existing = await self.list_user_passkeys(db, user_id=user.id, include_revoked=False)

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
        config = await self._load_config(db)

        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge_record.challenge),
            expected_rp_id=config.rp_id,
            expected_origin=config.expected_origins,
            require_user_verification=(config.user_verification == UserVerificationRequirement.REQUIRED),
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
    ) -> tuple[dict[str, Any], UserAccount]:
        normalized_username = username.strip().lower()
        user_result = await db.execute(select(UserAccount).where(cast(Any, UserAccount.username == normalized_username)))
        user = user_result.scalar_one_or_none()
        if user is None:
            raise PasskeyCredentialNotFoundError()
        if user.account_type != AccountType.HUMAN:
            raise PasskeyCredentialNotFoundError()

        credentials = await self.list_user_passkeys(db, user_id=user.id, include_revoked=False)
        if not credentials:
            raise PasskeyCredentialNotFoundError()

        config = await self._load_config(db)
        allow_credentials = [
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(credential.credential_id),
                transports=self._to_transport_enums(credential.transports),
            )
            for credential in credentials
        ]

        options = generate_authentication_options(
            rp_id=config.rp_id,
            timeout=config.timeout_ms,
            allow_credentials=allow_credentials,
            user_verification=config.user_verification,
        )
        options_dict = self._parse_options_json(options)
        challenge = options_dict["challenge"]

        await self._create_challenge(
            db,
            challenge=challenge,
            flow_type="authentication",
            user_id=user.id,
            username=user.username,
            ttl_seconds=config.challenge_ttl_seconds,
            metadata={"rp_id": config.rp_id},
        )

        return {
            "challenge": challenge,
            "options": options_dict,
        }, user

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
        )

        credential_id = credential.get("id")
        if not credential_id:
            raise PasskeyCredentialNotFoundError()

        result = await db.execute(
            select(PasskeyCredential)
            .where(
                cast(Any, PasskeyCredential.credential_id == credential_id),
                cast(Any, PasskeyCredential.revoked_at == None),  # noqa: E711
            )
        )
        passkey = result.scalar_one_or_none()
        if passkey is None:
            raise PasskeyCredentialNotFoundError()

        if challenge_record.user_id and passkey.user_id != challenge_record.user_id:
            raise PasskeyOwnershipError()

        user = await db.get(UserAccount, passkey.user_id)
        if user is None:
            raise PasskeyCredentialNotFoundError()

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
        user_id,
        passkey_id,
        name: str,
    ) -> PasskeyCredential:
        passkey = await db.get(PasskeyCredential, passkey_id)
        if passkey is None:
            raise PasskeyCredentialNotFoundError()
        if passkey.user_id != user_id:
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
        passkey = await db.get(PasskeyCredential, passkey_id)
        if passkey is None:
            raise PasskeyCredentialNotFoundError()
        if user_id is not None and passkey.user_id != user_id:
            raise PasskeyOwnershipError()

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
    ) -> WebAuthnChallenge:
        now = datetime.now(timezone.utc)
        challenge_row = WebAuthnChallenge(
            challenge=challenge,
            flow_type=flow_type,
            user_id=user_id,
            username=username,
            expires_at=now + timedelta(seconds=ttl_seconds),
            challenge_metadata=metadata or {},
        )
        db.add(challenge_row)
        await db.flush()

        # Opportunistic cleanup
        await db.execute(
            select(WebAuthnChallenge).where(cast(Any, WebAuthnChallenge.expires_at < now))
        )
        return challenge_row

    async def _consume_challenge(
        self,
        db: AsyncSession,
        *,
        challenge: str,
        flow_type: str,
        user_id=None,
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

        result = await db.execute(query)
        challenge_row = result.scalar_one_or_none()
        if challenge_row is None:
            raise PasskeyChallengeNotFoundError()

        challenge_row.consumed_at = now
        return challenge_row

    async def _load_config(self, db: AsyncSession) -> PasskeyConfig:
        settings_service = SettingsService(db)  # type: ignore[arg-type]

        rp_id = await settings_service.get_typed_value(
            "auth.passkeys.rp_id",
            default=(settings.session_cookie_domain or "localhost"),
        )
        rp_name = await settings_service.get_typed_value(
            "auth.passkeys.rp_name",
            default="Tidemark Intercept",
        )
        expected_origins_raw = await settings_service.get_typed_value(
            "auth.passkeys.expected_origins",
            default=settings.cors_origins,
        )
        timeout_ms = await settings_service.get_typed_value("auth.passkeys.timeout_ms", default=60000)
        challenge_ttl_seconds = await settings_service.get_typed_value(
            "auth.passkeys.challenge_ttl_seconds",
            default=300,
        )
        user_verification_raw = await settings_service.get_typed_value(
            "auth.passkeys.user_verification",
            default="required",
        )
        resident_key_raw = await settings_service.get_typed_value(
            "auth.passkeys.resident_key",
            default="preferred",
        )
        attestation_raw = await settings_service.get_typed_value(
            "auth.passkeys.attestation",
            default="none",
        )
        attachment_raw = await settings_service.get_typed_value(
            "auth.passkeys.authenticator_attachment",
            default=None,
        )

        if isinstance(expected_origins_raw, str):
            expected_origins = [origin.strip() for origin in expected_origins_raw.split(",") if origin.strip()]
        elif isinstance(expected_origins_raw, list):
            expected_origins = [str(origin) for origin in expected_origins_raw if str(origin).strip()]
        else:
            expected_origins = list(settings.cors_origins)

        if not expected_origins:
            raise PasskeyConfigError("No expected WebAuthn origins configured")

        try:
            user_verification = UserVerificationRequirement(str(user_verification_raw).lower())
        except Exception:
            user_verification = UserVerificationRequirement.REQUIRED

        try:
            resident_key = ResidentKeyRequirement(str(resident_key_raw).lower())
        except Exception:
            resident_key = ResidentKeyRequirement.PREFERRED

        try:
            attestation = AttestationConveyancePreference(str(attestation_raw).lower())
        except Exception:
            attestation = AttestationConveyancePreference.NONE

        attachment: Optional[AuthenticatorAttachment] = None
        if attachment_raw:
            try:
                attachment = AuthenticatorAttachment(str(attachment_raw).lower())
            except Exception:
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
        import json

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
            except Exception:
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
    "PasskeyOwnershipError",
    "passkey_service",
]
