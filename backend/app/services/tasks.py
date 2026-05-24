"""
Background task handlers for LangFlow operations.

Defines task handlers for:
- Long-running LangFlow chat operations
- Batch processing
- Scheduled tasks
- Alert triage via LangFlow
- Terminal failure hooks for retried worker tasks
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any
from uuid import UUID, uuid4

from pgqueuer.errors import MaxRetriesExceeded, MaxTimeExceeded

from app.services.task_queue_service import get_task_queue_service
from app.services.langflow_service import LangFlowService, LangFlowConfigurationError
from app.services.realtime_service import emit_event
from app.services.settings_service import SettingsService
from app.core.database import async_session_factory
from app.services.enrichment.service import enrichment_service
from app.services.enrichment.bulk_sync_schedule_sync import (
    sync_bulk_sync_schedule_for_provider,
    sync_bulk_sync_schedules,
)
from app.services.maxmind_service import maxmind_service

logger = logging.getLogger(__name__)


# Task names
TASK_LANGFLOW_CHAT = "langflow_chat"
TASK_LANGFLOW_BATCH = "langflow_batch"
TASK_TRIAGE_ALERT = "triage_alert"
TASK_AUTONOMOUS_TASK = "autonomous_task"
TASK_ENRICH_ITEM = "enrich_item"
TASK_DIRECTORY_SYNC = "directory_sync"
TASK_MAXMIND_UPDATE = "maxmind_update"
TASK_REFRESH_BULK_SYNC_SCHEDULES = "refresh_bulk_sync_schedules"


def _unwrap_terminal_failure(exc: Exception) -> Exception:
    current = exc
    seen: set[int] = set()
    while getattr(current, "__cause__", None) is not None and id(current) not in seen:
        seen.add(id(current))
        current = current.__cause__  # type: ignore[assignment]
    if isinstance(current, Exception):
        return current
    return exc


def _format_terminal_failure_message(exc: Exception) -> str:
    root_cause = _unwrap_terminal_failure(exc)
    root_message = str(root_cause).strip() or root_cause.__class__.__name__

    if isinstance(exc, MaxTimeExceeded):
        return f"Retry time limit exceeded: {root_message}"
    if isinstance(exc, MaxRetriesExceeded):
        return f"Retries exhausted: {root_message}"
    return root_message


async def _handle_triage_terminal_failure(payload: Dict[str, Any], exc: Exception) -> None:
    """Mark triage as failed only after retry exhaustion."""
    await _mark_triage_failed(int(payload["alert_id"]), _format_terminal_failure_message(exc))


async def _handle_enrich_item_terminal_failure(
    payload: Dict[str, Any],
    exc: Exception,
    *,
    task_id: str | None = None,
) -> None:
    """Mark enrichment as failed after retry exhaustion."""
    async with async_session_factory() as db:
        await enrichment_service.mark_item_enrichment_failed(
            db,
            entity_type=str(payload["entity_type"]),
            entity_id=int(payload["entity_id"]),
            item_id=str(payload["item_id"]),
            error_message=_format_terminal_failure_message(exc),
            task_id=task_id,
        )


async def _handle_autonomous_task_terminal_failure(payload: Dict[str, Any], exc: Exception) -> None:
    """Record autonomous task failure after retry exhaustion."""
    await _record_autonomous_task_failure(
        int(payload["task_id"]),
        str(payload.get("agent_username") or "AI agent"),
        _format_terminal_failure_message(exc),
    )


async def _handle_directory_sync_terminal_failure(payload: Dict[str, Any], exc: Exception) -> None:
    """Re-enqueue the next scheduled bulk sync after terminal failure."""
    if not bool(payload.get("reschedule", False)):
        return

    provider_id = str(payload["provider_id"])
    logger.warning(
        "Directory sync failed after retries; scheduling next occurrence",
        extra={"provider_id": provider_id, "error": _format_terminal_failure_message(exc)},
    )

    async with async_session_factory() as db:
        await sync_bulk_sync_schedule_for_provider(db, provider_id)


async def handle_langflow_chat(payload: Dict[str, Any]):
    """
    Handle a background LangFlow chat task.
    
    Payload:
        session_id: UUID of the session
        message: User message content
        flow_id: LangFlow flow identifier
        context: Optional conversation context
    """
    session_id = UUID(payload["session_id"])
    message = payload["message"]
    flow_id = payload["flow_id"]
    context = payload.get("context", {})
    
    logger.info(
        f"Processing LangFlow chat task",
        extra={
            "session_id": str(session_id),
            "flow_id": flow_id,
        }
    )
    
    # Get database session
    async with async_session_factory() as db:
        # Get LangFlow service
        settings_service = SettingsService(db)
        langflow_service = await LangFlowService.from_settings(settings_service)
        
        try:
            # Send message to LangFlow
            response = await langflow_service.send_message(
                flow_id=flow_id,
                message=message,
                session_id=session_id,
                context=context,
            )
            
            logger.info(
                f"LangFlow chat task completed",
                extra={
                    "session_id": str(session_id),
                    "response_length": len(str(response)),
                }
            )
            
            # TODO: Store response in database (session messages)
            # This would be implemented based on your requirements
            
        finally:
            await langflow_service.close()


async def handle_langflow_batch(payload: Dict[str, Any]):
    """
    Handle batch LangFlow processing.
    
    Payload:
        messages: List of messages to process
        flow_id: LangFlow flow identifier
    """
    messages = payload["messages"]
    flow_id = payload["flow_id"]
    
    logger.info(
        f"Processing LangFlow batch task",
        extra={
            "flow_id": flow_id,
            "message_count": len(messages),
        }
    )
    
    # Get database session
    async with async_session_factory() as db:
        # Get LangFlow service
        settings_service = SettingsService(db)
        langflow_service = await LangFlowService.from_settings(settings_service)
        
        try:
            results = []
            
            for msg in messages:
                try:
                    response = await langflow_service.send_message(
                        flow_id=flow_id,
                        message=msg["content"],
                        context=msg.get("context", {}),
                    )
                    results.append({
                        "message_id": msg.get("id"),
                        "success": True,
                        "response": response,
                    })
                except Exception as e:
                    logger.error(f"Batch message failed: {e}")
                    results.append({
                        "message_id": msg.get("id"),
                        "success": False,
                        "error": str(e),
                    })
            
            logger.info(
                f"LangFlow batch task completed",
                extra={
                    "flow_id": flow_id,
                    "total": len(messages),
                    "successful": sum(1 for r in results if r["success"]),
                    "failed": sum(1 for r in results if not r["success"]),
                }
            )
            
        finally:
            await langflow_service.close()


async def handle_triage_alert(payload: Dict[str, Any]):
    """
    Handle an alert triage task via LangFlow.

    Sends the alert ID to the configured LangFlow alert triage flow.
    LangFlow is expected to fetch alert details via MCP tools and create
    a triage recommendation via the MCP create_triage_recommendation tool.

    This handler updates the QUEUED placeholder recommendation:
    - On success: The LangFlow agent will call create_triage_recommendation
      which supersedes the QUEUED record with a PENDING one
    - On retryable failure: Leaves the recommendation QUEUED so the worker can retry
    - On terminal failure: A queue-level failure hook updates the record to FAILED

    Payload:
        alert_id: ID of the alert to triage (int or str)
    """
    from sqlmodel import select
    from app.models.models import TriageRecommendation
    from app.models.enums import RecommendationStatus
    from app.services.ai_triage_context_service import AITriageContextService

    alert_id = payload["alert_id"]
    session_id = uuid4()  # Generate a new session ID for each triage

    logger.info(
        "Processing alert triage task",
        extra={
            "alert_id": alert_id,
            "session_id": str(session_id),
        }
    )

    async with async_session_factory() as db:
        # Idempotency guard: if LangFlow already created a recommendation on a
        # prior attempt (timeout fired after LangFlow completed), skip re-running.
        result = await db.execute(
            select(TriageRecommendation).where(
                TriageRecommendation.alert_id == int(alert_id),
                TriageRecommendation.status != RecommendationStatus.QUEUED,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            logger.info(
                "Skipping triage — recommendation already exists with status %s",
                existing.status,
                extra={"alert_id": alert_id},
            )
            return

        settings_service = SettingsService(db)

        # Get the alert triage flow ID from settings
        flow_id = await settings_service.get_typed_value("langflow.alert_triage_flow_id")

        if not flow_id:
            raise LangFlowConfigurationError(
                "Alert triage flow not configured. Please set 'langflow.alert_triage_flow_id' in settings."
            )

        applied_context_entries = await AITriageContextService(db).get_matching_context_for_alert(int(alert_id))
        queued_result = await db.execute(
            select(TriageRecommendation).where(
                TriageRecommendation.alert_id == int(alert_id),
                TriageRecommendation.status == RecommendationStatus.QUEUED,
            )
        )
        queued_recommendation = queued_result.scalar_one_or_none()
        if queued_recommendation is not None:
            queued_recommendation.applied_context_entries = applied_context_entries
            db.add(queued_recommendation)
            await db.commit()

        langflow_service = await LangFlowService.from_settings(settings_service)

        try:
            # Use SSE streaming so the per-read timeout (300s of silence)
            # acts as a heartbeat against the agent flow. The synchronous
            # send_message call would time out at the global langflow.timeout
            # (default 30s) which is far below the natural runtime of an
            # agent doing MCP tool calls and multi-turn LLM reasoning.
            response = await langflow_service.run_flow_streaming(
                flow_id=flow_id,
                message="Run alert triage",
                session_id=session_id,
                context={
                    "entity_id": {"input_value": str(alert_id)},
                    "triage_context_entries": {
                        "input_value": json.dumps(applied_context_entries, default=str)
                    },
                },
                per_read_timeout=300.0,
            )

            logger.info(
                "Alert triage task completed",
                extra={
                    "alert_id": alert_id,
                    "flow_id": flow_id,
                    "session_id": str(session_id),
                    "response_length": len(str(response)),
                }
            )

            # Note: The LangFlow agent should call create_triage_recommendation MCP tool
            # which supersedes the QUEUED placeholder. If it didn't, the record stays QUEUED
            # and will be picked up on retry or marked failed after retries are exhausted.

        finally:
            await langflow_service.close()


async def _add_task_agent_note(db, task, agent_username: str, description: str, tags: list[str]) -> None:
    from app.services.timeline_service import timeline_service

    now = datetime.now(timezone.utc)
    timeline_service.add_timeline_item(
        task,
        {
            "id": str(uuid4()),
            "type": "note",
            "description": description,
            "created_at": now.isoformat(),
            "timestamp": now.isoformat(),
            "created_by": agent_username,
            "tags": tags,
            "flagged": False,
            "highlighted": False,
            "replies": [],
        },
        created_by=agent_username,
    )


async def _record_autonomous_task_failure(task_id: int, agent_username: str, error_message: str) -> None:
    from app.models.enums import TaskStatus
    from app.models.models import Task

    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return
        if task.status == TaskStatus.IN_PROGRESS:
            task.status = TaskStatus.TODO
        task.assignee = None
        await _add_task_agent_note(
            db,
            task,
            agent_username,
            f"Autonomous task execution failed: {error_message}",
            ["ai-agent", "automation-failed"],
        )
        await db.commit()


async def handle_autonomous_task(payload: Dict[str, Any]):
    """Run a configured LangFlow autonomous task flow for an assigned task."""
    from app.models.enums import TaskStatus
    from app.models.models import Task

    task_id = int(payload["task_id"])
    agent_username = str(payload["agent_username"])
    session_id = uuid4()

    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return

        settings_service = SettingsService(db)
        flow_id = await settings_service.get_typed_value("langflow.autonomous_task_flow_id")
        if not flow_id:
            raise LangFlowConfigurationError(
                "Autonomous task flow not configured. Please set 'langflow.autonomous_task_flow_id' in settings."
            )

        task.status = TaskStatus.IN_PROGRESS
        await _add_task_agent_note(
            db,
            task,
            agent_username,
            "Autonomous task execution started.",
            ["ai-agent", "automation-started"],
        )
        await db.commit()

        langflow_service = await LangFlowService.from_settings(settings_service)
        try:
            response = await langflow_service.run_flow_streaming(
                flow_id=flow_id,
                message="Run autonomous task",
                session_id=session_id,
                context={
                    "entity_id": {"input_value": str(task_id)},
                    "task_id": {"input_value": str(task_id)},
                },
                per_read_timeout=300.0,
            )
        finally:
            await langflow_service.close()

        task = await db.get(Task, task_id)
        if task is None:
            return
        task.status = TaskStatus.DONE
        task.assignee = None
        await _add_task_agent_note(
            db,
            task,
            agent_username,
            f"Autonomous task execution completed successfully.\n\n{str(response).strip()}",
            ["ai-agent", "automation-completed"],
        )
        await db.commit()


async def _mark_triage_failed(alert_id: int, error_message: str):
    """
    Mark a QUEUED triage recommendation as FAILED.
    
    Uses a fresh database session to ensure the status update succeeds
    even if the calling context's session is in a bad state (e.g., after rollback).
    """
    from sqlmodel import select
    from app.models.models import TriageRecommendation
    from app.models.enums import RecommendationStatus, RealtimeEventType
    
    try:
        # Use a fresh session to avoid issues with rolled-back transactions
        async with async_session_factory() as db:
            query = select(TriageRecommendation).where(
                TriageRecommendation.alert_id == alert_id,
                TriageRecommendation.status == RecommendationStatus.QUEUED
            )
            result = await db.execute(query)
            recommendation = result.scalar_one_or_none()
            
            if recommendation:
                recommendation.status = RecommendationStatus.FAILED
                recommendation.error_message = error_message[:1000] if error_message else None
                db.add(recommendation)
                await emit_event(
                    db,
                    entity_type="alert",
                    entity_id=alert_id,
                    event_type=RealtimeEventType.TRIAGE_COMPLETED,
                    performed_by="system",
                )
                await db.commit()
                logger.warning(
                    f"Marked triage recommendation as FAILED",
                    extra={"alert_id": alert_id, "error": error_message}
                )
            else:
                logger.warning(
                    f"Could not find QUEUED triage recommendation to mark as FAILED",
                    extra={"alert_id": alert_id}
                )
    except Exception as e:
        logger.error(
            f"Failed to mark triage recommendation as FAILED",
            extra={"alert_id": alert_id, "error": str(e)}
        )


async def handle_enrich_item(payload: Dict[str, Any], *, task_id: str | None = None):
    """Handle timeline item enrichment in the background worker.

    Retryable failures are surfaced back to the queue executor so the item can
    remain pending during retries. A terminal failure hook clears the pending
    state if retries are exhausted.
    """
    entity_type = str(payload["entity_type"])
    entity_id = int(payload["entity_id"])
    item_id = str(payload["item_id"])

    logger.info(
        "Processing enrichment task",
        extra={"entity_type": entity_type, "entity_id": entity_id, "item_id": item_id},
    )

    async with async_session_factory() as db:
        await enrichment_service.run_item_enrichment(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
            task_id=task_id,
        )


async def handle_directory_sync(payload: Dict[str, Any]):
    """Handle full provider directory synchronization."""
    provider_id = str(payload["provider_id"])
    reschedule = bool(payload.get("reschedule", False))

    logger.info(
        "Processing directory sync task",
        extra={"provider_id": provider_id, "reschedule": reschedule},
    )

    async with async_session_factory() as db:
        await enrichment_service.run_directory_sync(db, provider_id)
        if reschedule:
            await sync_bulk_sync_schedule_for_provider(db, provider_id)


async def handle_refresh_bulk_sync_schedules(payload: Dict[str, Any]):
    """Refresh worker-resident bulk sync schedules from current settings."""
    logger.info("Refreshing bulk sync schedules", extra={"payload": payload})

    async with async_session_factory() as db:
        await sync_bulk_sync_schedules(db)


async def handle_maxmind_update(payload: Dict[str, Any]):
    """Download and refresh MaxMind MMDB files on workers."""
    reschedule = bool(payload.get("reschedule", False))

    logger.info("Processing MaxMind update task", extra={"reschedule": reschedule})

    async with async_session_factory() as db:
        settings = SettingsService(db)
        enabled = bool(await settings.get("enrichment.maxmind.enabled", False))
        if not enabled:
            logger.info("Skipping MaxMind update because provider is disabled")
            return

        results = await maxmind_service.download_databases(db)
        synced = await maxmind_service.sync_local_cache(settings=settings)
        await maxmind_service.ensure_readers_loaded(settings=settings)

        logger.info(
            "Completed MaxMind update task",
            extra={"results": results, "synced_editions": synced},
        )

        if reschedule:
            await maxmind_service.enqueue_next_scheduled_update(db)


def register_task_handlers():
    """
    Register all task handlers with the task queue service.
    
    This should be called during application startup.
    """
    try:
        task_queue = get_task_queue_service()
        
        # Register LangFlow chat handler
        task_queue.register_handler(
            task_name=TASK_LANGFLOW_CHAT,
            handler=handle_langflow_chat,
            max_retries=3,
        )
        
        # Register LangFlow batch handler
        task_queue.register_handler(
            task_name=TASK_LANGFLOW_BATCH,
            handler=handle_langflow_batch,
            max_retries=2,
        )
        
        # Register alert triage handler.
        # Streaming run uses a per-read heartbeat timeout, so a timeout means
        # LangFlow is genuinely stuck — not "still thinking". One retry is
        # plenty (covers a transient network blip); more would just compound
        # the cost since each attempt runs full LLM+MCP work.
        task_queue.register_handler(
            task_name=TASK_TRIAGE_ALERT,
            handler=handle_triage_alert,
            max_retries=1,
            on_terminal_failure=_handle_triage_terminal_failure,
        )

        task_queue.register_handler(
            task_name=TASK_AUTONOMOUS_TASK,
            handler=handle_autonomous_task,
            max_retries=1,
            on_terminal_failure=_handle_autonomous_task_terminal_failure,
        )

        task_queue.register_handler(
            task_name=TASK_ENRICH_ITEM,
            handler=handle_enrich_item,
            max_retries=3,
            on_terminal_failure=_handle_enrich_item_terminal_failure,
        )

        task_queue.register_handler(
            task_name=TASK_DIRECTORY_SYNC,
            handler=handle_directory_sync,
            max_retries=2,
            on_terminal_failure=_handle_directory_sync_terminal_failure,
        )

        task_queue.register_handler(
            task_name=TASK_REFRESH_BULK_SYNC_SCHEDULES,
            handler=handle_refresh_bulk_sync_schedules,
            max_retries=0,
        )

        task_queue.register_handler(
            task_name=TASK_MAXMIND_UPDATE,
            handler=handle_maxmind_update,
            max_retries=2,
        )
        
        logger.info("Registered all task handlers")
        
    except RuntimeError:
        logger.warning("Task queue not initialized - skipping handler registration")
