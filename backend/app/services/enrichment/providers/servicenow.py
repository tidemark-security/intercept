"""ServiceNow user enrichment provider.

Uses the ServiceNow Table API for sys_user-style directory lookups.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple
from urllib.parse import quote, urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.enrichment.base import AliasMapping, EnrichmentProvider, EnrichmentResult
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

_DEFAULT_TABLE = "sys_user"
_DEFAULT_FIELDS = (
    "sys_id,user_name,email,name,first_name,last_name,title,department,department.name,"
    "company,company.name,phone,mobile_phone,active,vip,u_privileged_user"
)
_DEFAULT_CMDB_FIELDS = "sys_id,name,fqdn,ip_address,asset_tag,sys_class_name,classification,criticality,u_privileged_system,install_status"


class ServiceNowProvider(EnrichmentProvider):
    """Enrich InternalActorItem and SystemItem via ServiceNow records."""

    provider_id = "servicenow"
    display_name = "ServiceNow"
    settings_prefix = "enrichment.servicenow"
    supported_item_types = ("internal_actor", "system")
    supports_bulk_sync = True

    def can_enrich(self, item: Dict[str, Any]) -> bool:
        item_type = item.get("type")
        if item_type == "internal_actor":
            return bool(self._get_identifier(item))
        if item_type == "system":
            return bool(self._get_system_identifier(item))
        return False

    def build_cache_key(self, item: Dict[str, Any]) -> str:
        if item.get("type") == "system":
            identifier = self._get_system_identifier(item)
            if not identifier:
                raise ValueError("Cannot determine identifier for ServiceNow system cache key")
            return self._build_system_cache_key(identifier)
        identifier = self._get_identifier(item)
        if not identifier:
            raise ValueError("Cannot determine identifier for ServiceNow user cache key")
        return f"user:{identifier}"

    def _build_system_cache_key(self, identifier: str) -> str:
        return f"system:{identifier.strip().lower()}"

    def _get_identifier(self, item: Dict[str, Any]) -> str:
        for key in ("user_id", "contact_email", "name"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        return ""

    def _get_system_identifier(self, item: Dict[str, Any]) -> str:
        for key in ("hostname", "ip_address", "cmdb_id"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        return ""

    def _split_fields(self, value: Any, default: str) -> List[str]:
        fields = [
            field.strip()
            for field in str(value or default).split(",")
            if field.strip()
        ]
        return list(dict.fromkeys(fields)) or [default]

    def _get_system_lookup_candidates(self, item: Dict[str, Any], cfg: Dict[str, Any]) -> List[Tuple[str, str, str]]:
        candidates: List[Tuple[str, str, str]] = []

        def _add(kind: str, fields: List[str], value: Any) -> None:
            if not isinstance(value, str) or not value.strip():
                return
            normalized_value = value.strip().lower()
            for field in fields:
                candidate = (kind, field, normalized_value)
                if candidate not in candidates:
                    candidates.append(candidate)

        configured_fields = self._split_fields(cfg.get("cmdb_query_field"), "name")
        _add("hostname", list(dict.fromkeys(["name", "fqdn", *configured_fields])), item.get("hostname"))
        _add("ip_address", list(dict.fromkeys(["ip_address", *configured_fields])), item.get("ip_address"))
        _add("cmdb_id", configured_fields, item.get("cmdb_id"))
        return candidates

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
            "user_vip_field": str(await settings.get(f"{self.settings_prefix}.user_vip_field", "vip") or "vip").strip(),
            "user_privileged_field": str(
                await settings.get(f"{self.settings_prefix}.user_privileged_field", "u_privileged_user")
                or "u_privileged_user"
            ).strip(),
            "cmdb_table": str(await settings.get(f"{self.settings_prefix}.cmdb_table", "cmdb_ci") or "cmdb_ci").strip(),
            "cmdb_query_field": str(await settings.get(f"{self.settings_prefix}.cmdb_query_field", "name") or "name").strip(),
            "cmdb_fields": str(await settings.get(f"{self.settings_prefix}.cmdb_fields", _DEFAULT_CMDB_FIELDS) or _DEFAULT_CMDB_FIELDS).strip(),
            "cmdb_criticality_field": str(
                await settings.get(f"{self.settings_prefix}.cmdb_criticality_field", "criticality")
                or "criticality"
            ).strip(),
            "cmdb_privileged_field": str(
                await settings.get(f"{self.settings_prefix}.cmdb_privileged_field", "u_privileged_system")
                or "u_privileged_system"
            ).strip(),
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

    def _cmdb_table_url(self, cfg: Dict[str, Any]) -> str:
        table = quote(str(cfg["cmdb_table"]), safe="")
        return f"{cfg['instance_url']}/api/now/table/{table}"

    def _cmdb_record_url(self, cfg: Dict[str, Any], sys_id: str) -> str:
        table = quote(str(cfg["cmdb_table"]), safe="")
        return f"{cfg['instance_url']}/nav_to.do?uri=/{table}.do?sys_id={quote(sys_id, safe='')}"

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

    def _bool_field(self, record: Dict[str, Any], field: str) -> bool:
        value = self._str_field(record, field).strip().lower()
        return value in {"true", "1", "yes", "y", "on"}

    def _record_link(self, cfg: Dict[str, Any], table: str, sys_id: str) -> str:
        if not sys_id:
            return ""
        return f"{cfg['instance_url']}/{quote(table, safe='')}.do?sys_id={quote(sys_id, safe='')}"

    def _build_result(
        self,
        record: Dict[str, Any],
        *,
        cache_key: str,
        cfg: Dict[str, Any] | None = None,
        matched_identifier: str = "",
    ) -> EnrichmentResult:
        cfg = cfg or {}
        sys_id = self._str_field(record, "sys_id")
        user_name = self._str_field(record, "user_name")
        email = self._str_field(record, "email")
        display_name = self._str_field(record, "name")
        first_name = self._str_field(record, "first_name")
        last_name = self._str_field(record, "last_name")
        department = self._str_field(record, "department.name") or self._str_field(record, "department")
        company = self._str_field(record, "company.name") or self._str_field(record, "company")

        vip_field = str(cfg.get("user_vip_field") or "vip")
        privileged_field = str(cfg.get("user_privileged_field") or "u_privileged_user")
        is_vip = self._bool_field(record, vip_field)
        is_privileged = self._bool_field(record, privileged_field)

        enrichment_data = {
            "source_table": str(cfg.get("table") or _DEFAULT_TABLE),
            "record_id": sys_id,
            "record_link": self._record_link(cfg, str(cfg.get("table") or _DEFAULT_TABLE), sys_id) if cfg else "",
            "matched_identifier": matched_identifier,
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
            "is_vip": is_vip,
            "is_privileged": is_privileged,
            "mapped_fields": {
                "vip": {"field": vip_field, "value": self._str_field(record, vip_field), "mapped": is_vip},
                "privileged": {
                    "field": privileged_field,
                    "value": self._str_field(record, privileged_field),
                    "mapped": is_privileged,
                },
            },
        }

        canonical_value = email.lower() or user_name.lower() or sys_id or cache_key
        canonical_display = display_name or email or user_name or sys_id
        meta = {
            "department": department,
            "job_title": enrichment_data["job_title"],
            "display_name": display_name,
            "is_vip": is_vip,
            "is_privileged": is_privileged,
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

    def _build_system_result(
        self,
        record: Dict[str, Any],
        *,
        cache_key: str,
        cfg: Dict[str, Any],
        matched_identifier: Dict[str, str],
    ) -> EnrichmentResult:
        sys_id = self._str_field(record, "sys_id")
        name = self._str_field(record, "name")
        fqdn = self._str_field(record, "fqdn")
        ip_address = self._str_field(record, "ip_address")
        criticality = self._str_field(record, str(cfg["cmdb_criticality_field"]))
        privileged_field = str(cfg["cmdb_privileged_field"])
        privilege_value = self._str_field(record, privileged_field)
        is_critical = self._boolish_criticality(criticality)
        is_privileged = self._bool_field(record, privileged_field)

        enrichment_data = {
            "status": "matched",
            "source_table": str(cfg["cmdb_table"]),
            "sys_id": sys_id,
            "record_id": sys_id,
            "record_link": self._cmdb_record_url(cfg, sys_id) if sys_id else "",
            "matched_identifier": matched_identifier,
            "name": name,
            "fqdn": fqdn,
            "ip_address": ip_address,
            "asset_tag": self._str_field(record, "asset_tag"),
            "ci_class": self._str_field(record, "sys_class_name"),
            "ci_type": self._str_field(record, "sys_class_name") or self._str_field(record, "classification"),
            "classification": self._str_field(record, "classification"),
            "criticality": criticality,
            "install_status": self._str_field(record, "install_status"),
            "privilege_fields": {privileged_field: privilege_value},
            "is_critical": is_critical,
            "is_privileged": is_privileged,
        }
        canonical_value = fqdn.lower() or name.lower() or sys_id or cache_key
        aliases: List[AliasMapping] = []

        def _add(alias_type: str, value: str) -> None:
            if value:
                aliases.append(
                    AliasMapping(
                        entity_type="system",
                        canonical_value=canonical_value,
                        canonical_display=name or fqdn or sys_id,
                        alias_type=alias_type,
                        alias_value=value,
                        attributes={"is_critical": is_critical, "is_privileged": is_privileged},
                    )
                )

        _add("servicenow_sys_id", sys_id)
        _add("hostname", name.lower() if name else "")
        _add("fqdn", fqdn.lower() if fqdn else "")
        _add("ip_address", ip_address)

        return EnrichmentResult(
            provider_id=self.provider_id,
            cache_key=cache_key,
            enrichment_data=enrichment_data,
            aliases=aliases,
        )

    def _boolish_criticality(self, value: str) -> bool:
        normalized = value.strip().lower()
        return normalized in {"true", "1", "yes", "high", "critical", "most critical"}

    def normalize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        instance_url = str(config.get("instance_url") or "").strip().rstrip("/")
        parsed = urlparse(instance_url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError("ServiceNow instance URL must be an absolute http(s) URL")

        user_query_field = str(config.get("user_query_field") or "user_name").strip()
        active_only = bool(config.get("active_only", True))
        lookup_query_template = f"{user_query_field}={{value}}"
        if active_only:
            lookup_query_template += "^active=true"

        fields = ",".join(
            dict.fromkeys(
                [
                    field.strip()
                    for field in (
                        _DEFAULT_FIELDS
                        + ","
                        + str(config.get("user_vip_field") or "vip")
                        + ","
                        + str(config.get("user_privileged_field") or "u_privileged_user")
                    ).split(",")
                    if field.strip()
                ]
            )
        )

        return {
            "instance_url": instance_url,
            "username": str(config.get("username") or "").strip(),
            "password": str(config.get("password") or ""),
            "table": str(config.get("user_table") or config.get("table") or _DEFAULT_TABLE).strip(),
            "fields": fields,
            "lookup_query_template": lookup_query_template,
            "bulk_sync_query": "active=true" if active_only else "",
            "page_size": 500,
            "max_records": 5000,
            "user_vip_field": str(config.get("user_vip_field") or "vip").strip(),
            "user_privileged_field": str(config.get("user_privileged_field") or "u_privileged_user").strip(),
            "cmdb_table": str(config.get("cmdb_table") or "cmdb_ci").strip(),
            "cmdb_query_field": str(config.get("cmdb_query_field") or "name").strip(),
            "cmdb_fields": _DEFAULT_CMDB_FIELDS,
            "cmdb_criticality_field": str(config.get("cmdb_criticality_field") or "criticality").strip(),
            "cmdb_privileged_field": str(config.get("cmdb_privileged_field") or "u_privileged_system").strip(),
        }

    async def preview(self, *, config: Dict[str, Any], item: Dict[str, Any]) -> EnrichmentResult:
        cfg = self.normalize_config(config)
        if not cfg["username"] or not cfg["password"]:
            raise ValueError("ServiceNow username and password are required")
        if not self.can_enrich(item):
            raise ValueError("ServiceNow preview requires an internal_actor or system item with a lookup identifier")
        return await self._lookup(cfg, item)

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

        return await self._lookup(cfg, item)

    async def _lookup(self, cfg: Dict[str, Any], item: Dict[str, Any]) -> EnrichmentResult:
        if item.get("type") == "system":
            candidates = self._get_system_lookup_candidates(item, cfg)
            if not candidates:
                raise ValueError("Cannot determine identifier for ServiceNow CMDB lookup")
            cache_key = self.build_cache_key(item)
            async with httpx.AsyncClient(timeout=20, auth=(cfg["username"], cfg["password"])) as client:
                for source, field, identifier in candidates:
                    candidate_cache_key = self._build_system_cache_key(identifier)
                    params = {
                        "sysparm_query": f"{field}={self._escape_query_value(identifier)}",
                        "sysparm_fields": cfg["cmdb_fields"],
                        "sysparm_display_value": "all",
                        "sysparm_limit": 2,
                    }
                    try:
                        resp = await client.get(self._cmdb_table_url(cfg), params=params)
                        resp.raise_for_status()
                        records = resp.json().get("result") or []
                    except httpx.HTTPError as exc:
                        logger.warning(
                            "ServiceNow CMDB lookup failed",
                            extra={
                                "source_table": str(cfg["cmdb_table"]),
                                "matched_identifier": {"source": source, "field": field, "value": identifier},
                            },
                        )
                        raise exc
                    if len(records) > 1:
                        return EnrichmentResult(
                            provider_id=self.provider_id,
                            cache_key=candidate_cache_key,
                            enrichment_data={
                                "status": "ambiguous",
                                "source_table": str(cfg["cmdb_table"]),
                                "matched_identifier": {"source": source, "field": field, "value": identifier},
                                "error": f"CMDB lookup returned multiple records for {field}={identifier}",
                                "record_count": len(records),
                            },
                        )
                    if records:
                        return self._build_system_result(
                            records[0],
                            cache_key=candidate_cache_key,
                            cfg=cfg,
                            matched_identifier={"source": source, "field": field, "value": identifier},
                        )

                return EnrichmentResult(
                    provider_id=self.provider_id,
                    cache_key=cache_key,
                    enrichment_data={
                        "status": "not_found",
                        "source_table": str(cfg["cmdb_table"]),
                        "lookup_identifiers": [
                            {"source": source, "field": field, "value": identifier}
                            for source, field, identifier in candidates
                        ],
                        "error": "CMDB item not found",
                    },
                )

        identifier = self._get_identifier(item)
        if not identifier:
            raise ValueError("Cannot determine identifier for ServiceNow lookup")
        params = {
            "sysparm_query": self._build_lookup_query(cfg["lookup_query_template"], identifier),
            "sysparm_fields": cfg["fields"],
            "sysparm_display_value": "all",
            "sysparm_limit": 2,
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
        if len(records) > 1:
            return EnrichmentResult(
                provider_id=self.provider_id,
                cache_key=self.build_cache_key(item),
                enrichment_data={"error": f"Ambiguous user lookup: {identifier}", "matched_identifier": identifier},
            )
        return self._build_result(
            records[0],
            cache_key=self.build_cache_key(item),
            cfg=cfg,
            matched_identifier=identifier,
        )

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
                        results.append(
                            self._build_result(
                                record,
                                cache_key=f"user:{canonical}",
                                cfg=cfg,
                                matched_identifier=canonical,
                            )
                        )
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
