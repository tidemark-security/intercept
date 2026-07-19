"""Forgiving ID parsing utility for MCP tools.

Handles formats for any kind registered in ``app.core.entity_ids``:
- Plain integers: "123"
- Zero-padded: "000123"
- Prefixed: "ALT-0000123", "CAS-000123", "TSK-000123"
"""

import re
from typing import Tuple

from app.core.entity_ids import (
    KIND_TO_PREFIX,
    PREFIX_TO_KIND,
)

# ID format patterns
PLAIN_INT_PATTERN = re.compile(r"^(\d+)$")
PREFIXED_ID_PATTERN = re.compile(
    rf"^({'|'.join(map(re.escape, PREFIX_TO_KIND))})-(\d+)$",
    re.IGNORECASE,
)


class EntityIdParseError(ValueError):
    """Raised when an entity ID cannot be parsed for the expected kind."""


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
        EntityIdParseError: If format is invalid or prefix doesn't match expected kind
        
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
        supported_kinds = ", ".join(KIND_TO_PREFIX)
        raise EntityIdParseError(
            f"Invalid entity kind '{expected_kind}'. Must be one of: {supported_kinds}"
        )
    
    canonical_prefix = KIND_TO_PREFIX[expected_kind]
    
    # Try plain integer
    match = PLAIN_INT_PATTERN.match(raw)
    if match:
        numeric_id = int(match.group(1))
        return (numeric_id, canonical_prefix)
    
    # Try a known prefixed format.
    match = PREFIXED_ID_PATTERN.match(raw)
    if match:
        supplied_prefix = match.group(1).upper()
        supplied_kind = PREFIX_TO_KIND[supplied_prefix]
        if expected_kind != supplied_kind:
            raise EntityIdParseError(
                f"ID '{raw}' has {supplied_kind} prefix but expected '{expected_kind}'"
            )
        numeric_id = int(match.group(2))
        return (numeric_id, canonical_prefix)
    
    # No match - provide helpful error
    raise EntityIdParseError(
        f"Invalid ID format '{raw}' for {expected_kind}. "
        f"Expected formats: plain number (123), "
        f"zero-padded (000123), or prefixed ({canonical_prefix}-000123)"
    )
