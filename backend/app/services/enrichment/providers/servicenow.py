"""ServiceNow user enrichment provider.

Uses the ServiceNow Table API for sys_user-style directory lookups.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Tuple
from urllib.parse import quote, urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.enrichment.base import (
    EnrichmentProvider,
    EnrichmentProviderConfigurationError,
    EnrichmentProviderError,
    EnrichmentResult,
    MalformedProviderRecordError,
)
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

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
            return bool(self._get_user_identifier(item))
        if item_type == "system":
            return bool(self._get_system_identifier(item))
        return False

    def build_cache_key(self, item: Dict[str, Any]) -> str:
        if item.get("type") == "system":
            identifier = self._get_system_identifier(item)
            if not identifier:
                raise EnrichmentProviderError(
                    "Cannot determine identifier for ServiceNow system cache key"
                )
            return self._build_system_cache_key(identifier)
        identifier = self._get_user_identifier(item)
        if not identifier:
            raise EnrichmentProviderError(
                "Cannot determine identifier for ServiceNow user cache key"
            )
        return f"user:{identifier}"

    def _build_system_cache_key(self, identifier: str) -> str:
        return f"system:{identifier.strip().lower()}"

    def _get_system_identifier(self, item: Dict[str, Any]) -> str:
        return self._get_normalized_identifier(item, ("hostname", "ip_address", "cmdb_id"))

    def _parse_bool(self, value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y", "on"}:
                return True
            if normalized in {"false", "0", "no", "n", "off", ""}:
                return False
        return bool(value)

    def _config_string(self, config: Dict[str, Any], *keys: str, default: str = "") -> str:
        for key in keys:
            if key in config and config[key] is not None:
                return str(config[key]).strip()
        return default

    def _split_fields(self, value: Any, default: str = "") -> List[str]:
        fields = [
            field.strip()
            for field in str(value if value is not None else default).split(",")
            if field.strip()
        ]
        return list(dict.fromkeys(fields))

    def _join_fields(self, fields: List[str]) -> str:
        return ",".join(fields)

    def _build_or_lookup_query(self, fields: List[str], identifier: str, *, active_only: bool = False) -> str:
        escaped = self._escape_query_value(identifier)
        query = "^OR".join(f"{field}={escaped}" for field in fields)
        if active_only:
            query = f"{query}^active=true"
        return query

    def _build_skip_result(self, item: Dict[str, Any], reason: str) -> EnrichmentResult:
        return EnrichmentResult(
            provider_id=self.provider_id,
            cache_key=self.build_cache_key(item),
            enrichment_data={"status": "skipped", "reason": reason},
        )

    def _bool_any_field(self, record: Dict[str, Any], fields: List[str]) -> bool:
        return any(self._bool_field(record, field) for field in fields)

    def _field_values(self, record: Dict[str, Any], fields: List[str]) -> Dict[str, str]:
        return {field: self._str_field(record, field) for field in fields}

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

        configured_fields = self._split_fields(cfg.get("cmdb_query_field"))
        if not configured_fields:
            return candidates
        _add("hostname", list(dict.fromkeys(["name", "fqdn", *configured_fields])), item.get("hostname"))
        _add("ip_address", list(dict.fromkeys(["ip_address", *configured_fields])), item.get("ip_address"))
        _add("cmdb_id", configured_fields, item.get("cmdb_id"))
        return candidates

    async def _get_settings(self, settings: SettingsService) -> Dict[str, Any] | None:
        values = await self._get_setting_values(
            settings,
            (
                "instance_url",
                "username",
                "password",
                "auth_type",
                "oauth_client_id",
                "oauth_client_secret",
                "user_table_enabled",
                "table",
                "fields",
                "user_query_field",
                "active_only",
                "bulk_sync_query",
                "page_size",
                "max_records",
                "user_vip_field",
                "user_privileged_field",
                "cmdb_table_enabled",
                "cmdb_table",
                "cmdb_query_field",
                "cmdb_fields",
                "cmdb_criticality_field",
                "cmdb_privileged_field",
            ),
        )
        instance_url = str(values["instance_url"] or "").strip().rstrip("/")
        username = str(values["username"] or "").strip()
        password = str(values["password"] or "")
        auth_type = str(
            values["auth_type"] or self._get_setting_default("auth_type")
        ).strip()
        oauth_client_id = str(values["oauth_client_id"] or "").strip()
        oauth_client_secret = str(values["oauth_client_secret"] or "")
        user_table_enabled = self._parse_bool(
            values["user_table_enabled"],
            bool(self._get_setting_default("user_table_enabled")),
        )
        table = str(values["table"]).strip()
        fields = str(values["fields"] or self._get_setting_default("fields")).strip()
        user_query_field = str(values["user_query_field"]).strip()
        active_only = self._parse_bool(
            values["active_only"],
            bool(self._get_setting_default("active_only")),
        )
        bulk_sync_query = str(values["bulk_sync_query"] or "").strip()
        page_size = self._bounded_int(
            values["page_size"],
            minimum=1,
            maximum=1000,
        )
        max_records = self._bounded_int(
            values["max_records"],
            minimum=1,
            maximum=50000,
        )

        if not (instance_url and username and password):
            return None
        if auth_type == "oauth_password" and not (oauth_client_id and oauth_client_secret):
            return None

        return {
            "instance_url": instance_url,
            "username": username,
            "password": password,
            "auth_type": auth_type,
            "oauth_client_id": oauth_client_id,
            "oauth_client_secret": oauth_client_secret,
            "user_table_enabled": user_table_enabled,
            "table": table,
            "user_query_field": user_query_field,
            "fields": fields,
            "bulk_sync_query": bulk_sync_query,
            "active_only": active_only,
            "page_size": page_size,
            "max_records": max_records,
            "user_vip_field": str(values["user_vip_field"]).strip(),
            "user_privileged_field": str(values["user_privileged_field"]).strip(),
            "cmdb_table_enabled": self._parse_bool(
                values["cmdb_table_enabled"],
                bool(self._get_setting_default("cmdb_table_enabled")),
            ),
            "cmdb_table": str(values["cmdb_table"]).strip(),
            "cmdb_query_field": str(values["cmdb_query_field"]).strip(),
            "cmdb_fields": str(
                values["cmdb_fields"] or self._get_setting_default("cmdb_fields")
            ).strip(),
            "cmdb_criticality_field": str(values["cmdb_criticality_field"]).strip(),
            "cmdb_privileged_field": str(values["cmdb_privileged_field"]).strip(),
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

    async def _oauth_access_token(self, cfg: Dict[str, Any]) -> str:
        try:
            import pysnow
        except ImportError as exc:
            raise EnrichmentProviderConfigurationError(
                "pysnow is required for ServiceNow OAuth authentication"
            ) from exc

        parsed = urlparse(str(cfg["instance_url"]))

        def _generate_access_token() -> str:
            client = pysnow.OAuthClient(
                host=parsed.netloc,
                use_ssl=parsed.scheme == "https",
                client_id=str(cfg["oauth_client_id"]),
                client_secret=str(cfg["oauth_client_secret"]),
            )
            token = client.generate_token(str(cfg["username"]), str(cfg["password"]))
            client.set_token(token)
            return str(token.get("access_token") or "")

        access_token = await asyncio.to_thread(_generate_access_token)
        if not access_token:
            raise EnrichmentProviderError(
                "ServiceNow OAuth token response did not include an access token"
            )
        return access_token

    @asynccontextmanager
    async def _http_client(self, cfg: Dict[str, Any], *, timeout: int):
        auth_type = str(
            cfg.get("auth_type") or self._get_setting_default("auth_type")
        )
        if auth_type == "oauth_password":
            access_token = await self._oauth_access_token(cfg)
            async with httpx.AsyncClient(
                timeout=timeout,
                headers={"Authorization": f"Bearer {access_token}"},
            ) as client:
                yield client
            return

        async with httpx.AsyncClient(timeout=timeout, auth=(cfg["username"], cfg["password"])) as client:
            yield client

    def _escape_query_value(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("^", "\\^").replace("=", "\\=")

    def _str_field(self, record: Dict[str, Any], field: str) -> str:
        record = self._require_record_mapping(record)
        raw = record.get(field)
        if isinstance(raw, dict):
            value = raw.get("display_value") or raw.get("value")
        else:
            value = raw
        if value is None:
            return ""
        if not isinstance(value, (str, int, float, bool)):
            raise MalformedProviderRecordError(
                f"Provider record field {field!r} must contain a scalar value"
            )
        return str(value)

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

        vip_fields = self._split_fields(cfg.get("user_vip_field"))
        privileged_fields = self._split_fields(cfg.get("user_privileged_field"))
        is_vip = self._bool_any_field(record, vip_fields)
        is_privileged = self._bool_any_field(record, privileged_fields)
        vip_values = self._field_values(record, vip_fields)
        privileged_values = self._field_values(record, privileged_fields)

        mapped_fields: Dict[str, Dict[str, Any]] = {}
        if vip_fields:
            mapped_fields["vip"] = {
                "field": self._join_fields(vip_fields),
                "value": ", ".join(value for value in vip_values.values() if value),
                "values": vip_values,
                "mapped": is_vip,
            }
        if privileged_fields:
            mapped_fields["privileged"] = {
                "field": self._join_fields(privileged_fields),
                "value": ", ".join(value for value in privileged_values.values() if value),
                "values": privileged_values,
                "mapped": is_privileged,
            }

        source_table = str(cfg.get("table") or self._get_setting_default("table"))
        enrichment_data = {
            "source_table": source_table,
            "record_id": sys_id,
            "record_link": self._record_link(cfg, source_table, sys_id) if cfg else "",
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
            "mapped_fields": mapped_fields,
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
        aliases = self._build_alias_mappings(
            entity_type="user",
            canonical_value=canonical_value,
            canonical_display=canonical_display,
            attributes=meta,
            aliases=[
                ("servicenow_sys_id", sys_id),
                ("username", user_name.lower() if user_name else ""),
                ("email", email.lower() if email else ""),
                ("display_name", display_name.lower() if display_name else ""),
            ],
        )

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
        criticality_fields = self._split_fields(cfg.get("cmdb_criticality_field"))
        privileged_fields = self._split_fields(cfg.get("cmdb_privileged_field"))
        criticality_values = self._field_values(record, criticality_fields)
        privilege_values = self._field_values(record, privileged_fields)
        criticality = next((value for value in criticality_values.values() if value), "")
        is_critical = any(self._boolish_criticality(value) for value in criticality_values.values())
        is_privileged = self._bool_any_field(record, privileged_fields)

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
            "criticality_fields": criticality_values,
            "privilege_fields": privilege_values,
            "is_critical": is_critical,
            "is_privileged": is_privileged,
        }
        canonical_value = fqdn.lower() or name.lower() or sys_id or cache_key
        aliases = self._build_alias_mappings(
            entity_type="system",
            canonical_value=canonical_value,
            canonical_display=name or fqdn or sys_id,
            attributes={"is_critical": is_critical, "is_privileged": is_privileged},
            aliases=[
                ("servicenow_sys_id", sys_id),
                ("hostname", name.lower() if name else ""),
                ("fqdn", fqdn.lower() if fqdn else ""),
                ("ip_address", ip_address),
            ],
        )

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
            raise EnrichmentProviderConfigurationError(
                "ServiceNow instance URL must be an absolute http(s) URL"
            )

        user_query_field = self._config_string(
            config,
            "user_query_field",
            default=str(self._get_setting_default("user_query_field")),
        )
        user_query_fields = self._split_fields(user_query_field)
        default_active_only = bool(self._get_setting_default("active_only"))
        active_only = self._parse_bool(
            config.get("active_only", default_active_only),
            default_active_only,
        )
        lookup_query_template = "^OR".join(f"{field}={{value}}" for field in user_query_fields)
        if lookup_query_template and active_only:
            lookup_query_template += "^active=true"

        user_vip_field = self._config_string(
            config,
            "user_vip_field",
            default=str(self._get_setting_default("user_vip_field")),
        )
        user_privileged_field = self._config_string(
            config,
            "user_privileged_field",
            default=str(self._get_setting_default("user_privileged_field")),
        )
        cmdb_criticality_field = self._config_string(
            config,
            "cmdb_criticality_field",
            default=str(self._get_setting_default("cmdb_criticality_field")),
        )
        cmdb_privileged_field = self._config_string(
            config,
            "cmdb_privileged_field",
            default=str(self._get_setting_default("cmdb_privileged_field")),
        )

        default_fields = str(self._get_setting_default("fields"))
        fields = ",".join(
            dict.fromkeys(
                [
                    field.strip()
                    for field in (
                        default_fields
                        + ","
                        + user_vip_field
                        + ","
                        + user_privileged_field
                    ).split(",")
                    if field.strip()
                ]
            )
        )

        auth_type = str(
            config.get("auth_type") or self._get_setting_default("auth_type")
        ).strip()
        if auth_type not in {"basic", "oauth_password"}:
            raise EnrichmentProviderConfigurationError(
                "ServiceNow auth_type must be basic or oauth_password"
            )

        default_user_table_enabled = bool(
            self._get_setting_default("user_table_enabled")
        )
        default_cmdb_table_enabled = bool(
            self._get_setting_default("cmdb_table_enabled")
        )
        normalized = {
            "instance_url": instance_url,
            "username": str(config.get("username") or "").strip(),
            "password": str(config.get("password") or ""),
            "auth_type": auth_type,
            "oauth_client_id": str(config.get("oauth_client_id") or "").strip(),
            "oauth_client_secret": str(config.get("oauth_client_secret") or ""),
            "user_table_enabled": self._parse_bool(
                config.get("user_table_enabled", default_user_table_enabled),
                default_user_table_enabled,
            ),
            "table": self._config_string(
                config,
                "user_table",
                "table",
                default=str(self._get_setting_default("table")),
            ),
            "user_query_field": user_query_field,
            "fields": fields,
            "lookup_query_template": lookup_query_template,
            "bulk_sync_query": (
                str(self._get_setting_default("bulk_sync_query"))
                if active_only
                else ""
            ),
            "active_only": active_only,
            "page_size": self._get_setting_default("page_size"),
            "max_records": self._get_setting_default("max_records"),
            "user_vip_field": user_vip_field,
            "user_privileged_field": user_privileged_field,
            "cmdb_table_enabled": self._parse_bool(
                config.get("cmdb_table_enabled", default_cmdb_table_enabled),
                default_cmdb_table_enabled,
            ),
            "cmdb_table": self._config_string(
                config,
                "cmdb_table",
                default=str(self._get_setting_default("cmdb_table")),
            ),
            "cmdb_query_field": self._config_string(
                config,
                "cmdb_query_field",
                default=str(self._get_setting_default("cmdb_query_field")),
            ),
            "cmdb_fields": ",".join(
                dict.fromkeys(
                    [
                        field.strip()
                        for field in (
                            str(self._get_setting_default("cmdb_fields"))
                            + ","
                            + cmdb_criticality_field
                            + ","
                            + cmdb_privileged_field
                        ).split(",")
                        if field.strip()
                    ]
                )
            ),
            "cmdb_criticality_field": cmdb_criticality_field,
            "cmdb_privileged_field": cmdb_privileged_field,
        }
        if not normalized["username"] or not normalized["password"]:
            raise EnrichmentProviderConfigurationError(
                "ServiceNow username and password are required"
            )
        if auth_type == "oauth_password" and not (
            normalized["oauth_client_id"] and normalized["oauth_client_secret"]
        ):
            raise EnrichmentProviderConfigurationError(
                "ServiceNow OAuth client ID and client secret are required"
            )
        return normalized

    async def preview(self, *, config: Dict[str, Any], item: Dict[str, Any]) -> EnrichmentResult:
        cfg = self.normalize_config(config)
        if not self.can_enrich(item):
            raise EnrichmentProviderError(
                "ServiceNow preview requires an internal_actor or system item "
                "with a lookup identifier"
            )
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
            raise EnrichmentProviderConfigurationError(
                "ServiceNow provider is not fully configured"
            )

        return await self._lookup(cfg, item)

    async def _lookup(self, cfg: Dict[str, Any], item: Dict[str, Any]) -> EnrichmentResult:
        if item.get("type") == "system":
            if not self._parse_bool(
                cfg.get("cmdb_table_enabled"),
                bool(self._get_setting_default("cmdb_table_enabled")),
            ):
                return self._build_skip_result(item, "ServiceNow CMDB table is disabled")
            if not str(cfg.get("cmdb_table") or "").strip():
                return self._build_skip_result(item, "ServiceNow CMDB table is blank")
            if not self._split_fields(cfg.get("cmdb_query_field")):
                return self._build_skip_result(item, "ServiceNow CMDB lookup fields are blank")
            candidates = self._get_system_lookup_candidates(item, cfg)
            if not candidates:
                return self._build_skip_result(item, "ServiceNow CMDB lookup fields are blank")
            cache_key = self.build_cache_key(item)
            async with self._http_client(cfg, timeout=20) as client:
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
                            "ServiceNow CMDB lookup failed for %s lookup field %s",
                            source,
                            field,
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

        identifier = self._get_user_identifier(item)
        if not identifier:
            raise EnrichmentProviderError(
                "Cannot determine identifier for ServiceNow lookup"
            )
        if not self._parse_bool(
            cfg.get("user_table_enabled"),
            bool(self._get_setting_default("user_table_enabled")),
        ):
            return self._build_skip_result(item, "ServiceNow user table is disabled")
        if not str(cfg.get("table") or "").strip():
            return self._build_skip_result(item, "ServiceNow user table is blank")
        user_query_fields = self._split_fields(cfg.get("user_query_field"))
        if not user_query_fields:
            return self._build_skip_result(item, "ServiceNow user lookup fields are blank")
        params = {
            "sysparm_query": self._build_or_lookup_query(
                user_query_fields,
                identifier,
                active_only=self._parse_bool(
                    cfg.get("active_only"),
                    bool(self._get_setting_default("active_only")),
                ),
            ),
            "sysparm_fields": cfg["fields"],
            "sysparm_display_value": "all",
            "sysparm_limit": 2,
        }
        async with self._http_client(cfg, timeout=20) as client:
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
            raise EnrichmentProviderConfigurationError(
                "ServiceNow provider is not fully configured"
            )
        if (
            not self._parse_bool(
                cfg.get("user_table_enabled"),
                bool(self._get_setting_default("user_table_enabled")),
            )
            or not str(cfg.get("table") or "").strip()
            or not self._split_fields(cfg.get("user_query_field"))
        ):
            return []

        results: List[EnrichmentResult] = []
        malformed_records = 0
        remaining = int(cfg["max_records"])
        offset = 0

        async with self._http_client(cfg, timeout=30) as client:
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
                        cache_key = self._build_user_cache_key_from_values(
                            self._str_field(record, "email"),
                            self._str_field(record, "user_name"),
                            self._str_field(record, "sys_id"),
                        )
                        canonical = cache_key.removeprefix("user:")
                        results.append(
                            self._build_result(
                                record,
                                cache_key=cache_key,
                                cfg=cfg,
                                matched_identifier=canonical,
                            )
                        )
                    except MalformedProviderRecordError:
                        malformed_records += 1

                fetched = len(records)
                if fetched < limit:
                    break
                remaining -= fetched
                offset += fetched

        if malformed_records:
            logger.warning(
                "ServiceNow bulk sync skipped malformed user records (count=%d)",
                malformed_records,
            )
        logger.info("ServiceNow bulk sync: %d users", len(results))
        return results


servicenow_provider = ServiceNowProvider()
