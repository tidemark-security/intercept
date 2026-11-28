"""MITRE ATT&CK data service for dynamic technique/tactic/group lookups.

This service loads the MITRE ATT&CK STIX bundle once at startup and provides
efficient lookups by ATT&CK ID (e.g., T1059, TA0001, G0001, S0001).

Timeline items of type 'ttp' store only the mitre_id reference; this service
populates the full details (name, description, tactics, url, etc.) on read.
"""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from mitreattack.stix20 import MitreAttackData

logger = logging.getLogger(__name__)

# Lazy-loaded MitreAttackData instance
_mitre_data: Optional[MitreAttackData] = None


class MitreDataUnavailableError(RuntimeError):
    """Raised when the configured ATT&CK bundle cannot be loaded."""


def _get_stix_path() -> Path:
    """Get the path to the MITRE ATT&CK STIX bundle.
    
    Checks in order:
    1. MITRE_ATTACK_STIX_PATH from app settings
    2. MITRE_ATTACK_STIX_PATH environment variable (fallback)
    3. Default location relative to this file's models directory
    """
    # Try to get from settings registry first
    try:
        from app.core.settings_registry import get_local
        stix_path = get_local("mitre.attack_stix_path")
        if stix_path:
            return Path(stix_path)
    except (ImportError, KeyError):
        pass
    
    # Fallback to environment variable
    env_path = os.environ.get("MITRE_ATTACK_STIX_PATH")
    if env_path:
        return Path(env_path)
    
    # Default to the models directory
    return Path(__file__).parent.parent / "models" / "enterprise-attack-18.1.json"


def _load_mitre_data() -> "MitreAttackData":
    """Load the MITRE ATT&CK data from the STIX bundle.
    
    Raises:
        MitreDataUnavailableError: If the bundle or its parser is unavailable.
    """
    global _mitre_data
    if _mitre_data is not None:
        return _mitre_data
    
    stix_path = _get_stix_path()
    if not stix_path.exists():
        logger.warning("MITRE ATT&CK STIX file not found: %s", stix_path)
        raise MitreDataUnavailableError("MITRE ATT&CK data file is unavailable")

    try:
        from mitreattack.stix20 import MitreAttackData
        from stix2.exceptions import STIXError
    except ImportError as exc:
        logger.warning("MITRE ATT&CK parser is not installed")
        raise MitreDataUnavailableError("MITRE ATT&CK parser is unavailable") from exc

    try:
        _mitre_data = MitreAttackData(stix_filepath=str(stix_path))
        logger.info("Loaded MITRE ATT&CK data from %s", stix_path)
        return _mitre_data
    except (OSError, JSONDecodeError, STIXError, KeyError, TypeError) as exc:
        logger.exception("Failed to load MITRE ATT&CK data from %s", stix_path)
        raise MitreDataUnavailableError("MITRE ATT&CK data could not be loaded") from exc


# STIX type mappings for ATT&CK ID prefixes
ATTACK_ID_STIX_TYPES = {
    "T": "attack-pattern",  # Technique/Sub-technique
    "TA": "x-mitre-tactic",  # Tactic
    "G": "intrusion-set",  # Group (threat actor)
    "S": "tool",  # Software (malware/tool) - note: also check "malware" type
    "M": "course-of-action",  # Mitigation
    "DS": "x-mitre-data-source",  # Data Source
    "C": "campaign",  # Campaign
}

ATTACK_ID_PATTERN = re.compile(
    r"^(?:T\d{4}(?:\.\d{3})?|TA\d{4}|G\d{4}|S\d{4}|M\d{4}|DS\d{4}|C\d{4})$",
    re.IGNORECASE,
)

SEARCH_OBJECT_TYPE_TO_STIX = {
    "technique": "attack-pattern",
    "tactic": "x-mitre-tactic",
    "group": "intrusion-set",
    "software": None,
    "mitigation": "course-of-action",
    "campaign": "campaign",
}
DIRECT_RESULT_TYPE_TO_STIX = {
    "technique": "attack-pattern",
    "tactic": "x-mitre-tactic",
    "group": "intrusion-set",
    "software": "tool",
    "mitigation": "course-of-action",
    "campaign": "campaign",
}
SEARCHABLE_ATTACK_ID_PREFIXES = ("T", "TA", "G", "S", "M", "C", "DS")


