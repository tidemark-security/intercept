"""MITRE ATT&CK API routes for technique/tactic/group/software lookups and search.

These endpoints provide:
- Search functionality for finding ATT&CK objects by name/ID/description
- Individual lookups by ATT&CK ID
- Bulk listing of techniques and tactics
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
import logging

from app.services.mitre_service import MitreService
from app.api.routes.admin_auth import require_authenticated_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/mitre",
    tags=["mitre"],
    dependencies=[Depends(require_authenticated_user)]
)

# Single service instance
_service = MitreService()


@router.get("/search")
async def search_attack_objects(
    q: str = Query(..., min_length=1, description="Search query (ID, name, or keyword)"),
    types: Optional[List[str]] = Query(
        None,
        description="Object types to search: technique, tactic, group, software, mitigation, campaign"
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum results to return")
):
    """Search MITRE ATT&CK objects by ID, name, or description.
    
    Returns matching techniques, tactics, groups, and software sorted by relevance:
    - Exact ID matches rank highest
    - Name matches rank higher than description matches
    
    Example queries:
    - "T1059" - find technique by ID
    - "PowerShell" - find techniques related to PowerShell
    - "credential" - find techniques involving credentials
    """
    try:
        results = _service.search(q, object_types=types, limit=limit)
        return {
            "query": q,
            "count": len(results),
            "results": results
        }
    except Exception as e:
        logger.error(f"Error searching MITRE ATT&CK: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/techniques")
async def list_techniques(
    limit: int = Query(100, ge=1, le=1000, description="Maximum techniques to return"),
    include_subtechniques: bool = Query(True, description="Include sub-techniques (e.g., T1059.001)")
):
    """List all MITRE ATT&CK techniques.
    
    Returns techniques sorted alphabetically by name.
    Each technique includes:
    - attack_id: The technique ID (e.g., T1059)
    - name: Human-readable name
    - tactics: Associated tactics
    - url: Link to MITRE ATT&CK page
    """
    try:
        techniques = _service.get_all_techniques(include_subtechniques=include_subtechniques)
        
        # Apply limit
        if limit and len(techniques) > limit:
            techniques = techniques[:limit]
        
        return {
            "count": len(techniques),
            "techniques": techniques
        }
    except Exception as e:
        logger.error(f"Error listing techniques: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list techniques: {str(e)}")


@router.get("/techniques/{attack_id}")
async def get_technique(attack_id: str):
    """Get a specific MITRE ATT&CK technique by ID.
    
    Supports both techniques (T1059) and sub-techniques (T1059.001).
    """
    result = _service.get_technique(attack_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Technique not found: {attack_id}"
        )
    return result


@router.get("/tactics")
async def list_tactics():
    """List all MITRE ATT&CK tactics.
    
    Returns all 14 tactics in the Enterprise ATT&CK matrix:
    - Reconnaissance (TA0043)
    - Resource Development (TA0042)
    - Initial Access (TA0001)
    - Execution (TA0002)
    - Persistence (TA0003)
    - Privilege Escalation (TA0004)
    - Defense Evasion (TA0005)
    - Credential Access (TA0006)
    - Discovery (TA0007)
    - Lateral Movement (TA0008)
    - Collection (TA0009)
    - Command and Control (TA0011)
    - Exfiltration (TA0010)
    - Impact (TA0040)
    """
    try:
        tactics = _service.get_all_tactics()
        return {
            "count": len(tactics),
            "tactics": tactics
        }
    except Exception as e:
        logger.error(f"Error listing tactics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list tactics: {str(e)}")


@router.get("/tactics/{attack_id}")
async def get_tactic(attack_id: str):
    """Get a specific MITRE ATT&CK tactic by ID."""
    result = _service.get_tactic(attack_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tactic not found: {attack_id}"
        )
    return result


@router.get("/groups/{attack_id}")
async def get_group(attack_id: str):
    """Get a specific MITRE ATT&CK threat group by ID.
    
    Group IDs start with 'G' (e.g., G0001 for Axiom).
    """
    result = _service.get_group(attack_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Group not found: {attack_id}"
        )
    return result


@router.get("/software/{attack_id}")
async def get_software(attack_id: str):
    """Get a specific MITRE ATT&CK software/tool by ID.
    
    Software IDs start with 'S' (e.g., S0002 for Mimikatz).
    """
    result = _service.get_software(attack_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Software not found: {attack_id}"
        )
    return result


@router.get("/lookup/{attack_id}")
async def lookup_attack_object(attack_id: str):
    """Look up any MITRE ATT&CK object by ID.
    
    Automatically detects the object type from the ID prefix:
    - T: Technique (e.g., T1059, T1059.001)
    - TA: Tactic (e.g., TA0001)
    - G: Group (e.g., G0001)
    - S: Software (e.g., S0002)
    - M: Mitigation (e.g., M1036)
    - C: Campaign (e.g., C0001)
    - DS: Data Source (e.g., DS0001)
    """
    result = _service.get_attack_object(attack_id)
    if result is None:
        # Check if ID format is valid but not found
        if _service.validate_attack_id(attack_id):
            raise HTTPException(
                status_code=404,
                detail=f"ATT&CK object not found: {attack_id}"
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid ATT&CK ID format: {attack_id}"
            )
    return result
