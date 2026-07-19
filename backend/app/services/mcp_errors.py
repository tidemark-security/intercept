"""Typed failures raised by MCP business logic.

Transport adapters translate these errors into protocol-specific responses.
"""


class McpServiceError(Exception):
    """Base class for failures safe to expose to an MCP client."""


class McpValidationError(McpServiceError):
    """The caller supplied an invalid tool argument."""


class McpNotFoundError(McpServiceError):
    """A requested entity or nested item does not exist."""


class McpConflictError(McpServiceError):
    """The requested operation conflicts with current state."""


class McpUnavailableError(McpServiceError):
    """A required local dependency is unavailable."""


class McpTimeoutError(McpServiceError):
    """A required local dependency exceeded its time limit."""
