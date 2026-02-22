"""Unit tests for TTP (MITRE ATT&CK) timeline item normalization."""

import pytest
from app.services.normalization_service import normalization_service


class TestTTPNormalization:
    """Test TTP timeline item normalization (stripping denormalized fields)."""
    
    def test_normalize_strips_denormalized_fields(self):
        """Test that normalization strips ATT&CK-sourced fields."""
        item = {
            "type": "ttp",
            "mitre_id": "T1059",
            "title": "Command and Scripting Interpreter",
            "tactic": "Execution",
            "technique": "Command and Scripting Interpreter",
            "url": "https://attack.mitre.org/techniques/T1059",
            "description": "Adversary used PowerShell to run commands",
            "flagged": True,
        }
        
        normalized = normalization_service._normalize_ttp(item)
        
        # mitre_id should be preserved
        assert normalized["mitre_id"] == "T1059"
        # type should be preserved
        assert normalized["type"] == "ttp"
        # description should be preserved (user-provided)
        assert normalized["description"] == "Adversary used PowerShell to run commands"
        # flagged should be preserved
        assert normalized["flagged"] is True
        
        # ATT&CK-sourced fields should be stripped
        assert "title" not in normalized
        assert "tactic" not in normalized
        assert "technique" not in normalized
        assert "url" not in normalized
    
    def test_normalize_uppercases_mitre_id(self):
        """Test that mitre_id is normalized to uppercase."""
        item = {
            "type": "ttp",
            "mitre_id": "t1059.001",
        }
        
        normalized = normalization_service._normalize_ttp(item)
        
        assert normalized["mitre_id"] == "T1059.001"
    
    def test_normalize_strips_whitespace_from_mitre_id(self):
        """Test that whitespace is stripped from mitre_id."""
        item = {
            "type": "ttp",
            "mitre_id": "  T1059  ",
        }
        
        normalized = normalization_service._normalize_ttp(item)
        
        assert normalized["mitre_id"] == "T1059"
    
    def test_normalize_preserves_base_timeline_fields(self):
        """Test that base timeline item fields are preserved."""
        item = {
            "type": "ttp",
            "mitre_id": "T1059",
            "id": "item-123",
            "created_at": "2024-01-01T00:00:00Z",
            "created_by": "analyst1",
            "flagged": True,
            "highlighted": False,
            "tags": ["lateral-movement", "powershell"],
        }
        
        normalized = normalization_service._normalize_ttp(item)
        
        assert normalized["id"] == "item-123"
        assert normalized["created_at"] == "2024-01-01T00:00:00Z"
        assert normalized["created_by"] == "analyst1"
        assert normalized["flagged"] is True
        assert normalized["highlighted"] is False
        assert normalized["tags"] == ["lateral-movement", "powershell"]


class TestTTPDenormalization:
    """Test TTP timeline item denormalization (populating from ATT&CK database)."""
    
    def test_denormalize_populates_technique_fields(self):
        """Test that denormalization populates technique details."""
        item = {
            "type": "ttp",
            "mitre_id": "T1059",
            "description": "Adversary used command interpreter",
        }
        
        denormalized = normalization_service._denormalize_ttp(item)
        
        assert denormalized["title"] == "Command and Scripting Interpreter"
        assert denormalized["url"] == "https://attack.mitre.org/techniques/T1059"
        assert denormalized["object_type"] == "technique"
        assert "Execution" in denormalized["tactics"]
        assert denormalized["tactic"] == "Execution"
        # User-provided description should be preserved
        assert denormalized["description"] == "Adversary used command interpreter"
    
    def test_denormalize_populates_subtechnique_fields(self):
        """Test that denormalization handles sub-techniques correctly."""
        item = {
            "type": "ttp",
            "mitre_id": "T1059.001",
        }
        
        denormalized = normalization_service._denormalize_ttp(item)
        
        assert denormalized["title"] == "PowerShell"
        assert denormalized["is_subtechnique"] is True
        assert denormalized["parent_technique"] == "T1059"
        assert "001" in denormalized["url"]
    
    def test_denormalize_populates_tactic_fields(self):
        """Test that denormalization populates tactic details."""
        item = {
            "type": "ttp",
            "mitre_id": "TA0001",
        }
        
        denormalized = normalization_service._denormalize_ttp(item)
        
        assert denormalized["title"] == "Initial Access"
        assert denormalized["object_type"] == "tactic"
        assert denormalized["url"] == "https://attack.mitre.org/tactics/TA0001"
    
    def test_denormalize_populates_group_fields(self):
        """Test that denormalization populates group details."""
        item = {
            "type": "ttp",
            "mitre_id": "G0001",
        }
        
        denormalized = normalization_service._denormalize_ttp(item)
        
        assert denormalized["title"] == "Axiom"
        assert denormalized["object_type"] == "group"
        assert "aliases" in denormalized
    
    def test_denormalize_handles_missing_mitre_id(self):
        """Test that denormalization handles missing mitre_id gracefully."""
        item = {
            "type": "ttp",
            "description": "Some TTP without mitre_id",
        }
        
        denormalized = normalization_service._denormalize_ttp(item)
        
        # Should return item unchanged
        assert denormalized["type"] == "ttp"
        assert denormalized["description"] == "Some TTP without mitre_id"
        assert "title" not in denormalized
    
    def test_denormalize_handles_invalid_mitre_id(self):
        """Test that denormalization handles invalid mitre_id gracefully."""
        item = {
            "type": "ttp",
            "mitre_id": "INVALID",
        }
        
        denormalized = normalization_service._denormalize_ttp(item)
        
        # Should return item unchanged (not found in ATT&CK database)
        assert denormalized["mitre_id"] == "INVALID"
        assert "title" not in denormalized
    
    def test_denormalize_preserves_user_fields(self):
        """Test that user-provided fields are preserved during denormalization."""
        item = {
            "type": "ttp",
            "mitre_id": "T1059",
            "id": "item-123",
            "description": "Custom analyst notes about this technique",
            "flagged": True,
            "tags": ["important"],
        }
        
        denormalized = normalization_service._denormalize_ttp(item)
        
        # User fields should be preserved
        assert denormalized["id"] == "item-123"
        assert denormalized["description"] == "Custom analyst notes about this technique"
        assert denormalized["flagged"] is True
        assert denormalized["tags"] == ["important"]
        # ATT&CK fields should be populated
        assert denormalized["title"] == "Command and Scripting Interpreter"


class TestNormalizeDenormalizeRoundTrip:
    """Test that normalize -> denormalize produces expected results."""
    
    def test_roundtrip_preserves_reference_and_user_data(self):
        """Test that round-trip through normalize/denormalize works correctly."""
        original = {
            "type": "ttp",
            "mitre_id": "T1059.001",
            "title": "PowerShell",  # Will be stripped then repopulated
            "tactic": "Execution",  # Will be stripped then repopulated
            "description": "Attacker used PowerShell for C2",
            "flagged": True,
        }
        
        # Normalize (strip ATT&CK fields)
        normalized = normalization_service._normalize_ttp(original)
        assert "title" not in normalized
        assert "tactic" not in normalized
        assert normalized["mitre_id"] == "T1059.001"
        assert normalized["description"] == "Attacker used PowerShell for C2"
        
        # Denormalize (repopulate from ATT&CK database)
        denormalized = normalization_service._denormalize_ttp(normalized)
        assert denormalized["title"] == "PowerShell"
        assert denormalized["tactic"] == "Execution"
        assert denormalized["mitre_id"] == "T1059.001"
        assert denormalized["description"] == "Attacker used PowerShell for C2"
        assert denormalized["flagged"] is True
