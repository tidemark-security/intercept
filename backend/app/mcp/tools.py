"""Adapters for the nine intentionally exposed MCP tools.

This module contains:
1. get_summary - Bounded context retrieval
2. list_work - Global work discovery
3. find_related - Similarity search
4. search_case_runbooks - Published runbook discovery
5. get_case_runbook - Published runbook detail
6. record_triage_decision - Triage recommendations
7. add_timeline_item - Timeline note appending
8. get_item - Full content retrieval
9. validate_mermaid - Mermaid syntax validation
"""

from collections.abc import Awaitable
from typing import Any, Dict, TypeVar

from fastapi import HTTPException

from app.api.timestamp_overrides import normalize_created_at_override
from app.core.database import async_session_factory
from app.mcp.principal import get_current_mcp_principal
from app.models.enums import UserRole
from app.services import mcp_service
from app.services.date_filter_utils import parse_utc_datetime
from app.services.mcp_errors import (
    McpConflictError,
    McpNotFoundError,
    McpServiceError,
    McpTimeoutError,
    McpUnavailableError,
    McpValidationError,
)

_PRUNED = object()
_PRESERVE_EMPTY_CONTAINER_KEYS = {"items", "resources", "errors"}
_ServiceResult = TypeVar("_ServiceResult")
_MCP_SERVICE_ERROR_STATUS_CODES: dict[type[McpServiceError], int] = {
    McpValidationError: 400,
    McpNotFoundError: 404,
    McpConflictError: 409,
    McpUnavailableError: 503,
    McpTimeoutError: 504,
}


async def _run_service_call(awaitable: Awaitable[_ServiceResult]) -> _ServiceResult:
    """Translate safe business failures at the HTTP-facing tool seam."""
    try:
        return await awaitable
    except McpServiceError as exc:
        status_code = next(
            (
                code
                for error_type, code in _MCP_SERVICE_ERROR_STATUS_CODES.items()
                if isinstance(exc, error_type)
            ),
            400,
        )
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


def _prune_llm_payload(value: Any, *, preserve_empty: bool = False) -> Any:
    """Recursively remove token-wasting empty values from LLM-facing payloads."""
    if value is None:
        return _PRUNED

    if isinstance(value, str):
        return value if value.strip() else _PRUNED

    if isinstance(value, dict):
        pruned_dict: Dict[str, Any] = {}
        for key, child_value in value.items():
            pruned_child = _prune_llm_payload(
                child_value,
                preserve_empty=key in _PRESERVE_EMPTY_CONTAINER_KEYS,
            )
            if pruned_child is _PRUNED:
                continue
            pruned_dict[key] = pruned_child

        if pruned_dict or preserve_empty:
            return pruned_dict
        return _PRUNED

    if isinstance(value, list):
        pruned_list = []
        for child in value:
            pruned_child = _prune_llm_payload(child)
            if pruned_child is not _PRUNED:
                pruned_list.append(pruned_child)
        if pruned_list or preserve_empty:
            return pruned_list
        return _PRUNED

    return value


def _get_authenticated_user() -> Any | None:
    """Get the freshly reloaded user bound by native FastMCP middleware."""

    principal = get_current_mcp_principal()
    return principal.user if principal is not None else None


def _get_authenticated_username() -> str:
    """Get the authenticated username from the MCP request context.

    Returns:
        Username of the authenticated API key user, or "System" if not available.
    """
    user = _get_authenticated_user()
    if user and hasattr(user, "username"):
        return user.username
    return "System"


def _require_mcp_non_auditor_user_object() -> Any:
    """Require an authenticated non-auditor MCP user for write operations."""
    user = _get_authenticated_user()
    if not user or not hasattr(user, "username"):
        raise HTTPException(status_code=401, detail="Authentication required")

    if getattr(user, "role", None) == UserRole.AUDITOR:
        raise HTTPException(
            status_code=403, detail="Auditor accounts have read-only access"
        )

    return user


def _require_mcp_non_auditor_user() -> str:
    """Require an authenticated non-auditor MCP user for commit operations."""
    return _require_mcp_non_auditor_user_object().username


