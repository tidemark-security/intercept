from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.entity_ids import KIND_TO_PREFIX, format_entity_id
from app.services.enrichment.base import (
    EnrichmentProvider,
    EnrichmentProviderError,
    EnrichmentResult,
)
from app.services.enrichment.providers.ip_eligibility import normalize_public_ip_address
from app.services.settings_service import SettingsService


DEFAULT_MAX_LOOKBACK_DAYS = 180

MATCH_SQL = """
    (
        jsonb_extract_path_text(timeline_match.item, 'type') = 'observable'
        AND upper(coalesce(jsonb_extract_path_text(timeline_match.item, 'observable_type'), '')) = :observable_type
        AND lower(coalesce(jsonb_extract_path_text(timeline_match.item, 'observable_value'), '')) = :observable_value
    )
    OR EXISTS (
        SELECT 1
        FROM jsonb_to_recordset(CAST(:field_mappings AS jsonb)) AS field_mapping(item_type text, field_name text)
        WHERE jsonb_extract_path_text(timeline_match.item, 'type') = field_mapping.item_type
          AND lower(coalesce(jsonb_extract_path_text(timeline_match.item, field_mapping.field_name), '')) = :observable_value
    )
"""

CORRELATION_FIELD_MAPPINGS: dict[str, list[tuple[str, str]]] = {
    "IP": [
        ("system", "ip_address"),
        ("network_traffic", "source_ip"),
        ("network_traffic", "destination_ip"),
    ],
    "EMAIL": [
        ("internal_actor", "contact_email"),
        ("external_actor", "contact_email"),
        ("threat_actor", "contact_email"),
        ("email", "sender"),
        ("email", "recipient"),
    ],
    "URL": [
        ("attachment", "url"),
        ("ttp", "url"),
        ("link", "url"),
        ("forensic_artifact", "url"),
    ],
    "DOMAIN": [
        ("system", "hostname"),
    ],
    "HASH": [
        ("attachment", "file_hash"),
        ("forensic_artifact", "hash"),
    ],
    "FILENAME": [
        ("attachment", "file_name"),
        ("process", "process_name"),
    ],
    "PROCESS_NAME": [
        ("process", "process_name"),
    ],
}


