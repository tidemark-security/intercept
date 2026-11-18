"""Search service for unified full-text search across alerts, cases, and tasks.

This service implements PostgreSQL full-text search with:
- Weighted zones (A=title, B=description, C=source/assignee, D=timeline)
- ts_headline for snippet generation with <mark> tags
- Unified pagination across alert, case, and task queries
- Fuzzy matching fallback using pg_trgm similarity
- Type-specific timeline queries for IOCs (IPs, emails, URLs, hashes)
"""
import ipaddress
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.entity_ids import (
    ALERT_PREFIX,
    CASE_PREFIX,
    PREFIX_TO_KIND,
    TASK_PREFIX,
    WORK_ITEM_KIND_TO_PREFIX,
    format_entity_id,
)
from app.models.search_schemas import (
    EntityType,
    SearchResultItem,
    SearchTagMatch,
    DateRangeApplied,
    PaginatedSearchResponse,
)
from app.core.validation import STRICT_PATTERNS


logger = logging.getLogger(__name__)


TIMELINE_ITEMS_SQL = """
    SELECT value AS item
    FROM jsonb_each(
        CASE
            WHEN jsonb_typeof(timeline_items) = 'object' THEN timeline_items
            ELSE '{}'::jsonb
        END
    )
    UNION ALL
    SELECT value AS item
    FROM jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(timeline_items) = 'array' THEN timeline_items
            ELSE '[]'::jsonb
        END
    )
"""


# =============================================================================
# Query Classification
# =============================================================================

class QueryType(str, Enum):
    """Classified query types for optimized search routing."""
    HUMAN_ID = "human_id"  # Entity ID like ALT-0000001, CAS-000001, TSK-000001
    NUMERIC_ID = "numeric_id"  # Plain integer that could be an entity ID
    IP = "ip"              # IPv4 or IPv6 address
    EMAIL = "email"        # Email address
    URL = "url"            # Full URL with protocol
    DOMAIN = "domain"      # Domain/hostname without protocol
    HASH = "hash"          # MD5, SHA1, or SHA256 hash
    FILENAME = "filename"  # Filename pattern (has extension)
    MITRE = "mitre"        # MITRE ATT&CK technique ID (T1234 or T1234.001)
    GENERIC = "generic"    # Fallback for unclassified queries


@dataclass
class QueryClassification:
    """Result of query classification."""
    query_type: QueryType
    normalized_value: str  # Trimmed, cleaned query value
    has_wildcard: bool     # True if query contains * wildcard
    original_query: str    # Original query before normalization
    human_id_entity_type: Optional[str] = None  # 'alert', 'case', or 'task' if HUMAN_ID
    human_id_numeric: Optional[int] = None      # Numeric ID if HUMAN_ID
    numeric_id: Optional[int] = None            # Plain numeric ID (could match any entity type)


# Regex patterns for query classification
# Order matters - more specific patterns should be checked first

# Human ID patterns - ALT-0000001, CAS-000001, TSK-000001 (1-9 digits after prefix)
_HUMAN_ID_PATTERN = re.compile(
    rf"^({'|'.join(map(re.escape, WORK_ITEM_KIND_TO_PREFIX.values()))})-(\d{{1,9}})$",
    re.IGNORECASE,
)

# Use patterns from shared validation module
_IPV4_PATTERN = STRICT_PATTERNS["ipv4"]
_EMAIL_PATTERN = STRICT_PATTERNS["email"]
_URL_PATTERN = STRICT_PATTERNS["url"]
_DOMAIN_PATTERN = STRICT_PATTERNS["domain"]
_MD5_PATTERN = STRICT_PATTERNS["md5"]
_SHA1_PATTERN = STRICT_PATTERNS["sha1"]
_SHA256_PATTERN = STRICT_PATTERNS["sha256"]
_HASH_PATTERNS = (_SHA256_PATTERN, _SHA1_PATTERN, _MD5_PATTERN)
_FILENAME_PATTERN = STRICT_PATTERNS["filename"]
_MITRE_ATTACK_PATTERN = STRICT_PATTERNS["mitre_attack"]

# IPv4 with wildcards - supports partial IPs like 192.168.* or 10.*
# (Search-specific pattern, not in shared validation)
_IPV4_WILDCARD_PATTERN = re.compile(
    r'^(\d{1,3}\.){1,3}\*$|'  # Trailing wildcard: 192.168.* or 10.*
    r'^(\d{1,3}|\*)\.(\d{1,3}|\*)\.(\d{1,3}|\*)\.(\d{1,3}|\*)$'  # Full form with wildcards
)

# Filename extensions whitelist (for query classification heuristics)
_FILENAME_EXTENSIONS = {
    'exe', 'dll', 'bat', 'cmd', 'ps1', 'vbs', 'js', 'jar', 'msi',  # Executables
    'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'pdf', 'rtf',     # Documents
    'zip', 'rar', '7z', 'tar', 'gz',                                # Archives
    'txt', 'log', 'csv', 'json', 'xml', 'yaml', 'yml',              # Text
    'py', 'rb', 'php', 'sh', 'pl',                                  # Scripts
    'iso', 'img', 'dmg',                                            # Disk images
}


