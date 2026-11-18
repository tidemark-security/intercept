"""MCP service layer for tool implementations.

This service provides business logic for MCP tools, coordinating between
various backend services to fulfill MCP tool requests.
"""

import asyncio
import base64
import binascii
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, NoReturn, Optional, Union, cast

from sqlalchemy import String, cast as sql_cast, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.entity_ids import (
    ALERT_PREFIX,
    RUNBOOK_PREFIX,
    format_entity_id,
    get_prefix_for_kind,
)
from app.core.id_parser import EntityIdParseError, parse_entity_id
from app.mcp.schemas import (
    AddTimelineItemOutput,
    CaseRunbookSearchResult,
    ContextEntrySummary,
    ContextSection,
    FindRelatedOutput,
    GetCaseRunbookOutput,
    GetItemOutput,
    GetSummaryOutput,
    ItemMetadata,
    LeanRunbookTask,
    ListWorkOutput,
    ObjectHeader,
    ObservablesSection,
    RecordTriageDecisionOutput,
    RelatedCounts,
    RelatedMatch,
    Resource,
    SearchCaseRunbooksOutput,
    SuggestedPatch,
    TimelinePreview,
    TimelineSection,
    ValidateMermaidOutput,
    WorkItemPreview,
)
from app.models.enums import (
    AlertStatus,
    CaseRunbookStatus,
    CaseStatus,
    Priority,
    TaskStatus,
)
from app.models.models import Alert, Case, CaseRunbook, Task
from app.services import triage_recommendation_service
from app.services.case_runbook_service import parse_case_runbook_id
from app.services.case_runbook_validation import coerce_runbook_tasks
from app.services.context_service import ContextService
from app.services.date_filter_utils import parse_utc_datetime
from app.services.observable_service import extract_observables
from app.services.similarity_service import count_similar_alerts
from app.services.mcp_errors import (
    McpConflictError,
    McpNotFoundError,
    McpTimeoutError,
    McpUnavailableError,
    McpValidationError,
)
from app.services.tag_filter_utils import (
    merge_persisted_tags,
    normalize_persisted_tags,
    persisted_tag_delta,
)


_MERMAID_VALIDATION_TIMEOUT_SECONDS = 10
_MERMAID_MAX_ERROR_LINES = 10
_MERMAID_VALIDATOR_SCRIPT_CANDIDATES = (
    Path("/opt/mermaid-validator/validate_mermaid_syntax.mjs"),
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "mermaid-validator"
    / "validate_mermaid_syntax.mjs",
)
_MERMAID_INVALID_ERROR_MARKERS = (
    "parse error",
    "syntax error",
    "lexical error",
    "expecting",
    "unknowndiagramerror",
    "no diagram type detected",
)
_MERMAID_OPERATIONAL_ERROR_MARKERS = (
    "browser was not found",
    "could not find expected browser",
    "failed to launch the browser process",
    "failed to launch the browser",
    "spawn",
    "enoent",
    "eacces",
    "err_module_not_found",
    "cannot find package",
    "cannot find module",
    "dompurify.addhook is not a function",
    "dompurify.sanitize is not a function",
)

_GET_ITEM_PARENT_MODELS = {
    "alert": Alert,
    "case": Case,
    "task": Task,
}
_GET_ITEM_PARENT_TABLES = {
    "alert": "alerts",
    "case": "cases",
    "task": "tasks",
}
_LINKED_TIMELINE_ID_FIELDS = {
    "alert": "alert_id",
    "case": "case_id",
    "task": "task_id",
}
_WORK_STATUS_ENUMS = {
    "alert": AlertStatus,
    "case": CaseStatus,
    "task": TaskStatus,
}
_CLOSED_ALERT_STATUS_VALUES = [
    "CLOSED_TP",
    "CLOSED_BP",
    "CLOSED_FP",
    "CLOSED_UNRESOLVED",
    "CLOSED_DUPLICATE",
]


def _build_timeline_preview_text(item: Dict[str, Any]) -> str:
    """Build a concise preview string tailored to the timeline item type."""
    item_type = _timeline_item_type(item)
    description = str(item.get("description") or "").strip()

    if item_type == "observable":
        observable_value = str(item.get("observable_value") or item.get("value") or "").strip()
        if observable_value and description:
            return f"{observable_value}: {description}"
        if observable_value:
            return observable_value
        return description

    return _timeline_item_content(item).strip()


def _timeline_item_type(item: Dict[str, Any]) -> str:
    item_type = item.get("type")
    return item_type if isinstance(item_type, str) and item_type else "note"


def _timeline_item_content(item: Dict[str, Any]) -> str:
    content = item.get("body") or item.get("content") or item.get("description")
    return str(content) if content is not None else ""


def _timeline_item_author(item: Dict[str, Any]) -> Optional[str]:
    author = item.get("created_by") or item.get("author")
    return str(author) if author is not None else None


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    try:
        return parse_utc_datetime(str(value))
    except (TypeError, ValueError):
        return None


def _decode_cursor(cursor: str) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(base64.b64decode(cursor, validate=True).decode())
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _encode_cursor(payload: Dict[str, Any]) -> str:
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _non_negative_int(value: Any) -> Optional[int]:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return min(max(minimum, value), maximum)


