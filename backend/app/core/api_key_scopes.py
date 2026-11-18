"""API-key scope vocabulary and role ceilings."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from app.models.enums import UserRole


API_READ_SCOPE: Final = "api:read"
API_WRITE_SCOPE: Final = "api:write"
API_ADMIN_SCOPE: Final = "api:admin"
MCP_ACCESS_SCOPE: Final = "mcp:access"

ALL_API_KEY_SCOPES: Final[frozenset[str]] = frozenset(
    {
        API_READ_SCOPE,
        API_WRITE_SCOPE,
        API_ADMIN_SCOPE,
        MCP_ACCESS_SCOPE,
    }
)


def allowed_api_key_scopes(role: UserRole) -> frozenset[str]:
    """Return the maximum API-key scope set for an account role."""
    if role == UserRole.ADMIN:
        return ALL_API_KEY_SCOPES
    if role == UserRole.AUDITOR:
        return frozenset({API_READ_SCOPE, MCP_ACCESS_SCOPE})
    return frozenset({API_READ_SCOPE, API_WRITE_SCOPE, MCP_ACCESS_SCOPE})


def normalize_api_key_scopes(scopes: Iterable[str]) -> frozenset[str]:
    """Normalize caller-provided scope names without silently dropping values."""
    return frozenset(str(scope).strip().lower() for scope in scopes if str(scope).strip())


__all__ = [
    "ALL_API_KEY_SCOPES",
    "API_ADMIN_SCOPE",
    "API_READ_SCOPE",
    "API_WRITE_SCOPE",
    "MCP_ACCESS_SCOPE",
    "allowed_api_key_scopes",
    "normalize_api_key_scopes",
]