class CrossCaseObservableProvider(EnrichmentProvider):
    provider_id = "cross_case_observable"
    display_name = "Cross-Timeline Observable Correlation"
    settings_prefix = "enrichment.cross_case_observable"
    supported_item_types = ("observable", "network_traffic", "system")
    supports_bulk_sync = False
    cacheable = False

    def can_enrich(self, item: Dict[str, Any]) -> bool:
        return bool(self._observables(item))

    def build_cache_key(self, item: Dict[str, Any]) -> str:
        observables = self._observables(item)
        if not observables:
            raise EnrichmentProviderError(
                "No observable available for cross-case correlation"
            )
        return "|".join(f"{observable_type}:{observable_value}" for observable_type, observable_value in observables)

    async def enrich(
        self,
        *,
        db: AsyncSession,
        settings: SettingsService,
        item: Dict[str, Any],
        entity_type: str,
        entity_id: int,
    ) -> EnrichmentResult:
        observables = self._observables(item)
        if not observables:
            raise EnrichmentProviderError(
                "No observable available for cross-case correlation"
            )

        max_lookback_days = await self._max_lookback_days(settings)
        lookback_started_at = datetime.now(timezone.utc) - timedelta(days=max_lookback_days)

        correlations: list[dict[str, Any]] = []
        for observable_type, observable_value in observables:
            correlations.append(
                await self._run_correlation_query(
                    db=db,
                    observable_type=observable_type,
                    observable_value=observable_value,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    lookback_started_at=lookback_started_at,
                    max_lookback_days=max_lookback_days,
                )
            )

        primary = correlations[0]
        return EnrichmentResult(
            provider_id=self.provider_id,
            cache_key=self.build_cache_key(item),
            enrichment_data={
                "observable_type": primary["observable_type"],
                "observable_value": primary["observable_value"],
                "queried_at": datetime.now(timezone.utc).isoformat(),
                "max_lookback_days": max_lookback_days,
                "lookback_started_at": lookback_started_at.isoformat(),
                "match_count": primary["match_count"],
                "matches": primary["matches"],
                "correlations": correlations,
            },
            ttl_seconds=None,
        )

    async def _run_correlation_query(
        self,
        *,
        db: AsyncSession,
        observable_type: str,
        observable_value: str,
        entity_type: str,
        entity_id: int,
        lookback_started_at: datetime,
        max_lookback_days: int,
    ) -> dict[str, Any]:
        prefilter_sql, match_sql, match_params = self._build_match_sql(observable_type)
        query = text(f"""
            WITH candidate_entities AS (
                SELECT
                    'alert' AS entity_type,
                    id AS entity_id,
                    title,
                    CAST(status AS text) AS status,
                    CAST(priority AS text) AS priority,
                    created_at,
                    updated_at,
                    timeline_items
                FROM alerts
                WHERE updated_at >= :lookback_started_at
                  AND NOT (:entity_type = 'alert' AND id = :entity_id)
                  AND ({prefilter_sql})
                UNION ALL
                SELECT
                    'case' AS entity_type,
                    id AS entity_id,
                    title,
                    CAST(status AS text) AS status,
                    CAST(priority AS text) AS priority,
                    created_at,
                    updated_at,
                    timeline_items
                FROM cases
                WHERE updated_at >= :lookback_started_at
                  AND NOT (:entity_type = 'case' AND id = :entity_id)
                  AND ({prefilter_sql})
                UNION ALL
                SELECT
                    'task' AS entity_type,
                    id AS entity_id,
                    title,
                    CAST(status AS text) AS status,
                    CAST(priority AS text) AS priority,
                    created_at,
                    updated_at,
                    timeline_items
                FROM tasks
                WHERE updated_at >= :lookback_started_at
                  AND NOT (:entity_type = 'task' AND id = :entity_id)
                  AND ({prefilter_sql})
            ),
            matches AS (
                SELECT
                    entity_type,
                    entity_id,
                    title,
                    status,
                    priority,
                    created_at,
                    updated_at
                FROM candidate_entities
                WHERE EXISTS (
                    SELECT 1
                    FROM jsonb_each(
                        CASE
                            WHEN jsonb_typeof(timeline_items) = 'object' THEN timeline_items
                            ELSE '{{}}'::jsonb
                        END
                    ) AS timeline_match(key, item)
                    WHERE {match_sql}
                )
                OR EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(
                        CASE
                            WHEN jsonb_typeof(timeline_items) = 'array' THEN timeline_items
                            ELSE '[]'::jsonb
                        END
                    ) AS timeline_match(item)
                    WHERE {match_sql}
                )
            ),
            counted AS (
                SELECT
                    *,
                    count(*) OVER () AS match_count
                FROM matches
            )
            SELECT *
            FROM counted
            ORDER BY updated_at DESC
            LIMIT 5
        """)
        result = await db.execute(
            query,
            {
                "entity_type": entity_type.lower(),
                "entity_id": entity_id,
                "observable_type": observable_type,
                "observable_value": observable_value,
                "lookback_started_at": lookback_started_at,
                **match_params,
            },
        )
        rows = result.mappings().all()
        matches = [self._format_match(row) for row in rows]
        total = int(rows[0]["match_count"]) if rows else 0

        return {
            "observable_type": observable_type,
            "observable_value": observable_value,
            "max_lookback_days": max_lookback_days,
            "lookback_started_at": lookback_started_at.isoformat(),
            "match_count": total,
            "matches": matches,
        }

    def _build_match_sql(self, observable_type: str) -> tuple[str, str, dict[str, Any]]:
        field_mappings = CORRELATION_FIELD_MAPPINGS.get(observable_type, [])
        candidate_types = sorted({"observable", *(item_type for item_type, _ in field_mappings)})
        field_mapping_records = [
            {"item_type": item_type, "field_name": field_name}
            for item_type, field_name in field_mappings
        ]
        params: dict[str, Any] = {
            "field_mappings": json.dumps(field_mapping_records),
        }
        prefilter_parts: list[str] = []
        for index, item_type in enumerate(candidate_types):
            object_path_param = f"candidate_object_path_{index}"
            array_path_param = f"candidate_array_path_{index}"
            encoded_item_type = json.dumps(item_type)
            prefilter_parts.append(f"timeline_items @? CAST(:{object_path_param} AS jsonpath)")
            prefilter_parts.append(f"timeline_items @? CAST(:{array_path_param} AS jsonpath)")
            params[object_path_param] = f"$.* ? (@.type == {encoded_item_type})"
            params[array_path_param] = f"$[*] ? (@.type == {encoded_item_type})"

        return " OR ".join(prefilter_parts), f"({MATCH_SQL})", params

    async def _max_lookback_days(self, settings: SettingsService) -> int:
        try:
            raw_value = await settings.get(
                "enrichment.cross_case_observable.max_lookback_days",
                DEFAULT_MAX_LOOKBACK_DAYS,
            )
            value = int(raw_value)
        except (TypeError, ValueError):
            return DEFAULT_MAX_LOOKBACK_DAYS
        return value if value > 0 else DEFAULT_MAX_LOOKBACK_DAYS

    def _observables(self, item: Dict[str, Any]) -> list[tuple[str, str]]:
        item_type = item.get("type")
        raw_candidates: list[tuple[str, str]] = []

        if item_type == "observable":
            observable_type = str(item.get("observable_type") or "").strip().upper()
            observable_value = str(item.get("observable_value") or "").strip().lower()
            if observable_type and observable_value:
                raw_candidates.append((observable_type, observable_value))
        elif item_type == "system" and item.get("ip_address"):
            raw_candidates.append(("IP", str(item["ip_address"]).strip().lower()))
        elif item_type == "network_traffic":
            for field_name in ("source_ip", "destination_ip"):
                if item.get(field_name):
                    raw_candidates.append(("IP", str(item[field_name]).strip().lower()))

        observables: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for observable_type, observable_value in raw_candidates:
            if observable_type == "IP" and normalize_public_ip_address(observable_value) is None:
                continue
            candidate = (observable_type, observable_value)
            if candidate in seen:
                continue
            seen.add(candidate)
            observables.append(candidate)
        return observables

    def _format_match(self, row: Any) -> dict[str, Any]:
        entity_type = str(row["entity_type"])
        entity_id = int(row["entity_id"])
        prefix = KIND_TO_PREFIX.get(entity_type, entity_type.upper())
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "human_id": format_entity_id(entity_id, prefix),
            "title": row["title"],
            "status": row["status"],
            "priority": row["priority"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }


cross_case_observable_provider = CrossCaseObservableProvider()