def _parse_work_item_id(raw: str, kind: str) -> tuple[int, str]:
    try:
        return parse_entity_id(raw, kind)
    except EntityIdParseError as exc:
        raise McpValidationError(str(exc)) from exc


def _work_item_model(
    kind: str,
    *,
    field_name: str = "kind",
) -> type[Alert] | type[Case] | type[Task]:
    model = _GET_ITEM_PARENT_MODELS.get(kind)
    if model is None:
        raise McpValidationError(
            f"Invalid {field_name} '{kind}'. Must be 'alert', 'case', or 'task'."
        )
    return model


async def _load_work_item(
    db: AsyncSession,
    kind: str,
    numeric_id: int,
    human_id: str,
) -> Union[Alert, Case, Task]:
    entity = await db.get(_work_item_model(kind), numeric_id)
    if entity is None:
        raise McpNotFoundError(f"{kind.title()} {human_id} not found")
    return entity


def _enum_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value.value) if hasattr(value, "value") else str(value)


def _work_item_header(entity: Union[Alert, Case, Task]) -> ObjectHeader:
    return ObjectHeader(
        title=entity.title,
        status=_enum_value(entity.status) or "",
        priority=_enum_value(entity.priority),
        assignee=entity.assignee,
        source=getattr(entity, "source", None),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _timeline_preview(
    item: Dict[str, Any],
    default_timestamp: datetime,
) -> TimelinePreview:
    item_type = _timeline_item_type(item)
    timestamp = _parse_iso_datetime(item.get("timestamp")) or default_timestamp
    body = _build_timeline_preview_text(item)

    linked_id_field = _LINKED_TIMELINE_ID_FIELDS.get(item_type)
    linked_id = item.get(linked_id_field) if linked_id_field else None
    entity_id = None
    if isinstance(linked_id, int) and not isinstance(linked_id, bool):
        entity_id = format_entity_id(linked_id, get_prefix_for_kind(item_type))

    observable_type = None
    observable_value = None
    if item_type == "observable":
        raw_type = item.get("observable_type")
        raw_value = item.get("observable_value") or item.get("value")
        observable_type = str(raw_type) if raw_type else None
        observable_value = str(raw_value) if raw_value else None

    is_truncated = len(body) > 200
    return TimelinePreview(
        timeline_id=str(item.get("id", "unknown")),
        type=item_type,
        timestamp=timestamp,
        author=_timeline_item_author(item),
        preview=body[:200],
        is_truncated=is_truncated,
        full_length_chars=len(body) if is_truncated else None,
        entity_id=entity_id,
        observable_type=observable_type,
        observable_value=observable_value,
        enrichment_status=(
            item.get("enrichment_status")
            if "enrichment_status" in item
            else None
        ),
        enrichments=(
            item.get("enrichments")
            if isinstance(item.get("enrichments"), dict)
            else None
        ),
    )


def _summarize_timeline(
    timeline_items: List[Dict[str, Any]],
    *,
    since: Optional[datetime],
    limit: int,
    default_timestamp: datetime,
) -> tuple[TimelineSection, List[Dict[str, Any]]]:
    """Filter, order, and bound timeline items for a summary response."""
    if since is not None:
        timeline_items = [
            item
            for item in timeline_items
            if (timestamp := _parse_iso_datetime(item.get("timestamp"))) is not None
            and timestamp >= since
        ]
    timeline_items.sort(
        key=lambda item: str(item.get("timestamp") or ""),
        reverse=True,
    )
    bounded_items = timeline_items[:limit]
    return TimelineSection(
        items=[_timeline_preview(item, default_timestamp) for item in bounded_items],
        total_count=len(timeline_items),
        omitted_count=max(0, len(timeline_items) - len(bounded_items)),
        bounded_by="since" if since is not None else "max_timeline_items",
    ), timeline_items


async def _summary_context(
    db: AsyncSession,
    *,
    kind: str,
    entity_id: int,
    limit: int,
) -> ContextSection:
    if kind != "alert":
        return ContextSection(items=[], total_count=0, omitted_count=0)
    matching_context = await ContextService(db).get_matching_context_for_alert(entity_id)
    items = [
        ContextEntrySummary.model_validate(entry)
        for entry in matching_context[:limit]
    ]
    return ContextSection(
        items=items,
        total_count=len(matching_context),
        omitted_count=max(0, len(matching_context) - len(items)),
    )


async def _summary_related_counts(
    db: AsyncSession,
    kind: str,
    entity: Union[Alert, Case, Task],
) -> RelatedCounts:
    if kind == "alert":
        alert = cast(Alert, entity)
        return RelatedCounts(
            linked_cases=1 if alert.case_id else 0,
            similar_alerts=await count_similar_alerts(db, alert, days=30),
        )
    if kind == "case":
        alert_count = await db.execute(
            select(func.count(Alert.id)).where(Alert.case_id == entity.id)
        )
        task_count = await db.execute(
            select(func.count(Task.id)).where(Task.case_id == entity.id)
        )
        return RelatedCounts(
            linked_alerts=alert_count.scalar() or 0,
            linked_tasks=task_count.scalar() or 0,
        )
    return RelatedCounts(linked_cases=1 if entity.case_id else 0)


async def _resolve_published_runbook_id(
    db: AsyncSession,
    value: Any,
) -> Optional[int]:
    if value is None:
        return None
    try:
        runbook_id = parse_case_runbook_id(value)
    except ValueError as exc:
        raise McpValidationError(str(exc)) from exc
    runbook = await db.get(CaseRunbook, runbook_id)
    if runbook is None or runbook.status != CaseRunbookStatus.PUBLISHED:
        raise McpValidationError(
            "recommended_case_runbook_id must reference a published Case Runbook"
        )
    return runbook_id


def _suggested_triage_patches(
    alert: Alert,
    data: Dict[str, Any],
) -> tuple[List[SuggestedPatch], List[str], List[str]]:
    """Build the dry-run patch view and canonical persisted tag lists."""
    patches: List[SuggestedPatch] = []
    suggested_status = data["suggested_status"]
    if suggested_status and suggested_status != alert.status.value:
        patches.append(SuggestedPatch(
            field="status",
            current_value=alert.status.value,
            new_value=suggested_status,
        ))

    suggested_priority = data.get("suggested_priority")
    if suggested_priority and (
        not alert.priority or suggested_priority != alert.priority.value
    ):
        patches.append(SuggestedPatch(
            field="priority",
            current_value=alert.priority.value if alert.priority else None,
            new_value=suggested_priority,
        ))

    suggested_assignee = data.get("suggested_assignee")
    if suggested_assignee and suggested_assignee != alert.assignee:
        patches.append(SuggestedPatch(
            field="assignee",
            current_value=alert.assignee,
            new_value=suggested_assignee,
        ))

    alert_tags = normalize_persisted_tags(alert.tags)
    tags_to_add = normalize_persisted_tags(data["suggested_tags_add"])
    tags_to_remove = normalize_persisted_tags(data["suggested_tags_remove"])
    remove_tag_keys = {tag.lower() for tag in tags_to_remove}
    final_tags = [
        tag
        for tag in merge_persisted_tags(alert_tags, tags_to_add)
        if tag.lower() not in remove_tag_keys
    ]
    added_tags, removed_tags = persisted_tag_delta(alert_tags, final_tags)
    patches.extend(
        SuggestedPatch(field="tags", current_value=None, new_value=f"add:{tag}")
        for tag in added_tags
    )
    patches.extend(
        SuggestedPatch(field="tags", current_value=tag, new_value=f"remove:{tag}")
        for tag in removed_tags
    )
    return patches, tags_to_add, tags_to_remove


def _raise_triage_recommendation_mcp_error(
    error: triage_recommendation_service.TriageRecommendationError,
) -> NoReturn:
    """Translate a typed triage failure into the shared MCP error vocabulary."""
    if isinstance(
        error,
        triage_recommendation_service.TriageRecommendationNotFoundError,
    ):
        raise McpNotFoundError(str(error)) from error
    if isinstance(
        error,
        triage_recommendation_service.TriageRecommendationConflictError,
    ):
        raise McpConflictError(str(error)) from error
    raise McpValidationError(str(error)) from error


def _parse_work_time_filter(value: str, field_name: str) -> datetime:
    try:
        return parse_utc_datetime(value)
    except ValueError as exc:
        raise McpValidationError(
            f"Invalid {field_name} format: {value}"
        ) from exc


def _normalize_work_statuses(kind: str, statuses: List[str]) -> List[Any]:
    normalized = list(statuses)
    if kind == "alert" and "CLOSED" in normalized:
        normalized.remove("CLOSED")
        normalized.extend(
            status for status in _CLOSED_ALERT_STATUS_VALUES
            if status not in normalized
        )
    status_enum = _WORK_STATUS_ENUMS[kind]
    try:
        return [status_enum(status) for status in normalized]
    except ValueError as exc:
        raise McpValidationError(f"Invalid status value: {exc}") from exc


def _apply_list_work_filters(
    query: Any,
    model: Any,
    *,
    kind: str,
    statuses: Optional[List[str]],
    priorities: Optional[List[str]],
    assignees: Optional[List[str]],
    contains: Optional[str],
    time_range_start: Optional[str],
    time_range_end: Optional[str],
) -> Any:
    """Apply the complete filter contract for list_work."""
    start = (
        _parse_work_time_filter(time_range_start, "time_range_start")
        if time_range_start
        else datetime.now(timezone.utc) - timedelta(days=7)
    )
    query = query.where(model.created_at >= start)
    if time_range_end:
        query = query.where(
            model.created_at
            <= _parse_work_time_filter(time_range_end, "time_range_end")
        )
    if statuses:
        query = query.where(model.status.in_(_normalize_work_statuses(kind, statuses)))
    if priorities and hasattr(model, "priority"):
        try:
            enum_priorities = [Priority(priority) for priority in priorities]
        except ValueError as exc:
            raise McpValidationError(f"Invalid priority value: {exc}") from exc
        query = query.where(model.priority.in_(enum_priorities))
    if assignees:
        query = query.where(model.assignee.in_(assignees))
    if contains:
        search_term = f"%{contains}%"
        query = query.where(or_(
            model.title.ilike(search_term),
            (
                model.description.ilike(search_term)
                if hasattr(model, "description")
                else False
            ),
        ))
    return query


def _work_item_preview(item: Union[Alert, Case, Task], kind: str) -> WorkItemPreview:
    return WorkItemPreview(
        id=item.id,  # type: ignore[arg-type]
        human_id=format_entity_id(item.id, get_prefix_for_kind(kind)),  # type: ignore[arg-type]
        title=item.title,
        status=_enum_value(item.status) or "",
        priority=_enum_value(item.priority),
        assignee=item.assignee,
        created_at=item.created_at,
        updated_at=item.updated_at,
        source=getattr(item, "source", None),
    )


def _related_alert_preview(match_data: Dict[str, Any]) -> RelatedMatch:
    alert = cast(Alert, match_data["alert"])
    return RelatedMatch(
        kind="alert",
        id=alert.id,  # type: ignore[arg-type]
        human_id=format_entity_id(alert.id, ALERT_PREFIX),  # type: ignore[arg-type]
        title=alert.title,
        status=_enum_value(alert.status) or "",
        priority=_enum_value(alert.priority),
        score=match_data["score"],
        why=match_data["reasons"],
    )


def _existing_timeline_item_output(
    item_id: str,
    item: Dict[str, Any],
) -> AddTimelineItemOutput:
    timestamp = item.get("created_at") or item.get("timestamp")
    return AddTimelineItemOutput(
        mode="already_exists",
        item_id=item_id,
        created_at=_parse_iso_datetime(timestamp) if timestamp else None,
        author=_timeline_item_author(item),
        message=f"Item {item_id} already exists (idempotent)",
    )


def _cursor_offset(cursor: Optional[str]) -> int:
    if not cursor:
        return 0
    cursor_data = _decode_cursor(cursor)
    offset = _non_negative_int(cursor_data.get("offset") if cursor_data else None)
    return offset if offset is not None else 0


def _slice_timeline_content(
    content: str,
    *,
    mode: str,
    max_chars: int,
    offset: int,
) -> tuple[str, int]:
    if mode == "full":
        page = content[offset:offset + max_chars]
        return page, offset + len(page)
    if mode == "head":
        page = content[:max_chars]
        return page, len(page)
    start = max(0, len(content) - max_chars)
    return content[start:], len(content)


def _resolve_mermaid_validator_command() -> list[str]:
    """Resolve parser-based Mermaid validator dependencies and invocation command."""
    node_path = shutil.which("node")
    if not node_path:
        raise McpUnavailableError(
            "Mermaid validation is unavailable because 'node' is not installed on PATH."
        )

    for script_path in _MERMAID_VALIDATOR_SCRIPT_CANDIDATES:
        if script_path.exists():
            return [node_path, str(script_path)]

    raise McpUnavailableError(
        "Mermaid validation is unavailable because the parser script is missing."
    )


def _collect_mermaid_error_lines(*parts: str) -> List[str]:
    """Normalize Mermaid CLI stderr/stdout into compact, user-facing errors."""
    seen: set[str] = set()
    errors: List[str] = []

    for part in parts:
        for raw_line in part.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line in seen:
                continue
            seen.add(line)
            errors.append(line)
            if len(errors) >= _MERMAID_MAX_ERROR_LINES:
                return errors

    return errors


def _is_operational_mermaid_failure(error_text: str) -> bool:
    """Detect non-syntax failures that indicate an environment/runtime problem."""
    lowered = error_text.lower()
    if any(marker in lowered for marker in _MERMAID_OPERATIONAL_ERROR_MARKERS):
        return True

    return "timeout" in lowered and "parse error" not in lowered


def _is_invalid_mermaid_failure(error_text: str) -> bool:
    """Detect failures that should be reported as invalid Mermaid syntax."""
    lowered = error_text.lower()
    return any(marker in lowered for marker in _MERMAID_INVALID_ERROR_MARKERS)


async def validate_mermaid(diagram: str) -> ValidateMermaidOutput:
    """Validate Mermaid syntax using the local parser script.

    Args:
        diagram: Mermaid diagram source to validate.

    Returns:
        Validation result with syntax status and normalized errors.

    Raises:
        McpValidationError: Diagram content is empty or exceeds the size limit.
        McpUnavailableError: Validator dependencies are unavailable or cannot launch.
        McpTimeoutError: Validator timed out during validation.
    """
    if not diagram:
        raise McpValidationError("Mermaid diagram must not be empty.")
    if len(diagram) > 100_000:
        raise McpValidationError(
            "Mermaid diagram is too long (maximum 100,000 characters)."
        )

    command = _resolve_mermaid_validator_command()

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(diagram.encode("utf-8")),
                timeout=_MERMAID_VALIDATION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise McpTimeoutError(
                "Mermaid validation timed out while invoking parser validator."
            ) from exc

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        combined_output = "\n".join(part for part in (stderr_text, stdout_text) if part).strip()

        if process.returncode == 0:
            return ValidateMermaidOutput(
                valid=True,
                message="Mermaid diagram syntax is valid.",
                errors=[],
            )

        if _is_operational_mermaid_failure(combined_output):
            raise McpUnavailableError(
                "Mermaid validation is unavailable because parser validator could not run correctly."
            )

        error_lines = _collect_mermaid_error_lines(stderr_text, stdout_text)
        if _is_invalid_mermaid_failure(combined_output):
            return ValidateMermaidOutput(
                valid=False,
                message="Mermaid diagram syntax is invalid.",
                errors=error_lines or ["Mermaid validation failed."],
            )

        raise McpUnavailableError(
            "Mermaid validation failed due to an unexpected parser validator error."
        )
    except FileNotFoundError as exc:
        raise McpUnavailableError(
            "Mermaid validation is unavailable because parser dependencies are missing."
        ) from exc



async def get_summary(
    db: AsyncSession,
    kind: str,
    id_str: str,
    max_timeline_items: int = 25,
    max_observables: int = 20,
    since: Optional[str] = None,
) -> GetSummaryOutput:
    """Get bounded context summary for an alert, case, or task.

    Args:
        db: Database session
        kind: Entity type ("alert", "case", "task")
        id_str: Entity ID (forgiving format)
        max_timeline_items: Max timeline items to return
        max_observables: Max observables to extract
        since: ISO-8601 timestamp for incremental refresh

    Returns:
        GetSummaryOutput with header, timeline, observables, related_counts, resources

    Raises:
        McpValidationError: The ID, kind, or timestamp is invalid.
        McpNotFoundError: The requested entity does not exist.
    """
    max_timeline_items = _clamp_int(
        max_timeline_items,
        minimum=1,
        maximum=50,
    )
    max_observables = _clamp_int(max_observables, minimum=1, maximum=50)
    numeric_id, canonical_prefix = _parse_work_item_id(id_str, kind)
    human_id = format_entity_id(numeric_id, canonical_prefix)

    # Parse since timestamp if provided
    since_dt: Optional[datetime] = None
    if since:
        since_dt = _parse_iso_datetime(since)
        if since_dt is None:
            raise McpValidationError(
                f"Invalid 'since' timestamp format: {since}. Expected ISO-8601."
            )

    entity = await _load_work_item(db, kind, numeric_id, human_id)

    from app.services.timeline_service import timeline_service

    timeline_items: List[Dict[str, Any]] = timeline_service.response_items(entity.timeline_items)
    timeline_section, timeline_items = _summarize_timeline(
        timeline_items,
        since=since_dt,
        limit=max_timeline_items,
        default_timestamp=entity.created_at,
    )

    # Extract observables from ALL timeline items (not just bounded)
    all_observables = extract_observables(timeline_items, max_observables=None)
    observables = all_observables[:max_observables]
    observables_section = ObservablesSection(
        items=observables,
        total_count=len(all_observables),
        omitted_count=len(all_observables) - len(observables),
    )

    context_section = await _summary_context(
        db,
        kind=kind,
        entity_id=numeric_id,
        limit=max_timeline_items,
    )
    related_counts = await _summary_related_counts(db, kind, entity)

    resources = [
        Resource(
            label=f"View {kind.capitalize()}",
            url=f"/{kind}s/{human_id}"
        )
    ]

    return GetSummaryOutput(
        kind=kind,
        id=numeric_id,
        human_id=human_id,
        header=_work_item_header(entity),
        timeline=timeline_section,
        observables=observables_section,
        context=context_section,
        related_counts=related_counts,
        resources=resources,
    )


async def record_triage_decision(
    db: AsyncSession,
    alert_id_str: str,
    disposition: str,
    confidence: float,
    reasoning_bullets: Optional[List[str]] = None,
    recommended_actions: Optional[List[Dict[str, Any]]] = None,
    recommended_case_runbook_id: Optional[int | str] = None,
    suggested_status: Optional[str] = None,
    suggested_priority: Optional[str] = None,
    suggested_assignee: Optional[str] = None,
    suggested_tags_add: Optional[List[str]] = None,
    suggested_tags_remove: Optional[List[str]] = None,
    request_escalate_to_case: bool = False,
    commit: bool = False,
    created_by: str = "api_user",
) -> RecordTriageDecisionOutput:
    """Record AI triage recommendation for an alert.

    Args:
        db: Database session
        alert_id_str: Alert ID (forgiving format)
        disposition: Triage disposition
        confidence: AI confidence (0.0-1.0)
        reasoning_bullets: Why this disposition. Use markdown links for evidence references.
        recommended_actions: Suggested next steps for escalating dispositions only
        suggested_status: Optional status patch; canonical value is derived from disposition
        suggested_priority: Optional priority patch
        suggested_assignee: Optional assignee patch
        suggested_tags_add: Tags to add
        suggested_tags_remove: Tags to remove
        request_escalate_to_case: Optional/deprecated case creation request; persisted value is derived from disposition
        commit: If false, returns dry-run preview only
        created_by: Username from API key

    Returns:
        RecordTriageDecisionOutput with mode, suggested_patches, status

    Raises:
        McpValidationError: Invalid ID or recommendation data
        McpNotFoundError: Alert not found
        McpConflictError: Recommendation state conflicts with the operation
    """
    numeric_id, canonical_prefix = _parse_work_item_id(alert_id_str, "alert")

    # Get alert to verify it exists and build patches
    alert = await db.get(Alert, numeric_id)
    if alert is None:
        raise McpNotFoundError(
            f"Alert {format_entity_id(numeric_id, canonical_prefix)} not found"
        )

    try:
        data = triage_recommendation_service.normalize_recommendation_contract({
            "disposition": disposition,
            "confidence": confidence,
            "reasoning_bullets": reasoning_bullets or [],
            "recommended_actions": recommended_actions or [],
            "recommended_case_runbook_id": recommended_case_runbook_id,
            "suggested_status": suggested_status,
            "suggested_priority": suggested_priority,
            "suggested_assignee": suggested_assignee,
            "suggested_tags_add": suggested_tags_add or [],
            "suggested_tags_remove": suggested_tags_remove or [],
            "request_escalate_to_case": request_escalate_to_case,
        })
    except triage_recommendation_service.TriageRecommendationError as error:
        _raise_triage_recommendation_mcp_error(error)

    data["recommended_case_runbook_id"] = await _resolve_published_runbook_id(
        db,
        data["recommended_case_runbook_id"],
    )
    suggested_patches, tags_to_add, tags_to_remove = _suggested_triage_patches(
        alert,
        data,
    )

    # Dry-run mode
    if not commit:
        return RecordTriageDecisionOutput(
            mode="dry_run",
            recommendation_id=None,
            suggested_patches=suggested_patches,
            status="PENDING",
            message="Dry-run preview - no changes made",
        )

    data["suggested_tags_add"] = tags_to_add
    data["suggested_tags_remove"] = tags_to_remove

    # Check if existing recommendation
    existing = await triage_recommendation_service.get_by_alert_id(db, numeric_id)

    # Create or replace recommendation
    try:
        recommendation = (
            await triage_recommendation_service.create_or_replace_recommendation(
                db=db,
                alert_id=numeric_id,
                data=data,
                created_by=created_by,
            )
        )
    except triage_recommendation_service.TriageRecommendationError as error:
        _raise_triage_recommendation_mcp_error(error)

    mode = "replaced" if existing else "committed"

    return RecordTriageDecisionOutput(
        mode=mode,
        recommendation_id=recommendation.id,
        suggested_patches=suggested_patches,
        status="PENDING",
        message=f"Recommendation {mode} successfully. Status: PENDING until analyst reviews.",
    )


async def search_case_runbooks(
    db: AsyncSession,
    *,
    query: str | None = None,
    limit: int = 10,
) -> SearchCaseRunbooksOutput:
    limit = _clamp_int(limit, minimum=1, maximum=25)
    stmt = select(CaseRunbook).where(CaseRunbook.status == CaseRunbookStatus.PUBLISHED)
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        stmt = stmt.where(
            func.lower(
                func.concat(
                    CaseRunbook.title,
                    " ",
                    CaseRunbook.description,
                    " ",
                    sql_cast(CaseRunbook.runbook_tasks, String),
                )
            ).like(pattern.lower())
        )
    stmt = stmt.order_by(CaseRunbook.title.asc()).limit(limit)
    runbooks = (await db.execute(stmt)).scalars().all()

    items: list[CaseRunbookSearchResult] = []
    for runbook in runbooks:
        if runbook.id is None:
            continue
        tasks = coerce_runbook_tasks(runbook.runbook_tasks)
        items.append(
            CaseRunbookSearchResult(
                id=runbook.id,  # type: ignore[arg-type]
                human_id=format_entity_id(runbook.id, RUNBOOK_PREFIX),
                title=runbook.title or "",
                description=runbook.description,
                case_tags=runbook.case_tags or [],
                runbook_task_count=len(tasks),
                picerl_stages=sorted({task.picerl_stage.value for task in tasks}),
            )
        )
    return SearchCaseRunbooksOutput(items=items)


async def get_case_runbook(
    db: AsyncSession,
    *,
    id_str: str,
) -> GetCaseRunbookOutput:
    try:
        runbook_id = parse_case_runbook_id(id_str)
    except ValueError as exc:
        raise McpValidationError(str(exc)) from exc

    runbook = await db.get(CaseRunbook, runbook_id)
    if runbook is None or runbook.status != CaseRunbookStatus.PUBLISHED:
        raise McpNotFoundError("Published Case Runbook not found")

    return GetCaseRunbookOutput(
        id=runbook.id,  # type: ignore[arg-type]
        human_id=format_entity_id(runbook.id, RUNBOOK_PREFIX),
        title=runbook.title or "",
        description=runbook.description,
        case_tags=runbook.case_tags or [],
        runbook_tasks=[
            LeanRunbookTask(
                title=task.title,
                description=task.description,
                picerl_stage=task.picerl_stage.value,
                relative_due_seconds=task.relative_due_seconds,
                priority=task.priority.value if task.priority else None,
                tags=task.tags,
            )
            for task in coerce_runbook_tasks(runbook.runbook_tasks)
        ],
    )


async def list_work(
    db: AsyncSession,
    kind: str,
    statuses: Optional[List[str]] = None,
    priorities: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
    contains: Optional[str] = None,
    time_range_start: Optional[str] = None,
    time_range_end: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
) -> ListWorkOutput:
    """List and filter alerts, cases, or tasks.

    Args:
        db: Database session
        kind: Entity type ("alert", "case", "task")
        statuses: Filter by status
        priorities: Filter by priority
        assignees: Filter by assignee usernames
        contains: Search in title + description only (NOT timeline notes)
        time_range_start: Filter by created_at >= (ISO-8601, default: 7 days ago)
        time_range_end: Filter by created_at <= (ISO-8601)
        limit: Max items to return (1-50, enforced)
        cursor: Pagination cursor from previous response

    Returns:
        Dictionary with items, next_cursor, total_count

    Raises:
        McpValidationError: A filter or pagination argument is invalid.
    """
    # Enforce limit
    limit = _clamp_int(limit, minimum=1, maximum=50)
    model = _work_item_model(kind)
    query = _apply_list_work_filters(
        select(model),
        model,
        kind=kind,
        statuses=statuses,
        priorities=priorities,
        assignees=assignees,
        contains=contains,
        time_range_start=time_range_start,
        time_range_end=time_range_end,
    )

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total_count = int((await db.execute(count_query)).scalar_one())

    # Handle pagination cursor
    if cursor:
        cursor_data = _decode_cursor(cursor)
        last_id = _non_negative_int(
            cursor_data.get("last_id") if cursor_data else None
        )
        if last_id is None:
            raise McpValidationError("Invalid cursor")
        query = query.where(model.id > last_id)

    # Order by ID for consistent pagination
    query = query.order_by(model.id)

    # Fetch limit + 1 to check if there are more results
    query = query.limit(limit + 1)

    result = await db.execute(query)
    items = result.scalars().all()

    # Check if there are more results
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    # Build next cursor
    next_cursor = None
    if has_more and items:
        next_cursor = _encode_cursor({"last_id": items[-1].id})

    return ListWorkOutput(
        items=[_work_item_preview(item, kind) for item in items],
        next_cursor=next_cursor,
        total_count=total_count,
    )


async def find_related(
    db: AsyncSession,
    seed_kind: str,
    seed_id_str: str,
    max_matches: int = 10,
) -> FindRelatedOutput:
    """Find similar/related alerts, cases, or tasks.

    Args:
        db: Database session
        seed_kind: Seed entity type ("alert", "case", "task")
        seed_id_str: Seed entity ID (forgiving format)
        max_matches: Max matches to return (1-20, default: 10)

    Returns:
        Dictionary with seed and matches array

    Raises:
        McpValidationError: The seed ID or kind is invalid.
        McpNotFoundError: The seed entity does not exist.
    """
    from app.services.similarity_service import find_related_alerts

    numeric_id, canonical_prefix = _parse_work_item_id(seed_id_str, seed_kind)
    human_id = format_entity_id(numeric_id, canonical_prefix)

    seed_entity = await _load_work_item(db, seed_kind, numeric_id, human_id)

    # At this point seed_entity.id is guaranteed to be int (not None) since we fetched by ID
    assert seed_entity.id is not None

    # Find related items (currently only implemented for alerts)
    matches_list: List[RelatedMatch] = []

    if seed_kind == "alert":
        # Type narrowing: seed_entity is Alert in this branch
        alert_seed = cast(Alert, seed_entity)
        # Find related alerts
        raw_matches = await find_related_alerts(
            db,
            alert_seed,
            _clamp_int(max_matches, minimum=1, maximum=20),
        )

        matches_list = [_related_alert_preview(match) for match in raw_matches]

    # Related-item discovery is defined only for alert seeds; cases and tasks
    # return an empty match list.

    return FindRelatedOutput(
        seed=_work_item_preview(seed_entity, seed_kind),
        matches=matches_list,
    )


async def add_timeline_item(
    db: AsyncSession,
    target_kind: str,
    target_id_str: str,
    item_id: str,
    body: str,
    commit: bool = False,
    created_by: str = "api_user",
    created_at: Optional[datetime] = None,
) -> AddTimelineItemOutput:
    """Add timeline note to alert, case, or task.

    Delegates to the entity service layer for the actual mutation, which
    handles resource sync, denormalization, audit logging, and real-time
    event emission.  MCP-specific concerns (idempotency, dry-run, ID
    parsing, body validation) are handled here.

    Args:
        db: Database session
        target_kind: Entity type ("alert", "case", "task")
        target_id_str: Entity ID (forgiving format)
        item_id: Client-provided unique ID (for idempotency)
        body: Note content (max 16,000 chars)
        commit: If false, returns dry-run preview only
        created_by: Username from API key
        created_at: Authorized migration-only timestamp when item was created.

    Returns:
        Dictionary with mode, item_id, created_at, author, message

    Raises:
        McpValidationError: The target ID, kind, or body is invalid.
        McpNotFoundError: The target entity does not exist.
    """
    from app.models.models import NoteItem
    from app.services.timeline_add_service import add_timeline_item_and_commit
    from app.services.timeline_service import timeline_service

    # Validate body length
    if len(body) > 16000:
        raise McpValidationError(
            f"Body too long: {len(body)} chars (max 16,000)"
        )

    entity_model = _work_item_model(target_kind, field_name="target_kind")
    numeric_id, canonical_prefix = _parse_work_item_id(target_id_str, target_kind)
    target_human_id = format_entity_id(numeric_id, canonical_prefix)
    target_not_found_message = (
        f"{target_kind.capitalize()} {target_human_id} not found"
    )

    # Idempotency + existence check using a lightweight column query.
    # IMPORTANT: We must NOT load the full entity via db.get() here, because
    # that would place it in the session identity map without eagerly-loaded
    # relationships.  The service layer later loads the same entity with
    # selectinload() options — but SQLAlchemy returns the cached (bare)
    # instance, so relationship access triggers a lazy load that fails in
    # async context ("greenlet_spawn has not been called").
    row = (await db.execute(
        select(entity_model.timeline_items).where(entity_model.id == numeric_id)  # type: ignore[union-attr]
    )).first()

    if row is None:
        raise McpNotFoundError(target_not_found_message)

    # Check for existing item with same item_id (idempotency)
    timeline_items = row[0] or []
    existing_item = timeline_service.find_item_by_id(timeline_items, item_id)
    if existing_item:
        return _existing_timeline_item_output(item_id, existing_item)

    # Dry-run mode
    if not commit:
        return AddTimelineItemOutput(
            mode="dry_run",
            item_id=item_id,
            created_at=None,
            author=created_by,
            message="Dry-run preview - no changes made",
        )

    # Build typed timeline item and delegate to the service layer.
    timestamp = datetime.now(timezone.utc)
    created_at_value = created_at if created_at is not None else timestamp
    note_item = NoteItem(
        id=item_id,
        description=body,
        created_at=created_at_value,
        timestamp=timestamp,
        created_by=created_by,
    )

    result = await add_timeline_item_and_commit(
        db,
        entity_id=numeric_id,
        entity_type=target_kind,
        timeline_item=note_item,
        performed_by=created_by,
        created_at_override=created_at,
        preserve_item_id=True,
        idempotent=True,
    )
    if result is None:
        raise McpNotFoundError(target_not_found_message)

    if not result.created:
        return _existing_timeline_item_output(item_id, result.item)

    return AddTimelineItemOutput(
        mode="committed",
        item_id=item_id,
        created_at=created_at_value,
        author=created_by,
        message=(
            f"Timeline item added successfully to {target_kind} {target_human_id}"
        ),
    )


async def get_item(
    db: AsyncSession,
    parent_entity_type: str,
    parent_entity_id: str,
    item_id: str,
    mode: str = "full",
    max_chars: int = 4000,
    cursor: Optional[str] = None,
) -> GetItemOutput:
    """Get full content of truncated timeline item.

    Supports pagination for very large items.

    Args:
        db: Database session
        parent_entity_type: Parent entity type ("alert", "case", "task")
        parent_entity_id: Parent entity ID in forgiving format
        item_id: Timeline item ID
        mode: Retrieval mode ("full", "head", "tail")
        max_chars: Max characters to return (100-10000, default: 4000)
        cursor: Pagination cursor from previous response

    Returns:
        Dictionary with item_id, content, metadata, next_cursor, is_truncated

    Raises:
        McpValidationError: A parent or retrieval argument is invalid.
        McpNotFoundError: The parent or timeline item does not exist.
    """
    # Validate max_chars
    max_chars = _clamp_int(max_chars, minimum=100, maximum=10_000)

    # Validate mode
    if mode not in ("full", "head", "tail"):
        raise McpValidationError(
            f"Invalid mode '{mode}'. Must be 'full', 'head', or 'tail'."
        )

    parent_kind = parent_entity_type
    _work_item_model(parent_kind, field_name="parent_entity_type")
    numeric_id, canonical_prefix = _parse_work_item_id(
        parent_entity_id,
        parent_kind,
    )
    parent_human_id = format_entity_id(numeric_id, canonical_prefix)
    table_name = _GET_ITEM_PARENT_TABLES[parent_kind]

    # Table name is selected from the hardcoded map above; all user input is
    # passed as query parameters.
    query = text(f"""
        WITH parent AS (
            SELECT
                id,
                timeline_items,
                CASE
                    WHEN jsonb_typeof(timeline_items) = 'object'
                        AND timeline_items ? :item_id
                    THEN timeline_items -> :item_id
                    ELSE NULL
                END AS top_level_item
            FROM {table_name}
            WHERE id = :parent_id
        )
        SELECT
            id,
            COALESCE(
                top_level_item,
                jsonb_path_query_first(
                    timeline_items,
                    '$.** ? (@.id == $item_id)'::jsonpath,
                    jsonb_build_object('item_id', to_jsonb(CAST(:item_id AS text)))
                )
            ) AS item
        FROM parent
    """)
    row = (
        await db.execute(query, {"parent_id": numeric_id, "item_id": item_id})
    ).mappings().one_or_none()

    if row is None:
        raise McpNotFoundError(
            f"{parent_kind.capitalize()} {parent_human_id} not found"
        )

    found_item = row["item"]

    if not isinstance(found_item, dict):
        raise McpNotFoundError(
            f"Timeline item '{item_id}' not found under {parent_kind} "
            f"{parent_human_id}. get_item no longer searches other alerts, "
            "cases, or tasks; send the correct parent_entity_type and "
            "parent_entity_id."
        )

    full_content = _timeline_item_content(found_item)
    content, new_offset = _slice_timeline_content(
        full_content,
        mode=mode,
        max_chars=max_chars,
        offset=_cursor_offset(cursor),
    )

    # Check if truncated
    is_truncated = new_offset < len(full_content)

    # Build next cursor
    next_cursor = None
    if is_truncated:
        next_cursor = _encode_cursor({"offset": new_offset})

    # Build metadata
    timestamp_dt = (
        _parse_iso_datetime(found_item.get("timestamp"))
        or datetime.now(timezone.utc)
    )

    metadata = ItemMetadata(
        type=_timeline_item_type(found_item),
        timestamp=timestamp_dt,
        author=_timeline_item_author(found_item),
        parent_kind=parent_kind,
        parent_id=numeric_id,
        parent_human_id=parent_human_id,
    )

    return GetItemOutput(
        item_id=item_id,
        content=content,
        metadata=metadata,
        next_cursor=next_cursor,
        is_truncated=is_truncated,
    )
