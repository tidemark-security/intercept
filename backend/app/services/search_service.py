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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Generic, List, Optional, Tuple, TypeVar

from sqlalchemy import and_, func, literal, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement, TextClause

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
    QueueSearchResponse,
    QueueSearchRow,
)
from app.core.validation import STRICT_PATTERNS
from app.models.models import Alert, Case, Task
from app.models.enums import AlertStatus, CaseStatus, TaskStatus
from app.services.assignee_filter_utils import append_assignee_filter
from app.services.tag_filter_utils import append_tag_filters


logger = logging.getLogger(__name__)

QUEUE_MODELS = {
    EntityType.ALERT: (Alert, AlertStatus),
    EntityType.CASE: (Case, CaseStatus),
    EntityType.TASK: (Task, TaskStatus),
}
QUEUE_SORT_FIELDS = {"created_at", "updated_at", "priority", "status"}
FULL_TEXT_MATCH_SQL = "search_vector @@ websearch_to_tsquery('english', :query)"
SUBSTRING_MATCH_SQL = """(
    title ILIKE :substring_pattern ESCAPE '\\'
    OR description ILIKE :substring_pattern ESCAPE '\\'
)"""
FUZZY_MATCH_SQL = """(
    similarity(COALESCE(title, ''), :query) > :threshold
    OR similarity(COALESCE(description, ''), :query) > :threshold
)"""
FUZZY_SIMILARITY_THRESHOLD = 0.3
_SUBSTRING_TRIGRAM_PATTERN = re.compile(r"[^\W_]{3}")


def timeline_values_sql(container: str) -> str:
    """Expand a trusted SQL expression containing object- or array-backed timeline items."""
    return f"""
    SELECT value AS item
    FROM jsonb_each(
        CASE
            WHEN jsonb_typeof({container}) = 'object' THEN {container}
            ELSE '{{}}'::jsonb
        END
    )
    UNION ALL
    SELECT value AS item
    FROM jsonb_array_elements(
        CASE
            WHEN jsonb_typeof({container}) = 'array' THEN {container}
            ELSE '[]'::jsonb
        END
    )
"""


TIMELINE_ITEMS_SQL = timeline_values_sql("timeline_items")

# Superset of parents across all mapped fields and reply depths. The caller
# supplies the exact type, field and depth check after the index lookup.
IOC_CANDIDATE_SQL = (
    "timeline_ioc_keys(timeline_items) @> "
    "ARRAY[hashtextextended(lower(CAST(:ioc_candidate AS text)), 0)]"
)


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

    @property
    def is_filter_only(self) -> bool:
        return self.original_query == "*"


_ExactMatch = TypeVar("_ExactMatch")
_ContentMatch = TypeVar("_ContentMatch")


@dataclass
class _EntityMatches(Generic[_ExactMatch, _ContentMatch]):
    exact: _ExactMatch | None
    content: _ContentMatch | None
    total: int


async def _match_entity(
    classification: QueryClassification,
    entity_type: EntityType,
    *,
    lookup_exact: Callable[[int], Awaitable[_ExactMatch | None]],
    lookup_content: Callable[[int | None], Awaitable[tuple[_ContentMatch, int]]],
    lookup_fuzzy: Callable[[int | None], Awaitable[tuple[_ContentMatch, int]]],
) -> _EntityMatches[_ExactMatch, _ContentMatch]:
    """Apply the matching rules to one entity type within the caller's filters."""
    if classification.query_type == QueryType.HUMAN_ID:
        entity_id = classification.human_id_numeric
        if classification.human_id_entity_type != entity_type.value or entity_id is None:
            return _EntityMatches(exact=None, content=None, total=0)
        exact = await lookup_exact(entity_id)
        return _EntityMatches(exact=exact, content=None, total=int(exact is not None))

    numeric_id = classification.numeric_id
    exact = await lookup_exact(numeric_id) if numeric_id is not None else None
    # Count the exact row only once, and don't let it suppress fuzzy fallback
    # when there is no other eligible content match.
    excluded_id = numeric_id if exact is not None else None
    content, count = await lookup_content(excluded_id)
    if count == 0 and not classification.is_filter_only:
        content, count = await lookup_fuzzy(excluded_id)

    return _EntityMatches(exact=exact, content=content, total=count + int(exact is not None))


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


