"""Unit tests for search service fuzzy matching functionality.

These tests verify the query construction and logic for fuzzy matching,
without requiring a full database setup.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.search_schemas import EntityType
from app.services.search_service import (
    QueryType,
    SearchDateRangeValidationError,
    SearchService,
    classify_query,
    resolve_search_date_range,
)


def _make_mock_db() -> AsyncMock:
    return AsyncMock()


def _search_row(**overrides) -> SimpleNamespace:
    values = {
        "id": 1,
        "title": "Phishing Alert",
        "description": "This is a phishing attack",
        "tags": [],
        "timeline_items": {},
        "created_at": datetime.now(timezone.utc),
        "updated_at": None,
        "priority": None,
        "status": None,
        "assignee": None,
        "score": 0.45,
        "snippet": "This is a <mark>phishing</mark> attack",
        "total_count": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TestQueryClassification:
    """Tests for query classification including human IDs."""
    
    def test_classify_case_id_uppercase(self):
        """Case IDs like CAS-000001 should be classified as HUMAN_ID."""
        result = classify_query("CAS-000001")
        assert result.query_type == QueryType.HUMAN_ID
        assert result.human_id_entity_type == "case"
        assert result.human_id_numeric == 1
    
    def test_classify_case_id_lowercase(self):
        """Case IDs are case-insensitive."""
        result = classify_query("cas-123")
        assert result.query_type == QueryType.HUMAN_ID
        assert result.human_id_entity_type == "case"
        assert result.human_id_numeric == 123
    
    def test_classify_alert_id(self):
        """Alert IDs like ALT-0000001 should be classified as HUMAN_ID."""
        result = classify_query("ALT-42")
        assert result.query_type == QueryType.HUMAN_ID
        assert result.human_id_entity_type == "alert"
        assert result.human_id_numeric == 42
    
    def test_classify_task_id(self):
        """Task IDs like TSK-0000001 should be classified as HUMAN_ID."""
        result = classify_query("TSK-9999999")
        assert result.query_type == QueryType.HUMAN_ID
        assert result.human_id_entity_type == "task"
        assert result.human_id_numeric == 9999999
    
    def test_classify_human_id_mixed_case(self):
        """Human IDs with mixed case should work."""
        result = classify_query("Alt-12345")
        assert result.query_type == QueryType.HUMAN_ID
        assert result.human_id_entity_type == "alert"
        assert result.human_id_numeric == 12345
    
    def test_classify_human_id_normalizes_uppercase(self):
        """Human ID normalized value should be uppercase."""
        result = classify_query("cas-1")
        assert result.normalized_value == "CAS-1"
    
    def test_classify_ip_not_human_id(self):
        """IP addresses should not be classified as HUMAN_ID."""
        result = classify_query("192.168.1.1")
        assert result.query_type == QueryType.IP
    
    def test_classify_generic_text_not_human_id(self):
        """Generic text should not be classified as HUMAN_ID."""
        result = classify_query("phishing attack")
        assert result.query_type == QueryType.GENERIC
    
    def test_classify_invalid_prefix_not_human_id(self):
        """Invalid prefixes should not be classified as HUMAN_ID."""
        result = classify_query("FOO-123")
        assert result.query_type == QueryType.GENERIC

    @pytest.mark.parametrize("query", ["ALT-42*", "42*"])
    def test_wildcard_ids_are_not_treated_as_exact_ids(self, query):
        """A wildcard query must not bypass content-search semantics."""
        result = classify_query(query)

        assert result.query_type not in {QueryType.HUMAN_ID, QueryType.NUMERIC_ID}


class TestNumericIdClassification:
    """Tests for plain numeric ID classification."""
    
    def test_classify_single_digit_as_numeric_id(self):
        """Single digit should be classified as NUMERIC_ID."""
        result = classify_query("1")
        assert result.query_type == QueryType.NUMERIC_ID
        assert result.numeric_id == 1
    
    def test_classify_multi_digit_as_numeric_id(self):
        """Multi-digit number should be classified as NUMERIC_ID."""
        result = classify_query("12345")
        assert result.query_type == QueryType.NUMERIC_ID
        assert result.numeric_id == 12345
    
    def test_classify_large_number_as_numeric_id(self):
        """Large numbers within range should be classified as NUMERIC_ID."""
        result = classify_query("999999999")
        assert result.query_type == QueryType.NUMERIC_ID
        assert result.numeric_id == 999999999
    
    def test_classify_zero_as_generic(self):
        """Zero should not be classified as NUMERIC_ID (invalid entity ID)."""
        result = classify_query("0")
        assert result.query_type == QueryType.GENERIC
    
    def test_classify_number_with_leading_zeros(self):
        """Numbers with leading zeros should still be classified as NUMERIC_ID."""
        result = classify_query("007")
        assert result.query_type == QueryType.NUMERIC_ID
        assert result.numeric_id == 7
    
    def test_classify_number_with_spaces_as_generic(self):
        """Numbers with spaces should be classified as GENERIC."""
        result = classify_query("123 456")
        assert result.query_type == QueryType.GENERIC
    
    def test_classify_ip_not_numeric_id(self):
        """IP addresses should not be classified as NUMERIC_ID."""
        result = classify_query("192.168.1.1")
        assert result.query_type == QueryType.IP
    
    def test_classify_human_id_preferred_over_numeric(self):
        """Human IDs (CAS-123) should be preferred over plain numeric ID."""
        result = classify_query("CAS-123")
        assert result.query_type == QueryType.HUMAN_ID
        assert result.human_id_entity_type == "case"


class TestSearchDateRange:
    def test_end_only_range_is_resolved_relative_to_requested_end(self):
        end = datetime(2020, 1, 31, tzinfo=timezone.utc)

        start, resolved_end = resolve_search_date_range(None, end)

        assert start == end - timedelta(days=30)
        assert resolved_end == end

    @pytest.mark.parametrize(
        ("start", "end", "message"),
        [
            (
                datetime(2025, 1, 2, tzinfo=timezone.utc),
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                "Start date must be before end date",
            ),
            (
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
                "Date range cannot exceed 1 year",
            ),
        ],
    )
    def test_invalid_resolved_range_is_rejected(self, start, end, message):
        with pytest.raises(SearchDateRangeValidationError, match=message):
            resolve_search_date_range(start, end)


class TestSearchServiceHumanId:
    """Tests for human ID generation."""
    
    def test_generate_human_id_alert(self):
        """Alert IDs should have ALT- prefix with zero-padded 7-digit number."""
        service = SearchService()
        assert service._generate_human_id(EntityType.ALERT, 123) == "ALT-0000123"
        assert service._generate_human_id(EntityType.ALERT, 1) == "ALT-0000001"
        assert service._generate_human_id(EntityType.ALERT, 9999999) == "ALT-9999999"
    
    def test_generate_human_id_case(self):
        """Case IDs should have CAS- prefix with zero-padded 7-digit number."""
        service = SearchService()
        assert service._generate_human_id(EntityType.CASE, 456) == "CAS-0000456"
    
    def test_generate_human_id_task(self):
        """Task IDs should have TSK- prefix with zero-padded 7-digit number."""
        service = SearchService()
        assert service._generate_human_id(EntityType.TASK, 789) == "TSK-0000789"


class TestSearchServiceFuzzyFallback:
    """Tests for fuzzy search fallback behavior."""
    
    @pytest.mark.asyncio
    async def test_global_search_uses_fuzzy_fallback_when_no_fulltext_results(self):
        """When full-text search returns no results, fuzzy search should be used."""
        service = SearchService()
        mock_db = _make_mock_db()
        
        # Create empty result for fulltext search
        fulltext_result = MagicMock()
        fulltext_result.fetchall.return_value = []
        
        # Create fuzzy result with one match
        fuzzy_result = MagicMock()
        fuzzy_row = _search_row()
        fuzzy_result.fetchall.return_value = [fuzzy_row]
        
        # Mock execute to return empty fulltext, then fuzzy results
        call_count = 0
        async def mock_execute(sql, params=None):
            nonlocal call_count
            call_count += 1
            # First call is fulltext for ALERT type only
            # Second call is fuzzy search fallback
            if call_count == 1:
                return fulltext_result
            return fuzzy_result
        
        mock_db.execute = mock_execute
        
        # Execute search with typo "phising" for just ALERT type
        response = await service.paginated_search(
            db=mock_db,
            query="phising",  # typo of "phishing"
            entity_types=[EntityType.ALERT],
            limit=5,
        )
        
        # Should have called fulltext (1 for alert) then fuzzy search (1 call)
        assert call_count >= 2, f"Fuzzy search should have been called after fulltext, got {call_count} calls"
        # Note: The actual fuzzy results depend on database state
    
    @pytest.mark.asyncio
    async def test_global_search_skips_fuzzy_when_fulltext_has_results(self):
        """When full-text search has results, fuzzy should not be called."""
        service = SearchService()
        mock_db = _make_mock_db()
        
        # Create fulltext result with matches
        fulltext_result = MagicMock()
        fulltext_row = _search_row(score=0.8)
        fulltext_result.fetchall.return_value = [fulltext_row]
        
        call_count = 0
        async def mock_execute(sql, params=None):
            nonlocal call_count
            call_count += 1
            return fulltext_result
        
        mock_db.execute = mock_execute
        
        # Execute search with exact term
        response = await service.paginated_search(
            db=mock_db,
            query="phishing",  # exact match
            entity_types=[EntityType.ALERT],
            limit=5,
        )
        
        # Should only have called fulltext search (1 call per entity type)
        # Since we're filtering to just alerts, should be exactly 1 call
        assert call_count == 1, "Only fulltext search should have been called"
        assert response.total == 1


class TestSearchServiceQueryConstruction:
    """Tests for fuzzy matching query construction."""
    
    @pytest.mark.asyncio
    async def test_fuzzy_search_uses_similarity_function(self):
        """Fuzzy search should use pg_trgm similarity function."""
        service = SearchService()
        mock_db = _make_mock_db()
        
        # Create empty result
        empty_result = MagicMock()
        empty_result.fetchall.return_value = []
        
        executed_sql = []
        async def mock_execute(sql, params=None):
            executed_sql.append(str(sql))
            return empty_result
        
        mock_db.execute = mock_execute
        
        now = datetime.now(timezone.utc)
        await service._fuzzy_search_entity_candidates(
            db=mock_db,
            table_name="alerts",
            entity_type=EntityType.ALERT,
            query="test",
            start_date=now - timedelta(days=30),
            end_date=now,
            candidate_limit=5,
            similarity_threshold=0.3,
        )
        
        # Verify the SQL uses similarity function
        assert len(executed_sql) > 0
        # The SQL should contain similarity function calls
        sql_text = executed_sql[0]
        assert "similarity" in sql_text.lower()

    @pytest.mark.asyncio
    async def test_fuzzy_search_sql_projects_timeline_items_before_selecting_it(self):
        """Fuzzy fallback must include timeline_items in its CTE when tag metadata is requested."""
        service = SearchService()
        mock_db = _make_mock_db()

        empty_result = MagicMock()
        empty_result.fetchall.return_value = []

        executed_sql = []
        async def mock_execute(sql, params=None):
            executed_sql.append(str(sql))
            return empty_result

        mock_db.execute = mock_execute

        await service._fuzzy_search_entity_candidates(
            db=mock_db,
            table_name="cases",
            entity_type=EntityType.CASE,
            query="credentialz",
            start_date=datetime.now(timezone.utc) - timedelta(days=1),
            end_date=datetime.now(timezone.utc),
            candidate_limit=20,
            normalized_tags=["credentials"],
        )

        sql_text = executed_sql[0]
        assert "assignee,\n                    timeline_items,\n                    GREATEST" in sql_text
        assert ", tags, timeline_items" in sql_text


class TestSearchServiceEntityTypes:
    """Tests for entity type filtering."""
    
    @pytest.mark.asyncio
    async def test_search_filters_by_entity_types(self):
        """Search should only query specified entity types."""
        service = SearchService()
        mock_db = _make_mock_db()
        
        empty_result = MagicMock()
        empty_result.fetchall.return_value = []
        
        tables_queried = []
        async def mock_execute(sql, params=None):
            sql_str = str(sql)
            if 'FROM alerts' in sql_str:
                tables_queried.append('alerts')
            if 'FROM cases' in sql_str:
                tables_queried.append('cases')
            if 'FROM tasks' in sql_str:
                tables_queried.append('tasks')
            return empty_result
        
        mock_db.execute = mock_execute
        
        # Search only alerts and cases
        await service.paginated_search(
            db=mock_db,
            query="test",
            entity_types=[EntityType.ALERT, EntityType.CASE],
            limit=5,
        )
        
        assert 'alerts' in tables_queried
        assert 'cases' in tables_queried
        assert 'tasks' not in tables_queried

    @pytest.mark.asyncio
    async def test_paginated_search_deduplicates_repeated_entity_types(self):
        service = SearchService()
        service._search_entity_candidates = AsyncMock(return_value=([], 1))

        response = await service.paginated_search(
            db=_make_mock_db(),
            query="test",
            entity_types=[EntityType.ALERT, EntityType.ALERT],
        )

        assert service._search_entity_candidates.await_count == 1
        assert response.entity_types == [EntityType.ALERT]


class TestSearchServiceResultMetadata:
    """Tests for search result display metadata used by frontend rows."""

    @pytest.mark.asyncio
    async def test_paginated_alert_search_includes_assignee_metadata(self):
        """Alert search rows should carry the same assignee metadata as alert detail."""
        service = SearchService()
        mock_db = _make_mock_db()
        created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        updated_at = datetime.now(timezone.utc)

        result = MagicMock()
        result.fetchall.return_value = [
            SimpleNamespace(
                id=42,
                title="Suspicious login",
                description="Suspicious login from an unusual location",
                tags=["identity"],
                created_at=created_at,
                updated_at=updated_at,
                priority="HIGH",
                status="IN_PROGRESS",
                assignee="analyst1",
                score=0.0,
                total_count=1,
                snippet="Suspicious login",
            )
        ]
        mock_db.execute.return_value = result

        items, total = await service._search_entity_candidates(
            db=mock_db,
            table_name="alerts",
            entity_type=EntityType.ALERT,
            query="*",
            start_date=created_at - timedelta(days=1),
            end_date=updated_at + timedelta(days=1),
            candidate_limit=20,
        )

        assert total == 1
        assert len(items) == 1
        assert items[0].assignee == "analyst1"
        assert items[0].status == "IN_PROGRESS"
        assert items[0].priority == "HIGH"
        assert items[0].updated_at == updated_at


class TestSearchServiceTagFilters:
    """Tests for tag filter normalization and SQL generation."""

    def test_normalize_tag_filters_trims_and_deduplicates(self):
        service = SearchService()

        normalized = service._normalize_tag_filters([
            "  SOCI Reportable  ",
            "soci reportable",
            "VIP",
            "",
            "   ",
            "vip",
        ])

        assert normalized == ["SOCI Reportable", "VIP"]

    def test_build_tag_filter_sql_empty(self):
        service = SearchService()

        sql, params = service._build_tag_filter_sql([])

        assert sql == ""
        assert params == {}

    def test_build_tag_filter_sql_uses_or_patterns(self):
        service = SearchService()

        sql, params = service._build_tag_filter_sql(["SOCI", "VIP"])

        assert "tag ILIKE :tag_pattern_0" in sql
        assert "tag ILIKE :tag_pattern_1" in sql
        assert "timeline_tag ILIKE :tag_pattern_0" in sql
        assert "timeline_tag ILIKE :tag_pattern_1" in sql
        assert params["tag_pattern_0"] == "%SOCI%"
        assert params["tag_pattern_1"] == "%VIP%"

    def test_tag_filter_treats_sql_wildcards_as_literal_text(self):
        service = SearchService()

        sql, params = service._build_tag_filter_sql([r"100%_done\later"])

        assert "ESCAPE '\\'" in sql
        assert params["tag_pattern_0"] == r"%100\%\_done\\later%"

    def test_timeline_wildcard_escapes_sql_wildcards(self):
        service = SearchService()

        sql, params = service._build_timeline_match_sql(
            classify_query("100%_done*")
        )

        assert "ESCAPE '\\'" in sql
        assert params["timeline_pattern"] == r"%100\%\_done%%"

    def test_build_tag_matches_includes_entity_tag_matches(self):
        service = SearchService()

        matches = service._build_tag_matches(
            entity_tags=["customer-data", "credentials"],
            timeline_items={},
            filters=["cred"],
        )

        assert len(matches) == 1
        assert matches[0].source == "entity"
        assert matches[0].tag == "credentials"
        assert matches[0].filter == "cred"
        assert matches[0].timeline_item_id is None

    def test_build_tag_matches_includes_timeline_tag_context(self):
        service = SearchService()

        matches = service._build_tag_matches(
            entity_tags=["malware"],
            timeline_items={
                "note-1": {
                    "id": "note-1",
                    "type": "note",
                    "description": "Credential harvesting observed",
                    "tags": ["credentials"],
                }
            },
            filters=["credentials"],
        )

        assert len(matches) == 1
        assert matches[0].source == "timeline"
        assert matches[0].tag == "credentials"
        assert matches[0].filter == "credentials"
        assert matches[0].timeline_item_id == "note-1"
        assert matches[0].timeline_item_type == "note"
        assert matches[0].timeline_item_label == "Credential harvesting observed"

    def test_build_tag_matches_deduplicates_by_source_tag_filter_and_timeline_item(self):
        service = SearchService()

        matches = service._build_tag_matches(
            entity_tags=["credentials", "Credentials"],
            timeline_items=[
                {"id": "note-1", "type": "note", "description": "First", "tags": ["credentials", "Credentials"]},
                {"id": "note-2", "type": "note", "description": "Second", "tags": ["credentials"]},
            ],
            filters=["credentials", "Credentials"],
        )

        assert [(match.source, match.tag, match.filter, match.timeline_item_id) for match in matches] == [
            ("entity", "credentials", "credentials", None),
            ("timeline", "credentials", "credentials", "note-1"),
            ("timeline", "credentials", "credentials", "note-2"),
        ]

    def test_build_tag_matches_uses_case_insensitive_substring_semantics(self):
        service = SearchService()

        matches = service._build_tag_matches(
            entity_tags=["stolen-CREDENTIALS"],
            timeline_items={},
            filters=["cred"],
        )

        assert len(matches) == 1
        assert matches[0].tag == "stolen-CREDENTIALS"

    def test_result_mapping_tolerates_malformed_legacy_tags(self):
        service = SearchService()
        row = _search_row(tags="not-a-list", timeline_items="not-a-container")

        result = service._result_from_row(
            row,
            EntityType.ALERT,
            snippet="Alert",
            score=0.5,
            normalized_tags=["alert"],
        )

        assert result.tags == []
        assert result.tag_matches == []

    def test_result_mapping_drops_non_string_tag_entries(self):
        service = SearchService()
        row = _search_row(tags=["valid", 7, None])

        result = service._result_from_row(
            row,
            EntityType.ALERT,
            snippet="Alert",
            score=0.5,
            normalized_tags=["valid"],
        )

        assert result.tags == ["valid"]
        assert [match.tag for match in result.tag_matches] == ["valid"]


class TestSearchServiceExactIdFilters:
    @pytest.mark.asyncio
    async def test_exact_id_lookup_applies_date_and_tag_filters(self):
        service = SearchService()
        db = _make_mock_db()
        query_result = MagicMock()
        query_result.fetchone.return_value = None
        db.execute.return_value = query_result
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        result = await service._lookup_exact_id(
            db,
            entity_type=EntityType.ALERT,
            entity_id=42,
            start_date=start,
            end_date=end,
            normalized_tags=["100%"],
        )

        assert result is None
        sql, params = db.execute.await_args.args
        sql_text = str(sql)
        assert "created_at >= :start_date" in sql_text
        assert "created_at <= :end_date" in sql_text
        assert "tag ILIKE :tag_pattern_0" in sql_text
        assert params == {
            "entity_id": 42,
            "start_date": start,
            "end_date": end,
            "tag_pattern_0": r"%100\%%",
        }

    @pytest.mark.asyncio
    async def test_exact_id_lookup_projects_timeline_items_for_tag_context(self):
        service = SearchService()
        db = _make_mock_db()
        query_result = MagicMock()
        query_result.fetchone.return_value = _search_row(
            tags=[],
            timeline_items={
                "note-1": {
                    "id": "note-1",
                    "type": "note",
                    "tags": ["credentials"],
                }
            },
        )
        db.execute.return_value = query_result
        end = datetime.now(timezone.utc)

        result = await service._lookup_exact_id(
            db,
            entity_type=EntityType.ALERT,
            entity_id=1,
            start_date=end - timedelta(days=1),
            end_date=end,
            normalized_tags=["credentials"],
        )

        assert result is not None
        assert result.tag_matches[0].timeline_item_id == "note-1"
        sql, _ = db.execute.await_args.args
        assert "timeline_items" in str(sql)
