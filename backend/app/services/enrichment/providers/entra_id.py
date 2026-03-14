"""Microsoft Entra ID (Azure AD) user enrichment provider.

Uses the Microsoft Graph API with the OAuth2 client credentials flow.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.enrichment.base import AliasMapping, EnrichmentProvider, EnrichmentResult
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
_TOKEN_SCOPE = "https://graph.microsoft.com/.default"

_USER_FIELDS = ",".join([
    "id",
    "displayName",
    "givenName",
    "surname",
    "mail",
    "userPrincipalName",
    "jobTitle",
    "department",
    "officeLocation",
    "mobilePhone",
    "businessPhones",
    "onPremisesSamAccountName",
    "employeeId",
    "accountEnabled",
])


class EntraIDProvider(EnrichmentProvider):
    """Enrich InternalActorItem via Microsoft Graph API."""

    provider_id = "entra_id"
    display_name = "Microsoft Entra ID"
    settings_prefix = "enrichment.entra_id"
    supported_item_types = ("internal_actor",)
    supports_bulk_sync = True

    def __init__(self) -> None:
        self._token_value: str | None = None
        self._token_expires_at: datetime | None = None

    def can_enrich(self, item: Dict[str, Any]) -> bool:
        return item.get("type") == "internal_actor" and bool(self._get_identifier(item))

    def build_cache_key(self, item: Dict[str, Any]) -> str:
        identifier = self._get_identifier(item)
        if not identifier:
            raise ValueError("Cannot determine identifier for Entra ID cache key")
        return f"user:{identifier}"

    def _get_identifier(self, item: Dict[str, Any]) -> str:
        for key in ("user_id", "contact_email", "name"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        return ""

    async def _get_token(self, tenant_id: str, client_id: str, client_secret: str) -> str:
        now = datetime.now(timezone.utc)
        if self._token_value and self._token_expires_at and now < self._token_expires_at:
            return self._token_value

        url = _TOKEN_URL.format(tenant_id=tenant_id)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": _TOKEN_SCOPE,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            self._token_value = payload["access_token"]
            expires_in = int(payload.get("expires_in") or 3600)
            self._token_expires_at = now + timedelta(seconds=max(60, expires_in - 60))
            return self._token_value

    async def _get_settings(self, settings: SettingsService) -> Optional[Dict[str, str]]:
        tenant_id = await settings.get(f"{self.settings_prefix}.tenant_id", "")
        client_id = await settings.get(f"{self.settings_prefix}.client_id", "")
        client_secret = await settings.get(f"{self.settings_prefix}.client_secret", "")
        if not (tenant_id and client_id and client_secret):
            return None
        return {"tenant_id": tenant_id, "client_id": client_id, "client_secret": client_secret}

    async def _lookup_manager(self, token: str, identifier: str) -> Dict[str, Any] | None:
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_GRAPH_BASE}/users/{identifier}/manager",
                headers=headers,
                params={"$select": "displayName,mail,userPrincipalName,id"},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def _lookup_user(self, token: str, identifier: str) -> Optional[Dict[str, Any]]:
        """Look up a single user by UPN/object id first, then by mail or samAccountName."""
        headers = {"Authorization": f"Bearer {token}"}
        encoded_identifier = identifier.replace("'", "''")
        async with httpx.AsyncClient(timeout=15) as client:
            endpoints = [
                (f"{_GRAPH_BASE}/users/{identifier}", {"$select": _USER_FIELDS}),
                (
                    f"{_GRAPH_BASE}/users",
                    {"$filter": f"mail eq '{encoded_identifier}'", "$select": _USER_FIELDS},
                ),
                (
                    f"{_GRAPH_BASE}/users",
                    {"$filter": f"onPremisesSamAccountName eq '{encoded_identifier}'", "$select": _USER_FIELDS},
                ),
            ]
            for endpoint, params in endpoints:
                try:
                    resp = await client.get(endpoint, headers=headers, params=params)
                    if resp.status_code == 404:
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    if isinstance(data, dict) and "value" in data:
                        values = data.get("value") or []
                        if values:
                            return values[0]
                        continue
                    return data
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        continue
                    raise
        return None

    def _build_result(self, user: Dict[str, Any], *, cache_key: str, manager: Dict[str, Any] | None) -> EnrichmentResult:
        object_id = user.get("id", "")
        display_name = user.get("displayName") or ""
        email = user.get("mail") or ""
        upn = user.get("userPrincipalName") or ""
        sam = user.get("onPremisesSamAccountName") or ""
        manager_info = manager or {}
        canonical_value = upn.lower() or email.lower() or object_id or cache_key

        enrichment_data = {
            "object_id": object_id,
            "display_name": display_name,
            "given_name": user.get("givenName") or "",
            "surname": user.get("surname") or "",
            "email": email,
            "upn": upn,
            "job_title": user.get("jobTitle") or "",
            "department": user.get("department") or "",
            "office": user.get("officeLocation") or "",
            "mobile_phone": user.get("mobilePhone") or "",
            "business_phones": user.get("businessPhones") or [],
            "employee_id": user.get("employeeId") or "",
            "manager_name": manager_info.get("displayName") or "",
            "manager_email": manager_info.get("mail") or "",
            "manager_upn": manager_info.get("userPrincipalName") or "",
            "sam_account_name": sam,
            "account_enabled": user.get("accountEnabled"),
        }

        aliases: List[AliasMapping] = []
        meta = {
            "department": enrichment_data["department"],
            "job_title": enrichment_data["job_title"],
            "display_name": display_name,
        }
        canonical_display = display_name or email or object_id

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

        _add("object_id", object_id)
        _add("email", email.lower() if email else "")
        _add("upn", upn.lower() if upn else "")
        _add("samaccountname", sam.lower() if sam else "")
        _add("display_name", display_name.lower() if display_name else "")
        if user.get("employeeId"):
            _add("employee_id", user["employeeId"])

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
            raise ValueError("Entra ID provider is not fully configured")

        identifier = self._get_identifier(item)
        if not identifier:
            raise ValueError("Cannot determine identifier for Entra ID lookup")

        token = await self._get_token(**cfg)
        user = await self._lookup_user(token, identifier)
        if user is None:
            return EnrichmentResult(
                provider_id=self.provider_id,
                cache_key=self.build_cache_key(item),
                enrichment_data={"error": f"User not found: {identifier}"},
            )

        manager = await self._lookup_manager(token, user.get("id") or identifier)
        return self._build_result(user, cache_key=self.build_cache_key(item), manager=manager)

    async def bulk_sync(self, *, db: AsyncSession, settings: SettingsService) -> List[EnrichmentResult]:
        cfg = await self._get_settings(settings)
        if not cfg:
            raise ValueError("Entra ID provider is not fully configured")

        token = await self._get_token(**cfg)
        headers = {"Authorization": f"Bearer {token}"}
        results: List[EnrichmentResult] = []
        url = f"{_GRAPH_BASE}/users?$select={_USER_FIELDS}&$top=999&$filter=accountEnabled eq true"

        async with httpx.AsyncClient(timeout=30) as client:
            while url:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                for user in data.get("value", []):
                    try:
                        cache_key = f"user:{str(user.get('userPrincipalName') or user.get('mail') or user.get('id') or '').strip().lower()}"
                        if cache_key == "user:":
                            continue
                        results.append(self._build_result(user, cache_key=cache_key, manager=None))
                    except Exception as exc:
                        logger.warning("Entra ID: skipping user %s: %s", user.get("id"), exc)
                url = data.get("@odata.nextLink")

        logger.info("Entra ID bulk sync: %d users", len(results))
        return results


entra_id_provider = EntraIDProvider()
