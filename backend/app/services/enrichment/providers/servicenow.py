"""ServiceNow user enrichment provider.

Uses the ServiceNow Table API for sys_user-style directory lookups.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List
from urllib.parse import quote

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.enrichment.base import AliasMapping, EnrichmentProvider, EnrichmentResult
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

_DEFAULT_TABLE = "sys_user"
_DEFAULT_FIELDS = (
    "sys_id,user_name,email,name,first_name,last_name,title,department,department.name,"
    "company,company.name,phone,mobile_phone,active"
)


class ServiceNowProvider(EnrichmentProvider):
    """Enrich InternalActorItem via ServiceNow user records."""

    provider_id = "servicenow"
    display_name = "ServiceNow"
    settings_prefix = "enrichment.servicenow"
    supported_item_types = ("internal_actor",)
    supports_bulk_sync = True

    def can_enrich(self, item: Dict[str, Any]) -> bool:
        return item.get("type") == "internal_actor" and bool(self._get_identifier(item))

    def build_cache_key(self, item: Dict[str, Any]) -> str:
        identifier = self._get_identifier(item)
        if not identifier:
            raise ValueError("Cannot determine identifier for ServiceNow cache key")
        return f"user:{identifier}"

    def _get_identifier(self, item: Dict[str, Any]) -> str:
        for key in ("user_id", "contact_email", "name"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        return ""

    async def _get_settings(self, settings: SettingsService) -> Dict[str, Any] | None:
        instance_url = str(await settings.get(f"{self.settings_prefix}.instance_url", "") or "").strip().rstrip("/")
        username = str(await settings.get(f"{self.settings_prefix}.username", "") or "").strip()
        password = str(await settings.get(f"{self.settings_prefix}.password", "") or "")
        table = str(await settings.get(f"{self.settings_prefix}.table", _DEFAULT_TABLE) or _DEFAULT_TABLE).strip()
        fields = str(await settings.get(f"{self.settings_prefix}.fields", _DEFAULT_FIELDS) or _DEFAULT_FIELDS).strip()
        lookup_query_template = str(
            await settings.get(
                f"{self.settings_prefix}.lookup_query_template",
                "email={value}^ORuser_name={value}^ORname={value}",
            )
            or ""
        ).strip()
        bulk_sync_query = str(
            await settings.get(f"{self.settings_prefix}.bulk_sync_query", "active=true") or ""
        ).strip()
        page_size = self._bounded_int(
            await settings.get(f"{self.settings_prefix}.page_size", 500),
            minimum=1,
            maximum=1000,
        )
        max_records = self._bounded_int(
            await settings.get(f"{self.settings_prefix}.max_records", 5000),
            minimum=1,
            maximum=50000,
        )

        if not (instance_url and username and password and table):
            return None

        return {
            "instance_url": instance_url,
            "username": username,
            "password": password,
            "table": table,
            "fields": fields,
            "lookup_query_template": lookup_query_template,
            "bulk_sync_query": bulk_sync_query,
            "page_size": page_size,
            "max_records": max_records,
        }

    def _bounded_int(self, value: Any, *, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = minimum
        return min(max(parsed, minimum), maximum)

    def _table_url(self, cfg: Dict[str, Any]) -> str:
        table = quote(str(cfg["table"]), safe="")
        return f"{cfg['instance_url']}/api/now/table/{table}"

    def _escape_query_value(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("^", "\\^").replace("=", "\\=")

    def _build_lookup_query(self, template: str, identifier: str) -> str:
        escaped = self._escape_query_value(identifier)
        return template.replace("{value}", escaped).replace("{uid}", escaped)

    def _str_field(self, record: Dict[str, Any], field: str) -> str:
        raw = record.get(field)
        if isinstance(raw, dict):
            value = raw.get("display_value") or raw.get("value")
            return str(value) if value is not None else ""
        if raw is None:
            return ""
        return str(raw)

    def _build_result(self, record: Dict[str, Any], *, cache_key: str) -> EnrichmentResult:
        sys_id = self._str_field(record, "sys_id")
        user_name = self._str_field(record, "user_name")
        email = self._str_field(record, "email")
        display_name = self._str_field(record, "name")
        first_name = self._str_field(record, "first_name")
        last_name = self._str_field(record, "last_name")
        department = self._str_field(record, "department.name") or self._str_field(record, "department")
        company = self._str_field(record, "company.name") or self._str_field(record, "company")

        enrichment_data = {
            "sys_id": sys_id,
            "user_name": user_name,
            "email": email,
            "display_name": display_name,
            "first_name": first_name,
            "last_name": last_name,
            "job_title": self._str_field(record, "title"),
            "department": department,
            "company": company,
            "phone": self._str_field(record, "phone"),
            "mobile_phone": self._str_field(record, "mobile_phone"),
            "active": self._str_field(record, "active"),
        }

        canonical_value = email.lower() or user_name.lower() or sys_id or cache_key
        canonical_display = display_name or email or user_name or sys_id
        meta = {
            "department": department,
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

        _add("servicenow_sys_id", sys_id)
        _add("username", user_name.lower() if user_name else "")
        _add("email", email.lower() if email else "")
        _add("display_name", display_name.lower() if display_name else "")

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
            raise ValueError("ServiceNow provider is not fully configured")

        identifier = self._get_identifier(item)
        if not identifier:
            raise ValueError("Cannot determine identifier for ServiceNow lookup")

        params = {
            "sysparm_query": self._build_lookup_query(cfg["lookup_query_template"], identifier),
            "sysparm_fields": cfg["fields"],
            "sysparm_display_value": "all",
            "sysparm_limit": 1,
        }
        async with httpx.AsyncClient(timeout=20, auth=(cfg["username"], cfg["password"])) as client:
            resp = await client.get(self._table_url(cfg), params=params)
            resp.raise_for_status()
            records = resp.json().get("result") or []

        if not records:
            return EnrichmentResult(
                provider_id=self.provider_id,
                cache_key=self.build_cache_key(item),
                enrichment_data={"error": f"User not found: {identifier}"},
            )
        return self._build_result(records[0], cache_key=self.build_cache_key(item))

    async def bulk_sync(self, *, db: AsyncSession, settings: SettingsService) -> List[EnrichmentResult]:
        cfg = await self._get_settings(settings)
        if not cfg:
            raise ValueError("ServiceNow provider is not fully configured")

        results: List[EnrichmentResult] = []
        remaining = int(cfg["max_records"])
        offset = 0

        async with httpx.AsyncClient(timeout=30, auth=(cfg["username"], cfg["password"])) as client:
            while remaining > 0:
                limit = min(int(cfg["page_size"]), remaining)
                params = {
                    "sysparm_fields": cfg["fields"],
                    "sysparm_display_value": "all",
                    "sysparm_limit": limit,
                    "sysparm_offset": offset,
                }
                if cfg["bulk_sync_query"]:
                    params["sysparm_query"] = cfg["bulk_sync_query"]

                resp = await client.get(self._table_url(cfg), params=params)
                resp.raise_for_status()
                records = resp.json().get("result") or []
                if not records:
                    break

                for record in records:
                    try:
                        canonical = (
                            self._str_field(record, "email")
                            or self._str_field(record, "user_name")
                            or self._str_field(record, "sys_id")
                        ).strip().lower()
                        if not canonical:
                            continue
                        results.append(self._build_result(record, cache_key=f"user:{canonical}"))
                    except Exception as exc:
                        logger.warning("ServiceNow: skipping user %s: %s", record.get("sys_id"), exc)

                fetched = len(records)
                if fetched < limit:
                    break
                remaining -= fetched
                offset += fetched

        logger.info("ServiceNow bulk sync: %d users", len(results))
        return results


servicenow_provider = ServiceNowProvider()
