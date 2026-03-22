"""
Validation API endpoints.

Exposes validation rules for dynamic frontend consumption.
Rules are fetched once and cached by clients (1h TTL recommended).
"""
from fastapi import APIRouter

from app.core.validation import get_all_rules


router = APIRouter(
    prefix="/validation",
    tags=["validation"],
)


@router.get("/rules")
async def get_validation_rules():
    """
    Get all validation rules.
    
    Returns a flat dictionary of validation rules keyed by rule identifier
    (e.g., "observable.IP", "network.src_port"). Each rule includes:
    - key: Rule identifier
    - label: Human-readable label
    - pattern: Regex pattern (if applicable)
    - allowed_values: List of valid values (if applicable, e.g., for enums)
    - examples: Example valid values
    - error_message: Error message to display on validation failure
    
    Clients should cache this response (recommended TTL: 1 hour).
    """
    return {
        "rules": get_all_rules()
    }
