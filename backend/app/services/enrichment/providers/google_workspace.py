"""Google Workspace user enrichment provider.

Uses the Google Admin SDK Directory API with a service account JWT.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any, Dict, List, Optional

from authlib.jose import jwt
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.enrichment.base import AliasMapping, EnrichmentProvider, EnrichmentResult
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
    token = jwt.encode(header, payload, service_account["private_key"])
    if isinstance(token, memoryview):
        return token.tobytes().decode("utf-8")
    if isinstance(token, (bytes, bytearray)):
        return bytes(token).decode("utf-8")
    return token


class GoogleWorkspaceProvider(EnrichmentProvider):
    """Enrich InternalActorItem via Google Workspace Admin SDK."""

    provider_id = "google_workspace"
    display_name = "Google Workspace"
    settings_prefix = "enrichment.google_workspace"
    supported_item_types = ("internal_actor",)
    supports_bulk_sync = True

    def __init__(self) -> None:
        self._token_value: str | None = None
        self._token_expires_at: datetime | None = None
        self._token_cache_key: str | None = None

    def can_enrich(self, item: Dict[str, Any]) -> bool:
        return item.get("type") == "internal_actor" and bool(self._get_identifier(item))

    def build_cache_key(self, item: Dict[str, Any]) -> str:
        identifier = self._get_identifier(item)
        if not identifier:
            raise ValueError("Cannot determine identifier for Google Workspace cache key")
        return f"user:{identifier}"

    def _get_identifier(self, item: Dict[str, Any]) -> str:
        for key in ("user_id", "contact_email", "name"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        return ""

    async def _get_settings(self, settings: SettingsService) -> Optional[Dict[str, Any]]:
        domain = await settings.get(f"{self.settings_prefix}.domain", "")
        admin_email = await settings.get(f"{self.settings_prefix}.admin_email", "")
        client_email = await settings.get(f"{self.settings_prefix}.client_email", "")
        private_key = await settings.get(f"{self.settings_prefix}.private_key", "")
        token_uri = await settings.get(f"{self.settings_prefix}.token_uri", "")
        private_key_id = await settings.get(f"{self.settings_prefix}.private_key_id", "")

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
            sa_json = await settings.get(f"{self.settings_prefix}.service_account_json", "")
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
            payload = resp.json()
            self._token_value = payload["access_token"]
            self._token_cache_key = cache_key
            expires_in = int(payload.get("expires_in") or 3600)
            self._token_expires_at = now + timedelta(seconds=max(60, expires_in - 60))
            return payload["access_token"]

    def _build_result(self, user: Dict[str, Any]) -> EnrichmentResult:
        google_id = user.get("id", "")
        primary_email = user.get("primaryEmail", "")
        name = user.get("name") or {}
        display_name = name.get("fullName") or ""
        given_name = name.get("givenName") or ""
        family_name = name.get("familyName") or ""

        org_info = (user.get("organizations") or [{}])[0]
        phone_info = (user.get("phones") or [{}])[0]

        enrichment_data = {
            "google_id": google_id,
            "primary_email": primary_email,
            "display_name": display_name,
            "given_name": given_name,
            "family_name": family_name,
            "job_title": org_info.get("title") or "",
            "department": org_info.get("department") or "",
            "organization": org_info.get("name") or "",
            "org_unit_path": user.get("orgUnitPath") or "",
            "phone": phone_info.get("value") or "",
            "suspended": user.get("suspended", False),
        }

        canonical_value = primary_email.lower() or google_id
        canonical_display = display_name or primary_email or google_id
        meta = {
            "department": enrichment_data["department"],
            "job_title": enrichment_data["job_title"],
            "display_name": display_name,
        }

        aliases: List[AliasMapping] = []

        def _add(alias_type: str, value: str) -> None:
            if value:
                aliases.append(
                    AliasMapping(
                        entity_type="user",
                        canonical_value=canonical_value,
                        canonical_display=canonical_display,
                        alias_type=alias_type,
                        alias_value=value,
                        attributes=meta,
                    )
                )

        _add("google_id", google_id)
        _add("email", primary_email.lower() if primary_email else "")
        _add("display_name", display_name.lower() if display_name else "")

        for alt in user.get("emails") or []:
            alt_addr = alt.get("address") or ""
            if alt_addr and alt_addr.lower() != primary_email.lower():
                _add("email", alt_addr.lower())

        for alias_email in user.get("aliases") or []:
            _add("email_alias", alias_email.lower())

        return EnrichmentResult(
            provider_id=self.provider_id,
            cache_key=f"user:{canonical_value or google_id}",
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
            raise ValueError("Google Workspace provider is not fully configured")

        identifier = self._get_identifier(item)
        if not identifier:
            raise ValueError("Cannot determine identifier for Google Workspace lookup")

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
            raise ValueError("Google Workspace provider is not fully configured")

        token = await self._get_token(cfg["service_account"], cfg["admin_email"])
        headers = {"Authorization": f"Bearer {token}"}
        domain = cfg.get("domain") or ""
        results: List[EnrichmentResult] = []
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
                    except Exception as exc:
                        logger.warning("Google Workspace: skipping user %s: %s", user.get("id"), exc)
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

        logger.info("Google Workspace bulk sync: %d users", len(results))
        return results


google_workspace_provider = GoogleWorkspaceProvider()
