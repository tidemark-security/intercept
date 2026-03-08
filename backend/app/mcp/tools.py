"""MCP tool function definitions.

This module contains the 7 intentional MCP tools:
1. get_summary - Bounded context retrieval
2. list_work - Global work discovery
3. find_related - Similarity search
4. record_triage_decision - Triage recommendations
5. add_timeline_item - Timeline note appending
6. get_item - Full content retrieval
7. validate_mermaid - Mermaid syntax validation

Tool implementations added per User Stories (Phase 3-8).
"""

from fastapi import HTTPException
from typing import Dict, Any

from app.core.database import async_session_factory
from app.services import mcp_service

# Import FastMCP dependency to access HTTP request for authenticated user
try:
    from fastmcp.server.dependencies import get_http_request
except ImportError:
    get_http_request = None


def _get_authenticated_username() -> str:
    """Get the authenticated username from the MCP request context.
    
    The MCPApiKeyAuthMiddleware stores the authenticated user in scope["mcp_user"].
    We access it via the Starlette request object.
    
    Returns:
        Username of the authenticated API key user, or "System" if not available.
    """
    if get_http_request is None:
        return "System"
    
    try:
        request = get_http_request()
        # The middleware stores the user object in request.scope["mcp_user"]
        user = request.scope.get("mcp_user")
        if user and hasattr(user, "username"):
            return user.username
        return "System"
    except Exception:
        # If called outside request context, return default
        return "System"


# Phase 3 (User Story 1): get_summary implementation ✅

async def get_summary_tool(
    kind: str,
    id: str,
    max_timeline_items: int = 25,
    max_observables: int = 20,
    since: str | None = None,
) -> Dict[str, Any]:
    """Get bounded context summary for an alert/case/task.
    
    Phase 3 (User Story 1): get_summary implementation
    """
    async with async_session_factory() as db:
        result = await mcp_service.get_summary(
            db=db,
            kind=kind,
            id_str=id,
            max_timeline_items=max_timeline_items,
            max_observables=max_observables,
            since=since,
        )
        return result.model_dump()



async def list_work_tool(
    kind: str,
    statuses: list[str] | None = None,
    priorities: list[str] | None = None,
    assignees: list[str] | None = None,
    contains: str | None = None,
    time_range_start: str | None = None,
    time_range_end: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> Dict[str, Any]:
    """List alerts/cases/tasks with filtering.
    
    Phase 5 (User Story 3): list_work implementation
    """
    async with async_session_factory() as db:
        result = await mcp_service.list_work(
            db=db,
            kind=kind,
            statuses=statuses,
            priorities=priorities,
            assignees=assignees,
            contains=contains,
            time_range_start=time_range_start,
            time_range_end=time_range_end,
            limit=limit,
            cursor=cursor,
        )
        return result.model_dump()



async def find_related_tool(
    seed_kind: str,
    seed_id: str,
    max_matches: int = 10,
) -> Dict[str, Any]:
    """Find related/similar alerts/cases/tasks.
    
    Phase 6 (User Story 4): find_related implementation
    """
    async with async_session_factory() as db:
        result = await mcp_service.find_related(
            db=db,
            seed_kind=seed_kind,
            seed_id_str=seed_id,
            max_matches=max_matches,
        )
        return result.model_dump()



async def record_triage_decision_tool(
    alert_id: str,
    disposition: str,
    confidence: float,
    reasoning_bullets: list[str] | None = None,
    recommended_actions: list[dict[str, Any]] | None = None,
    suggested_status: str | None = None,
    suggested_priority: str | None = None,
    suggested_assignee: str | None = None,
    suggested_tags_add: list[str] | None = None,
    suggested_tags_remove: list[str] | None = None,
    request_escalate_to_case: bool = False,
    commit: bool = False,
) -> Dict[str, Any]:
    """Record AI triage recommendation for an alert.
    
    Phase 4 (User Story 2): record_triage_decision implementation
    """
    # Get authenticated username from request context
    username = _get_authenticated_username()
    
    async with async_session_factory() as db:
        result = await mcp_service.record_triage_decision(
            db=db,
            alert_id_str=alert_id,
            disposition=disposition,
            confidence=confidence,
            reasoning_bullets=reasoning_bullets,
            recommended_actions=recommended_actions,
            suggested_status=suggested_status,
            suggested_priority=suggested_priority,
            suggested_assignee=suggested_assignee,
            suggested_tags_add=suggested_tags_add,
            suggested_tags_remove=suggested_tags_remove,
            request_escalate_to_case=request_escalate_to_case,
            commit=commit,
            created_by=username,
        )
        return result.model_dump()



async def add_timeline_item_tool(
    target_kind: str,
    target_id: str,
    item_id: str,
    body: str,
    commit: bool = False,
    created_at: str | None = None,
) -> Dict[str, Any]:
    """Add timeline note to alert/case/task.
    
    Phase 7 (User Story 5): add_timeline_item implementation
    """
    from datetime import datetime, timezone
    
    # Get authenticated username from request context
    username = _get_authenticated_username()
    
    # Parse created_at if provided
    parsed_created_at = None
    if created_at:
        try:
            parsed_created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        except ValueError:
            pass  # Will use default (current time)
    
    async with async_session_factory() as db:
        result = await mcp_service.add_timeline_item(
            db=db,
            target_kind=target_kind,
            target_id_str=target_id,
            item_id=item_id,
            body=body,
            commit=commit,
            created_by=username,
            created_at=parsed_created_at,
        )
        return result.model_dump()



async def get_item_tool(
    item_id: str,
    mode: str = "full",
    max_chars: int = 4000,
    cursor: str | None = None,
    hint_kind: str | None = None,
    hint_parent_id: str | None = None,
) -> Dict[str, Any]:
    """Get full content of truncated timeline item.
    
    Phase 8 (User Story 6): get_item implementation
    """
    async with async_session_factory() as db:
        result = await mcp_service.get_item(
            db=db,
            item_id=item_id,
            mode=mode,
            max_chars=max_chars,
            cursor=cursor,
            hint_kind=hint_kind,
            hint_parent_id=hint_parent_id,
        )
        return result.model_dump()


async def validate_mermaid_tool(diagram: str) -> Dict[str, Any]:
    """Validate Mermaid syntax using the local Mermaid CLI."""
    result = await mcp_service.validate_mermaid(diagram=diagram)
    return result.model_dump()