class SearchQueryValidationError(ValueError):
    """Search text cannot be evaluated by the selected search mode."""


def normalize_search_query(query: str, *, allow_filter_only: bool = True) -> str:
    query = " ".join(query.split())
    if len(query) < 2 and not (allow_filter_only and query == "*"):
        suffix = ", or '*' for filter-only search" if allow_filter_only else ""
        raise SearchQueryValidationError("Query must be at least 2 characters" + suffix)
    if len(query) > 200:
        raise SearchQueryValidationError("Query cannot exceed 200 characters")
    return query


class SearchDateRangeValidationError(ValueError):
    """Raised when resolved search date bounds are inconsistent."""


class SearchQueueValidationError(ValueError):
    """Raised for unsupported queue filters."""


def resolve_search_date_range(
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    *,
    now: Optional[datetime] = None,
    all_time: bool = False,
) -> tuple[datetime | None, datetime | None]:
    """Resolve explicit all-time or bounded search, preserving the default window."""
    if all_time:
        if start_date is not None or end_date is not None:
            raise SearchDateRangeValidationError("All time cannot be combined with date bounds")
        return None, None

    resolved_end = end_date or now or datetime.now(timezone.utc)
    resolved_start = start_date or resolved_end - timedelta(days=30)

    if resolved_start > resolved_end:
        raise SearchDateRangeValidationError("Start date must be before end date")
    if resolved_end - resolved_start > timedelta(days=365):
        raise SearchDateRangeValidationError("Date range cannot exceed 1 year")

    return resolved_start, resolved_end


def created_at_search_clause(
    start_date: datetime | None,
    end_date: datetime | None,
) -> tuple[str, dict[str, datetime]]:
    """Build optional date predicates without imposing bounds on all-time search."""
    clause = ""
    params: dict[str, datetime] = {}
    if start_date is not None:
        clause += " AND created_at >= :start_date"
        params["start_date"] = start_date
    if end_date is not None:
        clause += " AND created_at <= :end_date"
        params["end_date"] = end_date
    return clause, params


def _contains_like_pattern(value: str, *, asterisk_wildcard: bool = False) -> str:
    """Build a literal SQL LIKE substring pattern, optionally honoring ``*``."""
    escaped = value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    if asterisk_wildcard:
        escaped = escaped.replace("*", "%")
    return f"%{escaped}%"


