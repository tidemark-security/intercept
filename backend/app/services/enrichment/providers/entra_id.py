"""Microsoft Entra ID (Azure AD) user enrichment provider.

Uses the Microsoft Graph API with the OAuth2 client credentials flow.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
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

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
_TOKEN_SCOPE = "https://graph.microsoft.com/.default"
_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

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


class EntraIDProvider(UserDirectoryEnrichmentProvider):
    """Enrich InternalActorItem via Microsoft Graph API."""

    provider_id = "entra_id"
    display_name = "Microsoft Entra ID"
    settings_prefix = "enrichment.entra_id"
    supports_bulk_sync = True

    def __init__(self) -> None:
        self._token_value: str | None = None
        self._token_expires_at: datetime | None = None

    def _bounded_int(self, value: Any, *, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = minimum
        return max(minimum, min(maximum, parsed))

    def _bounded_float(self, value: Any, *, minimum: float, maximum: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = minimum
        return max(minimum, min(maximum, parsed))

    async def _get_token(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        request_timeout_seconds: float,
    ) -> str:
        now = datetime.now(timezone.utc)
        if self._token_value is not None and self._token_expires_at and now < self._token_expires_at:
            return self._token_value

        url = _TOKEN_URL.format(tenant_id=tenant_id)
        async with httpx.AsyncClient(timeout=request_timeout_seconds) as client:
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
            try:
                payload = resp.json()
            except ValueError as exc:
                raise EnrichmentProviderError(
                    "Entra ID token response is not valid JSON"
                ) from exc
            access_token, expires_in = self._parse_oauth_access_token_response(
                payload,
                provider_name="Entra ID",
            )
            self._token_value = access_token
            self._token_expires_at = now + timedelta(seconds=max(60, expires_in - 60))
            return self._token_value

    async def _get_settings(self, settings: SettingsService) -> Optional[Dict[str, Any]]:
        values = await self._get_setting_values(
            settings,
            (
                "tenant_id",
                "client_id",
                "client_secret",
                "request_timeout_seconds",
                "bulk_sync_page_size",
                "bulk_sync_max_records",
            ),
        )
        tenant_id = values["tenant_id"]
        client_id = values["client_id"]
        client_secret = values["client_secret"]
        if not (tenant_id and client_id and client_secret):
            return None
        return {
            "tenant_id": tenant_id,
            "client_id": client_id,
            "client_secret": client_secret,
            "request_timeout_seconds": self._bounded_float(
                values["request_timeout_seconds"],
                minimum=1,
                maximum=600,
            ),
            "bulk_sync_page_size": self._bounded_int(
                values["bulk_sync_page_size"],
                minimum=1,
                maximum=999,
            ),
            "bulk_sync_max_records": self._bounded_int(
                values["bulk_sync_max_records"],
                minimum=0,
                maximum=1_000_000,
            ),
        }

    async def _lookup_manager(
        self,
        token: str,
        identifier: str,
        request_timeout_seconds: float,
    ) -> Dict[str, Any] | None:
        headers = {"Authorization": f"Bearer {token}"}
        encoded_identifier = quote(identifier, safe="")
        async with httpx.AsyncClient(timeout=request_timeout_seconds) as client:
            resp = await client.get(
                f"{_GRAPH_BASE}/users/{encoded_identifier}/manager",
                headers=headers,
                params={"$select": "displayName,mail,userPrincipalName,id"},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    def _graph_headers(self, token: str, *, advanced_query: bool = False) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {token}"}
        if advanced_query:
            headers["ConsistencyLevel"] = "eventual"
        return headers

    def _should_try_direct_user_lookup(self, identifier: str) -> bool:
        return "@" in identifier or bool(_GUID_RE.match(identifier))

    def _normalize_sam_account_name(self, identifier: str) -> str:
        if "\\" in identifier:
            return identifier.rsplit("\\", 1)[-1]
        return identifier

    async def _lookup_user(
        self,
        token: str,
        identifier: str,
        request_timeout_seconds: float,
    ) -> Optional[Dict[str, Any]]:
        """Look up a single user by UPN/object id first, then by mail or samAccountName."""
        encoded_identifier = identifier.replace("'", "''")
        sam_identifier = self._normalize_sam_account_name(identifier)
        encoded_sam_identifier = sam_identifier.replace("'", "''")
        async with httpx.AsyncClient(timeout=request_timeout_seconds) as client:
            endpoints: List[tuple[str, Dict[str, str], Dict[str, Any]]] = []
            if self._should_try_direct_user_lookup(identifier):
                encoded_path_identifier = quote(identifier, safe="")
                endpoints.append(
                    (
                        f"{_GRAPH_BASE}/users/{encoded_path_identifier}",
                        self._graph_headers(token),
                        {"$select": _USER_FIELDS},
                    )
                )

            endpoints.extend([
                (
                    f"{_GRAPH_BASE}/users",
                    self._graph_headers(token),
                    {"$filter": f"mail eq '{encoded_identifier}'", "$select": _USER_FIELDS},
                ),
                (
                    f"{_GRAPH_BASE}/users",
                    self._graph_headers(token, advanced_query=True),
                    {
                        "$filter": f"onPremisesSamAccountName eq '{encoded_sam_identifier}'",
                        "$select": _USER_FIELDS,
                        "$count": "true",
                    },
                ),
            ])
            for endpoint, headers, params in endpoints:
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
        user = self._require_record_mapping(user)
        manager_info = (
            {}
            if manager is None
            else self._require_record_mapping(manager)
        )
        object_id = self._optional_string_field(user, "id")
        display_name = self._optional_string_field(user, "displayName")
        email = self._optional_string_field(user, "mail")
        upn = self._optional_string_field(user, "userPrincipalName")
        sam = self._optional_string_field(user, "onPremisesSamAccountName")
        employee_id = self._optional_string_field(user, "employeeId")
        business_phones = self._optional_string_list_field(user, "businessPhones")
        account_enabled = user.get("accountEnabled")
        if account_enabled is not None and not isinstance(account_enabled, bool):
            raise MalformedProviderRecordError(
                "Provider record field 'accountEnabled' must be a boolean"
            )
        canonical_value = self._build_user_cache_key_from_values(
            upn,
            email,
            object_id,
        ).removeprefix("user:")

        enrichment_data = {
            "object_id": object_id,
            "display_name": display_name,
            "given_name": self._optional_string_field(user, "givenName"),
            "surname": self._optional_string_field(user, "surname"),
            "email": email,
            "upn": upn,
            "job_title": self._optional_string_field(user, "jobTitle"),
            "department": self._optional_string_field(user, "department"),
            "office": self._optional_string_field(user, "officeLocation"),
            "mobile_phone": self._optional_string_field(user, "mobilePhone"),
            "business_phones": business_phones,
            "employee_id": employee_id,
            "manager_name": self._optional_string_field(manager_info, "displayName"),
            "manager_email": self._optional_string_field(manager_info, "mail"),
            "manager_upn": self._optional_string_field(
                manager_info,
                "userPrincipalName",
            ),
            "sam_account_name": sam,
            "account_enabled": account_enabled,
        }

        meta = {
            "department": enrichment_data["department"],
            "job_title": enrichment_data["job_title"],
            "display_name": display_name,
        }
        canonical_display = display_name or email or object_id

        alias_values = [
            ("object_id", object_id),
            ("email", email.lower() if email else ""),
            ("upn", upn.lower() if upn else ""),
            ("samaccountname", sam.lower() if sam else ""),
            ("display_name", display_name.lower() if display_name else ""),
        ]
        if employee_id:
            alias_values.append(("employee_id", employee_id))

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
                "Entra ID provider is not fully configured"
            )

        identifier = self._get_user_identifier(item)
        if not identifier:
            raise EnrichmentProviderError(
                "Cannot determine identifier for Entra ID lookup"
            )

        request_timeout_seconds = float(cfg["request_timeout_seconds"])
        token = await self._get_token(
            tenant_id=str(cfg["tenant_id"]),
            client_id=str(cfg["client_id"]),
            client_secret=str(cfg["client_secret"]),
            request_timeout_seconds=request_timeout_seconds,
        )
        user = await self._lookup_user(token, identifier, request_timeout_seconds)
        if user is None:
            return EnrichmentResult(
                provider_id=self.provider_id,
                cache_key=self.build_cache_key(item),
                enrichment_data={"error": f"User not found: {identifier}"},
            )

        manager = await self._lookup_manager(token, user.get("id") or identifier, request_timeout_seconds)
        return self._build_result(user, cache_key=self.build_cache_key(item), manager=manager)

    async def bulk_sync(self, *, db: AsyncSession, settings: SettingsService) -> List[EnrichmentResult]:
        cfg = await self._get_settings(settings)
        if not cfg:
            raise EnrichmentProviderConfigurationError(
                "Entra ID provider is not fully configured"
            )

        request_timeout_seconds = float(cfg["request_timeout_seconds"])
        token = await self._get_token(
            tenant_id=str(cfg["tenant_id"]),
            client_id=str(cfg["client_id"]),
            client_secret=str(cfg["client_secret"]),
            request_timeout_seconds=request_timeout_seconds,
        )
        headers = {"Authorization": f"Bearer {token}"}
        results: List[EnrichmentResult] = []
        malformed_records = 0
        page_size = int(cfg["bulk_sync_page_size"])
        max_records = int(cfg["bulk_sync_max_records"])
        url = f"{_GRAPH_BASE}/users?$select={_USER_FIELDS}&$top={page_size}&$filter=accountEnabled eq true"

        async with httpx.AsyncClient(timeout=request_timeout_seconds) as client:
            while url:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                for user in data.get("value", []):
                    if max_records > 0 and len(results) >= max_records:
                        break
                    try:
                        user = self._require_record_mapping(user)
                        cache_key = self._build_user_cache_key_from_values(
                            user.get("userPrincipalName"),
                            user.get("mail"),
                            user.get("id"),
                        )
                        results.append(self._build_result(user, cache_key=cache_key, manager=None))
                    except MalformedProviderRecordError:
                        malformed_records += 1
                if max_records > 0 and len(results) >= max_records:
                    break
                url = data.get("@odata.nextLink")

        if malformed_records:
            logger.warning(
                "Entra ID bulk sync skipped malformed user records (count=%d)",
                malformed_records,
            )
        logger.info("Entra ID bulk sync: %d users", len(results))
        return results


entra_id_provider = EntraIDProvider()
