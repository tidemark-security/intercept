from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.enrichment.base import (
    AliasMapping,
    EnrichmentProvider,
    EnrichmentProviderError,
    EnrichmentResult,
)
from app.services.enrichment.providers.ip_eligibility import normalize_public_ip_address
from app.services.maxmind_service import MaxMindConfigurationError, maxmind_service
from app.services.settings_service import SettingsService


class MaxMindProvider(EnrichmentProvider):
    provider_id = "maxmind"
    display_name = "MaxMind GeoIP"
    settings_prefix = "enrichment.maxmind"
    supported_item_types = ("observable", "system", "network_traffic")
    supports_bulk_sync = False

    def can_enrich(self, item: dict[str, Any]) -> bool:
        return bool(self._extract_candidate_ips(item))

    def build_cache_key(self, item: dict[str, Any]) -> str:
        ips = sorted(self._extract_candidate_ips(item))
        if not ips:
            raise EnrichmentProviderError(
                "No IP addresses available for MaxMind enrichment"
            )
        return "|".join(ips)

    async def enrich(
        self,
        *,
        db: AsyncSession,
        settings: SettingsService,
        item: dict[str, Any],
        entity_type: str,
        entity_id: int,
    ) -> EnrichmentResult:
        raw_ttl = await settings.get("enrichment.maxmind.ttl_seconds", 604800)
        if raw_ttl in (None, ""):
            raw_ttl = 604800
        try:
            ttl_seconds = int(raw_ttl)
        except (TypeError, ValueError) as exc:
            raise MaxMindConfigurationError(
                "MaxMind enrichment TTL must be an integer"
            ) from exc
        if ttl_seconds <= 0:
            raise MaxMindConfigurationError(
                "MaxMind enrichment TTL must be greater than zero"
            )

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
            ttl_seconds=ttl_seconds,
        )

    def _extract_candidate_ips(self, item: dict[str, Any]) -> list[str]:
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
            canonical = normalize_public_ip_address(normalized)
            if canonical is None:
                continue
            if canonical in seen:
                continue
            seen.add(canonical)
            ips.append(canonical)
        return ips

    def _build_aliases(self, ip: str, lookup: dict[str, Any]) -> list[AliasMapping]:
        databases = lookup.get("databases") or {}
        aliases: list[AliasMapping] = []

        def _add(
            alias_type: str,
            alias_value: str,
            attributes: dict[str, Any],
        ) -> None:
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