def _get_stix_type_for_attack_id(attack_id: str) -> Optional[str]:
    """Determine the STIX type for a given ATT&CK ID.
    
    ATT&CK IDs follow patterns like:
    - T1059, T1059.001 (Technique, Sub-technique)
    - TA0001 (Tactic)
    - G0001 (Group)
    - S0001 (Software)
    - M1001 (Mitigation)
    - DS0001 (Data Source)
    - C0001 (Campaign)
    """
    attack_id = attack_id.upper().strip()
    
    # Check for two-letter prefixes first (TA, DS)
    if attack_id.startswith("TA"):
        return ATTACK_ID_STIX_TYPES["TA"]
    if attack_id.startswith("DS"):
        return ATTACK_ID_STIX_TYPES["DS"]
    
    # Single-letter prefixes
    first_char = attack_id[0] if attack_id else ""
    return ATTACK_ID_STIX_TYPES.get(first_char)


class MitreService:
    """Service for looking up MITRE ATT&CK objects by ATT&CK ID."""
    
    @staticmethod
    def get_attack_object(attack_id: str) -> Optional[Dict[str, Any]]:
        """Look up an ATT&CK object by its ID (e.g., T1059, TA0001, G0001).
        
        Returns a dict with common fields:
        - attack_id: The ATT&CK ID
        - name: Object name
        - description: Object description
        - url: MITRE ATT&CK page URL
        - stix_id: The internal STIX ID
        - object_type: The type of object (technique, tactic, group, etc.)
        
        For techniques, also includes:
        - tactics: List of tactic names this technique belongs to
        - is_subtechnique: Whether this is a sub-technique
        - parent_technique: ATT&CK ID of parent technique (for sub-techniques)
        
        Returns None if the object is not found.
        """
        mitre_data = _load_mitre_data()

        attack_id = attack_id.upper().strip()
        if not MitreService.is_attack_id_format(attack_id):
            logger.warning("Unknown ATT&CK ID format: %s", attack_id)
            return None
        stix_type = _get_stix_type_for_attack_id(attack_id)
        if stix_type is None:  # pragma: no cover - pattern and prefix map are kept in sync
            return None
        
        # Special handling for software - it may be represented as a tool or malware.
        if stix_type == "tool":
            obj = mitre_data.get_object_by_attack_id(attack_id, "tool")
            if obj is None:
                obj = mitre_data.get_object_by_attack_id(attack_id, "malware")
        else:
            obj = mitre_data.get_object_by_attack_id(attack_id, stix_type)

        if obj is None:
            return None

        return MitreService._format_attack_object(mitre_data, obj, attack_id)
    
    @staticmethod
    def _format_attack_object(
        mitre_data: "MitreAttackData",
        obj: Any,
        attack_id: str
    ) -> Dict[str, Any]:
        """Format a STIX object into a standardized dict for API responses."""
        # Get common fields using the library's helper
        name = mitre_data.get_field(obj, "name")
        description = mitre_data.get_field(obj, "description")
        stix_id = obj.id if hasattr(obj, "id") else obj.get("id")
        stix_type = mitre_data.get_stix_type(stix_id)
        
        # Build MITRE ATT&CK URL
        url = MitreService._build_attack_url(attack_id, stix_type)
        
        result = {
            "attack_id": attack_id,
            "name": name,
            "description": description,
            "url": url,
            "stix_id": stix_id,
            "object_type": MitreService._get_friendly_type(stix_type),
        }
        
        # Add technique-specific fields
        if stix_type == "attack-pattern":
            result.update(MitreService._get_technique_details(mitre_data, obj, attack_id))
        
        # Add group-specific fields
        elif stix_type == "intrusion-set":
            result.update(MitreService._get_group_details(mitre_data, obj))
        
        # Add software-specific fields
        elif stix_type in ("tool", "malware"):
            result.update(MitreService._get_software_details(mitre_data, obj))
        
        return result
    
    @staticmethod
    def _build_attack_url(attack_id: str, stix_type: str) -> str:
        """Build the MITRE ATT&CK website URL for an object."""
        base_url = "https://attack.mitre.org"
        attack_id_lower = attack_id.lower()
        
        if stix_type == "attack-pattern":
            # Techniques: /techniques/T1059 or /techniques/T1059/001
            if "." in attack_id:
                # Sub-technique
                parts = attack_id.split(".")
                return f"{base_url}/techniques/{parts[0].upper()}/{parts[1]}"
            return f"{base_url}/techniques/{attack_id.upper()}"
        
        elif stix_type == "x-mitre-tactic":
            # Tactics: /tactics/TA0001
            return f"{base_url}/tactics/{attack_id.upper()}"
        
        elif stix_type == "intrusion-set":
            # Groups: /groups/G0001
            return f"{base_url}/groups/{attack_id.upper()}"
        
        elif stix_type in ("tool", "malware"):
            # Software: /software/S0001
            return f"{base_url}/software/{attack_id.upper()}"
        
        elif stix_type == "course-of-action":
            # Mitigations: /mitigations/M1001
            return f"{base_url}/mitigations/{attack_id.upper()}"
        
        elif stix_type == "campaign":
            # Campaigns: /campaigns/C0001
            return f"{base_url}/campaigns/{attack_id.upper()}"
        
        elif stix_type == "x-mitre-data-source":
            # Data Sources: /datasources/DS0001
            return f"{base_url}/datasources/{attack_id.upper()}"
        
        return base_url
    
    @staticmethod
    def _get_friendly_type(stix_type: str) -> str:
        """Convert STIX type to user-friendly type name."""
        type_map = {
            "attack-pattern": "technique",
            "x-mitre-tactic": "tactic",
            "intrusion-set": "group",
            "tool": "software",
            "malware": "software",
            "course-of-action": "mitigation",
            "campaign": "campaign",
            "x-mitre-data-source": "data_source",
        }
        return type_map.get(stix_type, stix_type)
    
    @staticmethod
    def _get_technique_details(
        mitre_data: "MitreAttackData",
        obj: Any,
        attack_id: str
    ) -> Dict[str, Any]:
        """Get technique-specific details."""
        stix_id = obj.id if hasattr(obj, "id") else obj.get("id")
        
        # Get tactics this technique belongs to
        tactic_objs = mitre_data.get_tactics_by_technique(stix_id)
        tactics = [t.name for t in tactic_objs] if tactic_objs else []
        
        # Check if this is a sub-technique
        is_subtechnique = "." in attack_id
        parent_technique = None
        if is_subtechnique:
            parent_technique = attack_id.split(".")[0]
        
        return {
            "tactics": tactics,
            "is_subtechnique": is_subtechnique,
            "parent_technique": parent_technique,
        }
    
    @staticmethod
    def _get_group_details(mitre_data: "MitreAttackData", obj: Any) -> Dict[str, Any]:
        """Get threat group-specific details."""
        aliases = mitre_data.get_field(obj, "aliases") or []
        return {
            "aliases": aliases,
        }
    
    @staticmethod
    def _get_software_details(mitre_data: "MitreAttackData", obj: Any) -> Dict[str, Any]:
        """Get software-specific details."""
        stix_type = obj.type if hasattr(obj, "type") else obj.get("type")
        aliases = mitre_data.get_field(obj, "x_mitre_aliases") or []
        return {
            "software_type": "malware" if stix_type == "malware" else "tool",
            "aliases": aliases,
        }
    
    @staticmethod
    def get_technique(attack_id: str) -> Optional[Dict[str, Any]]:
        """Convenience method to get a technique by ID (T1059, T1059.001)."""
        if not attack_id.upper().startswith("T"):
            return None
        return MitreService.get_attack_object(attack_id)
    
    @staticmethod
    def get_tactic(attack_id: str) -> Optional[Dict[str, Any]]:
        """Convenience method to get a tactic by ID (TA0001)."""
        if not attack_id.upper().startswith("TA"):
            return None
        return MitreService.get_attack_object(attack_id)
    
    @staticmethod
    def get_group(attack_id: str) -> Optional[Dict[str, Any]]:
        """Convenience method to get a threat group by ID (G0001)."""
        if not attack_id.upper().startswith("G"):
            return None
        return MitreService.get_attack_object(attack_id)
    
    @staticmethod
    def get_software(attack_id: str) -> Optional[Dict[str, Any]]:
        """Convenience method to get software by ID (S0001)."""
        if not attack_id.upper().startswith("S"):
            return None
        return MitreService.get_attack_object(attack_id)
    
    @staticmethod
    def is_attack_id_format(attack_id: str) -> bool:
        """Return whether a value has a supported ATT&CK external-ID format."""
        return bool(ATTACK_ID_PATTERN.fullmatch(attack_id.strip()))
    
    @staticmethod
    @lru_cache(maxsize=1000)
    def get_attack_object_cached(attack_id: str) -> Optional[Dict[str, Any]]:
        """Cached version of get_attack_object for high-frequency lookups.
        
        Use this in hot paths like timeline denormalization where the same
        techniques may be looked up repeatedly.
        """
        return MitreService.get_attack_object(attack_id)

    @staticmethod
    def _search_stix_types(object_types: Optional[List[str]]) -> List[str]:
        if not object_types:
            return ["attack-pattern"]
        stix_types: List[str] = []
        for object_type in object_types:
            if object_type == "software":
                stix_types.extend(("tool", "malware"))
            elif mapped_type := SEARCH_OBJECT_TYPE_TO_STIX.get(object_type):
                stix_types.append(mapped_type)
        return list(dict.fromkeys(stix_types))

    @staticmethod
    def _objects_for_search_type(
        mitre_data: "MitreAttackData",
        stix_type: str,
    ) -> List[Any]:
        if stix_type == "attack-pattern":
            return mitre_data.get_techniques(remove_revoked_deprecated=True)
        if stix_type == "x-mitre-tactic":
            return mitre_data.get_tactics(remove_revoked_deprecated=True)
        if stix_type == "intrusion-set":
            return mitre_data.get_groups(remove_revoked_deprecated=True)
        if stix_type in ("tool", "malware"):
            return [
                obj
                for obj in mitre_data.get_software(remove_revoked_deprecated=True)
                if obj.get("type") == stix_type
            ]
        if stix_type == "course-of-action":
            return mitre_data.get_mitigations(remove_revoked_deprecated=True)
        if stix_type == "campaign":
            return mitre_data.get_campaigns(remove_revoked_deprecated=True)
        return []

    @staticmethod
    def _search_match_score(
        *,
        query_upper: str,
        query_lower: str,
        attack_id: str,
        name: str,
    ) -> int:
        name_lower = name.lower()
        if attack_id.upper().startswith(query_upper) and len(query_upper) >= 2:
            return 90
        if name_lower == query_lower:
            return 80
        if name_lower.startswith(query_lower):
            return 70
        if query_lower in name_lower:
            return 60
        return 0

    @staticmethod
    def _add_search_result(
        mitre_data: "MitreAttackData",
        results_by_id: Dict[str, Dict[str, Any]],
        obj: Any,
        stix_type: str,
        score: int,
    ) -> None:
        stix_id = obj.get("id") if isinstance(obj, dict) else getattr(obj, "id", "")
        if not stix_id:
            return
        attack_id = mitre_data.get_attack_id(str(stix_id)) or ""
        if not attack_id:
            return
        existing = results_by_id.get(attack_id)
        if existing and existing["_score"] >= score:
            return
        results_by_id[attack_id] = {
            "attack_id": attack_id,
            "name": mitre_data.get_field(obj, "name") or "",
            "object_type": MitreService._get_friendly_type(stix_type),
            "_score": score,
        }
    
    @staticmethod
    def search(
        query: str,
        object_types: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search for ATT&CK objects by name, ID, or description content.
        
        Uses a hybrid approach:
        - Matches against ATT&CK ID (e.g., "T1059")
        - Matches against object name (e.g., "PowerShell")
        - Uses get_objects_by_content for description search (e.g., "LSASS")
        
        Args:
            query: Search string (matches against name, ID, and description)
            object_types: Optional filter by object type(s): 
                         "technique", "tactic", "group", "software", "mitigation", "campaign"
            limit: Maximum number of results to return
        
        Returns:
            List of matching ATT&CK objects with basic info (id, name, type)
        """
        mitre_data = _load_mitre_data()

        query_upper = query.upper().strip()
        query_lower = query.lower().strip()
        
        if not query_lower:
            return []
        
        stix_types_to_search = MitreService._search_stix_types(object_types)
        results_by_id: Dict[str, Dict[str, Any]] = {}

        # Strategy 1: Direct ATT&CK ID match (highest priority)
        if query_upper.startswith(SEARCHABLE_ATTACK_ID_PREFIXES):
            direct_obj = MitreService.get_attack_object(query_upper)
            if direct_obj:
                obj_type = direct_obj.get("object_type", "technique")
                stix_type = DIRECT_RESULT_TYPE_TO_STIX.get(
                    obj_type,
                    "attack-pattern",
                )

                # Check if this type is in our search filter
                if not stix_types_to_search or stix_type in stix_types_to_search:
                    results_by_id[direct_obj["attack_id"]] = {
                        "attack_id": direct_obj["attack_id"],
                        "name": direct_obj["name"],
                        "object_type": obj_type,
                        "_score": 100,  # Exact ID match
                    }
            
        # Strategy 2: Search by name first (higher priority than content)
        for stix_type in stix_types_to_search:
            for obj in MitreService._objects_for_search_type(mitre_data, stix_type):
                name = mitre_data.get_field(obj, "name") or ""
                stix_id = obj.get("id") if isinstance(obj, dict) else getattr(obj, "id", "")
                if not stix_id:
                    continue
                attack_id = mitre_data.get_attack_id(str(stix_id)) or ""
                score = MitreService._search_match_score(
                    query_upper=query_upper,
                    query_lower=query_lower,
                    attack_id=attack_id,
                    name=name,
                )
                if score > 0:
                    MitreService._add_search_result(
                        mitre_data,
                        results_by_id,
                        obj,
                        stix_type,
                        score,
                    )

        # Strategy 3: Search by description content (lower priority)
        for stix_type in stix_types_to_search:
            content_matches = mitre_data.get_objects_by_content(
                query_lower,
                stix_type,
                remove_revoked_deprecated=True,
            )
            for obj in content_matches:
                MitreService._add_search_result(
                    mitre_data,
                    results_by_id,
                    obj,
                    stix_type,
                    40,
                )

            # Early exit if we have enough results
            if len(results_by_id) >= limit * 2:
                break

        # Convert to list and sort by score (descending), then by name
        results = list(results_by_id.values())
        results.sort(key=lambda x: (-x["_score"], x["name"]))

        # Remove score from output and limit results
        for result in results:
            result.pop("_score", None)

        return results[:limit]
    
    @staticmethod
    def get_all_techniques(include_subtechniques: bool = True) -> List[Dict[str, Any]]:
        """Get all techniques for dropdown/autocomplete lists.
        
        Returns a simplified list with attack_id, name, and tactic info.
        """
        mitre_data = _load_mitre_data()

        techniques = mitre_data.get_techniques(
            include_subtechniques=include_subtechniques,
            remove_revoked_deprecated=True,
        )

        results = []
        for tech in techniques:
            stix_id = tech.get("id") if isinstance(tech, dict) else getattr(tech, "id", "")
            if not stix_id:
                continue
            stix_id_str = str(stix_id)
            attack_id = mitre_data.get_attack_id(stix_id_str) or ""
            name = mitre_data.get_field(tech, "name") or ""

            tactic_objs = mitre_data.get_tactics_by_technique(stix_id_str)
            tactics = [t.name for t in tactic_objs] if tactic_objs else []
            is_subtechnique = "." in attack_id

            results.append({
                "attack_id": attack_id,
                "name": name,
                "tactics": tactics,
                "is_subtechnique": is_subtechnique,
                "parent_technique": attack_id.split(".")[0] if is_subtechnique else None,
            })

        results.sort(key=lambda x: x["attack_id"])
        return results
    
    @staticmethod
    def get_all_tactics() -> List[Dict[str, Any]]:
        """Get all tactics for dropdown lists."""
        mitre_data = _load_mitre_data()

        tactics = mitre_data.get_tactics(remove_revoked_deprecated=True)

        results = []
        for tactic in tactics:
            stix_id = tactic.get("id") if isinstance(tactic, dict) else getattr(tactic, "id", "")
            attack_id = mitre_data.get_attack_id(stix_id) or ""
            name = mitre_data.get_field(tactic, "name") or ""
            shortname = mitre_data.get_field(tactic, "x_mitre_shortname") or ""

            results.append({
                "attack_id": attack_id,
                "name": name,
                "shortname": shortname,
            })

        results.sort(key=lambda x: x["attack_id"])
        return results


# Singleton instance for convenience
mitre_service = MitreService()