def _is_ipv6_address(value: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv6Address)
    except ValueError:
        return False


class SearchDateRangeValidationError(ValueError):
    """Raised when resolved search date bounds are inconsistent."""


def resolve_search_date_range(
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    *,
    now: Optional[datetime] = None,
) -> tuple[datetime, datetime]:
    """Resolve optional search bounds and enforce the supported one-year window."""
    resolved_end = end_date or now or datetime.now(timezone.utc)
    resolved_start = start_date or resolved_end - timedelta(days=30)

    if resolved_start > resolved_end:
        raise SearchDateRangeValidationError("Start date must be before end date")
    if resolved_end - resolved_start > timedelta(days=365):
        raise SearchDateRangeValidationError("Date range cannot exceed 1 year")

    return resolved_start, resolved_end


def _contains_like_pattern(value: str, *, asterisk_wildcard: bool = False) -> str:
    """Build a literal SQL LIKE substring pattern, optionally honoring ``*``."""
    escaped = value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    if asterisk_wildcard:
        escaped = escaped.replace("*", "%")
    return f"%{escaped}%"


def classify_query(query: str) -> QueryClassification:
    """Classify a search query to determine optimal search strategy.
    
    Args:
        query: Raw search query string
        
    Returns:
        QueryClassification with detected type, normalized value, and wildcard flag
    """
    original = query
    # Trim whitespace
    query = query.strip()
    
    # Check for wildcard
    has_wildcard = '*' in query

    def classified(
        query_type: QueryType,
        normalized_value: Optional[str] = None,
        *,
        human_id_entity_type: Optional[str] = None,
        human_id_numeric: Optional[int] = None,
        numeric_id: Optional[int] = None,
    ) -> QueryClassification:
        return QueryClassification(
            query_type=query_type,
            normalized_value=query if normalized_value is None else normalized_value,
            has_wildcard=has_wildcard,
            original_query=original,
            human_id_entity_type=human_id_entity_type,
            human_id_numeric=human_id_numeric,
            numeric_id=numeric_id,
        )
    
    # For classification, remove wildcards temporarily
    test_value = query.replace('*', '')
    
    # Empty after removing wildcards means it's just wildcards
    if not test_value:
        return classified(QueryType.GENERIC)
    
    # Check patterns in order of specificity
    
    # Human ID (ALT-0000001, CAS-000001, TSK-000001) - highest priority
    human_id_match = _HUMAN_ID_PATTERN.match(test_value)
    if human_id_match and not has_wildcard:
        prefix = human_id_match.group(1).upper()
        numeric_id = int(human_id_match.group(2))
        entity_type = PREFIX_TO_KIND.get(prefix)
        return classified(
            QueryType.HUMAN_ID,
            query.upper(),
            human_id_entity_type=entity_type,
            human_id_numeric=numeric_id,
        )
    
    # Plain numeric ID (e.g., "123") - could be alert, case, or task ID
    # Check after human ID but before IP to avoid matching IPs like "192"
    if test_value.isdigit() and not has_wildcard:
        numeric_value = int(test_value)
        # Only treat as ID if it's a reasonable entity ID (positive, not too large)
        if 0 < numeric_value <= 999999999:
            return classified(QueryType.NUMERIC_ID, numeric_id=numeric_value)
    
    # IPv4 (exact match)
    if _IPV4_PATTERN.match(test_value):
        return classified(QueryType.IP)
    
    # IPv4 with wildcards (e.g., 192.168.* or 10.*.*.*)
    if has_wildcard and _IPV4_WILDCARD_PATTERN.match(query):
        return classified(QueryType.IP)
    
    # IPv6
    if _is_ipv6_address(test_value):
        return classified(QueryType.IP)
    
    # Email
    if _EMAIL_PATTERN.match(test_value):
        return classified(QueryType.EMAIL, query.lower())
    
    # URL (before domain since URLs contain domains)
    if _URL_PATTERN.match(test_value):
        return classified(QueryType.URL)
    
    # Hashes (check before domain since hex strings could match domain pattern)
    if any(pattern.match(test_value) for pattern in _HASH_PATTERNS):
        return classified(QueryType.HASH, query.lower())
    
    # MITRE ATT&CK ID (check BEFORE filename to avoid T1059.002 matching as filename)
    if _MITRE_ATTACK_PATTERN.match(test_value):
        return classified(QueryType.MITRE, query.upper())
    
    # Filename (check BEFORE domain - use extension whitelist to avoid false positives)
    filename_match = _FILENAME_PATTERN.match(test_value)
    if filename_match:
        extension = filename_match.group(1).lower()
        if extension in _FILENAME_EXTENSIONS:
            return classified(QueryType.FILENAME)
    
    # Domain/hostname (after filename check)
    if _DOMAIN_PATTERN.match(test_value):
        return classified(QueryType.DOMAIN, query.lower())
    
    # Fallback to generic
    return classified(QueryType.GENERIC)


# =============================================================================
# Type-Specific Field Mappings for Timeline Queries
# =============================================================================

