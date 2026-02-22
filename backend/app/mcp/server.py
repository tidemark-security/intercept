"""MCP Server with explicit tool registration.

Replaces the auto-generated FastMCP.from_fastapi() with intentionally designed tools.
Part of T013-T014 (Phase 2: MCP Server Skeleton).
"""

from fastmcp import FastMCP
from app.mcp.tools import (
    get_summary_tool,
    list_work_tool,
    find_related_tool,
    record_triage_decision_tool,
    add_timeline_item_tool,
    get_item_tool,
)


# Create MCP server instance with explicit tool registration
mcp = FastMCP("Tidemark Intercept MCP")


# Register tools explicitly (Phase 2 skeleton - implementations in Phase 3+)

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
    return await get_summary_tool(kind, id, max_timeline_items, max_observables, since)


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
    return await list_work_tool(
        kind, statuses, priorities, assignees, contains,
        time_range_start, time_range_end, limit, cursor
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
    return await find_related_tool(seed_kind, seed_id, max_matches)


@mcp.tool()
async def record_triage_decision(
    alert_id: str,
    disposition: str,
    confidence: float,
    reasoning_bullets: list[str] | None = None,
    recommended_actions: list[dict] | None = None,
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
    New recommendation replaces existing (sets old to SUPERSEDED).
    
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
        recommended_actions: Suggested next steps. Each action is an object with 'title' (required, max 200 chars) and 'description' (optional, markdown supported)
        suggested_status: Optional alert status patch. Valid values: NEW, IN_PROGRESS, ESCALATED, CLOSED_TP, CLOSED_BP, CLOSED_FP, CLOSED_UNRESOLVED, CLOSED_DUPLICATE
        suggested_priority: Optional priority patch. Valid values: INFO, LOW, MEDIUM, HIGH, CRITICAL, EXTREME
        suggested_assignee: Optional assignee patch (username)
        suggested_tags_add: Tags to add
        suggested_tags_remove: Tags to remove
        request_escalate_to_case: Request case creation
        commit: If false, returns dry-run preview only (default: false)
    """
    return await record_triage_decision_tool(
        alert_id, disposition, confidence, reasoning_bullets,
        recommended_actions, suggested_status, suggested_priority, suggested_assignee,
        suggested_tags_add, suggested_tags_remove, request_escalate_to_case, commit
    )


@mcp.tool()
async def add_timeline_item(
    target_kind: str,
    target_id: str,
    item_id: str,
    body: str,
    commit: bool = False,
    created_at: str | None = None,
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
        created_at: ISO-8601 timestamp. Defaults to current time if not specified.
    """
    return await add_timeline_item_tool(target_kind, target_id, item_id, body, commit, created_at)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_item(
    item_id: str,
    mode: str = "full",
    max_chars: int = 4000,
    cursor: str | None = None,
    hint_kind: str | None = None,
    hint_parent_id: str | None = None,
) -> dict:
    """Get full content of truncated timeline item.
    
    Supports pagination for very large items.
    
    Returns:
        - item_id: Item identifier
        - content: Item content (bounded by max_chars)
        - metadata: Type, timestamp, author
        - next_cursor: Pagination cursor if truncated
        
    Args:
        item_id: Timeline item ID
        mode: Retrieval mode ("full", "head", "tail")
        max_chars: Max characters to return (100-10000, default: 4000)
        cursor: Pagination cursor from previous response
        hint_kind: Optional entity type hint for faster lookup
        hint_parent_id: Optional parent entity ID hint
    """
    return await get_item_tool(item_id, mode, max_chars, cursor, hint_kind, hint_parent_id)


# Export MCP server instance
__all__ = ["mcp"]
