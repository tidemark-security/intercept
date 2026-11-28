"""Unit tests for the MITRE ATT&CK service."""

from pathlib import Path

import pytest

from app.services import mitre_service as mitre_module
from app.services.mitre_service import (
    MitreDataUnavailableError,
    MitreService,
    mitre_service,
)


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
    
    @pytest.mark.parametrize(
        "attack_id",
        ["T1059", "T1059.001", "TA0001", "G0001", "S0001", "M1036", "DS0001", "C0001"],
    )
    def test_attack_id_format_accepts_supported_external_ids(self, attack_id):
        assert mitre_service.is_attack_id_format(attack_id) is True

    @pytest.mark.parametrize("attack_id", ["T999", "T1059.01", "TA001", "INVALID", "T1059 extra"])
    def test_attack_id_format_rejects_malformed_external_ids(self, attack_id):
        assert mitre_service.is_attack_id_format(attack_id) is False


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


class TestMitreSearchHelpers:
    def test_search_types_expand_software_and_preserve_order(self):
        assert MitreService._search_stix_types(
            ["group", "software", "group", "unknown"]
        ) == ["intrusion-set", "tool", "malware"]

    @pytest.mark.parametrize(
        ("query", "attack_id", "name", "expected"),
        [
            ("T1059", "T1059.001", "PowerShell", 90),
            ("powershell", "T1059.001", "PowerShell", 80),
            ("power", "T1059.001", "PowerShell", 70),
            ("shell", "T1059.001", "PowerShell", 60),
            ("unrelated", "T1059.001", "PowerShell", 0),
        ],
    )
    def test_search_match_score_encodes_search_precedence(
        self,
        query,
        attack_id,
        name,
        expected,
    ):
        assert MitreService._search_match_score(
            query_upper=query.upper(),
            query_lower=query.lower(),
            attack_id=attack_id,
            name=name,
        ) == expected

    def test_add_search_result_skips_objects_without_external_id(self):
        class MissingExternalIdData:
            @staticmethod
            def get_attack_id(_stix_id):
                return None

        results = {}

        MitreService._add_search_result(
            MissingExternalIdData(),
            results,
            {"id": "attack-pattern--without-external-id"},
            "attack-pattern",
            60,
        )

        assert results == {}


def test_missing_bundle_has_explicit_unavailable_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mitre_module, "_mitre_data", None)
    monkeypatch.setattr(
        mitre_module,
        "_get_stix_path",
        lambda: tmp_path / "missing.json",
    )

    with pytest.raises(MitreDataUnavailableError, match="file is unavailable"):
        MitreService.get_attack_object("T1059")


def test_lookup_does_not_hide_unexpected_parser_defects(monkeypatch) -> None:
    class BrokenMitreData:
        def get_object_by_attack_id(self, *_args):
            raise RuntimeError("programming defect")

    monkeypatch.setattr(mitre_module, "_mitre_data", BrokenMitreData())

    with pytest.raises(RuntimeError, match="programming defect"):
        MitreService.get_attack_object("T1059")
