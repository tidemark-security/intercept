"""MCP server with an explicit, intentionally limited tool interface."""

from collections.abc import Awaitable
from typing import Any, Callable, TypeVar

from fastapi import HTTPException
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AuthProvider
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from mcp import McpError
from mcp.types import ErrorData

from app.mcp.tools import (
    get_summary_tool,
    list_work_tool,
    find_related_tool,
    search_case_runbooks_tool,
    get_case_runbook_tool,
    record_triage_decision_tool,
    add_timeline_item_tool,
    get_item_tool,
    validate_mermaid_tool,
)
from app.core.database import async_session_factory
from app.mcp.principal import MCPPrincipalMiddleware


_GET_ITEM_OLD_CONTRACT_MESSAGE = (
    'get_item changed: use parent_entity_type and parent_entity_id instead of '
    'hint_kind and hint_parent_id. Example: parent_entity_type="case", '
    'parent_entity_id="CAS-000001".'
)
_GET_ITEM_MIXED_CONTRACT_MESSAGE = (
    "get_item changed: remove hint_kind and hint_parent_id. Keep "
    "parent_entity_type and parent_entity_id so the server only searches one "
    "alert, case, or task."
)
_GET_ITEM_MISSING_SCOPE_MESSAGE = (
    "get_item now requires the parent entity scope. Send parent_entity_type "
    "plus parent_entity_id so the server only searches one alert, case, or task."
)
_ToolResult = TypeVar("_ToolResult")


async def _run_tool(awaitable: Awaitable[_ToolResult]) -> _ToolResult:
    """Expose only explicitly curated FastAPI errors through the MCP boundary."""
    try:
        return await awaitable
    except HTTPException as exc:
        message = exc.detail if isinstance(exc.detail, str) else "Tool request rejected"
        raise ToolError(message) from exc


