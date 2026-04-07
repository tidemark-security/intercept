"""MCP service layer for tool implementations.

This service provides business logic for MCP tools, coordinating between
various backend services to fulfill MCP tool requests.
"""

import asyncio
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, cast
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.id_parser import parse_entity_id, format_entity_id, get_prefix_for_kind, ALERT_PREFIX
from app.models.models import Alert, Case, Task
from app.models.enums import AlertStatus, CaseStatus, TaskStatus, Priority, TriageDisposition
from app.mcp.schemas import (
    GetSummaryOutput,
    ObjectHeader,
    TimelineSection,
    TimelinePreview,
    ObservablesSection,
    RelatedCounts,
    Resource,
    RecordTriageDecisionOutput,
    SuggestedPatch,
    ListWorkOutput,
    FindRelatedOutput,
    AddTimelineItemOutput,
    GetItemOutput,
    ItemMetadata,
    ValidateMermaidOutput,
    WorkItemPreview,
    RelatedMatch,
)
from app.services.observable_service import extract_observables, extract_high_signal_entities
from app.services.similarity_service import count_similar_alerts
from app.services import triage_recommendation_service


_MERMAID_VALIDATION_TIMEOUT_SECONDS = 10
_MERMAID_MAX_ERROR_LINES = 10
_MERMAID_VALIDATOR_SCRIPT_CANDIDATES = (
    Path("/opt/mermaid-validator/validate_mermaid_syntax.mjs"),
    Path(__file__).resolve().parents[2] / "scripts" / "mermaid-validator" / "validate_mermaid_syntax.mjs",
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


def _build_timeline_preview_text(item: Dict[str, Any]) -> str:
    """Build a concise preview string tailored to the timeline item type."""
    item_type = item.get("type", "")
    description = str(item.get("description") or "").strip()

    if item_type == "observable":
        observable_value = str(item.get("observable_value") or item.get("value") or "").strip()
        if observable_value and description:
            return f"{observable_value}: {description}"
        if observable_value:
            return observable_value
        return description

    return str(item.get("body") or item.get("content") or description).strip()


def _resolve_mermaid_validator_command() -> list[str]:
    """Resolve parser-based Mermaid validator dependencies and invocation command."""
    node_path = shutil.which("node")
    if not node_path:
        raise HTTPException(
            status_code=503,
            detail="Mermaid validation is unavailable because 'node' is not installed on PATH.",
        )

    for script_path in _MERMAID_VALIDATOR_SCRIPT_CANDIDATES:
        if script_path.exists():
            return [node_path, str(script_path)]

    raise HTTPException(
        status_code=503,
        detail="Mermaid validation is unavailable because the parser script is missing.",
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
        HTTPException(503): Validator dependencies are unavailable or cannot launch.
        HTTPException(504): Validator timed out during validation.
    """
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
            raise HTTPException(
                status_code=504,
                detail="Mermaid validation timed out while invoking parser validator.",
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
            raise HTTPException(
                status_code=503,
                detail="Mermaid validation is unavailable because parser validator could not run correctly.",
            )

        error_lines = _collect_mermaid_error_lines(stderr_text, stdout_text)
        if not error_lines:
            error_lines = ["Mermaid validation failed."]

        if _is_invalid_mermaid_failure(combined_output) or error_lines:
            return ValidateMermaidOutput(
                valid=False,
                message="Mermaid diagram syntax is invalid.",
                errors=error_lines,
            )

        raise HTTPException(
            status_code=503,
            detail="Mermaid validation failed due to an unexpected parser validator error.",
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="Mermaid validation is unavailable because parser dependencies are missing.",
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
        HTTPException(400): Invalid ID format or kind
        HTTPException(404): Entity not found
    """
    # Parse entity ID
    numeric_id, canonical_prefix = parse_entity_id(id_str, kind)
    human_id = format_entity_id(numeric_id, canonical_prefix)
    
    # Parse since timestamp if provided
    since_dt: Optional[datetime] = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid 'since' timestamp format: {since}. Expected ISO-8601."
            )
    
    # Fetch entity based on kind
    if kind == "alert":
        entity = await db.get(Alert, numeric_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Alert {human_id} not found")
    elif kind == "case":
        entity = await db.get(Case, numeric_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Case {human_id} not found")
    elif kind == "task":
        entity = await db.get(Task, numeric_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Task {human_id} not found")
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid kind '{kind}'. Must be 'alert', 'case', or 'task'."
        )
    
    # Build header
    header = ObjectHeader(
        title=entity.title,
        status=entity.status.value if hasattr(entity.status, 'value') else str(entity.status),
        priority=entity.priority.value if entity.priority and hasattr(entity.priority, 'value') else (str(entity.priority) if entity.priority else None),
        assignee=entity.assignee,
        source=getattr(entity, 'source', None),  # Alert only
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )
    
    # Get timeline items
    from app.services.timeline_service import timeline_service

    timeline_items: List[Dict[str, Any]] = timeline_service._response_items(entity.timeline_items)
    
    # Apply since filter if provided
    if since_dt:
        timeline_items = [
            item for item in timeline_items
            if item.get('timestamp') and datetime.fromisoformat(str(item['timestamp'])) >= since_dt
        ]
    
    # Sort by timestamp (newest first)
    timeline_items.sort(
        key=lambda x: x.get('timestamp', ''),
        reverse=True
    )
    
    # Bound timeline
    total_count = len(timeline_items)
    bounded_timeline = timeline_items[:max_timeline_items]
    omitted_count = max(0, total_count - len(bounded_timeline))
    
    # Build timeline previews
    timeline_previews = []
    for item in bounded_timeline:
        # Extract key fields
        item_id = item.get('id', 'unknown')
        item_type = item.get('type', 'note')
        timestamp_str = item.get('timestamp', entity.created_at.isoformat())
        
        # Parse timestamp
        try:
            timestamp = datetime.fromisoformat(str(timestamp_str))
        except:
            timestamp = entity.created_at
        
        author = item.get('author')

        # Generate preview from item content with observable-specific formatting.
        body = _build_timeline_preview_text(item)
        preview = body[:200]
        is_truncated = len(body) > 200
        observable_type = None
        observable_value = None
        enrichment_status = item.get('enrichment_status') if 'enrichment_status' in item else None
        enrichments = item.get('enrichments') if isinstance(item.get('enrichments'), dict) else None
        
        # Extract entity_id for linked items (alerts, tasks, cases)
        entity_id = None
        if item_type == 'alert':
            alert_id = item.get('alert_id')
            if alert_id is not None:
                entity_id = format_entity_id(alert_id, get_prefix_for_kind('alert'))
        elif item_type == 'task':
            task_id = item.get('task_id')
            if task_id is not None:
                entity_id = format_entity_id(task_id, get_prefix_for_kind('task'))
        elif item_type == 'case':
            case_id = item.get('case_id')
            if case_id is not None:
                entity_id = format_entity_id(case_id, get_prefix_for_kind('case'))
        elif item_type == 'observable':
            raw_observable_type = item.get('observable_type')
            raw_observable_value = item.get('observable_value') or item.get('value')
            observable_type = str(raw_observable_type) if raw_observable_type else None
            observable_value = str(raw_observable_value) if raw_observable_value else None
        
        timeline_previews.append(TimelinePreview(
            timeline_id=str(item_id),
            type=item_type,
            timestamp=timestamp,
            author=author,
            preview=preview,
            is_truncated=is_truncated,
            full_length_chars=len(body) if is_truncated else None,
            entity_id=entity_id,
            observable_type=observable_type,
            observable_value=observable_value,
            enrichment_status=enrichment_status,
            enrichments=enrichments,
        ))
    
    timeline_section = TimelineSection(
        items=timeline_previews,
        total_count=total_count,
        omitted_count=omitted_count,
        bounded_by="since" if since_dt else "max_timeline_items",
    )
    
    # Extract observables from ALL timeline items (not just bounded)
    observables = extract_observables(timeline_items, max_observables)
    observables_section = ObservablesSection(
        items=observables,
        total_count=len(observables),
        omitted_count=0,  # extract_observables already limits
    )
    
    # Count related items
    related_counts = RelatedCounts()
    
    if kind == "alert":
        # Type narrowing: entity is Alert in this branch
        alert_entity = cast(Alert, entity)
        # Count similar alerts (based on similarity key)
        similar_count = await count_similar_alerts(db, alert_entity, days=30)
        related_counts.similar_alerts = similar_count
        
        # Count linked case
        if alert_entity.case_id:
            related_counts.linked_cases = 1
    
    elif kind == "case":
        # Count linked alerts using explicit async query (avoid lazy loading)
        alert_count_result = await db.execute(
            select(func.count(Alert.id)).where(Alert.case_id == entity.id)
        )
        related_counts.linked_alerts = alert_count_result.scalar() or 0
        
        # Count linked tasks using explicit async query (avoid lazy loading)
        task_count_result = await db.execute(
            select(func.count(Task.id)).where(Task.case_id == entity.id)
        )
        related_counts.linked_tasks = task_count_result.scalar() or 0
    
    elif kind == "task":
        # Count linked case
        if getattr(entity, 'case_id', None):
            related_counts.linked_cases = 1
    
    # Build resource links
    base_url = "http://localhost:3000"  # TODO: Get from config
    resources = [
        Resource(
            label=f"View {kind.capitalize()}",
            url=f"{base_url}/{kind}s/{human_id}"
        )
    ]
    
    return GetSummaryOutput(
        kind=kind,
        id=numeric_id,
        human_id=human_id,
        header=header,
        timeline=timeline_section,
        observables=observables_section,
        related_counts=related_counts,
        resources=resources,
    )


async def record_triage_decision(
    db: AsyncSession,
    alert_id_str: str,
    disposition: str,
    confidence: float,
    reasoning_bullets: Optional[List[str]] = None,
    recommended_actions: Optional[List[str]] = None,
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
        recommended_actions: Suggested next steps
        suggested_status: Optional status patch
        suggested_priority: Optional priority patch
        suggested_assignee: Optional assignee patch
        suggested_tags_add: Tags to add
        suggested_tags_remove: Tags to remove
        request_escalate_to_case: Request case creation
        commit: If false, returns dry-run preview only
        created_by: Username from API key
        
    Returns:
        RecordTriageDecisionOutput with mode, suggested_patches, status
        
    Raises:
        HTTPException(400): Invalid ID format
        HTTPException(404): Alert not found
    """
    # Parse alert ID
    numeric_id, canonical_prefix = parse_entity_id(alert_id_str, "alert")
    
    # Get alert to verify it exists and build patches
    alert = await db.get(Alert, numeric_id)
    if not alert:
        raise HTTPException(
            status_code=404,
            detail=f"Alert {format_entity_id(numeric_id, canonical_prefix)} not found"
        )

    normalized_suggested_status = suggested_status
    if not normalized_suggested_status:
        try:
            disposition_enum = TriageDisposition(disposition)
            inferred_status = triage_recommendation_service.DISPOSITION_TO_CLOSED_STATUS.get(disposition_enum)
            normalized_suggested_status = inferred_status.value if inferred_status else None
        except ValueError:
            normalized_suggested_status = None
    
    # Build suggested patches
    suggested_patches = []
    
    if normalized_suggested_status and normalized_suggested_status != alert.status.value:
        suggested_patches.append(SuggestedPatch(
            field="status",
            current_value=alert.status.value,
            new_value=normalized_suggested_status,
        ))
    
    if suggested_priority and (not alert.priority or suggested_priority != alert.priority.value):
        suggested_patches.append(SuggestedPatch(
            field="priority",
            current_value=alert.priority.value if alert.priority else None,
            new_value=suggested_priority,
        ))
    
    if suggested_assignee and suggested_assignee != alert.assignee:
        suggested_patches.append(SuggestedPatch(
            field="assignee",
            current_value=alert.assignee,
            new_value=suggested_assignee,
        ))
    
    if suggested_tags_add:
        for tag in suggested_tags_add:
            if tag not in (alert.tags or []):
                suggested_patches.append(SuggestedPatch(
                    field="tags",
                    current_value=None,
                    new_value=f"add:{tag}",
                ))
    
    if suggested_tags_remove:
        for tag in suggested_tags_remove:
            if tag in (alert.tags or []):
                suggested_patches.append(SuggestedPatch(
                    field="tags",
                    current_value=tag,
                    new_value=f"remove:{tag}",
                ))
    
    # Dry-run mode
    if not commit:
        return RecordTriageDecisionOutput(
            mode="dry_run",
            recommendation_id=None,
            suggested_patches=suggested_patches,
            status="PENDING",
            message="Dry-run preview - no changes made",
        )
    
    # Build recommendation data
    data = {
        "disposition": disposition,
        "confidence": confidence,
        "reasoning_bullets": reasoning_bullets or [],
        "recommended_actions": recommended_actions or [],
        "suggested_status": normalized_suggested_status,
        "suggested_priority": suggested_priority,
        "suggested_assignee": suggested_assignee,
        "suggested_tags_add": suggested_tags_add or [],
        "suggested_tags_remove": suggested_tags_remove or [],
        "request_escalate_to_case": request_escalate_to_case,
    }
    
    # Check if existing recommendation
    existing = await triage_recommendation_service.get_by_alert_id(db, numeric_id)
    
    # Create or replace recommendation
    recommendation = await triage_recommendation_service.create_or_replace_recommendation(
        db=db,
        alert_id=numeric_id,
        data=data,
        created_by=created_by,
    )
    
    mode = "replaced" if existing else "committed"
    
    return RecordTriageDecisionOutput(
        mode=mode,
        recommendation_id=recommendation.id,
        suggested_patches=suggested_patches,
        status="PENDING",
        message=f"Recommendation {mode} successfully. Status: PENDING until analyst reviews.",
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
        HTTPException(400): Invalid parameters
    """
    from datetime import timedelta
    from sqlmodel import or_, and_, func
    import base64
    import json
    
    # Enforce limit
    limit = min(max(1, limit), 50)
    
    # Determine entity model
    if kind == "alert":
        model = Alert
    elif kind == "case":
        model = Case
    elif kind == "task":
        model = Task
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid kind '{kind}'. Must be 'alert', 'case', or 'task'."
        )
    
    # Build base query
    query = select(model)
    
    # Apply time range filter (default: last 7 days)
    if time_range_start:
        try:
            start_dt = datetime.fromisoformat(time_range_start.replace('Z', '+00:00'))
            query = query.where(model.created_at >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid time_range_start format: {time_range_start}"
            )
    else:
        # Default: last 7 days
        default_start = datetime.now(timezone.utc) - timedelta(days=7)
        query = query.where(model.created_at >= default_start)
    
    if time_range_end:
        try:
            end_dt = datetime.fromisoformat(time_range_end.replace('Z', '+00:00'))
            query = query.where(model.created_at <= end_dt)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid time_range_end format: {time_range_end}"
            )
    
    # Apply status filter with normalization for alerts
    if statuses:
        normalized_statuses = list(statuses)  # Copy to avoid mutating input
        
        # For alerts, expand "CLOSED" shorthand to all closed variants
        if kind == "alert" and "CLOSED" in normalized_statuses:
            normalized_statuses.remove("CLOSED")
            # Add all closed alert statuses
            closed_variants = [
                "CLOSED_TP",
                "CLOSED_BP", 
                "CLOSED_FP",
                "CLOSED_UNRESOLVED",
                "CLOSED_DUPLICATE",
            ]
            for variant in closed_variants:
                if variant not in normalized_statuses:
                    normalized_statuses.append(variant)
        
        # Convert string statuses to enum values for proper comparison
        if kind == "alert":
            status_enum = AlertStatus
        elif kind == "case":
            status_enum = CaseStatus
        else:  # task
            status_enum = TaskStatus
        
        try:
            enum_statuses = [status_enum(s) for s in normalized_statuses]
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status value: {e}"
            )
        
        query = query.where(model.status.in_(enum_statuses))  # type: ignore[union-attr]
    
    # Apply priority filter (convert strings to Priority enum)
    if priorities and hasattr(model, 'priority'):
        try:
            enum_priorities = [Priority(p) for p in priorities]
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid priority value: {e}"
            )
        query = query.where(model.priority.in_(enum_priorities))  # type: ignore[union-attr]
    
    # Apply assignee filter
    if assignees:
        query = query.where(model.assignee.in_(assignees))  # type: ignore[union-attr]
    
    # Apply contains filter (title + description only, NOT timeline)
    if contains:
        search_term = f"%{contains}%"
        query = query.where(
            or_(
                model.title.ilike(search_term),  # type: ignore[union-attr]
                model.description.ilike(search_term) if hasattr(model, 'description') else False  # type: ignore[union-attr]
            )
        )
    
    # Handle pagination cursor
    if cursor:
        try:
            cursor_data = json.loads(base64.b64decode(cursor).decode())
            last_id = cursor_data.get("last_id")
            if last_id:
                query = query.where(model.id > last_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid cursor")
    
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
        cursor_data = {"last_id": items[-1].id}
        next_cursor = base64.b64encode(json.dumps(cursor_data).encode()).decode()
    
    # Get total count (approximation for performance)
    # In production, consider caching this or using explain
    count_query = select(func.count(model.id))
    if time_range_start or time_range_end or statuses or priorities or assignees or contains:
        # Apply same filters to count query
        # (simplified - copy filter logic from above)
        pass  # For now, return count of current page
    
    total_count = len(items)  # Simplified
    
    # Build response items
    work_items = []
    for item in items:
        prefix = get_prefix_for_kind(kind)
        
        human_id = format_entity_id(item.id, prefix)
        
        work_items.append(WorkItemPreview(
            id=item.id,
            human_id=human_id,
            title=item.title,
            status=item.status.value if hasattr(item.status, 'value') else str(item.status),
            priority=item.priority.value if item.priority and hasattr(item.priority, 'value') else (str(item.priority) if item.priority else None),
            assignee=item.assignee,
            created_at=item.created_at,
            updated_at=item.updated_at,
            source=getattr(item, 'source', None),
        ))
    
    return ListWorkOutput(
        items=work_items,
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
        HTTPException(400): Invalid ID format or kind
        HTTPException(404): Seed entity not found
    """
    from app.services.similarity_service import find_related_alerts
    
    # Parse seed ID
    numeric_id, canonical_prefix = parse_entity_id(seed_id_str, seed_kind)
    human_id = format_entity_id(numeric_id, canonical_prefix)
    
    # Fetch seed entity - use explicit typing per branch
    seed_entity: Union[Alert, Case, Task]
    if seed_kind == "alert":
        alert_entity = await db.get(Alert, numeric_id)
        if not alert_entity:
            raise HTTPException(
                status_code=404,
                detail=f"Alert {human_id} not found"
            )
        seed_entity = alert_entity
    elif seed_kind == "case":
        case_entity = await db.get(Case, numeric_id)
        if not case_entity:
            raise HTTPException(
                status_code=404,
                detail=f"Case {human_id} not found"
            )
        seed_entity = case_entity
    elif seed_kind == "task":
        task_entity = await db.get(Task, numeric_id)
        if not task_entity:
            raise HTTPException(
                status_code=404,
                detail=f"Task {human_id} not found"
            )
        seed_entity = task_entity
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid seed_kind '{seed_kind}'. Must be 'alert', 'case', or 'task'."
        )
    
    # At this point seed_entity.id is guaranteed to be int (not None) since we fetched by ID
    assert seed_entity.id is not None
    
    # Build seed preview
    seed = WorkItemPreview(
        id=seed_entity.id,
        human_id=human_id,
        title=seed_entity.title,
        status=seed_entity.status.value if hasattr(seed_entity.status, 'value') else str(seed_entity.status),
        priority=seed_entity.priority.value if seed_entity.priority and hasattr(seed_entity.priority, 'value') else (str(seed_entity.priority) if seed_entity.priority else None),
        assignee=seed_entity.assignee,
        created_at=seed_entity.created_at,
        updated_at=seed_entity.updated_at,
        source=getattr(seed_entity, 'source', None),
    )
    
    # Find related items (currently only implemented for alerts)
    matches_list: List[RelatedMatch] = []
    
    if seed_kind == "alert":
        # Type narrowing: seed_entity is Alert in this branch
        alert_seed = cast(Alert, seed_entity)
        # Find related alerts
        raw_matches = await find_related_alerts(db, alert_seed, max_matches)
        
        for match_data in raw_matches:
            match_alert = match_data["alert"]
            match_human_id = format_entity_id(match_alert.id, ALERT_PREFIX)
            
            matches_list.append(RelatedMatch(
                kind="alert",
                id=match_alert.id,
                human_id=match_human_id,
                title=match_alert.title,
                status=match_alert.status.value if hasattr(match_alert.status, 'value') else str(match_alert.status),
                priority=match_alert.priority.value if match_alert.priority and hasattr(match_alert.priority, 'value') else (str(match_alert.priority) if match_alert.priority else None),
                score=match_data["score"],
                why=match_data["reasons"],
            ))
    
    # For cases and tasks, return empty matches for now
    # (could extend in future to find related by linked entities)
    
    return FindRelatedOutput(
        seed=seed,
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
        created_at: Timestamp when item was created. Defaults to current time if not specified.
        
    Returns:
        Dictionary with mode, item_id, created_at, author, message
        
    Raises:
        HTTPException(400): Invalid ID format, kind, or body too long
        HTTPException(404): Target entity not found
    """
    from app.mcp.schemas import AddTimelineItemOutput
    from app.models.models import NoteItem
    from app.services.alert_service import alert_service
    from app.services.case_service import case_service
    from app.services.task_service import task_service
    
    # Validate body length
    if len(body) > 16000:
        raise HTTPException(
            status_code=400,
            detail=f"Body too long: {len(body)} chars (max 16,000)"
        )
    
    # Validate target_kind
    if target_kind not in ("alert", "case", "task"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target_kind '{target_kind}'. Must be 'alert', 'case', or 'task'."
        )
    
    # Parse target ID
    numeric_id, canonical_prefix = parse_entity_id(target_id_str, target_kind)
    
    # Idempotency + existence check using a lightweight column query.
    # IMPORTANT: We must NOT load the full entity via db.get() here, because
    # that would place it in the session identity map without eagerly-loaded
    # relationships.  The service layer later loads the same entity with
    # selectinload() options — but SQLAlchemy returns the cached (bare)
    # instance, so relationship access triggers a lazy load that fails in
    # async context ("greenlet_spawn has not been called").
    entity_model = {"alert": Alert, "case": Case, "task": Task}[target_kind]
    row = (await db.execute(
        select(entity_model.timeline_items).where(entity_model.id == numeric_id)  # type: ignore[union-attr]
    )).first()
    
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"{target_kind.capitalize()} {format_entity_id(numeric_id, canonical_prefix)} not found"
        )
    
    # Check for existing item with same item_id (idempotency)
    timeline_items = row[0] or []
    for existing_item in timeline_items:
        if existing_item.get("id") == item_id:
            return AddTimelineItemOutput(
                mode="already_exists",
                item_id=item_id,
                created_at=datetime.fromisoformat(existing_item.get("timestamp", "")),
                author=existing_item.get("author"),
                message=f"Item {item_id} already exists (idempotent)",
            )
    
    # Dry-run mode
    if not commit:
        return AddTimelineItemOutput(
            mode="dry_run",
            item_id=item_id,
            created_at=None,
            author=created_by,
            message="Dry-run preview - no changes made",
        )
    
    # Build typed timeline item and delegate to the service layer
    timestamp = created_at if created_at else datetime.now(timezone.utc)
    note_item = NoteItem(
        id=item_id,
        description=body,
        created_at=timestamp,
        timestamp=timestamp,
        created_by=created_by,
    )
    
    service_map = {
        "alert": lambda: alert_service.add_timeline_item(db, numeric_id, note_item, created_by),
        "case": lambda: case_service.add_timeline_item(db, numeric_id, note_item, created_by),
        "task": lambda: task_service.add_timeline_item(db, numeric_id, note_item, created_by),
    }
    
    result = await service_map[target_kind]()
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"{target_kind.capitalize()} {format_entity_id(numeric_id, canonical_prefix)} not found"
        )
    
    return AddTimelineItemOutput(
        mode="committed",
        item_id=item_id,
        created_at=timestamp,
        author=created_by,
        message=f"Timeline item added successfully to {target_kind} {format_entity_id(numeric_id, canonical_prefix)}",
    )


