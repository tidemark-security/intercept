"""Locate individual timeline items that share a typed observable."""

import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.entity_ids import WORK_ITEM_KIND_TO_PREFIX, format_entity_id
from app.models.search_schemas import EntityType
from app.services.search_service import (
    IOC_CANDIDATE_SQL, SearchService, TIMELINE_ITEMS_SQL, created_at_search_clause, timeline_values_sql,
)


TYPED_VALUE_MATCH_SQL = """
    jsonb_extract_path_text(timeline_match.item, 'type') = 'observable'
    AND upper(coalesce(jsonb_extract_path_text(timeline_match.item, 'observable_type'), '')) = :observable_type
    AND lower(coalesce(nullif(timeline_match.item->>'observable_value', ''), timeline_match.item->>'value', '')) = :observable_value
"""

MAPPED_FIELD_MATCHES_SQL = """
    SELECT field_mapping.field_name
    FROM jsonb_to_recordset(CAST(:field_mappings AS jsonb)) AS field_mapping(item_type text, field_name text)
    WHERE jsonb_extract_path_text(timeline_match.item, 'type') = field_mapping.item_type
      AND lower(coalesce(jsonb_extract_path_text(timeline_match.item, field_mapping.field_name), '')) = :observable_value
"""

MATCH_SQL = f"({TYPED_VALUE_MATCH_SQL}) OR EXISTS ({MAPPED_FIELD_MATCHES_SQL})"

MATCHED_FIELDS_SQL = f"""
    ARRAY(
        SELECT CASE WHEN nullif(timeline_match.item->>'observable_value', '') IS NOT NULL
                    THEN 'observable_value' ELSE 'value' END AS field_name
        WHERE {TYPED_VALUE_MATCH_SQL}
        UNION ALL
        {MAPPED_FIELD_MATCHES_SQL}
        ORDER BY field_name
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


def correlation_field_records(observable_type: str) -> str:
    return json.dumps([
        {"item_type": item_type, "field_name": field}
        for item_type, field in CORRELATION_FIELD_MAPPINGS.get(observable_type, ())
    ])


async def observable_occurrences(
    db: AsyncSession, *, observable_type: str, value: str, entity_types: list[EntityType],
    start: datetime | None, end: datetime | None, skip: int, limit: int,
) -> dict:
    date_clause, params = created_at_search_clause(start, end)
    # Only table names from the shared enum mapping enter SQL. Descend through replies
    # specifically so cached enrichment results cannot masquerade as timeline evidence.
    parents = " UNION ALL ".join(
        f"SELECT '{kind.value}' AS kind, id, title, created_at, timeline_items "
        f"FROM {SearchService.TABLE_NAMES[kind]} WHERE {IOC_CANDIDATE_SQL} {date_clause}"
        for kind in dict.fromkeys(entity_types)
    )
    replies = timeline_values_sql("parent.item->'replies'")
    query = text(f"""
        WITH RECURSIVE parents AS ({parents}),
        entries(kind, id, title, created_at, item) AS (
            SELECT kind, id, title, created_at, entry.item FROM parents
            CROSS JOIN LATERAL ({TIMELINE_ITEMS_SQL}) AS entry
            UNION ALL
            SELECT parent.kind, parent.id, parent.title, parent.created_at, reply.item
            FROM entries AS parent CROSS JOIN LATERAL ({replies}) AS reply
        ),
        matched_items AS (
            SELECT kind, id, title, created_at, item->>'id' AS item_id,
                   item->>'type' AS item_type, item->>'timestamp' AS item_timestamp,
                   {MATCHED_FIELDS_SQL} AS matched_fields
            FROM entries AS timeline_match
            WHERE item->>'id' IS NOT NULL
        ),
        hits AS (
            SELECT * FROM matched_items WHERE cardinality(matched_fields) > 0
        )
        SELECT page.*, totals.total FROM (SELECT count(*) AS total FROM hits) AS totals
        LEFT JOIN LATERAL (
            SELECT * FROM hits ORDER BY created_at DESC, kind, id DESC, item_id OFFSET :skip LIMIT :limit
        ) AS page ON true
        ORDER BY page.created_at DESC, page.kind, page.id DESC, page.item_id
    """)
    rows = (await db.execute(query, {
        **params, "observable_type": observable_type, "observable_value": value.lower(), "ioc_candidate": value.lower(),
        "field_mappings": correlation_field_records(observable_type), "skip": skip, "limit": limit,
    })).mappings().all()
    return {
        "observable_type": observable_type, "value": value,
        "date_range": {"start": start, "end": end},
        "total": rows[0]["total"], "skip": skip, "limit": limit,
        "items": [
            {"parent_entity_type": row["kind"],
             "parent_entity_id": format_entity_id(row["id"], WORK_ITEM_KIND_TO_PREFIX[row["kind"]]),
             "title": row["title"], "item_id": row["item_id"], "type": row["item_type"],
             "timestamp": row["item_timestamp"], "matched_fields": row["matched_fields"]}
            for row in rows if row["item_id"] is not None
        ],
    }
