"""Unit tests for ID parsing utility."""

import pytest
from fastapi import HTTPException

from app.core.id_parser import parse_entity_id, format_entity_id


class TestParseEntityId:
    """Test parse_entity_id function."""
    
    def test_plain_integer_alert(self):
        """Test parsing plain integer for alert."""
        numeric_id, prefix = parse_entity_id("123", "alert")
        assert numeric_id == 123
        assert prefix == "ALT"
    
    def test_plain_integer_case(self):
        """Test parsing plain integer for case."""
        numeric_id, prefix = parse_entity_id("456", "case")
        assert numeric_id == 456
        assert prefix == "CAS"
    
    def test_plain_integer_task(self):
        """Test parsing plain integer for task."""
        numeric_id, prefix = parse_entity_id("789", "task")
        assert numeric_id == 789
        assert prefix == "TSK"
    
    def test_zero_padded(self):
        """Test parsing zero-padded integers."""
        numeric_id, prefix = parse_entity_id("000123", "alert")
        assert numeric_id == 123
        assert prefix == "ALT"
    
    def test_alt_prefix(self):
        """Test parsing ALT- prefix."""
        numeric_id, prefix = parse_entity_id("ALT-0000123", "alert")
        assert numeric_id == 123
        assert prefix == "ALT"
    
    def test_cas_prefix(self):
        """Test parsing CAS- prefix."""
        numeric_id, prefix = parse_entity_id("CAS-000456", "case")
        assert numeric_id == 456
        assert prefix == "CAS"
    
    def test_tsk_prefix(self):
        """Test parsing TSK- prefix."""
        numeric_id, prefix = parse_entity_id("TSK-000789", "task")
        assert numeric_id == 789
        assert prefix == "TSK"
    
    def test_case_insensitive_prefix(self):
        """Test that prefixes are case-insensitive."""
        numeric_id1, _ = parse_entity_id("alt-123", "alert")
        numeric_id2, _ = parse_entity_id("ALT-123", "alert")
        numeric_id3, _ = parse_entity_id("Alt-123", "alert")
        
        assert numeric_id1 == numeric_id2 == numeric_id3 == 123
    
    def test_whitespace_trimming(self):
        """Test that whitespace is trimmed."""
        numeric_id, prefix = parse_entity_id("  123  ", "alert")
        assert numeric_id == 123
        
        numeric_id, prefix = parse_entity_id("  ALT-123  ", "alert")
        assert numeric_id == 123
    
    def test_wrong_prefix_for_alert(self):
        """Test error when using case prefix for alert."""
        with pytest.raises(HTTPException) as exc_info:
            parse_entity_id("CAS-123", "alert")
        
        assert exc_info.value.status_code == 400
        assert "has case prefix but expected 'alert'" in exc_info.value.detail
    
    def test_wrong_prefix_for_case(self):
        """Test error when using alert prefix for case."""
        with pytest.raises(HTTPException) as exc_info:
            parse_entity_id("ALT-123", "case")
        
        assert exc_info.value.status_code == 400
        assert "has alert prefix but expected 'case'" in exc_info.value.detail
    
    def test_wrong_prefix_for_task(self):
        """Test error when using case prefix for task."""
        with pytest.raises(HTTPException) as exc_info:
            parse_entity_id("CAS-123", "task")
        
        assert exc_info.value.status_code == 400
        assert "has case prefix but expected 'task'" in exc_info.value.detail
    
    def test_invalid_format_letters(self):
        """Test error with invalid format containing letters."""
        with pytest.raises(HTTPException) as exc_info:
            parse_entity_id("abc", "alert")
        
        assert exc_info.value.status_code == 400
        assert "Invalid ID format" in exc_info.value.detail
    
    def test_invalid_format_special_chars(self):
        """Test error with invalid special characters."""
        with pytest.raises(HTTPException) as exc_info:
            parse_entity_id("123@456", "alert")
        
        assert exc_info.value.status_code == 400
        assert "Invalid ID format" in exc_info.value.detail
    
    def test_invalid_kind(self):
        """Test error with invalid entity kind."""
        with pytest.raises(HTTPException) as exc_info:
            parse_entity_id("123", "invalid_kind")
        
        assert exc_info.value.status_code == 400
        assert "Invalid entity kind" in exc_info.value.detail
    
    def test_helpful_error_message(self):
        """Test that error messages are helpful."""
        with pytest.raises(HTTPException) as exc_info:
            parse_entity_id("xyz", "alert")
        
        error_detail = exc_info.value.detail
        assert "Invalid ID format" in error_detail
        assert "ALT-" in error_detail  # Mentions expected format
        assert "123" in error_detail  # Shows example


class TestFormatEntityId:
    """Test format_entity_id function."""
    
    def test_format_alert(self):
        """Test formatting alert ID."""
        formatted = format_entity_id(123, "ALT")
        assert formatted == "ALT-0000123"
    
    def test_format_case(self):
        """Test formatting case ID."""
        formatted = format_entity_id(456, "CAS")
        assert formatted == "CAS-0000456"
    
    def test_format_task(self):
        """Test formatting task ID."""
        formatted = format_entity_id(789, "TSK")
        assert formatted == "TSK-0000789"
    
    def test_format_with_custom_padding(self):
        """Test formatting with custom padding."""
        formatted = format_entity_id(123, "ALT", padding=5)
        assert formatted == "ALT-00123"
    
    def test_format_large_number(self):
        """Test formatting number larger than padding."""
        formatted = format_entity_id(12345678, "ALT", padding=7)
        assert formatted == "ALT-12345678"
    
    def test_format_zero(self):
        """Test formatting zero."""
        formatted = format_entity_id(0, "ALT")
        assert formatted == "ALT-0000000"


class TestRoundTrip:
    """Test round-trip parsing and formatting."""
    
    def test_roundtrip_alert(self):
        """Test parse → format → parse for alert."""
        original = "ALT-0000123"
        numeric_id, prefix = parse_entity_id(original, "alert")
        formatted = format_entity_id(numeric_id, prefix)
        assert formatted == original
    
    def test_roundtrip_case(self):
        """Test parse → format → parse for case."""
        original = "CAS-0000456"
        numeric_id, prefix = parse_entity_id(original, "case")
        formatted = format_entity_id(numeric_id, prefix)
        assert formatted == original
    
    def test_roundtrip_plain_to_formatted(self):
        """Test plain number parses and formats correctly."""
        numeric_id, prefix = parse_entity_id("123", "alert")
        formatted = format_entity_id(numeric_id, prefix)
        assert formatted == "ALT-0000123"