def _substring_match_params(classification: QueryClassification) -> dict[str, str]:
    """Bind a literal fragment that can use the existing column trigram indexes."""
    value = classification.normalized_value
    # An unanchored pattern without a usable trigram can require a full scan.
    # Keep ID and explicit wildcard searches on their existing paths.
    if (
        classification.query_type in {QueryType.HUMAN_ID, QueryType.NUMERIC_ID}
        or classification.has_wildcard
        or not _SUBSTRING_TRIGRAM_PATTERN.search(value)
    ):
        return {}
    return {"substring_pattern": _contains_like_pattern(value)}


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
    
    async def _lookup_exact_id(
        self,
        db: AsyncSession,
        *,
        entity_type: EntityType,
        entity_id: int,
        start_date: datetime | None,
        end_date: datetime | None,
        normalized_tags: List[str],
    ) -> Optional[SearchResultItem]:
        """Return an exact ID match that satisfies the active search filters."""
        table_name = self.TABLE_NAMES[entity_type]
        date_clause, date_params = created_at_search_clause(start_date, end_date)
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
              {date_clause}
              {tag_filter_clause}
        """)

        result = await db.execute(sql, {
            "entity_id": entity_id,
            **date_params,
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
    
    def _build_timeline_match_sql(
        self,
        classification: QueryClassification,
    ) -> tuple[str, dict]:
        """Build timeline-item match conditions for a classified query.

        Structured values use exact field comparisons. Wildcard and generic
        queries use a safely escaped text search. Domain queries combine indexed
        timeline text with a check for a domain-bearing item type.
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
        
        # The value index narrows parents, including candidates with a matching
        # reply or a different field. Check the queue's exact top-level semantics
        # once per candidate using trusted field names from FIELD_MAPPINGS.
        params = {"ioc_candidate": value}
        conditions = []
        for i, (item_type, field_name) in enumerate(FIELD_MAPPINGS.get(query_type, [])):
            params[f"item_type_{i}"] = item_type
            conditions.append(
                f"(item->>'type' = :item_type_{i} AND item->>'{field_name}' = :ioc_candidate)"
            )
        for i, obs_type in enumerate(OBSERVABLE_TYPE_MAPPINGS.get(query_type, [])):
            params[f"obs_type_{i}"] = obs_type
            conditions.append(
                f"(item->>'type' = 'observable' AND item->>'observable_type' = :obs_type_{i} "
                "AND item->>'observable_value' = :ioc_candidate)"
            )
        if not conditions:
            return (
                "CAST(timeline_items AS text) ILIKE :timeline_pattern ESCAPE '\\'",
                {"timeline_pattern": _contains_like_pattern(value)},
            )
        return (
            f"""({IOC_CANDIDATE_SQL} AND EXISTS (
                SELECT 1 FROM ({TIMELINE_ITEMS_SQL}) AS entries
                WHERE {" OR ".join(conditions)}
            ))""",
            params,
        )

    # Timeline item types that could contain domain strings
    # A matching parent must contain at least one of these top-level items.
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
                f"(timeline_domain.item->>'type' = :{type_param}{observable_clause})"
            )
            params[type_param] = str(type_filter["type"])
        
        params["domain_pattern"] = _contains_like_pattern(domain)
        sql = f"""(
            EXISTS (
                SELECT 1 FROM ({TIMELINE_ITEMS_SQL}) AS timeline_domain
                WHERE {" OR ".join(type_conditions)}
            )
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

    async def queue_match_predicates(
        self, db: AsyncSession, query: str, entity_type: EntityType, filters: list[Any],
    ) -> tuple[list[Any], int]:
        """Match within the full filtered queue before applying the caller's pagination."""
        model, _ = QUEUE_MODELS[entity_type]
        count = select(func.count()).select_from(model).where(*filters)
        classification = classify_query(query)

        async def lookup_exact(entity_id: int) -> ColumnElement[bool] | None:
            predicate = model.id == entity_id
            return predicate if await db.scalar(count.where(predicate)) else None

        async def lookup_content(
            excluded_id: int | None, *, fuzzy: bool = False,
        ) -> tuple[ColumnElement[bool] | TextClause, int]:
            predicate: ColumnElement[bool] | TextClause
            substring: ColumnElement[bool] | TextClause | None = None
            if fuzzy:
                # pg_trgm's indexable % operator uses a session setting and an
                # inclusive threshold. Pin it for this search transaction and
                # retain the existing strict comparison on the candidates.
                await db.execute(
                    text("SELECT set_config('pg_trgm.similarity_threshold', :threshold, true)"),
                    {"threshold": str(FUZZY_SIMILARITY_THRESHOLD)},
                )
                predicate = text(f"(title % :query OR description % :query) AND {FUZZY_MATCH_SQL}").bindparams(
                    query=query, threshold=FUZZY_SIMILARITY_THRESHOLD,
                )
            else:
                timeline_sql, timeline_params = self._build_timeline_match_sql(classification)
                substring_params = _substring_match_params(classification)
                predicate = or_(
                    text(FULL_TEXT_MATCH_SQL).bindparams(query=classification.normalized_value),
                    text(timeline_sql).bindparams(**timeline_params),
                )
                if substring_params:
                    substring = text(SUBSTRING_MATCH_SQL).bindparams(**substring_params)
            if excluded_id is not None:
                exclusion = model.id != excluded_id
                predicate = and_(exclusion, predicate)
                if substring is not None:
                    substring = and_(exclusion, substring)
            if substring is not None:
                # Give the count query an indexable substring branch. The
                # ordered page can still use the existing single-row predicate.
                scoped_ids = select(model.id).where(*filters)
                matched_ids = scoped_ids.where(predicate).union(scoped_ids.where(substring))
                total = await db.scalar(select(func.count()).select_from(matched_ids.subquery()))
                return or_(predicate, substring), total or 0
            return predicate, await db.scalar(count.where(predicate)) or 0

        matches = await _match_entity(
            classification,
            entity_type,
            lookup_exact=lookup_exact,
            lookup_content=lookup_content,
            lookup_fuzzy=lambda excluded_id: lookup_content(excluded_id, fuzzy=True),
        )

        return [p for p in (matches.exact, matches.content) if p is not None], matches.total

    async def search_queue(
        self,
        db: AsyncSession,
        *,
        query: str,
        entity_type: EntityType,
        status: list[str] | None,
        assignee: list[str] | None,
        include_tags: list[str] | None,
        exclude_tags: list[str] | None,
        start_date: datetime | None,
        end_date: datetime | None,
        sort_by: str,
        sort_order: str,
        skip: int,
        limit: int,
    ) -> QueueSearchResponse:
        """Use Search matching with the queue's scope, sort and row projection."""
        model, status_enum = QUEUE_MODELS[entity_type]
        if sort_by not in QUEUE_SORT_FIELDS or sort_order not in {"asc", "desc"}:
            raise SearchQueueValidationError("Unsupported queue sort")
        try:
            statuses = [status_enum(value) for value in status or []]
        except ValueError as exc:
            raise SearchQueueValidationError(f"Invalid status for {entity_type.value} queue") from exc

        filters: list[Any] = []
        if statuses:
            filters.append(model.status.in_(statuses))
        append_assignee_filter(filters, model.assignee, assignee)
        append_tag_filters(filters, model.tags, include_tags, exclude_tags)
        if start_date is not None:
            filters.append(model.created_at >= start_date)
        if end_date is not None:
            filters.append(model.created_at <= end_date)

        predicates, total = await self.queue_match_predicates(db, query, entity_type, filters)
        rows = []
        if skip < total:
            sort_column = getattr(model, sort_by)
            ordering = sort_column.asc() if sort_order == "asc" else sort_column.desc()
            statement = (
                select(
                    model.id, model.title, model.created_at, model.updated_at,
                    model.status, model.priority, model.assignee, model.tags,
                    (model.case_id if model is not Case else literal(None)).label("case_id"),
                )
                .where(*filters, or_(*predicates))
                .order_by(ordering, model.id.desc())
                .offset(skip)
                .limit(limit)
            )
            rows = (await db.execute(statement)).all()

        return QueueSearchResponse(
            results=[
                QueueSearchRow(
                    id=row.id,
                    human_id=self._generate_human_id(entity_type, row.id),
                    title=row.title,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    status=row.status,
                    priority=row.priority,
                    assignee=row.assignee,
                    tags=self._coerce_tags(row.tags),
                    case_id=row.case_id,
                )
                for row in rows
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

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
        *,
        all_time: bool = False,
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
            all_time: Search without date bounds, rather than applying defaults

        Returns:
            PaginatedSearchResponse with results and pagination info
        """
        start_date, end_date = resolve_search_date_range(start_date, end_date, all_time=all_time)
        entity_types = list(dict.fromkeys(entity_types))
        normalized_tags = self._normalize_tag_filters(tags)
        classification = classify_query(query)

        async def search_entity(entity_type: EntityType) -> _EntityMatches[SearchResultItem, List[SearchResultItem]]:
            candidate_args = {
                "db": db,
                "table_name": self.TABLE_NAMES[entity_type],
                "entity_type": entity_type,
                "start_date": start_date,
                "end_date": end_date,
                "candidate_limit": skip + limit,
                "normalized_tags": normalized_tags,
            }
            return await _match_entity(
                classification,
                entity_type,
                lookup_exact=lambda entity_id: self._lookup_exact_id(
                    db,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    start_date=start_date,
                    end_date=end_date,
                    normalized_tags=normalized_tags,
                ),
                lookup_content=lambda excluded_id: self._search_entity_candidates(
                    classification=classification,
                    excluded_entity_id=excluded_id,
                    **candidate_args,
                ),
                lookup_fuzzy=lambda excluded_id: self._fuzzy_search_entity_candidates(
                    query=query,
                    excluded_entity_id=excluded_id,
                    **candidate_args,
                ),
            )

        # Search across all entity types and aggregate results
        all_items: List[SearchResultItem] = []
        numeric_match_types: list[str] = []
        total_count = 0

        for entity_type in entity_types:
            matches = await search_entity(entity_type)
            if matches.exact is not None:
                all_items.append(matches.exact)
                if classification.numeric_id is not None:
                    numeric_match_types.append(entity_type.value)
            if matches.content is not None:
                all_items.extend(matches.content)
            total_count += matches.total

        if numeric_match_types:
            logger.info(
                "Numeric ID matches found in paginated search",
                extra={
                    "user_id": user_id,
                    "query": query,
                    "numeric_id": classification.numeric_id,
                    "match_count": len(numeric_match_types),
                    "entity_types": numeric_match_types,
                },
            )
        
        # Sort merged results by score (descending), then by created_at (descending)
        if classification.is_filter_only:
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
                "all_time": all_time,
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
                start=start_date.isoformat() if start_date is not None else None,
                end=end_date.isoformat() if end_date is not None else None,
            ),
        )

    async def _search_entity_candidates(
        self,
        db: AsyncSession,
        table_name: str,
        entity_type: EntityType,
        classification: QueryClassification,
        start_date: datetime | None,
        end_date: datetime | None,
        candidate_limit: int,
        normalized_tags: Optional[List[str]] = None,
        excluded_entity_id: Optional[int] = None,
    ) -> Tuple[List[SearchResultItem], int]:
        """Return one entity type's top candidates and unpaginated count."""
        normalized_tags = normalized_tags or []
        date_clause, date_params = created_at_search_clause(start_date, end_date)
        tag_filter_sql, tag_filter_params = self._build_tag_filter_sql(normalized_tags)
        tag_filter_clause = f" AND {tag_filter_sql}" if tag_filter_sql else ""
        id_exclusion_clause = (
            " AND id != :excluded_entity_id" if excluded_entity_id is not None else ""
        )
        candidate_scope = f"{date_clause}{id_exclusion_clause}{tag_filter_clause}"
        common_params = {
            **date_params,
            "limit": candidate_limit,
            **(
                {"excluded_entity_id": excluded_entity_id}
                if excluded_entity_id is not None
                else {}
            ),
            **tag_filter_params,
        }

        if classification.is_filter_only:
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
                    WHERE TRUE {candidate_scope}
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

        normalized_query = classification.normalized_value

        # Build JSONB containment conditions based on classification
        timeline_condition, timeline_params = self._build_timeline_match_sql(classification)
        substring_params = _substring_match_params(classification)
        candidate_fields = """
            id, title, description, tags, created_at, updated_at, priority,
            status, assignee, timeline_items
        """
        # Keep substring in its own branch so PostgreSQL can use title and
        # description trigram indexes even if the timeline condition scans.
        substring_union = (
            f"""
                UNION ALL
                SELECT {candidate_fields}, 0.0 AS score, 'substring' AS match_source
                FROM {table_name}
                WHERE {SUBSTRING_MATCH_SQL}
                {candidate_scope}
            """
            if substring_params else ""
        )
        
        sql = text(f"""
            WITH search_results AS (
                SELECT {candidate_fields},
                    GREATEST(ts_rank(search_vector, websearch_to_tsquery('english', :query)), 0.000001) AS score,
                    'fulltext' AS match_source
                FROM {table_name}
                WHERE {FULL_TEXT_MATCH_SQL}
                {candidate_scope}
                
                UNION ALL
                
                SELECT {candidate_fields}, 0.8 AS score, 'jsonb' AS match_source
                FROM {table_name}
                WHERE {timeline_condition}
                {candidate_scope}
                {substring_union}
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
                    WHEN match_source = 'jsonb' THEN
                        COALESCE(
                            (
                                SELECT item.item::text
                                FROM ({TIMELINE_ITEMS_SQL}) AS item
                                WHERE item.item::text ILIKE :snippet_pattern ESCAPE '\\'
                                LIMIT 1
                            ),
                            COALESCE(title, '') || ' ' || COALESCE(LEFT(description, 100), '')
                        )
                    ELSE COALESCE(title, '') || ' ' || COALESCE(LEFT(description, 100), '')
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
            **substring_params,
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
        start_date: datetime | None,
        end_date: datetime | None,
        candidate_limit: int,
        similarity_threshold: float = FUZZY_SIMILARITY_THRESHOLD,
        normalized_tags: Optional[List[str]] = None,
        excluded_entity_id: Optional[int] = None,
    ) -> Tuple[List[SearchResultItem], int]:
        """Return fuzzy candidates for one entity type and its full count."""
        normalized_tags = normalized_tags or []
        date_clause, date_params = created_at_search_clause(start_date, end_date)
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
                WHERE {FUZZY_MATCH_SQL}
                {date_clause}
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
            **date_params,
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
