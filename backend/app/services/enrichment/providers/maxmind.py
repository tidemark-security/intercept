from __future__ import annotations

import ipaddress
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.enrichment.base import AliasMapping, EnrichmentProvider, EnrichmentResult
from app.services.maxmind_service import maxmind_service
from app.services.settings_service import SettingsService


class MaxMindProvider(EnrichmentProvider):
    provider_id = "maxmind"
    display_name = "MaxMind GeoIP"
    settings_prefix = "enrichment.maxmind"
    supported_item_types = ("observable", "system", "network_traffic")
    supports_bulk_sync = False

    def can_enrich(self, item: Dict[str, Any]) -> bool:
        return bool(self._extract_candidate_ips(item))

    def build_cache_key(self, item: Dict[str, Any]) -> str:
        ips = sorted(self._extract_candidate_ips(item))
        if not ips:
            raise ValueError("No IP addresses available for MaxMind enrichment")
        return "|".join(ips)

    async def enrich(
        self,
        *,
        db: AsyncSession,
        settings: SettingsService,
        item: Dict[str, Any],
        entity_type: str,
        entity_id: int,
    ) -> EnrichmentResult:
        await maxmind_service.ensure_readers_loaded(settings=settings)

        ip_results: dict[str, Any] = {}
        aliases: list[AliasMapping] = []

        for ip in sorted(self._extract_candidate_ips(item)):
            lookup = await maxmind_service.lookup_ip(ip)
            ip_results[ip] = lookup
            aliases.extend(self._build_aliases(ip, lookup))

        return EnrichmentResult(
            provider_id=self.provider_id,
            cache_key=self.build_cache_key(item),
            enrichment_data={"results": ip_results},
            aliases=aliases,
            ttl_seconds=int(await settings.get("enrichment.maxmind.ttl_seconds", 604800) or 604800),
        )

    def _extract_candidate_ips(self, item: Dict[str, Any]) -> List[str]:
        item_type = item.get("type")
        raw_values: list[str] = []

        if item_type == "observable" and str(item.get("observable_type") or "").upper() == "IP":
            if item.get("observable_value"):
                raw_values.append(str(item["observable_value"]))
        elif item_type == "system":
            if item.get("ip_address"):
                raw_values.append(str(item["ip_address"]))
        elif item_type == "network_traffic":
            if item.get("source_ip"):
                raw_values.append(str(item["source_ip"]))
            if item.get("destination_ip"):
                raw_values.append(str(item["destination_ip"]))

        ips: list[str] = []
        seen: set[str] = set()
        for raw_value in raw_values:
            normalized = raw_value.strip()
            if not normalized:
                continue
            try:
                parsed = ipaddress.ip_address(normalized)
            except ValueError:
                continue
            if parsed.is_private or parsed.is_loopback or parsed.is_multicast or parsed.is_reserved or parsed.is_unspecified:
                continue
            canonical = str(parsed)
            if canonical in seen:
                continue
            seen.add(canonical)
            ips.append(canonical)
        return ips

    def _build_aliases(self, ip: str, lookup: Dict[str, Any]) -> List[AliasMapping]:
        databases = lookup.get("databases") or {}
        aliases: list[AliasMapping] = []

        def _add(alias_type: str, alias_value: str, attributes: Dict[str, Any]) -> None:
            normalized = alias_value.strip().lower()
            if not normalized:
                return
            aliases.append(
                AliasMapping(
                    entity_type="ip",
                    canonical_value=ip,
                    canonical_display=ip,
                    alias_type=alias_type,
                    alias_value=normalized,
                    attributes=attributes,
                )
            )

        asn_payload = databases.get("GeoLite2-ASN") or {}
        asn_org = asn_payload.get("autonomous_system_organization") or ""
        asn_number = asn_payload.get("autonomous_system_number")
        country_payload = (
            databases.get("GeoLite2-City")
            or databases.get("GeoIP2-City")
            or databases.get("GeoLite2-Country")
            or databases.get("GeoIP2-Country")
            or {}
        )
        country = country_payload.get("country") or {}
        attributes = {
            "asn": asn_number,
            "asn_organization": asn_org,
            "country_iso_code": country.get("iso_code"),
            "country_name": country.get("name"),
        }

        if asn_org:
            _add("asn_organization", asn_org, attributes)
        if country.get("iso_code"):
            _add("country_iso_code", str(country["iso_code"]), attributes)
        if country.get("name"):
            _add("country_name", str(country["name"]), attributes)

        return aliases


maxmind_provider = MaxMindProvider()