async def get_item(
    db: AsyncSession,
    item_id: str,
    mode: str = "full",
    max_chars: int = 4000,
    cursor: Optional[str] = None,
    hint_kind: Optional[str] = None,
    hint_parent_id: Optional[str] = None,
) -> GetItemOutput:
    """Get full content of truncated timeline item.
    
    Supports pagination for very large items.
    
    Args:
        db: Database session
        item_id: Timeline item ID
        mode: Retrieval mode ("full", "head", "tail")
        max_chars: Max characters to return (100-10000, default: 4000)
        cursor: Pagination cursor from previous response
        hint_kind: Optional entity type hint for faster lookup
        hint_parent_id: Optional parent entity ID hint
        
    Returns:
        Dictionary with item_id, content, metadata, next_cursor, is_truncated
        
    Raises:
        HTTPException(400): Invalid parameters
        HTTPException(404): Item not found
    """
    import base64
    import json
    from app.services.timeline_service import timeline_service
    
    # Validate max_chars
    max_chars = min(max(100, max_chars), 10000)
    
    # Validate mode
    if mode not in ("full", "head", "tail"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{mode}'. Must be 'full', 'head', or 'tail'."
        )
    
    # Search for item
    # If hints provided, search only in hinted entity
    # Otherwise, search across all alerts, cases, tasks
    
    found_item = None
    parent_entity = None
    parent_kind = None
    
    if hint_kind and hint_parent_id:
        # Use hints for faster lookup
        try:
            numeric_id, _ = parse_entity_id(hint_parent_id, hint_kind)
            
            if hint_kind == "alert":
                parent_entity = await db.get(Alert, numeric_id)
                parent_kind = "alert"
            elif hint_kind == "case":
                parent_entity = await db.get(Case, numeric_id)
                parent_kind = "case"
            elif hint_kind == "task":
                parent_entity = await db.get(Task, numeric_id)
                parent_kind = "task"
            
            if parent_entity:
                for item in timeline_service._iter_items(parent_entity.timeline_items):
                    if item.get("id") == item_id:
                        found_item = item
                        break
        except:
            pass  # Ignore hint errors, fallback to full search
    
    # Full search if not found with hints
    if not found_item:
        # Search alerts
        from sqlmodel import select
        
        for model, kind in [(Alert, "alert"), (Case, "case"), (Task, "task")]:
            query = select(model)
            result = await db.execute(query)
            entities = result.scalars().all()
            
            for entity in entities:
                for item in timeline_service._iter_items(entity.timeline_items):
                    if item.get("id") == item_id:
                        found_item = item
                        parent_entity = entity
                        parent_kind = kind
                        break
                if found_item:
                    break
            
            if found_item:
                break
    
    if not found_item:
        raise HTTPException(
            status_code=404,
            detail=f"Timeline item '{item_id}' not found"
        )
    
    # Extract content from item.
    # Notes are stored under the canonical timeline field `description`,
    # while older items may still use `body` or `content`.
    full_content = found_item.get("body") or found_item.get("content") or found_item.get("description") or ""
    
    # Handle pagination cursor
    offset = 0
    if cursor:
        try:
            cursor_data = json.loads(base64.b64decode(cursor).decode())
            offset = cursor_data.get("offset", 0)
        except:
            pass  # Ignore invalid cursor
    
    # Apply mode and max_chars
    if mode == "full":
        content = full_content[offset:offset + max_chars]
        new_offset = offset + len(content)
    elif mode == "head":
        content = full_content[:max_chars]
        new_offset = len(content)
    elif mode == "tail":
        start_pos = max(0, len(full_content) - max_chars)
        content = full_content[start_pos:]
        new_offset = len(full_content)
    
    # Check if truncated
    is_truncated = new_offset < len(full_content)
    
    # Build next cursor
    next_cursor = None
    if is_truncated:
        cursor_data = {"offset": new_offset}
        next_cursor = base64.b64encode(json.dumps(cursor_data).encode()).decode()
    
    # Build metadata
    timestamp = found_item.get("timestamp")
    if timestamp:
        try:
            timestamp_dt = datetime.fromisoformat(str(timestamp))
        except:
            timestamp_dt = datetime.now(timezone.utc)
    else:
        timestamp_dt = datetime.now(timezone.utc)
    
    # Guard against None (shouldn't happen since found_item implies parent_entity was found)
    if parent_kind is None or parent_entity is None:
        raise HTTPException(
            status_code=500,
            detail="Internal error: parent entity not found for timeline item"
        )
    
    # parent_entity.id is guaranteed non-None since it was fetched from DB
    assert parent_entity.id is not None
    
    prefix = get_prefix_for_kind(parent_kind)
    
    metadata = ItemMetadata(
        type=found_item.get("type", "note"),
        timestamp=timestamp_dt,
        author=found_item.get("author"),
        parent_kind=parent_kind,
        parent_id=parent_entity.id,
        parent_human_id=format_entity_id(parent_entity.id, prefix),
    )
    
    return GetItemOutput(
        item_id=item_id,
        content=content,
        metadata=metadata,
        next_cursor=next_cursor,
        is_truncated=is_truncated,
    )