# Maps QueryType to list of (timeline_item_type, field_name) tuples
# These are used to match structured timeline item fields.
FIELD_MAPPINGS: dict[QueryType, list[tuple[str, str]]] = {
    QueryType.IP: [
        ("system", "ip_address"),
        ("network_traffic", "source_ip"),
        ("network_traffic", "destination_ip"),
    ],
    QueryType.EMAIL: [
        ("internal_actor", "contact_email"),
        ("external_actor", "contact_email"),
        ("threat_actor", "contact_email"),
        ("email", "sender"),
        ("email", "recipient"),
    ],
    QueryType.URL: [
        ("attachment", "url"),
        ("ttp", "url"),
        ("link", "url"),
        ("forensic_artifact", "url"),
    ],
    QueryType.DOMAIN: [
        ("system", "hostname"),
    ],
    QueryType.HASH: [
        ("attachment", "file_hash"),
        ("forensic_artifact", "hash"),
    ],
    QueryType.FILENAME: [
        ("attachment", "file_name"),
        ("process", "process_name"),
    ],
    QueryType.MITRE: [
        ("ttp", "mitre_id"),
    ],
}

# Observable type mappings - these use compound containment with observable_type
OBSERVABLE_TYPE_MAPPINGS: dict[QueryType, list[str]] = {
    QueryType.IP: ["IP"],
    QueryType.EMAIL: ["EMAIL"],
    QueryType.URL: ["URL"],
    QueryType.DOMAIN: ["DOMAIN"],
    QueryType.HASH: ["HASH"],
    QueryType.FILENAME: ["FILENAME", "PROCESS_NAME"],
}


