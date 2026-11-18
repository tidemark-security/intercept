"""Google Workspace user enrichment provider.

Uses the Google Admin SDK Directory API with a service account JWT.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
from joserfc import jwt
from joserfc.jwk import import_key
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.enrichment.base import (
    EnrichmentProviderConfigurationError,
    EnrichmentProviderError,
    EnrichmentResult,
    MalformedProviderRecordError,
    UserDirectoryEnrichmentProvider,
)
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

_ADMIN_SDK_BASE = "https://admin.googleapis.com/admin/directory/v1"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/admin.directory.user.readonly"
_USER_FIELDS = "id,primaryEmail,name,emails,phones,organizations,aliases,thumbnailPhotoUrl,suspended,orgUnitPath"


def _normalize_private_key(private_key: Any) -> str:
    if not isinstance(private_key, str):
        return ""

    normalized = private_key.strip()
    if not normalized:
        return ""

    if normalized.startswith('"') and normalized.endswith('"'):
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(parsed, str):
                normalized = parsed.strip()

    normalized = normalized.replace("\\r\\n", "\n").replace("\\n", "\n")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return normalized


def _build_jwt(service_account: Dict[str, Any], subject_email: str) -> str:
    """Build a signed JWT for service account authentication."""
    now = int(datetime.now(timezone.utc).timestamp())
    header = {"alg": "RS256", "typ": "JWT"}
    if service_account.get("private_key_id"):
        header["kid"] = service_account["private_key_id"]
    payload = {
        "iss": service_account["client_email"],
        "sub": subject_email,
        "scope": _SCOPE,
        "aud": service_account.get("token_uri") or _TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    signing_key = import_key(service_account["private_key"], "RSA")
    return jwt.encode(header, payload, signing_key, algorithms=["RS256"])


class GoogleWorkspaceProvider(UserDirectoryEnrichmentProvider):
    """Enrich InternalActorItem via Google Workspace Admin SDK."""

    provider_id = "google_workspace"
    display_name = "Google Workspace"
    settings_prefix = "enrichment.google_workspace"
    supports_bulk_sync = True

    def __init__(self) -> None:
        self._token_value: str | None = None
        self._token_expires_at: datetime | None = None
        self._token_cache_key: str | None = None

    def _optional_mapping_list_field(
        self,
        record: Dict[str, Any],
        field_name: str,
    ) -> List[Dict[str, Any]]:
        value = record.get(field_name)
        if value is None:
            return []
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise MalformedProviderRecordError(
                f"Provider record field {field_name!r} must be a list of objects"
            )
        return value

    async def _get_settings(self, settings: SettingsService) -> Optional[Dict[str, Any]]:
        values = await self._get_setting_values(
            settings,
            (
                "domain",
                "admin_email",
                "client_email",
                "private_key",
                "token_uri",
                "private_key_id",
                "service_account_json",
            ),
        )
        domain = values["domain"]
        admin_email = values["admin_email"]
        client_email = values["client_email"]
        private_key = values["private_key"]
        token_uri = values["token_uri"]
        private_key_id = values["private_key_id"]

        sa: Dict[str, Any] | None = None
        if client_email and private_key and admin_email:
            sa = {
                "type": "service_account",
                "client_email": client_email,
                "private_key": _normalize_private_key(private_key),
            }
            if token_uri:
                sa["token_uri"] = token_uri
            if private_key_id:
                sa["private_key_id"] = private_key_id
        else:
            sa_json = values["service_account_json"]
            if sa_json and admin_email:
                try:
                    parsed = json.loads(sa_json)
                except json.JSONDecodeError:
                    return None
                if isinstance(parsed, dict):
                    parsed_private_key = _normalize_private_key(parsed.get("private_key"))
                    if parsed_private_key:
                        parsed["private_key"] = parsed_private_key
                    sa = parsed

        if not (sa and admin_email):
            return None
        return {"service_account": sa, "domain": domain, "admin_email": admin_email}

    async def _get_token(self, service_account: Dict[str, Any], admin_email: str) -> str:
        now = datetime.now(timezone.utc)
        cache_key = "|".join(
            [
                str(service_account.get("client_email") or ""),
                str(service_account.get("token_uri") or _TOKEN_URL),
                admin_email,
            ]
        )
        if (
            self._token_value
            and self._token_expires_at
            and self._token_cache_key == cache_key
            and now < self._token_expires_at
        ):
            return self._token_value

        jwt_token = _build_jwt(service_account, admin_email)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                service_account.get("token_uri") or _TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": jwt_token,
                },
            )
            resp.raise_for_status()
            try:
                payload = resp.json()
            except ValueError as exc:
                raise EnrichmentProviderError(
                    "Google Workspace token response is not valid JSON"
                ) from exc
            access_token, expires_in = self._parse_oauth_access_token_response(
                payload,
                provider_name="Google Workspace",
            )
            self._token_value = access_token
            self._token_cache_key = cache_key
            self._token_expires_at = now + timedelta(seconds=max(60, expires_in - 60))
            return access_token

    def _build_result(self, user: Dict[str, Any]) -> EnrichmentResult:
        user = self._require_record_mapping(user)
        google_id = self._optional_string_field(user, "id")
        primary_email = self._optional_string_field(user, "primaryEmail")
        raw_name = user.get("name")
        if raw_name is None:
            name: Dict[str, Any] = {}
        elif isinstance(raw_name, dict):
            name = raw_name
        else:
            raise MalformedProviderRecordError(
                "Provider record field 'name' must be an object"
            )
        display_name = self._optional_string_field(name, "fullName")
        given_name = self._optional_string_field(name, "givenName")
        family_name = self._optional_string_field(name, "familyName")

        organizations = self._optional_mapping_list_field(user, "organizations")
        phones = self._optional_mapping_list_field(user, "phones")
        emails = self._optional_mapping_list_field(user, "emails")
        aliases = self._optional_string_list_field(user, "aliases")
        org_info = organizations[0] if organizations else {}
        phone_info = phones[0] if phones else {}
        suspended = user.get("suspended", False)
        if not isinstance(suspended, bool):
            raise MalformedProviderRecordError(
                "Provider record field 'suspended' must be a boolean"
            )

        enrichment_data = {
            "google_id": google_id,
            "primary_email": primary_email,
            "display_name": display_name,
            "given_name": given_name,
            "family_name": family_name,
            "job_title": self._optional_string_field(org_info, "title"),
            "department": self._optional_string_field(org_info, "department"),
            "organization": self._optional_string_field(org_info, "name"),
            "org_unit_path": self._optional_string_field(user, "orgUnitPath"),
            "phone": self._optional_string_field(phone_info, "value"),
            "suspended": suspended,
        }

        cache_key = self._build_user_cache_key_from_values(
            primary_email,
            google_id,
        )
        canonical_value = cache_key.removeprefix("user:")
        canonical_display = display_name or primary_email or google_id
        meta = {
            "department": enrichment_data["department"],
            "job_title": enrichment_data["job_title"],
            "display_name": display_name,
        }

        alias_values = [
            ("google_id", google_id),
            ("email", primary_email.lower() if primary_email else ""),
            ("display_name", display_name.lower() if display_name else ""),
        ]

        for alt in emails:
            alt_addr = self._optional_string_field(alt, "address")
            if alt_addr and alt_addr.lower() != primary_email.lower():
                alias_values.append(("email", alt_addr.lower()))

        for alias_email in aliases:
            alias_values.append(("email_alias", alias_email.lower()))

        aliases = self._build_alias_mappings(
            entity_type="user",
            canonical_value=canonical_value,
            canonical_display=canonical_display,
            attributes=meta,
            aliases=alias_values,
        )

        return EnrichmentResult(
            provider_id=self.provider_id,
            cache_key=cache_key,
            enrichment_data=enrichment_data,
            aliases=aliases,
        )

    async def enrich(
        self,
        *,
        db: AsyncSession,
        settings: SettingsService,
        item: Dict[str, Any],
        entity_type: str,
        entity_id: int,
    ) -> EnrichmentResult:
        cfg = await self._get_settings(settings)
        if not cfg:
            raise EnrichmentProviderConfigurationError(
                "Google Workspace provider is not fully configured"
            )

        identifier = self._get_user_identifier(item)
        if not identifier:
            raise EnrichmentProviderError(
                "Cannot determine identifier for Google Workspace lookup"
            )

        token = await self._get_token(cfg["service_account"], cfg["admin_email"])
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_ADMIN_SDK_BASE}/users/{identifier}",
                headers=headers,
                params={"projection": "full", "viewType": "admin_view"},
            )
            if resp.status_code == 404:
                return EnrichmentResult(
                    provider_id=self.provider_id,
                    cache_key=self.build_cache_key(item),
                    enrichment_data={"error": f"User not found: {identifier}"},
                )
            resp.raise_for_status()
            user = resp.json()

        return self._build_result(user)

    async def bulk_sync(self, *, db: AsyncSession, settings: SettingsService) -> List[EnrichmentResult]:
        cfg = await self._get_settings(settings)
        if not cfg:
            raise EnrichmentProviderConfigurationError(
                "Google Workspace provider is not fully configured"
            )

        token = await self._get_token(cfg["service_account"], cfg["admin_email"])
        headers = {"Authorization": f"Bearer {token}"}
        domain = cfg.get("domain") or ""
        results: List[EnrichmentResult] = []
        malformed_records = 0
        page_token: Optional[str] = None

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params: Dict[str, Any] = {
                    "fields": f"nextPageToken,users({_USER_FIELDS})",
                    "maxResults": 500,
                    "orderBy": "email",
                    "projection": "full",
                }
                if domain:
                    params["domain"] = domain
                else:
                    params["customer"] = "my_customer"
                if page_token:
                    params["pageToken"] = page_token

                resp = await client.get(f"{_ADMIN_SDK_BASE}/users", headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                for user in data.get("users") or []:
                    try:
                        results.append(self._build_result(user))
                    except MalformedProviderRecordError:
                        malformed_records += 1
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

        if malformed_records:
            logger.warning(
                "Google Workspace bulk sync skipped malformed user records (count=%d)",
                malformed_records,
            )
        logger.info("Google Workspace bulk sync: %d users", len(results))
        return results


google_workspace_provider = GoogleWorkspaceProvider()
