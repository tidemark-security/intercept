"""Unit tests for the MITRE ATT&CK service."""

import pytest
from app.services.mitre_service import mitre_service, MitreService


class TestMitreServiceLookups:
    """Test MITRE ATT&CK object lookups."""
    
    def test_get_technique_by_id(self):
        """Test looking up a technique by ATT&CK ID."""
        result = mitre_service.get_attack_object("T1059")
        assert result is not None
        assert result["attack_id"] == "T1059"
        assert result["name"] == "Command and Scripting Interpreter"
        assert result["object_type"] == "technique"
        assert "Execution" in result["tactics"]
        assert result["url"] == "https://attack.mitre.org/techniques/T1059"
    
    def test_get_subtechnique_by_id(self):
        """Test looking up a sub-technique by ATT&CK ID."""
        result = mitre_service.get_attack_object("T1059.001")
        assert result is not None
        assert result["attack_id"] == "T1059.001"
        assert result["name"] == "PowerShell"
        assert result["object_type"] == "technique"
        assert result["is_subtechnique"] is True
        assert result["parent_technique"] == "T1059"
        assert result["url"] == "https://attack.mitre.org/techniques/T1059/001"
    
    def test_get_tactic_by_id(self):
        """Test looking up a tactic by ATT&CK ID."""
        result = mitre_service.get_attack_object("TA0001")
        assert result is not None
        assert result["attack_id"] == "TA0001"
        assert result["name"] == "Initial Access"
        assert result["object_type"] == "tactic"
        assert result["url"] == "https://attack.mitre.org/tactics/TA0001"
    
    def test_get_group_by_id(self):
        """Test looking up a threat group by ATT&CK ID."""
        result = mitre_service.get_attack_object("G0001")
        assert result is not None
        assert result["attack_id"] == "G0001"
        assert result["name"] == "Axiom"
        assert result["object_type"] == "group"
        assert "aliases" in result
        assert result["url"] == "https://attack.mitre.org/groups/G0001"
    
    def test_get_software_by_id(self):
        """Test looking up software by ATT&CK ID."""
        result = mitre_service.get_attack_object("S0001")
        assert result is not None
        assert result["attack_id"] == "S0001"
        assert result["object_type"] == "software"
        assert "software_type" in result
        assert result["url"] == "https://attack.mitre.org/software/S0001"
    
    def test_lowercase_id_is_normalized(self):
        """Test that lowercase ATT&CK IDs are normalized."""
        result = mitre_service.get_attack_object("t1059")
        assert result is not None
        assert result["attack_id"] == "T1059"
    
    def test_nonexistent_id_returns_none(self):
        """Test that nonexistent ATT&CK IDs return None."""
        result = mitre_service.get_attack_object("T9999")
        assert result is None
    
    def test_invalid_id_format_returns_none(self):
        """Test that invalid ATT&CK ID formats return None."""
        result = mitre_service.get_attack_object("INVALID")
        assert result is None
    
    def test_validate_attack_id(self):
        """Test ATT&CK ID validation."""
        assert mitre_service.validate_attack_id("T1059") is True
        assert mitre_service.validate_attack_id("T9999") is False


class TestMitreServiceCaching:
    """Test caching behavior of the MITRE service."""
    
    def test_cached_lookup_returns_same_result(self):
        """Test that cached lookups return consistent results."""
        result1 = mitre_service.get_attack_object_cached("T1059")
        result2 = mitre_service.get_attack_object_cached("T1059")
        assert result1 == result2
    
    def test_cache_handles_nonexistent_ids(self):
        """Test that cache correctly handles nonexistent IDs."""
        result1 = mitre_service.get_attack_object_cached("T9999")
        result2 = mitre_service.get_attack_object_cached("T9999")
        assert result1 is None
        assert result2 is None


class TestConvenienceMethods:
    """Test convenience methods for specific object types."""
    
    def test_get_technique_convenience(self):
        """Test get_technique convenience method."""
        result = mitre_service.get_technique("T1059")
        assert result is not None
        assert result["object_type"] == "technique"
    
    def test_get_technique_rejects_non_technique(self):
        """Test get_technique rejects non-technique IDs."""
        result = mitre_service.get_technique("G0001")
        assert result is None
    
    def test_get_tactic_convenience(self):
        """Test get_tactic convenience method."""
        result = mitre_service.get_tactic("TA0001")
        assert result is not None
        assert result["object_type"] == "tactic"
    
    def test_get_group_convenience(self):
        """Test get_group convenience method."""
        result = mitre_service.get_group("G0001")
        assert result is not None
        assert result["object_type"] == "group"
    
    def test_get_software_convenience(self):
        """Test get_software convenience method."""
        result = mitre_service.get_software("S0001")
        assert result is not None
        assert result["object_type"] == "software"