class GetItemContractGuidanceMiddleware(Middleware):
    """Give MCP clients repairable get_item contract errors before validation."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        if context.message.name != "get_item":
            return await call_next(context)

        arguments = context.message.arguments or {}
        old_fields = {"hint_kind", "hint_parent_id"} & arguments.keys()
        has_parent_scope = bool(arguments.get("parent_entity_type")) and bool(
            arguments.get("parent_entity_id")
        )

        if old_fields and has_parent_scope:
            raise McpError(
                ErrorData(code=-32602, message=_GET_ITEM_MIXED_CONTRACT_MESSAGE)
            )
        if old_fields:
            raise McpError(
                ErrorData(code=-32602, message=_GET_ITEM_OLD_CONTRACT_MESSAGE)
            )
        if not has_parent_scope:
            raise McpError(
                ErrorData(code=-32602, message=_GET_ITEM_MISSING_SCOPE_MESSAGE)
            )

        return await call_next(context)


# Keep unexpected implementation, database, and transport details out of MCP
# protocol errors. Intentional client-facing failures become ToolError values.
mcp = FastMCP("Tidemark Intercept MCP", mask_error_details=True)
mcp.add_middleware(GetItemContractGuidanceMiddleware())


# Register tools explicitly.

@mcp.tool(annotations={"readOnlyHint": True})
async def get_summary(
    kind: str,
    id: str,
    max_timeline_items: int = 25,
    max_observables: int = 20,
    since: str | None = None,
) -> dict:
    """Get bounded context summary for an alert, case, or task.
    
    Returns:
        - header: Object metadata (title, status, priority, etc.)
        - timeline: Bounded timeline items (max 25 by default)
        - observables: Deduplicated IOCs extracted from timeline
        - related_counts: Counts of linked/similar items
        - resources: Links to web UI
        
    Args:
        kind: Entity type ("alert", "case", "task")
        id: Entity ID (forgiving format: "123", "ALT-000123", etc.)
        max_timeline_items: Max timeline items to return (1-50, default: 25)
        max_observables: Max observables to extract (1-50, default: 20)
        since: ISO-8601 timestamp for incremental refresh (optional)
    """
    return await _run_tool(
        get_summary_tool(kind, id, max_timeline_items, max_observables, since)
    )


@mcp.tool(annotations={"readOnlyHint": True})
async def list_work(
    kind: str,
    statuses: list[str] | None = None,
    priorities: list[str] | None = None,
    assignees: list[str] | None = None,
    contains: str | None = None,
    time_range_start: str | None = None,
    time_range_end: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> dict:
    """List and filter alerts, cases, or tasks.
    
    Returns:
        - items: List of work items (bounded to limit)
        - next_cursor: Pagination cursor (null if no more)
        - total_count: Total matching items (may be higher than returned)
        
    Args:
        kind: Entity type ("alert", "case", "task")
        statuses: Filter by status. Valid values depend on kind:
            - alert: NEW, IN_PROGRESS, ESCALATED, CLOSED_TP, CLOSED_BP, CLOSED_FP, CLOSED_UNRESOLVED, CLOSED_DUPLICATE
                     (shorthand "CLOSED" expands to all CLOSED_* statuses)
            - case: NEW, IN_PROGRESS, CLOSED
            - task: TODO, IN_PROGRESS, DONE
        priorities: Filter by priority. Valid values (all kinds): INFO, LOW, MEDIUM, HIGH, CRITICAL, EXTREME
        assignees: Filter by assignee usernames
        contains: Search in title + description only (NOT timeline notes)
        time_range_start: Filter by created_at >= (ISO-8601, default: 7 days ago)
        time_range_end: Filter by created_at <= (ISO-8601)
        limit: Max items to return (1-50, default: 50)
        cursor: Pagination cursor from previous response
    """
    return await _run_tool(
        list_work_tool(
            kind,
            statuses,
            priorities,
            assignees,
            contains,
            time_range_start,
            time_range_end,
            limit,
            cursor,
        )
    )


@mcp.tool(annotations={"readOnlyHint": True})
async def find_related(
    seed_kind: str,
    seed_id: str,
    max_matches: int = 10,
) -> dict:
    """Find similar/related alerts, cases, or tasks.
    
    Returns:
        - matches: List of related items with explainable reasons
        - seed: Original item metadata
        
    Each match includes:
        - kind, id, title, status, priority
        - score: 0.0-1.0 similarity score
        - why: Array of reasons (e.g., ["same_source_title", "shared_ip:x.x.x.x"])
        
    Args:
        seed_kind: Seed entity type ("alert", "case", "task")
        seed_id: Seed entity ID (forgiving format)
        max_matches: Max matches to return (1-20, default: 10)
    """
    return await _run_tool(find_related_tool(seed_kind, seed_id, max_matches))


@mcp.tool(annotations={"readOnlyHint": True})
async def search_case_runbooks(
    query: str | None = None,
    limit: int = 10,
) -> dict:
    """Search published Case Runbooks by runbook and task text.

    Args:
        query: Optional text search. Empty query returns published runbooks by title.
        limit: Max runbooks to return (1-25, default: 10).
    """
    return await _run_tool(search_case_runbooks_tool(query, limit))


@mcp.tool(annotations={"readOnlyHint": True})
async def get_case_runbook(id: str) -> dict:
    """Get lean detail for one published Case Runbook.

    Args:
        id: Case Runbook ID in forgiving format, e.g. "123" or "RUN-0000123".
    """
    return await _run_tool(get_case_runbook_tool(id))


@mcp.tool()
async def record_triage_decision(
    alert_id: str,
    disposition: str,
    confidence: float,
    reasoning_bullets: list[str] | None = None,
    recommended_actions: list[dict] | None = None,
    recommended_case_runbook_id: int | str | None = None,
    suggested_status: str | None = None,
    suggested_priority: str | None = None,
    suggested_assignee: str | None = None,
    suggested_tags_add: list[str] | None = None,
    suggested_tags_remove: list[str] | None = None,
    request_escalate_to_case: bool = False,
    commit: bool = False,
) -> dict:
    """Record AI triage recommendation for an alert.
    
    Recommendations start as PENDING until analyst accepts/rejects.
    A new recommendation replaces the existing per-alert row in place.
    
    Returns:
        - mode: "dry_run" or "committed" or "replaced"
        - recommendation_id: ID if committed
        - suggested_patches: What would be changed on acceptance
        - status: "PENDING" (always, until analyst acts)
        
    Args:
        alert_id: Alert ID (forgiving format)
        disposition: Triage outcome. Valid values: TRUE_POSITIVE, FALSE_POSITIVE, BENIGN, NEEDS_INVESTIGATION, DUPLICATE, UNKNOWN
        confidence: Agent confidence (0.0-1.0)
        reasoning_bullets: Why this disposition (list of strings). Use markdown links for evidence references, e.g. [ALT-0000123:item-uuid](/alerts/ALT-0000123#timeline-item-uuid)
        recommended_actions: Suggested next steps for escalating dispositions only. Each action is an object with 'title' (required, max 200 chars) and 'description' (optional, markdown supported)
        recommended_case_runbook_id: Published Case Runbook ID to apply on escalation. Mutually exclusive with recommended_actions and only valid for escalating dispositions.
        suggested_status: Optional alert status patch. Valid values: NEW, IN_PROGRESS, ESCALATED, CLOSED_TP, CLOSED_BP, CLOSED_FP, CLOSED_UNRESOLVED, CLOSED_DUPLICATE. Persisted value is derived from disposition.
        suggested_priority: Optional priority patch. Valid values: INFO, LOW, MEDIUM, HIGH, CRITICAL, EXTREME
        suggested_assignee: Optional assignee patch (username)
        suggested_tags_add: Tags to add
        suggested_tags_remove: Tags to remove
        request_escalate_to_case: Optional/deprecated case creation request. Persisted value is derived from disposition.
        commit: If false, returns dry-run preview only (default: false)
    """
    return await _run_tool(
        record_triage_decision_tool(
            alert_id,
            disposition,
            confidence,
            reasoning_bullets,
            recommended_actions,
            recommended_case_runbook_id,
            suggested_status,
            suggested_priority,
            suggested_assignee,
            suggested_tags_add,
            suggested_tags_remove,
            request_escalate_to_case,
            commit,
        )
    )


@mcp.tool()
async def add_timeline_item(
    target_kind: str,
    target_id: str,
    item_id: str,
    body: str,
    commit: bool = False,
    created_at: str | None = None,
    migration: bool = False,
) -> dict:
    """Add timeline note to alert, case, or task.
    
    Append-only operation. Idempotent via client-provided item_id.
    
    Returns:
        - mode: "dry_run" or "committed" or "already_exists"
        - item_id: Unique item identifier
        - created_at: Timestamp if committed
        - author: API key user
        
    Args:
        target_kind: Entity type ("alert", "case", "task")
        target_id: Entity ID (forgiving format)
        item_id: Client-provided unique ID (for idempotency)
        body: Note content (max 16,000 chars)
        commit: If false, returns dry-run preview only (default: false)
        created_at: Migration-only ISO-8601 creation timestamp.
        migration: Required when an authorized NHI supplies created_at.
    """
    return await _run_tool(
        add_timeline_item_tool(
            target_kind,
            target_id,
            item_id,
            body,
            commit,
            created_at,
            migration,
        )
    )


@mcp.tool(annotations={"readOnlyHint": True})
async def get_item(
    parent_entity_type: str,
    parent_entity_id: str,
    item_id: str,
    mode: str = "full",
    max_chars: int = 4000,
    cursor: str | None = None,
) -> dict:
    """Get full content of truncated timeline item.
    
    Supports pagination for very large items.
    The parent entity scope is required; get_item no longer searches all alerts,
    cases, and tasks when a timeline item ID is missing or ambiguous.
    
    Returns:
        - item_id: Item identifier
        - content: Item content (bounded by max_chars)
        - metadata: Type, timestamp, author
        - next_cursor: Pagination cursor if truncated
        
    Args:
        parent_entity_type: Parent entity type ("alert", "case", or "task")
        parent_entity_id: Parent entity ID (forgiving format: "123", "CAS-000123", etc.)
        item_id: Timeline item ID
        mode: Retrieval mode ("full", "head", "tail")
        max_chars: Max characters to return (100-10000, default: 4000)
        cursor: Pagination cursor from previous response
    """
    return await _run_tool(
        get_item_tool(
            parent_entity_type,
            parent_entity_id,
            item_id,
            mode,
            max_chars,
            cursor,
        )
    )


@mcp.tool(annotations={"readOnlyHint": True})
async def validate_mermaid(
    diagram: str,
) -> dict:
    """Validate Mermaid diagram syntax with Mermaid CLI.

    Returns:
        - valid: Whether the Mermaid source parsed successfully
        - message: Summary of the validation result
        - errors: Normalized CLI error lines when invalid

    Args:
        diagram: Raw Mermaid diagram definition to validate
    """
    return await _run_tool(validate_mermaid_tool(diagram))


_TOOL_REGISTRATIONS: tuple[tuple[Callable[..., Any], dict[str, Any] | None], ...] = (
    (get_summary, {"readOnlyHint": True}),
    (list_work, {"readOnlyHint": True}),
    (find_related, {"readOnlyHint": True}),
    (search_case_runbooks, {"readOnlyHint": True}),
    (get_case_runbook, {"readOnlyHint": True}),
    (record_triage_decision, None),
    (add_timeline_item, None),
    (get_item, {"readOnlyHint": True}),
    (validate_mermaid, {"readOnlyHint": True}),
)


def create_mcp_server(
    *,
    auth: AuthProvider,
    lifespan: Any,
    session_factory: Callable[..., Any] = async_session_factory,
) -> FastMCP:
    """Build the authenticated server before its HTTP application is captured."""

    server = FastMCP(
        "Tidemark Intercept MCP",
        auth=auth,
        lifespan=lifespan,
        mask_error_details=True,
    )
    server.add_middleware(MCPPrincipalMiddleware(session_factory=session_factory))
    server.add_middleware(GetItemContractGuidanceMiddleware())
    for tool_function, annotations in _TOOL_REGISTRATIONS:
        server.tool(annotations=annotations)(tool_function)
    return server


# Export the schema-only server plus the runtime factory.
__all__ = ["create_mcp_server", "mcp"]