class SearchService:
    """Service for unified search across alerts, cases, and tasks."""
    
    # Human ID prefixes for each entity type
    PREFIXES = {
        EntityType.ALERT: ALERT_PREFIX,
        EntityType.CASE: CASE_PREFIX,
        EntityType.TASK: TASK_PREFIX,
    }
    TABLE_NAMES = {
        EntityType.ALERT: "alerts",
        EntityType.CASE: "cases",
        EntityType.TASK: "tasks",
    }
    ENTITY_TYPES_BY_KIND = {
        "alert": EntityType.ALERT,
        "case": EntityType.CASE,
        "task": EntityType.TASK,
    }
    
    def _generate_human_id(self, entity_type: EntityType, entity_id: int) -> str:
        """Generate human-readable ID like ALT-0000123."""
        prefix = self.PREFIXES[entity_type]
        return format_entity_id(entity_id, prefix)

    @staticmethod
    def _search_metadata(row: Any) -> dict[str, Any]:
        """Extract optional display metadata shared by alert/case/task rows."""
        def as_optional_str(value: Any) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, Enum):
                return str(value.value)
            return str(value)

        return {
            "updated_at": getattr(row, "updated_at", None),
            "priority": as_optional_str(getattr(row, "priority", None)),
            "status": as_optional_str(getattr(row, "status", None)),
            "assignee": as_optional_str(getattr(row, "assignee", None)),
        }

    @staticmethod
    def _coerce_tags(value: Any) -> List[str]:
        """Keep valid string tags while tolerating malformed legacy JSON."""
        if not isinstance(value, list):
            return []
        return [tag for tag in value if isinstance(tag, str)]

    @staticmethod
    def _title_description_snippet(row: Any) -> str:
        """Build the compact snippet used by exact-ID results."""
        snippet = row.title or ""
        if row.description:
            description = row.description[:100]
            snippet = f"{snippet} - {description}" if snippet else description
        return snippet

    @staticmethod
    def _truncate_snippet(snippet: Any, *, preserve_json: bool = False) -> str:
        value = str(snippet or "")
        if len(value) <= 150 or (preserve_json and value.strip().startswith("{")):
            return value
        return value[:147] + "..."

    def _result_from_row(
        self,
        row: Any,
        entity_type: EntityType,
        *,
        snippet: str,
        score: float,
        normalized_tags: Optional[List[str]] = None,
    ) -> SearchResultItem:
        """Map a database search row into the shared response contract."""
        tags = self._coerce_tags(getattr(row, "tags", None))
        return SearchResultItem(
            entity_type=entity_type,
            entity_id=row.id,
            human_id=self._generate_human_id(entity_type, row.id),
            title=row.title or "",
            snippet=snippet,
            score=score,
            timeline_item_id=None,
            created_at=row.created_at,
            **self._search_metadata(row),
            tags=tags,
            tag_matches=self._build_tag_matches(
                tags,
                getattr(row, "timeline_items", None),
                normalized_tags,
            ),
        )

    @staticmethod
    def _iter_timeline_items(timeline_items: Any) -> List[dict]:
        """Return timeline item dicts from object-backed or array-backed storage."""
        if isinstance(timeline_items, dict):
            candidates = timeline_items.values()
        elif isinstance(timeline_items, list):
            candidates = timeline_items
        else:
            return []

        return [item for item in candidates if isinstance(item, dict)]

    @staticmethod
    def _timeline_item_label(item: dict) -> str:
        """Build a compact label for timeline tag match context."""
        for field in (
            "title",
            "description",
            "subject",
            "file_name",
            "process_name",
            "observable_value",
            "hostname",
            "mitre_id",
            "url",
            "name",
            "id",
        ):
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                label = value.strip()
                return label[:77] + "..." if len(label) > 80 else label
            if field == "id" and value is not None:
                return str(value)

        item_type = item.get("type")
        return str(item_type) if item_type else "Timeline item"

    def _build_tag_matches(
        self,
        entity_tags: Optional[List[str]],
        timeline_items: Any,
        filters: Optional[List[str]],
    ) -> List[SearchTagMatch]:
        """Explain tag-filter matches using the same case-insensitive substring semantics as SQL."""
        normalized_filters = self._normalize_tag_filters(filters)
        if not normalized_filters:
            return []

        matches: List[SearchTagMatch] = []
        seen: set[tuple[str, str, str, Optional[str]]] = set()

        def add_match(
            *,
            source: str,
            tag: str,
            filter_value: str,
            timeline_item: Optional[dict] = None,
        ) -> None:
            item_id = None
            item_type = None
            item_label = None
            if timeline_item is not None:
                raw_item_id = timeline_item.get("id")
                raw_item_type = timeline_item.get("type")
                item_id = str(raw_item_id) if raw_item_id is not None else None
                item_type = str(raw_item_type) if raw_item_type is not None else None
                item_label = self._timeline_item_label(timeline_item)

            key = (source, tag.lower(), filter_value.lower(), item_id)
            if key in seen:
                return
            seen.add(key)
            matches.append(SearchTagMatch(
                source=source,
                tag=tag,
                filter=filter_value,
                timeline_item_id=item_id,
                timeline_item_type=item_type,
                timeline_item_label=item_label,
            ))

        for tag in self._coerce_tags(entity_tags):
            tag_lower = tag.lower()
            for filter_value in normalized_filters:
                if filter_value.lower() in tag_lower:
                    add_match(source="entity", tag=tag, filter_value=filter_value)

        for item in self._iter_timeline_items(timeline_items):
            for tag in self._coerce_tags(item.get("tags")):
                tag_lower = tag.lower()
                for filter_value in normalized_filters:
                    if filter_value.lower() in tag_lower:
                        add_match(
                            source="timeline",
                            tag=tag,
                            filter_value=filter_value,
                            timeline_item=item,
                        )

        return matches
    
    async def _lookup_by_human_id(
        self,
        db: AsyncSession,
        classification: QueryClassification,
        target_entity_type: EntityType,
        start_date: datetime,
        end_date: datetime,
        normalized_tags: List[str],
    ) -> Optional[SearchResultItem]:
        """Look up a filtered exact human-ID match for one entity type."""
        if classification.query_type != QueryType.HUMAN_ID:
            return None
        
        entity_type_str = classification.human_id_entity_type
        entity_id = classification.human_id_numeric
        
        if not entity_type_str or entity_id is None:
            return None
        
        entity_type = self.ENTITY_TYPES_BY_KIND.get(entity_type_str)
        if not entity_type:
            return None
        
        if entity_type != target_entity_type:
            return None

        return await self._lookup_exact_id(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            start_date=start_date,
            end_date=end_date,
            normalized_tags=normalized_tags,
        )

    async def _lookup_exact_id(
        self,
        db: AsyncSession,
        *,
        entity_type: EntityType,
        entity_id: int,
        start_date: datetime,
        end_date: datetime,
        normalized_tags: List[str],
    ) -> Optional[SearchResultItem]:
        """Return an exact ID match that satisfies the active search filters."""
        table_name = self.TABLE_NAMES[entity_type]
        tag_filter_sql, tag_filter_params = self._build_tag_filter_sql(normalized_tags)
        tag_filter_clause = f" AND {tag_filter_sql}" if tag_filter_sql else ""

        sql = text(f"""
            SELECT
                id,
                title,
                description,
                tags,
                timeline_items,
                created_at,
                updated_at,
                priority,
                status,
                assignee
            FROM {table_name}
            WHERE id = :entity_id
              AND created_at >= :start_date
              AND created_at <= :end_date
              {tag_filter_clause}
        """)

        result = await db.execute(sql, {
            "entity_id": entity_id,
            "start_date": start_date,
            "end_date": end_date,
            **tag_filter_params,
        })
        row = result.fetchone()

        if not row:
            return None

        return self._result_from_row(
            row,
            entity_type,
            snippet=self._title_description_snippet(row),
            score=1.0,
            normalized_tags=normalized_tags,
        )
    
    async def _lookup_by_numeric_id(
        self,
        db: AsyncSession,
        classification: QueryClassification,
        entity_types: List[EntityType],
        start_date: datetime,
        end_date: datetime,
        normalized_tags: List[str],
    ) -> List[SearchResultItem]:
        """Look up filtered plain numeric-ID matches across entity types."""
        if classification.query_type != QueryType.NUMERIC_ID:
            return []
        
        entity_id = classification.numeric_id
        if entity_id is None:
            return []
        
        results: List[SearchResultItem] = []

        for entity_type in entity_types:
            match = await self._lookup_exact_id(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                start_date=start_date,
                end_date=end_date,
                normalized_tags=normalized_tags,
            )
            if match:
                results.append(match)

        return results
    
    def _build_timeline_match_sql(
        self,
        classification: QueryClassification,
    ) -> tuple[str, dict]:
        """Build timeline-item match conditions for a classified query.

        Structured values use exact field comparisons. Wildcard and generic
        queries use a safely escaped text search. Domain queries first restrict
        the scan to timeline item types that can contain domain strings.
        This catches domains within email addresses (e.g., evil.com in user@evil.com).
        """
        query_type = classification.query_type
        value = classification.normalized_value
        has_wildcard = classification.has_wildcard
        
        # For wildcards or generic queries, use ILIKE fallback
        if has_wildcard or query_type == QueryType.GENERIC:
            return (
                "CAST(timeline_items AS text) ILIKE :timeline_pattern ESCAPE '\\'",
                {
                    "timeline_pattern": _contains_like_pattern(
                        value,
                        asterisk_wildcard=True,
                    )
                },
            )
        
        # Restrict domain text scans to item types that can contain domains.
        # This catches domains within email addresses (evil.com in user@evil.com)
        # and URLs (evil.com in https://evil.com/path)
        if query_type == QueryType.DOMAIN:
            return self._build_domain_match_sql(value)
        
        # Build containment conditions for specific field mappings
        conditions = []
        params = {}
        param_idx = 0
        
        # Get field mappings for this query type
        field_mappings = FIELD_MAPPINGS.get(query_type, [])
        for item_type, field_name in field_mappings:
            type_param = f"containment_type_{param_idx}"
            value_param = f"containment_value_{param_idx}"
            conditions.append(
                f"""EXISTS (
                    SELECT 1
                    FROM ({TIMELINE_ITEMS_SQL}) AS timeline_match
                    WHERE timeline_match.item->>'type' = :{type_param}
                      AND timeline_match.item->>'{field_name}' = :{value_param}
                )"""
            )
            params[type_param] = item_type
            params[value_param] = value
            param_idx += 1
        
        # Add observable type mappings
        observable_types = OBSERVABLE_TYPE_MAPPINGS.get(query_type, [])
        for obs_type in observable_types:
            observable_type_param = f"containment_observable_type_{param_idx}"
            observable_value_param = f"containment_observable_value_{param_idx}"
            conditions.append(
                f"""EXISTS (
                    SELECT 1
                    FROM ({TIMELINE_ITEMS_SQL}) AS timeline_match
                    WHERE timeline_match.item->>'type' = 'observable'
                      AND timeline_match.item->>'observable_type' = :{observable_type_param}
                      AND timeline_match.item->>'observable_value' = :{observable_value_param}
                )"""
            )
            params[observable_type_param] = obs_type
            params[observable_value_param] = value
            param_idx += 1
        
        if not conditions:
            return (
                "CAST(timeline_items AS text) ILIKE :timeline_pattern ESCAPE '\\'",
                {"timeline_pattern": _contains_like_pattern(value)},
            )
        
        # Join conditions with OR - any of them matching is a hit
        return (
            "(" + " OR ".join(conditions) + ")",
            params
        )
    
    # Timeline item types that could contain domain strings
    # Used to narrow domain text searches before ILIKE refinement.
    DOMAIN_CONTAINING_TYPES: list[dict] = [
        {"type": "email"},                                    # sender, recipient contain domains
        {"type": "observable", "observable_type": "DOMAIN"},  # direct domain observable
        {"type": "observable", "observable_type": "EMAIL"},   # email addresses contain domains
        {"type": "observable", "observable_type": "URL"},     # URLs contain domains
        {"type": "link"},                                     # link URLs contain domains
        {"type": "system"},                                   # hostname is a domain
        {"type": "attachment"},                               # url field may contain domains
        {"type": "internal_actor"},                           # contact_email contains domains
        {"type": "external_actor"},                           # contact_email contains domains
        {"type": "threat_actor"},                             # contact_email contains domains
    ]

    def _build_domain_match_sql(self, domain: str) -> tuple[str, dict]:
        """Restrict a domain substring search to relevant timeline item types."""
        type_conditions = []
        params = {}
        
        for idx, type_filter in enumerate(self.DOMAIN_CONTAINING_TYPES):
            type_param = f"domain_type_{idx}"
            observable_type = type_filter.get("observable_type")
            observable_type_param = f"domain_observable_type_{idx}"
            observable_clause = ""
            if observable_type is not None:
                observable_clause = f" AND timeline_domain.item->>'observable_type' = :{observable_type_param}"
                params[observable_type_param] = str(observable_type)

            type_conditions.append(
                f"""EXISTS (
                    SELECT 1
                    FROM ({TIMELINE_ITEMS_SQL}) AS timeline_domain
                    WHERE timeline_domain.item->>'type' = :{type_param}{observable_clause}
                )"""
            )
            params[type_param] = str(type_filter["type"])
        
        params["domain_pattern"] = _contains_like_pattern(domain)
        sql = f"""(
            ({" OR ".join(type_conditions)})
            AND CAST(timeline_items AS text) ILIKE :domain_pattern ESCAPE '\\'
        )"""
        
        return sql, params

    def _normalize_tag_filters(self, tags: Optional[List[str]]) -> List[str]:
        """Normalize tag filter values by trimming and de-duplicating."""
        if not tags:
            return []

        normalized: List[str] = []
        seen: set[str] = set()
        for raw_tag in tags:
            if not isinstance(raw_tag, str):
                continue
            cleaned = raw_tag.strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(cleaned)

        return normalized

    def _build_tag_filter_sql(self, tags: List[str]) -> tuple[str, dict]:
        """Build OR-based tag filter SQL across top-level and timeline item tags."""
        if not tags:
            return "", {}

        params: dict[str, str] = {}
        top_level_tag_conditions: List[str] = []
        timeline_tag_conditions: List[str] = []

        for idx, tag in enumerate(tags):
            param_name = f"tag_pattern_{idx}"
            params[param_name] = _contains_like_pattern(tag)
            top_level_tag_conditions.append(
                f"tag ILIKE :{param_name} ESCAPE '\\'"
            )
            timeline_tag_conditions.append(
                f"timeline_tag ILIKE :{param_name} ESCAPE '\\'"
            )

        top_level_where = " OR ".join(top_level_tag_conditions)
        timeline_where = " OR ".join(timeline_tag_conditions)

        sql = f"""(
            EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(
                    CASE
                        WHEN jsonb_typeof(tags) = 'array' THEN tags
                        ELSE '[]'::jsonb
                    END
                ) AS tag
                WHERE {top_level_where}
            )
            OR EXISTS (
                SELECT 1
                FROM ({TIMELINE_ITEMS_SQL}) AS item
                WHERE EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(
                        CASE
                            WHEN jsonb_typeof(item.item->'tags') = 'array' THEN item.item->'tags'
                            ELSE '[]'::jsonb
                        END
                    ) AS timeline_tag
                    WHERE {timeline_where}
                )
            )
        )"""

        return sql, params

    async def paginated_search(
        self,
        db: AsyncSession,
        query: str,
        entity_types: List[EntityType],
        skip: int = 0,
        limit: int = 20,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
    ) -> PaginatedSearchResponse:
        """Perform paginated search across one or more entity types.

        This is the canonical search entrypoint used by the dedicated search page.

        Args:
            db: Database session
            query: Search query text (2-200 chars)
            entity_types: List of entity types to search (alert, case, task)
            skip: Number of results to skip (offset)
            limit: Maximum number of results to return (1-100)
            start_date: Start of date range (default: 30 days ago)
            end_date: End of date range (default: now)
            user_id: User ID for audit logging

        Returns:
            PaginatedSearchResponse with results and pagination info
        """
        start_date, end_date = resolve_search_date_range(start_date, end_date)
        entity_types = list(dict.fromkeys(entity_types))
        normalized_tags = self._normalize_tag_filters(tags)
        filter_only_mode = query == "*"

        # Check for human ID query - don't do fuzzy fallback for these
        classification = classify_query(query) if not filter_only_mode else QueryClassification(
            query_type=QueryType.GENERIC,
            normalized_value=query,
            has_wildcard=True,
            original_query=query,
        )
        is_human_id_query = classification.query_type == QueryType.HUMAN_ID
        is_numeric_id_query = classification.query_type == QueryType.NUMERIC_ID
        
        # For numeric ID queries, look up matching entities first
        numeric_id_matches: List[SearchResultItem] = []
        if is_numeric_id_query and not filter_only_mode:
            numeric_id_matches = await self._lookup_by_numeric_id(
                db,
                classification,
                entity_types,
                start_date,
                end_date,
                normalized_tags,
            )
            if numeric_id_matches:
                logger.info(
                    "Numeric ID matches found in paginated search",
                    extra={
                        "user_id": user_id,
                        "query": query,
                        "numeric_id": classification.numeric_id,
                        "match_count": len(numeric_id_matches),
                        "entity_types": [m.entity_type.value for m in numeric_id_matches],
                    },
                )

        numeric_match_by_type = {
            match.entity_type: match for match in numeric_id_matches
        }
        
        # Search across all entity types and aggregate results
        all_items: List[SearchResultItem] = []
        total_count = 0
        
        for entity_type in entity_types:
            table_name = self.TABLE_NAMES[entity_type]
            # First try full-text search
            exact_numeric_match = numeric_match_by_type.get(entity_type)
            items, count = await self._search_entity_candidates(
                db=db,
                table_name=table_name,
                entity_type=entity_type,
                query=query,
                start_date=start_date,
                end_date=end_date,
                candidate_limit=skip + limit,
                normalized_tags=normalized_tags,
                excluded_entity_id=(
                    exact_numeric_match.entity_id if exact_numeric_match else None
                ),
            )
            
            # If no results, try fuzzy search fallback (but NOT for human ID queries)
            if count == 0 and not is_human_id_query and not filter_only_mode:
                items, count = await self._fuzzy_search_entity_candidates(
                    db=db,
                    table_name=table_name,
                    entity_type=entity_type,
                    query=query,
                    start_date=start_date,
                    end_date=end_date,
                    candidate_limit=skip + limit,
                    normalized_tags=normalized_tags,
                    excluded_entity_id=(
                        exact_numeric_match.entity_id if exact_numeric_match else None
                    ),
                )
            
            all_items.extend(items)
            total_count += count
        
        # Content queries exclude these rows, so exact-ID totals cannot double-count.
        all_items.extend(numeric_id_matches)
        total_count += len(numeric_id_matches)
        
        # Sort merged results by score (descending), then by created_at (descending)
        if filter_only_mode:
            all_items.sort(
                key=lambda item: (
                    -item.created_at.timestamp(),
                    item.entity_type.value,
                    -item.entity_id,
                )
            )
        else:
            all_items.sort(
                key=lambda item: (
                    -item.score,
                    -item.created_at.timestamp(),
                    item.entity_type.value,
                    -item.entity_id,
                )
            )
        
        # Apply pagination to merged results
        paginated_items = all_items[skip:skip + limit]
        
        logger.info(
            "Paginated search executed",
            extra={
                "user_id": user_id,
                "query": query,
                "tags": normalized_tags,
                "entity_types": [et.value for et in entity_types],
                "skip": skip,
                "limit": limit,
                "total_results": total_count,
            },
        )
        
        return PaginatedSearchResponse(
            results=paginated_items,
            total=total_count,
            skip=skip,
            limit=limit,
            query=query,
            entity_types=entity_types,
            date_range=DateRangeApplied(
                start=start_date.isoformat(),
                end=end_date.isoformat(),
            ),
        )

    async def _search_entity_candidates(
        self,
        db: AsyncSession,
        table_name: str,
        entity_type: EntityType,
        query: str,
        start_date: datetime,
        end_date: datetime,
        candidate_limit: int,
        normalized_tags: Optional[List[str]] = None,
        excluded_entity_id: Optional[int] = None,
    ) -> Tuple[List[SearchResultItem], int]:
        """Return one entity type's top candidates and unpaginated count."""
        normalized_tags = normalized_tags or []
        tag_filter_sql, tag_filter_params = self._build_tag_filter_sql(normalized_tags)
        tag_filter_clause = f" AND {tag_filter_sql}" if tag_filter_sql else ""
        id_exclusion_clause = (
            " AND id != :excluded_entity_id" if excluded_entity_id is not None else ""
        )
        common_params = {
            "start_date": start_date,
            "end_date": end_date,
            "limit": candidate_limit,
            **(
                {"excluded_entity_id": excluded_entity_id}
                if excluded_entity_id is not None
                else {}
            ),
            **tag_filter_params,
        }

        if query == "*":
            sql = text(f"""
                WITH filtered AS (
                    SELECT
                        id,
                        title,
                        description,
                        tags,
                        timeline_items,
                        created_at,
                        updated_at,
                        priority,
                        status,
                        assignee
                    FROM {table_name}
                    WHERE created_at >= :start_date
                      AND created_at <= :end_date
                      {id_exclusion_clause}
                      {tag_filter_clause}
                ),
                counted AS (
                    SELECT *, COUNT(*) OVER() AS total_count
                    FROM filtered
                )
                SELECT
                    id,
                    title,
                    description,
                    tags,
                    timeline_items,
                    created_at,
                    updated_at,
                    priority,
                    status,
                    assignee,
                    0.0 AS score,
                    total_count,
                    COALESCE(title, '') || ' ' || COALESCE(LEFT(description, 100), '') AS snippet
                FROM counted
                ORDER BY created_at DESC, id DESC
                LIMIT :limit
            """)

            result = await db.execute(sql, common_params)
            rows = result.fetchall()
            if not rows:
                return [], 0

            return [
                self._result_from_row(
                    row,
                    entity_type,
                    snippet=self._truncate_snippet(row.snippet),
                    score=0.0,
                    normalized_tags=normalized_tags,
                )
                for row in rows
            ], rows[0].total_count

        classification = classify_query(query)
        normalized_query = classification.normalized_value
        
        # Check for exact human ID match first (highest priority)
        if classification.query_type == QueryType.HUMAN_ID:
            exact_match = await self._lookup_by_human_id(
                db,
                classification,
                entity_type,
                start_date,
                end_date,
                normalized_tags,
            )
            if exact_match:
                return [exact_match], 1
            # If no match for this entity type, return empty
            return [], 0
        
        # Build JSONB containment conditions based on classification
        timeline_condition, timeline_params = self._build_timeline_match_sql(classification)
        
        sql = text(f"""
            WITH search_results AS (
                SELECT 
                    id,
                    title,
                    description,
                    tags,
                    created_at,
                    updated_at,
                    priority,
                    status,
                    assignee,
                    timeline_items,
                    ts_rank(search_vector, websearch_to_tsquery('english', :query)) AS score,
                    'fulltext' AS match_source
                FROM {table_name}
                WHERE search_vector @@ websearch_to_tsquery('english', :query)
                  AND created_at >= :start_date
                  AND created_at <= :end_date
                  {id_exclusion_clause}
                  {tag_filter_clause}
                
                UNION ALL
                
                SELECT 
                    id,
                    title,
                    description,
                    tags,
                    created_at,
                    updated_at,
                    priority,
                    status,
                    assignee,
                    timeline_items,
                    0.8 AS score,
                    'jsonb' AS match_source
                FROM {table_name}
                WHERE {timeline_condition}
                  AND created_at >= :start_date
                  AND created_at <= :end_date
                  {id_exclusion_clause}
                  {tag_filter_clause}
            ),
            deduplicated AS (
                SELECT DISTINCT ON (id)
                    id,
                    title,
                    description,
                    tags,
                    created_at,
                    updated_at,
                    priority,
                    status,
                    assignee,
                    timeline_items,
                    score,
                    match_source
                FROM search_results
                ORDER BY id, score DESC
            ),
            counted AS (
                SELECT *, COUNT(*) OVER() AS total_count
                FROM deduplicated
            )
            SELECT 
                id, 
                title, 
                description, 
                tags,
                timeline_items,
                created_at, 
                updated_at,
                priority,
                status,
                assignee,
                score,
                match_source,
                total_count,
                CASE 
                    WHEN match_source = 'fulltext' THEN
                        ts_headline(
                            'english',
                            COALESCE(title, '') || ' ' || COALESCE(description, ''),
                            websearch_to_tsquery('english', :query),
                            'MaxWords=25, MinWords=10, StartSel=<mark>, StopSel=</mark>, MaxFragments=1'
                        )
                    ELSE
                        COALESCE(
                            (
                                SELECT item.item::text
                                FROM ({TIMELINE_ITEMS_SQL}) AS item
                                WHERE item.item::text ILIKE :snippet_pattern ESCAPE '\\'
                                LIMIT 1
                            ),
                            COALESCE(title, '') || ' ' || COALESCE(LEFT(description, 100), '')
                        )
                END AS snippet
            FROM counted
            ORDER BY score DESC, created_at DESC, id DESC
            LIMIT :limit
        """)
        
        params = {
            "query": normalized_query,
            "snippet_pattern": _contains_like_pattern(
                normalized_query,
                asterisk_wildcard=True,
            ),
            **timeline_params,
            **common_params,
        }

        result = await db.execute(sql, params)
        rows = result.fetchall()
        
        if not rows:
            return [], 0
        
        return [
            self._result_from_row(
                row,
                entity_type,
                snippet=self._truncate_snippet(row.snippet, preserve_json=True),
                score=min(1.0, row.score),
                normalized_tags=normalized_tags,
            )
            for row in rows
        ], rows[0].total_count

    async def _fuzzy_search_entity_candidates(
        self,
        db: AsyncSession,
        table_name: str,
        entity_type: EntityType,
        query: str,
        start_date: datetime,
        end_date: datetime,
        candidate_limit: int,
        similarity_threshold: float = 0.3,
        normalized_tags: Optional[List[str]] = None,
        excluded_entity_id: Optional[int] = None,
    ) -> Tuple[List[SearchResultItem], int]:
        """Return fuzzy candidates for one entity type and its full count."""
        normalized_tags = normalized_tags or []
        tag_filter_sql, tag_filter_params = self._build_tag_filter_sql(normalized_tags)
        tag_filter_clause = f" AND {tag_filter_sql}" if tag_filter_sql else ""
        id_exclusion_clause = (
            " AND id != :excluded_entity_id" if excluded_entity_id is not None else ""
        )

        sql = text(f"""
            WITH fuzzy_results AS (
                SELECT 
                    id,
                    title,
                    description,
                    tags,
                    created_at,
                    updated_at,
                    priority,
                    status,
                    assignee,
                    timeline_items,
                    GREATEST(
                        similarity(COALESCE(title, ''), :query),
                        similarity(COALESCE(description, ''), :query) * 0.8
                    ) AS score
                FROM {table_name}
                WHERE (
                    similarity(COALESCE(title, ''), :query) > :threshold
                    OR similarity(COALESCE(description, ''), :query) > :threshold
                )
                AND created_at >= :start_date
                AND created_at <= :end_date
                {id_exclusion_clause}
                {tag_filter_clause}
            ),
            counted AS (
                SELECT *, COUNT(*) OVER() AS total_count
                FROM fuzzy_results
            )
            SELECT id, title, description, created_at, updated_at, priority, status, assignee, score, total_count
                     , tags, timeline_items
            FROM counted
            ORDER BY score DESC, created_at DESC, id DESC
            LIMIT :limit
        """)
        
        result = await db.execute(sql, {
            "query": query,
            "threshold": similarity_threshold,
            "start_date": start_date,
            "end_date": end_date,
            "limit": candidate_limit,
            **(
                {"excluded_entity_id": excluded_entity_id}
                if excluded_entity_id is not None
                else {}
            ),
            **tag_filter_params,
        })
        
        rows = result.fetchall()
        if not rows:
            return [], 0
        return [
            self._result_from_row(
                row,
                entity_type,
                snippet=self._truncate_snippet(row.description),
                score=min(1.0, row.score),
                normalized_tags=normalized_tags,
            )
            for row in rows
        ], rows[0].total_count


# Singleton instance
search_service = SearchService()
