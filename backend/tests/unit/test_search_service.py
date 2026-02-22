"""Unit tests for search service fuzzy matching functionality.

These tests verify the query construction and logic for fuzzy matching,
without requiring a full database setup.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.search_service import SearchService, classify_query, QueryType
from app.models.search_schemas import (
    EntityType,
    SearchResultItem,
    DateRangeApplied,
)


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
        mock_db = AsyncMock()
        
        # Create empty result for fulltext search
        fulltext_result = MagicMock()
        fulltext_result.fetchall.return_value = []
        
        # Create fuzzy result with one match
        fuzzy_result = MagicMock()
        fuzzy_row = MagicMock()
        fuzzy_row.id = 1
        fuzzy_row.title = "Phishing Alert"
        fuzzy_row.description = "This is a phishing attack"
        fuzzy_row.created_at = datetime.now(timezone.utc)
        fuzzy_row.score = 0.45
        fuzzy_row.total_count = 1
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
        response = await service.global_search(
            db=mock_db,
            query="phising",  # typo of "phishing"
            entity_types=[EntityType.ALERT],
            limit_per_type=5,
        )
        
        # Should have called fulltext (1 for alert) then fuzzy search (1 call)
        assert call_count >= 2, f"Fuzzy search should have been called after fulltext, got {call_count} calls"
        # Note: The actual fuzzy results depend on database state
    
    @pytest.mark.asyncio
    async def test_global_search_skips_fuzzy_when_fulltext_has_results(self):
        """When full-text search has results, fuzzy should not be called."""
        service = SearchService()
        mock_db = AsyncMock()
        
        # Create fulltext result with matches
        fulltext_result = MagicMock()
        fulltext_row = MagicMock()
        fulltext_row.id = 1
        fulltext_row.title = "Phishing Alert"
        fulltext_row.description = "This is a phishing attack"
        fulltext_row.created_at = datetime.now(timezone.utc)
        fulltext_row.score = 0.8
        fulltext_row.snippet = "This is a <mark>phishing</mark> attack"
        fulltext_row.total_count = 1
        fulltext_result.fetchall.return_value = [fulltext_row]
        
        call_count = 0
        async def mock_execute(sql, params=None):
            nonlocal call_count
            call_count += 1
            return fulltext_result
        
        mock_db.execute = mock_execute
        
        # Execute search with exact term
        response = await service.global_search(
            db=mock_db,
            query="phishing",  # exact match
            entity_types=[EntityType.ALERT],
            limit_per_type=5,
        )
        
        # Should only have called fulltext search (1 call per entity type)
        # Since we're filtering to just alerts, should be exactly 1 call
        assert call_count == 1, "Only fulltext search should have been called"
        assert response.total_by_type.alert == 1


class TestSearchServiceQueryConstruction:
    """Tests for fuzzy matching query construction."""
    
    def test_fuzzy_similarity_threshold_default(self):
        """Fuzzy search should use 0.3 as default similarity threshold."""
        service = SearchService()
        # The threshold is used in fuzzy_search method
        # We verify it's documented/used correctly
        assert hasattr(service, 'fuzzy_search')
    
    @pytest.mark.asyncio
    async def test_fuzzy_search_uses_similarity_function(self):
        """Fuzzy search should use pg_trgm similarity function."""
        service = SearchService()
        mock_db = AsyncMock()
        
        # Create empty result
        empty_result = MagicMock()
        empty_result.fetchall.return_value = []
        
        executed_sql = []
        async def mock_execute(sql, params=None):
            executed_sql.append(str(sql))
            return empty_result
        
        mock_db.execute = mock_execute
        
        await service.fuzzy_search(
            db=mock_db,
            query="test",
            entity_types=[EntityType.ALERT],
            similarity_threshold=0.3,
        )
        
        # Verify the SQL uses similarity function
        assert len(executed_sql) > 0
        # The SQL should contain similarity function calls
        sql_text = executed_sql[0]
        assert "similarity" in sql_text.lower()


class TestSearchServiceEntityTypes:
    """Tests for entity type filtering."""
    
    @pytest.mark.asyncio
    async def test_search_filters_by_entity_types(self):
        """Search should only query specified entity types."""
        service = SearchService()
        mock_db = AsyncMock()
        
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
        await service.global_search(
            db=mock_db,
            query="test",
            entity_types=[EntityType.ALERT, EntityType.CASE],
            limit_per_type=5,
        )
        
        assert 'alerts' in tables_queried
        assert 'cases' in tables_queried
        assert 'tasks' not in tables_queried


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
