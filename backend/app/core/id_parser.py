"""Forgiving ID parsing utility for MCP tools.

Handles formats:
- Plain integers: "123"
- Zero-padded: "000123"
- Prefixed: "ALT-0000123", "CAS-000123", "TSK-000123"
"""

import re
from typing import Tuple
from fastapi import HTTPException


# Canonical entity prefixes
ALERT_PREFIX = "ALT"
CASE_PREFIX = "CAS"
TASK_PREFIX = "TSK"

# Mapping from entity kind to canonical prefix
KIND_TO_PREFIX = {
    "alert": ALERT_PREFIX,
    "case": CASE_PREFIX,
    "task": TASK_PREFIX,
}

# ID format patterns
PLAIN_INT_PATTERN = re.compile(r"^(\d+)$")
PREFIXED_ALERT_PATTERN = re.compile(rf"^{ALERT_PREFIX}-(\d+)$", re.IGNORECASE)
PREFIXED_CASE_PATTERN = re.compile(rf"^{CASE_PREFIX}-(\d+)$", re.IGNORECASE)
PREFIXED_TASK_PATTERN = re.compile(rf"^{TASK_PREFIX}-(\d+)$", re.IGNORECASE)


def parse_entity_id(raw: str, expected_kind: str) -> Tuple[int, str]:
    """Parse entity ID from various formats.
    
    Args:
        raw: Raw ID string (e.g., "123", "ALT-000123", "ALT-0000123")
        expected_kind: Expected entity type ("alert", "case", "task")
        
    Returns:
        Tuple of (numeric_id, canonical_prefix)
        - numeric_id: Integer ID
        - canonical_prefix: Canonical prefix ("ALT", "CAS", "TSK")
        
    Raises:
        HTTPException(400): If format is invalid or prefix doesn't match expected kind
        
    Examples:
        >>> parse_entity_id("123", "alert")
        (123, "ALT")
        >>> parse_entity_id("ALT-000123", "alert")
        (123, "ALT")
        >>> parse_entity_id("ALT-0000123", "alert")
        (123, "ALT")
        >>> parse_entity_id("CAS-000456", "case")
        (456, "CAS")
    """
    raw = raw.strip()
    
    if expected_kind not in KIND_TO_PREFIX:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity kind '{expected_kind}'. Must be one of: alert, case, task"
        )
    
    canonical_prefix = KIND_TO_PREFIX[expected_kind]
    
    # Try plain integer
    match = PLAIN_INT_PATTERN.match(raw)
    if match:
        numeric_id = int(match.group(1))
        return (numeric_id, canonical_prefix)
    
    # Try prefixed alert format (ALT-)
    match = PREFIXED_ALERT_PATTERN.match(raw)
    if match:
        if expected_kind != "alert":
            raise HTTPException(
                status_code=400,
                detail=f"ID '{raw}' has alert prefix but expected '{expected_kind}'"
            )
        numeric_id = int(match.group(1))
        return (numeric_id, canonical_prefix)
    
    # Try prefixed case format
    match = PREFIXED_CASE_PATTERN.match(raw)
    if match:
        if expected_kind != "case":
            raise HTTPException(
                status_code=400,
                detail=f"ID '{raw}' has case prefix but expected '{expected_kind}'"
            )
        numeric_id = int(match.group(1))
        return (numeric_id, canonical_prefix)
    
    # Try prefixed task format
    match = PREFIXED_TASK_PATTERN.match(raw)
    if match:
        if expected_kind != "task":
            raise HTTPException(
                status_code=400,
                detail=f"ID '{raw}' has task prefix but expected '{expected_kind}'"
            )
        numeric_id = int(match.group(1))
        return (numeric_id, canonical_prefix)
    
    # No match - provide helpful error
    raise HTTPException(
        status_code=400,
        detail=(
            f"Invalid ID format '{raw}' for {expected_kind}. "
            f"Expected formats: plain number (123), "
            f"zero-padded (000123), or prefixed ({canonical_prefix}-000123)"
        )
    )


def get_prefix_for_kind(kind: str) -> str:
    """Get the canonical prefix for an entity kind.
    
    Args:
        kind: Entity type ("alert", "case", "task")
        
    Returns:
        Canonical prefix ("ALT", "CAS", "TSK")
        
    Raises:
        ValueError: If kind is not recognized
    """
    if kind not in KIND_TO_PREFIX:
        raise ValueError(f"Unknown entity kind: {kind}")
    return KIND_TO_PREFIX[kind]


def format_entity_id(numeric_id: int, prefix: str, padding: int = 7) -> str:
    """Format entity ID in canonical form.
    
    Args:
        numeric_id: Numeric ID
        prefix: Prefix ("ALT", "CAS", "TSK")
        padding: Number of digits to pad to (default: 7)
        
    Returns:
        Formatted ID (e.g., "ALT-0000123", "CAS-0000456")
        
    Examples:
        >>> format_entity_id(123, "ALT")
        "ALT-0000123"
        >>> format_entity_id(456, "CAS", padding=5)
        "CAS-00456"
    """
    return f"{prefix}-{numeric_id:0{padding}d}"
