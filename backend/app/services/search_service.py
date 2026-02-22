"""Search service for unified full-text search across alerts, cases, and tasks.

This service implements PostgreSQL full-text search with:
- Weighted zones (A=title, B=description, C=source/assignee, D=timeline)
- ts_headline for snippet generation with <mark> tags
- Parallel async queries across all entity types
- Fuzzy matching fallback using pg_trgm similarity
- Type-specific JSONB containment queries for IOCs (IPs, emails, URLs, hashes)
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.models.search_schemas import (
    EntityType,
    SearchResultItem,
    DateRangeApplied,
    PaginatedSearchResponse,
)
from app.core.validation import STRICT_PATTERNS


logger = logging.getLogger(__name__)


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
    r'^(ALT|CAS|TSK)-(\d{1,9})$', re.IGNORECASE
)
_HUMAN_ID_PREFIX_MAP = {
    'ALT': 'alert',
    'CAS': 'case',
    'TSK': 'task',
}

# Use patterns from shared validation module
_IPV4_PATTERN = STRICT_PATTERNS["ipv4"]
_IPV6_PATTERN = STRICT_PATTERNS["ipv6"]
_EMAIL_PATTERN = STRICT_PATTERNS["email"]
_URL_PATTERN = STRICT_PATTERNS["url"]
_DOMAIN_PATTERN = STRICT_PATTERNS["domain"]
_MD5_PATTERN = STRICT_PATTERNS["md5"]
_SHA1_PATTERN = STRICT_PATTERNS["sha1"]
_SHA256_PATTERN = STRICT_PATTERNS["sha256"]
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
    
    # For classification, remove wildcards temporarily
    test_value = query.replace('*', '')
    
    # Empty after removing wildcards means it's just wildcards
    if not test_value:
        return QueryClassification(
            query_type=QueryType.GENERIC,
            normalized_value=query,
            has_wildcard=has_wildcard,
            original_query=original,
        )
    
    # Check patterns in order of specificity
    
    # Human ID (ALT-0000001, CAS-000001, TSK-000001) - highest priority
    human_id_match = _HUMAN_ID_PATTERN.match(test_value)
    if human_id_match:
        prefix = human_id_match.group(1).upper()
        numeric_id = int(human_id_match.group(2))
        entity_type = _HUMAN_ID_PREFIX_MAP.get(prefix)
        return QueryClassification(
            query_type=QueryType.HUMAN_ID,
            normalized_value=query.upper(),  # Normalize to uppercase
            has_wildcard=has_wildcard,
            original_query=original,
            human_id_entity_type=entity_type,
            human_id_numeric=numeric_id,
        )
    
    # Plain numeric ID (e.g., "123") - could be alert, case, or task ID
    # Check after human ID but before IP to avoid matching IPs like "192"
    if test_value.isdigit():
        numeric_value = int(test_value)
        # Only treat as ID if it's a reasonable entity ID (positive, not too large)
        if 0 < numeric_value <= 999999999:
            return QueryClassification(
                query_type=QueryType.NUMERIC_ID,
                normalized_value=query,
                has_wildcard=has_wildcard,
                original_query=original,
                numeric_id=numeric_value,
            )
    
    # IPv4 (exact match)
    if _IPV4_PATTERN.match(test_value):
        return QueryClassification(
            query_type=QueryType.IP,
            normalized_value=query,
            has_wildcard=has_wildcard,
            original_query=original,
        )
    
    # IPv4 with wildcards (e.g., 192.168.* or 10.*.*.*)
    if has_wildcard and _IPV4_WILDCARD_PATTERN.match(query):
        return QueryClassification(
            query_type=QueryType.IP,
            normalized_value=query,
            has_wildcard=True,
            original_query=original,
        )
    
    # IPv6
    if _IPV6_PATTERN.match(test_value):
        return QueryClassification(
            query_type=QueryType.IP,
            normalized_value=query,
            has_wildcard=has_wildcard,
            original_query=original,
        )
    
    # Email
    if _EMAIL_PATTERN.match(test_value):
        return QueryClassification(
            query_type=QueryType.EMAIL,
            normalized_value=query.lower(),  # Normalize email to lowercase
            has_wildcard=has_wildcard,
            original_query=original,
        )
    
    # URL (before domain since URLs contain domains)
    if _URL_PATTERN.match(test_value):
        return QueryClassification(
            query_type=QueryType.URL,
            normalized_value=query,
            has_wildcard=has_wildcard,
            original_query=original,
        )
    
    # Hashes (check before domain since hex strings could match domain pattern)
    if _SHA256_PATTERN.match(test_value):
        return QueryClassification(
            query_type=QueryType.HASH,
            normalized_value=query.lower(),  # Normalize hash to lowercase
            has_wildcard=has_wildcard,
            original_query=original,
        )
    if _SHA1_PATTERN.match(test_value):
        return QueryClassification(
            query_type=QueryType.HASH,
            normalized_value=query.lower(),
            has_wildcard=has_wildcard,
            original_query=original,
        )
    if _MD5_PATTERN.match(test_value):
        return QueryClassification(
            query_type=QueryType.HASH,
            normalized_value=query.lower(),
            has_wildcard=has_wildcard,
            original_query=original,
        )
    
    # MITRE ATT&CK ID (check BEFORE filename to avoid T1059.002 matching as filename)
    if _MITRE_ATTACK_PATTERN.match(test_value):
        return QueryClassification(
            query_type=QueryType.MITRE,
            normalized_value=query.upper(),  # Normalize to uppercase (T1059.001)
            has_wildcard=has_wildcard,
            original_query=original,
        )
    
    # Filename (check BEFORE domain - use extension whitelist to avoid false positives)
    filename_match = _FILENAME_PATTERN.match(test_value)
    if filename_match:
        extension = filename_match.group(1).lower()
        if extension in _FILENAME_EXTENSIONS:
            return QueryClassification(
                query_type=QueryType.FILENAME,
                normalized_value=query,
                has_wildcard=has_wildcard,
                original_query=original,
            )
    
    # Domain/hostname (after filename check)
    if _DOMAIN_PATTERN.match(test_value):
        return QueryClassification(
            query_type=QueryType.DOMAIN,
            normalized_value=query.lower(),  # Normalize domain to lowercase
            has_wildcard=has_wildcard,
            original_query=original,
        )
    
    # Fallback to generic
    return QueryClassification(
        query_type=QueryType.GENERIC,
        normalized_value=query,
        has_wildcard=has_wildcard,
        original_query=original,
    )


# =============================================================================
# Type-Specific Field Mappings for JSONB Containment Queries
# =============================================================================

# Maps QueryType to list of (timeline_item_type, field_name) tuples
# These are used to build efficient @> containment queries
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
        EntityType.ALERT: "ALT-",
        EntityType.CASE: "CAS-",
        EntityType.TASK: "TSK-",
    }
    
    def _generate_human_id(self, entity_type: EntityType, entity_id: int) -> str:
        """Generate human-readable ID like ALT-0000123."""
        prefix = self.PREFIXES[entity_type]
        return f"{prefix}{entity_id:07d}"
    
    async def _lookup_by_human_id(
        self,
        db: AsyncSession,
        classification: QueryClassification,
        target_entity_type: Optional[EntityType] = None,
    ) -> Optional[SearchResultItem]:
        """Look up an entity by exact human ID match.
        
        Returns a SearchResultItem with score 1.0 if found, None otherwise.
        
        Args:
            db: Database session
            classification: Query classification (must be HUMAN_ID type)
            target_entity_type: If specified, only match if entity type matches
            
        Returns:
            SearchResultItem with score 1.0 if exact match found, None otherwise
        """
        if classification.query_type != QueryType.HUMAN_ID:
            return None
        
        entity_type_str = classification.human_id_entity_type
        entity_id = classification.human_id_numeric
        
        if not entity_type_str or entity_id is None:
            return None
        
        # Map string to EntityType enum
        entity_type_map = {
            'alert': EntityType.ALERT,
            'case': EntityType.CASE,
            'task': EntityType.TASK,
        }
        entity_type = entity_type_map.get(entity_type_str)
        if not entity_type:
            return None
        
        # If target_entity_type is specified, check if it matches
        if target_entity_type and entity_type != target_entity_type:
            return None
        
        # Determine table name
        table_map = {
            EntityType.ALERT: "alerts",
            EntityType.CASE: "cases",
            EntityType.TASK: "tasks",
        }
        table_name = table_map[entity_type]
        
        # Query for exact ID match
        sql = text(f"""
            SELECT 
                id,
                title,
                description,
                tags,
                created_at
            FROM {table_name}
            WHERE id = :entity_id
        """)
        
        result = await db.execute(sql, {"entity_id": entity_id})
        row = result.fetchone()
        
        if not row:
            return None
        
        # Build snippet from title/description
        snippet = ""
        if row.title:
            snippet = row.title
        if row.description:
            desc_preview = row.description[:100] if len(row.description) > 100 else row.description
            snippet = f"{snippet} - {desc_preview}" if snippet else desc_preview
        
        return SearchResultItem(
            entity_type=entity_type,
            entity_id=row.id,
            human_id=self._generate_human_id(entity_type, row.id),
            title=row.title or "",
            snippet=snippet,
            score=1.0,  # Exact match = maximum score
            timeline_item_id=None,
            created_at=row.created_at,
            tags=row.tags or [],
        )
    
    async def _lookup_by_numeric_id(
        self,
        db: AsyncSession,
        classification: QueryClassification,
        entity_types: Optional[List[EntityType]] = None,
    ) -> List[SearchResultItem]:
        """Look up entities by plain numeric ID across all entity types.
        
        When a user enters just a number like "123", we check if it matches
        an alert, case, or task ID and return any matches as top results.
        
        Args:
            db: Database session
            classification: Query classification (must be NUMERIC_ID type)
            entity_types: If specified, only search these entity types
            
        Returns:
            List of SearchResultItems with score 1.0 for each matching entity
        """
        if classification.query_type != QueryType.NUMERIC_ID:
            return []
        
        entity_id = classification.numeric_id
        if entity_id is None:
            return []
        
        # Search all entity types by default
        if entity_types is None:
            entity_types = list(EntityType)
        
        results: List[SearchResultItem] = []
        
        # Check each entity type for a matching ID
        table_map = {
            EntityType.ALERT: "alerts",
            EntityType.CASE: "cases",
            EntityType.TASK: "tasks",
        }
        
        for entity_type in entity_types:
            table_name = table_map.get(entity_type)
            if not table_name:
                continue
            
            sql = text(f"""
                SELECT 
                    id,
                    title,
                    description,
                    tags,
                    created_at
                FROM {table_name}
                WHERE id = :entity_id
            """)
            
            result = await db.execute(sql, {"entity_id": entity_id})
            row = result.fetchone()
            
            if row:
                # Build snippet from title/description
                snippet = ""
                if row.title:
                    snippet = row.title
                if row.description:
                    desc_preview = row.description[:100] if len(row.description) > 100 else row.description
                    snippet = f"{snippet} - {desc_preview}" if snippet else desc_preview
                
                results.append(SearchResultItem(
                    entity_type=entity_type,
                    entity_id=row.id,
                    human_id=self._generate_human_id(entity_type, row.id),
                    title=row.title or "",
                    snippet=snippet,
                    score=1.0,  # Exact ID match = maximum score
                    timeline_item_id=None,
                    created_at=row.created_at,
                    tags=row.tags or [],
                ))
        
        return results
    
    def _build_jsonb_containment_sql(
        self,
        classification: QueryClassification,
    ) -> tuple[str, dict]:
        """Build JSONB containment query conditions for classified queries.
        
        For non-wildcard queries, generates efficient @> containment conditions
        that leverage the GIN index on timeline_items.
        
        For wildcard queries, falls back to ILIKE on timeline_items::text.
        
        For DOMAIN queries, uses hybrid approach: GIN pre-filter on item types
        that could contain domains, then ILIKE refinement for substring matching.
        This catches domains within email addresses (e.g., evil.com in user@evil.com).
        
        Args:
            classification: The classified query with type and normalized value
            
        Returns:
            Tuple of (SQL WHERE clause fragment, parameter dict)
        """
        query_type = classification.query_type
        value = classification.normalized_value
        has_wildcard = classification.has_wildcard
        
        # For wildcards or generic queries, use ILIKE fallback
        if has_wildcard or query_type == QueryType.GENERIC:
            # Convert * to % for SQL LIKE
            like_value = value.replace('*', '%')
            # Note: Use CAST() instead of :: to avoid SQLAlchemy parameter parsing issues
            return (
                "CAST(timeline_items AS text) ILIKE :jsonb_pattern",
                {"jsonb_pattern": f"%{like_value}%"}
            )
        
        # For DOMAIN queries, use hybrid GIN pre-filter + ILIKE approach
        # This catches domains within email addresses (evil.com in user@evil.com)
        # and URLs (evil.com in https://evil.com/path)
        if query_type == QueryType.DOMAIN:
            return self._build_hybrid_domain_sql(value)
        
        # Build containment conditions for specific field mappings
        conditions = []
        params = {}
        param_idx = 0
        
        # Get field mappings for this query type
        field_mappings = FIELD_MAPPINGS.get(query_type, [])
        for item_type, field_name in field_mappings:
            param_name = f"containment_{param_idx}"
            # Build JSONB containment: timeline_items @> CAST(:param AS jsonb)
            # Note: Use CAST() instead of :: to avoid SQLAlchemy parameter parsing issues
            conditions.append(f"timeline_items @> CAST(:{param_name} AS jsonb)")
            # Create the JSONB pattern - note we use a list with one object
            params[param_name] = json.dumps([{"type": item_type, field_name: value}])
            param_idx += 1
        
        # Add observable type mappings
        observable_types = OBSERVABLE_TYPE_MAPPINGS.get(query_type, [])
        for obs_type in observable_types:
            param_name = f"containment_{param_idx}"
            conditions.append(f"timeline_items @> CAST(:{param_name} AS jsonb)")
            params[param_name] = json.dumps([{
                "type": "observable",
                "observable_type": obs_type,
                "observable_value": value
            }])
            param_idx += 1
        
        if not conditions:
            # No mappings found, fallback to ILIKE
            # Note: Use CAST() instead of :: to avoid SQLAlchemy parameter parsing issues
            return (
                "CAST(timeline_items AS text) ILIKE :jsonb_pattern",
                {"jsonb_pattern": f"%{value}%"}
            )
        
        # Join conditions with OR - any of them matching is a hit
        return (
            "(" + " OR ".join(conditions) + ")",
            params
        )
    
    # Timeline item types that could contain domain strings
    # Used for hybrid GIN pre-filter before ILIKE refinement
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

    def _build_hybrid_domain_sql(self, domain: str) -> tuple[str, dict]:
        """Build hybrid GIN pre-filter + ILIKE query for domain searches.
        
        This approach:
        1. Uses GIN index to quickly find rows with domain-containing item types
        2. Applies ILIKE only on those filtered rows
        
        This is much faster than full-table ILIKE when domain-containing items
        are sparse, while still catching domains within email addresses
        (evil.com matches user@evil.com) and URLs.
        
        Args:
            domain: The domain to search for (e.g., "evil.com")
            
        Returns:
            Tuple of (SQL WHERE clause fragment, parameter dict)
        """
        # Build GIN containment conditions for types that could contain domains
        gin_conditions = []
        params = {}
        
        for idx, type_filter in enumerate(self.DOMAIN_CONTAINING_TYPES):
            param_name = f"domain_type_{idx}"
            gin_conditions.append(f"timeline_items @> CAST(:{param_name} AS jsonb)")
            params[param_name] = json.dumps([type_filter])
        
        # Combine: (GIN pre-filter) AND (ILIKE refinement)
        # The GIN conditions are OR'd together (any matching type)
        # Then ILIKE is applied to the reduced result set
        params["domain_pattern"] = f"%{domain}%"
        
        # PostgreSQL will use GIN index for the containment checks first,
        # then apply ILIKE filter on the reduced result set
        sql = f"""(
            ({" OR ".join(gin_conditions)})
            AND CAST(timeline_items AS text) ILIKE :domain_pattern
        )"""
        
        return sql, params

    def _normalize_tag_filters(self, tags: Optional[List[str]]) -> List[str]:
        """Normalize tag filter values by trimming and de-duplicating."""
        if not tags:
            return []

        normalized: List[str] = []
        seen: set[str] = set()
        for raw_tag in tags:
            if not raw_tag:
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
            params[param_name] = f"%{tag}%"
            top_level_tag_conditions.append(f"tag ILIKE :{param_name}")
            timeline_tag_conditions.append(f"timeline_tag ILIKE :{param_name}")

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
                FROM jsonb_array_elements(COALESCE(timeline_items, '[]'::jsonb)) AS item
                WHERE EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(
                        CASE
                            WHEN jsonb_typeof(item->'tags') = 'array' THEN item->'tags'
                            ELSE '[]'::jsonb
                        END
                    ) AS timeline_tag
                    WHERE {timeline_where}
                )
            )
        )"""

        return sql, params
    
    async def _search_entity(
        self,
        db: AsyncSession,
        table_name: str,
        entity_type: EntityType,
        query: str,
        start_date: datetime,
        end_date: datetime,
        limit: int,
        tags: Optional[List[str]] = None,
    ) -> Tuple[List[SearchResultItem], int]:
        """Search a single entity table and return results with total count.
        
        Args:
            db: Database session
            table_name: Name of the table to search (alerts, cases, tasks)
            entity_type: Type of entity being searched
            query: Search query text
            start_date: Start of date range filter
            end_date: End of date range filter
            limit: Maximum number of results to return
            
        Returns:
            Tuple of (list of SearchResultItem, total count)
            
        Note:
            This method combines multiple search strategies:
            1. Exact human ID match (ALT-000001, CAS-000001, TSK-000001) - score 1.0
            2. Full-text search using tsvector/tsquery for natural language queries
            3. Type-specific JSONB containment queries for IOCs (IPs, emails, etc.)
               using GIN indexes for fast lookup
            4. ILIKE fallback for wildcard queries or unclassified terms
        """
        normalized_tags = self._normalize_tag_filters(tags)
        tag_filter_sql, tag_filter_params = self._build_tag_filter_sql(normalized_tags)
        tag_filter_clause = f" AND {tag_filter_sql}" if tag_filter_sql else ""

        # Special filter-only mode (q='*'): skip content search and apply filters only
        if query == "*":
            sql = text(f"""
                WITH filtered AS (
                    SELECT
                        id,
                        title,
                        description,
                        tags,
                        created_at
                    FROM {table_name}
                    WHERE created_at >= :start_date
                      AND created_at <= :end_date
                      {tag_filter_clause}
                )
                SELECT
                    id,
                    title,
                    description,
                    tags,
                    created_at,
                    0.0 AS score,
                    COALESCE(title, '') || ' ' || COALESCE(LEFT(description, 100), '') AS snippet,
                    (SELECT COUNT(*) FROM filtered) AS total_count
                FROM filtered
                ORDER BY created_at DESC
                LIMIT :limit
            """)

            result = await db.execute(sql, {
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
                **tag_filter_params,
            })
            rows = result.fetchall()
            if not rows:
                return [], 0

            total_count = rows[0].total_count if rows else 0
            items = [
                SearchResultItem(
                    entity_type=entity_type,
                    entity_id=row.id,
                    human_id=self._generate_human_id(entity_type, row.id),
                    title=row.title or "",
                    snippet=(row.snippet or "")[:150],
                    score=0.0,
                    timeline_item_id=None,
                    created_at=row.created_at,
                    tags=row.tags or [],
                )
                for row in rows
            ]
            return items, total_count

        # Classify the query to determine optimal search strategy
        classification = classify_query(query)
        normalized_query = classification.normalized_value
        
        logger.debug(
            "Query classified",
            extra={
                "original": query,
                "type": classification.query_type.value,
                "has_wildcard": classification.has_wildcard,
                "normalized": normalized_query,
            }
        )
        
        # Check for exact human ID match first (highest priority)
        if classification.query_type == QueryType.HUMAN_ID:
            exact_match = await self._lookup_by_human_id(db, classification, entity_type)
            if exact_match:
                logger.debug(
                    "Exact human ID match found",
                    extra={"human_id": exact_match.human_id, "entity_type": entity_type.value}
                )
                return [exact_match], 1
            # If no match for this entity type (e.g., searching cases for ALT-000001),
            # return empty results
            return [], 0
        
        # Build JSONB containment conditions based on classification
        jsonb_condition, jsonb_params = self._build_jsonb_containment_sql(classification)
        
        # Build the search SQL
        # Combines full-text search with type-specific JSONB containment
        # Full-text search uses websearch_to_tsquery for natural language queries
        # (supports AND, OR, "phrases", -negation with fallback to plainto_tsquery)
        # JSONB search uses @> containment for IPs, hashes, and exact strings
        # ts_headline generates snippets with <mark> tags
        # Using websearch_to_tsquery for boolean operator support (AND, OR, "phrases", -negation)
        sql = text(f"""
            WITH search_results AS (
                -- Full-text search on search_vector (title, description, timeline text)
                SELECT 
                    id,
                    title,
                    description,
                    tags,
                    created_at,
                    timeline_items,
                    ts_rank(search_vector, websearch_to_tsquery('english', :query)) AS score,
                    'fulltext' AS match_source
                FROM {table_name}
                WHERE search_vector @@ websearch_to_tsquery('english', :query)
                  AND created_at >= :start_date
                  AND created_at <= :end_date
                                    {tag_filter_clause}
                
                UNION
                
                -- Type-specific JSONB containment search (for IPs, hashes, emails, etc.)
                SELECT 
                    id,
                    title,
                    description,
                    tags,
                    created_at,
                    timeline_items,
                    0.8 AS score,  -- High score for exact IOC matches
                    'jsonb' AS match_source
                FROM {table_name}
                WHERE {jsonb_condition}
                  AND created_at >= :start_date
                  AND created_at <= :end_date
                                    {tag_filter_clause}
            ),
            deduplicated AS (
                -- Deduplicate results, keeping the highest score per entity
                SELECT DISTINCT ON (id)
                    id,
                    title,
                    description,
                    tags,
                    created_at,
                    timeline_items,
                    score,
                    match_source
                FROM search_results
                ORDER BY id, score DESC
            )
            SELECT 
                id, 
                title, 
                description, 
                tags,
                created_at, 
                score,
                match_source,
                CASE 
                    WHEN match_source = 'fulltext' THEN
                        ts_headline(
                            'english',
                            COALESCE(title, '') || ' ' || COALESCE(description, ''),
                            websearch_to_tsquery('english', :query),
                            'MaxWords=25, MinWords=10, StartSel=<mark>, StopSel=</mark>, MaxFragments=1'
                        )
                    ELSE
                        -- For JSONB matches, return full timeline item JSON (no truncation)
                        COALESCE(
                            (
                                SELECT item::text
                                FROM jsonb_array_elements(timeline_items) AS item
                                WHERE item::text ILIKE '%' || :query || '%'
                                LIMIT 1
                            ),
                            COALESCE(title, '') || ' ' || COALESCE(LEFT(description, 100), '')
                        )
                END AS snippet,
                (SELECT COUNT(*) FROM deduplicated) AS total_count
            FROM deduplicated
            ORDER BY score DESC
            LIMIT :limit
        """)
        
        # Merge base params with JSONB containment params
        params = {
            "query": normalized_query,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
            **jsonb_params,
            **tag_filter_params,
        }
        
        try:
            result = await db.execute(sql, params)
            rows = result.fetchall()
        except Exception as e:
            # Graceful degradation: if websearch_to_tsquery fails due to malformed
            # boolean syntax (e.g., unbalanced quotes), fall back to plainto_tsquery
            logger.warning(
                "websearch_to_tsquery failed, falling back to plainto_tsquery",
                extra={"query": normalized_query, "error": str(e)}
            )
            fallback_sql = text(sql.text.replace(
                "websearch_to_tsquery('english', :query)",
                "plainto_tsquery('english', :query)"
            ))
            result = await db.execute(fallback_sql, params)
            rows = result.fetchall()
        
        if not rows:
            return [], 0
        
        total_count = rows[0].total_count if rows else 0
        
        items = []
        for row in rows:
            # Truncate snippet to 150 chars, but only for non-JSON snippets
            # JSON snippets (timeline items) should be returned in full for frontend rendering
            snippet = row.snippet or ""
            is_json_snippet = snippet.strip().startswith('{')
            if not is_json_snippet and len(snippet) > 150:
                # Find a good break point for text snippets
                snippet = snippet[:147] + "..."
            
            items.append(SearchResultItem(
                entity_type=entity_type,
                entity_id=row.id,
                human_id=self._generate_human_id(entity_type, row.id),
                title=row.title or "",
                snippet=snippet,
                score=min(1.0, row.score),  # Normalize score to 0-1
                timeline_item_id=None,  # TODO: Extract if match was in timeline
                created_at=row.created_at,
                tags=row.tags or [],
            ))
        
        return items, total_count
    
    async def search_alerts(
        self,
        db: AsyncSession,
        query: str,
        start_date: datetime,
        end_date: datetime,
        limit: int = 5,
    ) -> Tuple[List[SearchResultItem], int]:
        """Search alerts table."""
        return await self._search_entity(
            db, "alerts", EntityType.ALERT, query, start_date, end_date, limit
        )
    
    async def search_cases(
        self,
        db: AsyncSession,
        query: str,
        start_date: datetime,
        end_date: datetime,
        limit: int = 5,
    ) -> Tuple[List[SearchResultItem], int]:
        """Search cases table."""
        return await self._search_entity(
            db, "cases", EntityType.CASE, query, start_date, end_date, limit
        )
    
    async def search_tasks(
        self,
        db: AsyncSession,
        query: str,
        start_date: datetime,
        end_date: datetime,
        limit: int = 5,
    ) -> Tuple[List[SearchResultItem], int]:
        """Search tasks table."""
        return await self._search_entity(
            db, "tasks", EntityType.TASK, query, start_date, end_date, limit
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
    ) -> PaginatedSearchResponse:
        """Perform paginated search across one or more entity types.
        
        This is used by the dedicated search page for pagination.
        Unlike global_search which returns limit_per_type results per entity,
        this returns paginated results across specified entity types.
        
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
        # Default date range to last 30 days
        now = datetime.now(timezone.utc)
        if end_date is None:
            end_date = now
        if start_date is None:
            start_date = now - timedelta(days=30)
        
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
            numeric_id_matches = await self._lookup_by_numeric_id(db, classification, entity_types)
            if numeric_id_matches:
                logger.info(
                    "Numeric ID matches found in paginated search",
                    extra={
                        "user_id": user_id,
                        "query": query,
                        "numeric_id": classification.numeric_id,
                        "match_count": len(numeric_id_matches),
                        "entity_types": [m.entity_type.value for m in numeric_id_matches],
                    }
                )
        
        # Build table info for all requested entity types
        table_info = [
            (entity_type, {
                EntityType.ALERT: "alerts",
                EntityType.CASE: "cases",
                EntityType.TASK: "tasks",
            }[entity_type])
            for entity_type in entity_types
        ]
        
        # Search across all entity types and aggregate results
        all_items: List[SearchResultItem] = []
        total_count = 0
        
        for entity_type, table_name in table_info:
            # First try full-text search
            items, count = await self._search_entity_paginated(
                db=db,
                table_name=table_name,
                entity_type=entity_type,
                query=query,
                start_date=start_date,
                end_date=end_date,
                skip=0,  # We'll handle pagination after merging
                limit=skip + limit,  # Get enough to cover skip + limit
                tags=normalized_tags,
            )
            
            # If no results, try fuzzy search fallback (but NOT for human ID queries)
            if count == 0 and not is_human_id_query and not filter_only_mode:
                items, count = await self._fuzzy_search_entity_paginated(
                    db=db,
                    table_name=table_name,
                    entity_type=entity_type,
                    query=query,
                    start_date=start_date,
                    end_date=end_date,
                    skip=0,
                    limit=skip + limit,
                    tags=normalized_tags,
                )
            
            all_items.extend(items)
            total_count += count
        
        # Merge numeric ID matches: they have score 1.0 and should replace any lower-scored duplicates
        if numeric_id_matches:
            # Create a dict for fast lookup of existing results by (entity_type, entity_id)
            existing_by_key = {(r.entity_type, r.entity_id): i for i, r in enumerate(all_items)}
            
            for match in numeric_id_matches:
                key = (match.entity_type, match.entity_id)
                if key in existing_by_key:
                    # Replace the existing result with the higher-scored numeric ID match
                    all_items[existing_by_key[key]] = match
                else:
                    # Add new result and update count
                    all_items.append(match)
                    total_count += 1
        
        # Sort merged results by score (descending), then by created_at (descending)
        if filter_only_mode:
            all_items.sort(key=lambda x: -x.created_at.timestamp())
        else:
            all_items.sort(key=lambda x: (-x.score, -x.created_at.timestamp()))
        
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
            }
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

    async def _search_entity_paginated(
        self,
        db: AsyncSession,
        table_name: str,
        entity_type: EntityType,
        query: str,
        start_date: datetime,
        end_date: datetime,
        skip: int,
        limit: int,
        tags: Optional[List[str]] = None,
    ) -> Tuple[List[SearchResultItem], int]:
        """Search a single entity table with pagination support."""
        normalized_tags = self._normalize_tag_filters(tags)
        tag_filter_sql, tag_filter_params = self._build_tag_filter_sql(normalized_tags)
        tag_filter_clause = f" AND {tag_filter_sql}" if tag_filter_sql else ""

        if query == "*":
            sql = text(f"""
                WITH filtered AS (
                    SELECT
                        id,
                        title,
                        description,
                        tags,
                        created_at
                    FROM {table_name}
                    WHERE created_at >= :start_date
                      AND created_at <= :end_date
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
                    created_at,
                    0.0 AS score,
                    total_count,
                    COALESCE(title, '') || ' ' || COALESCE(LEFT(description, 100), '') AS snippet
                FROM counted
                ORDER BY created_at DESC
                OFFSET :skip
                LIMIT :limit
            """)

            result = await db.execute(sql, {
                "start_date": start_date,
                "end_date": end_date,
                "skip": skip,
                "limit": limit,
                **tag_filter_params,
            })
            rows = result.fetchall()
            if not rows:
                return [], 0

            total_count = rows[0].total_count if rows else 0
            items: List[SearchResultItem] = []
            for row in rows:
                snippet = row.snippet or ""
                if len(snippet) > 150:
                    snippet = snippet[:147] + "..."

                items.append(SearchResultItem(
                    entity_type=entity_type,
                    entity_id=row.id,
                    human_id=self._generate_human_id(entity_type, row.id),
                    title=row.title or "",
                    snippet=snippet,
                    score=0.0,
                    timeline_item_id=None,
                    created_at=row.created_at,
                    tags=row.tags or [],
                ))

            return items, total_count

        classification = classify_query(query)
        normalized_query = classification.normalized_value
        
        # Check for exact human ID match first (highest priority)
        if classification.query_type == QueryType.HUMAN_ID:
            exact_match = await self._lookup_by_human_id(db, classification, entity_type)
            if exact_match:
                # For pagination, if skip > 0, we're past the single result
                if skip > 0:
                    return [], 1  # Total is 1 but we've skipped past it
                return [exact_match], 1
            # If no match for this entity type, return empty
            return [], 0
        
        # Build JSONB containment conditions based on classification
        jsonb_condition, jsonb_params = self._build_jsonb_containment_sql(classification)
        
        sql = text(f"""
            WITH search_results AS (
                SELECT 
                    id,
                    title,
                    description,
                    tags,
                    created_at,
                    timeline_items,
                    ts_rank(search_vector, websearch_to_tsquery('english', :query)) AS score,
                    'fulltext' AS match_source
                FROM {table_name}
                WHERE search_vector @@ websearch_to_tsquery('english', :query)
                  AND created_at >= :start_date
                  AND created_at <= :end_date
                                    {tag_filter_clause}
                
                UNION
                
                SELECT 
                    id,
                    title,
                    description,
                    tags,
                    created_at,
                    timeline_items,
                    0.8 AS score,
                    'jsonb' AS match_source
                FROM {table_name}
                WHERE {jsonb_condition}
                  AND created_at >= :start_date
                  AND created_at <= :end_date
                                    {tag_filter_clause}
            ),
            deduplicated AS (
                SELECT DISTINCT ON (id)
                    id,
                    title,
                    description,
                    tags,
                    created_at,
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
                created_at, 
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
                                SELECT item::text
                                FROM jsonb_array_elements(timeline_items) AS item
                                WHERE item::text ILIKE '%' || :query || '%'
                                LIMIT 1
                            ),
                            COALESCE(title, '') || ' ' || COALESCE(LEFT(description, 100), '')
                        )
                END AS snippet
            FROM counted
            ORDER BY score DESC
            OFFSET :skip
            LIMIT :limit
        """)
        
        params = {
            "query": normalized_query,
            "start_date": start_date,
            "end_date": end_date,
            "skip": skip,
            "limit": limit,
            **jsonb_params,
            **tag_filter_params,
        }
        
        try:
            result = await db.execute(sql, params)
            rows = result.fetchall()
        except Exception as e:
            logger.warning(
                "websearch_to_tsquery failed, falling back to plainto_tsquery",
                extra={"query": normalized_query, "error": str(e)}
            )
            fallback_sql = text(sql.text.replace(
                "websearch_to_tsquery('english', :query)",
                "plainto_tsquery('english', :query)"
            ))
            result = await db.execute(fallback_sql, params)
            rows = result.fetchall()
        
        if not rows:
            return [], 0
        
        total_count = rows[0].total_count if rows else 0
        
        items = []
        for row in rows:
            snippet = row.snippet or ""
            is_json_snippet = snippet.strip().startswith('{')
            if not is_json_snippet and len(snippet) > 150:
                snippet = snippet[:147] + "..."
            
            items.append(SearchResultItem(
                entity_type=entity_type,
                entity_id=row.id,
                human_id=self._generate_human_id(entity_type, row.id),
                title=row.title or "",
                snippet=snippet,
                score=min(1.0, row.score),
                timeline_item_id=None,
                created_at=row.created_at,
                tags=row.tags or [],
            ))
        
        return items, total_count

    async def _fuzzy_search_entity_paginated(
        self,
        db: AsyncSession,
        table_name: str,
        entity_type: EntityType,
        query: str,
        start_date: datetime,
        end_date: datetime,
        skip: int,
        limit: int,
        similarity_threshold: float = 0.3,
        tags: Optional[List[str]] = None,
    ) -> Tuple[List[SearchResultItem], int]:
        """Fuzzy search fallback with pagination support."""
        normalized_tags = self._normalize_tag_filters(tags)
        tag_filter_sql, tag_filter_params = self._build_tag_filter_sql(normalized_tags)
        tag_filter_clause = f" AND {tag_filter_sql}" if tag_filter_sql else ""

        sql = text(f"""
            WITH fuzzy_results AS (
                SELECT 
                    id,
                    title,
                    description,
                    tags,
                    created_at,
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
                {tag_filter_clause}
            ),
            counted AS (
                SELECT *, COUNT(*) OVER() AS total_count
                FROM fuzzy_results
            )
            SELECT id, title, description, created_at, score, total_count
                     , tags
            FROM counted
            ORDER BY score DESC
            OFFSET :skip
            LIMIT :limit
        """)
        
        result = await db.execute(sql, {
            "query": query,
            "threshold": similarity_threshold,
            "start_date": start_date,
            "end_date": end_date,
            "skip": skip,
            "limit": limit,
            **tag_filter_params,
        })
        
        rows = result.fetchall()
        total_count = rows[0].total_count if rows else 0
        
        items = []
        for row in rows:
            snippet = row.description[:147] + "..." if row.description and len(row.description) > 150 else (row.description or "")
            items.append(SearchResultItem(
                entity_type=entity_type,
                entity_id=row.id,
                human_id=self._generate_human_id(entity_type, row.id),
                title=row.title or "",
                snippet=snippet,
                score=min(1.0, row.score),
                timeline_item_id=None,
                created_at=row.created_at,
                tags=row.tags or [],
            ))
        
        return items, total_count


# Singleton instance
search_service = SearchService()