async def get_summary_tool(
    kind: str,
    id: str,
    max_timeline_items: int = 25,
    max_observables: int = 20,
    since: str | None = None,
) -> Dict[str, Any]:
    """Get a bounded context summary for an alert, case, or task."""
    async with async_session_factory() as db:
        result = await _run_service_call(
            mcp_service.get_summary(
                db=db,
                kind=kind,
                id_str=id,
                max_timeline_items=max_timeline_items,
                max_observables=max_observables,
                since=since,
            )
        )
        payload = result.model_dump(mode="json")
        pruned_payload = _prune_llm_payload(payload, preserve_empty=True)
        return pruned_payload if isinstance(pruned_payload, dict) else payload


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
    """List alerts, cases, or tasks with filtering."""
    async with async_session_factory() as db:
        result = await _run_service_call(
            mcp_service.list_work(
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
        )
        return result.model_dump()


async def find_related_tool(
    seed_kind: str,
    seed_id: str,
    max_matches: int = 10,
) -> Dict[str, Any]:
    """Find related alerts, cases, or tasks."""
    async with async_session_factory() as db:
        result = await _run_service_call(
            mcp_service.find_related(
                db=db,
                seed_kind=seed_kind,
                seed_id_str=seed_id,
                max_matches=max_matches,
            )
        )
        return result.model_dump()


async def record_triage_decision_tool(
    alert_id: str,
    disposition: str,
    confidence: float,
    reasoning_bullets: list[str] | None = None,
    recommended_actions: list[dict[str, Any]] | None = None,
    recommended_case_runbook_id: int | str | None = None,
    suggested_status: str | None = None,
    suggested_priority: str | None = None,
    suggested_assignee: str | None = None,
    suggested_tags_add: list[str] | None = None,
    suggested_tags_remove: list[str] | None = None,
    request_escalate_to_case: bool = False,
    commit: bool = False,
) -> Dict[str, Any]:
    """Record an AI triage recommendation for an alert."""
    username = (
        _require_mcp_non_auditor_user() if commit else _get_authenticated_username()
    )

    async with async_session_factory() as db:
        result = await _run_service_call(
            mcp_service.record_triage_decision(
                db=db,
                alert_id_str=alert_id,
                disposition=disposition,
                confidence=confidence,
                reasoning_bullets=reasoning_bullets,
                recommended_actions=recommended_actions,
                recommended_case_runbook_id=recommended_case_runbook_id,
                suggested_status=suggested_status,
                suggested_priority=suggested_priority,
                suggested_assignee=suggested_assignee,
                suggested_tags_add=suggested_tags_add,
                suggested_tags_remove=suggested_tags_remove,
                request_escalate_to_case=request_escalate_to_case,
                commit=commit,
                created_by=username,
            )
        )
        return result.model_dump()


async def search_case_runbooks_tool(
    query: str | None = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Search published Case Runbooks for triage recommendation planning."""
    async with async_session_factory() as db:
        result = await _run_service_call(
            mcp_service.search_case_runbooks(db=db, query=query, limit=limit)
        )
        return result.model_dump()


async def get_case_runbook_tool(id: str) -> Dict[str, Any]:
    """Get lean detail for a published Case Runbook."""
    async with async_session_factory() as db:
        result = await _run_service_call(
            mcp_service.get_case_runbook(db=db, id_str=id)
        )
        return result.model_dump()


async def add_timeline_item_tool(
    target_kind: str,
    target_id: str,
    item_id: str,
    body: str,
    commit: bool = False,
    created_at: str | None = None,
    migration: bool = False,
) -> Dict[str, Any]:
    """Add a timeline note to an alert, case, or task."""
    requires_write_authorization = commit or migration or created_at is not None
    user = (
        _require_mcp_non_auditor_user_object()
        if requires_write_authorization
        else _get_authenticated_user()
    )
    username = user.username if user and hasattr(user, "username") else "System"

    parsed_created_at = None
    if created_at is not None:
        try:
            parsed_created_at = parse_utc_datetime(created_at)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="created_at must be a valid ISO-8601 datetime",
            ) from None

    created_at_override = normalize_created_at_override(
        current_user=user,
        migration=migration,
        created_at=parsed_created_at,
    )

    async with async_session_factory() as db:
        result = await _run_service_call(
            mcp_service.add_timeline_item(
                db=db,
                target_kind=target_kind,
                target_id_str=target_id,
                item_id=item_id,
                body=body,
                commit=commit,
                created_by=username,
                created_at=created_at_override,
            )
        )
        return result.model_dump()


async def get_item_tool(
    parent_entity_type: str,
    parent_entity_id: str,
    item_id: str,
    mode: str = "full",
    max_chars: int = 4000,
    cursor: str | None = None,
) -> Dict[str, Any]:
    """Get the full content of a truncated timeline item."""
    async with async_session_factory() as db:
        result = await _run_service_call(
            mcp_service.get_item(
                db=db,
                parent_entity_type=parent_entity_type,
                parent_entity_id=parent_entity_id,
                item_id=item_id,
                mode=mode,
                max_chars=max_chars,
                cursor=cursor,
            )
        )
        return result.model_dump()


async def validate_mermaid_tool(diagram: str) -> Dict[str, Any]:
    """Validate Mermaid syntax using the local Mermaid CLI."""
    result = await _run_service_call(mcp_service.validate_mermaid(diagram=diagram))
    return result.model_dump()
