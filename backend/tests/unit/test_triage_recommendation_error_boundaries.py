from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import triage_recommendations as triage_routes
from app.mcp import tools as mcp_tools
from app.models.enums import (
    AlertStatus,
    Priority,
    RecommendationStatus,
    RejectionCategory,
    TriageDisposition,
)
from app.models.models import Alert, TriageRecommendation
from app.services import mcp_service
from app.services import triage_recommendation_service as triage_service
from app.services.mcp_errors import McpValidationError
from app.services.task_queue_service import TaskQueueNotInitializedError


def _alert() -> Alert:
    return Alert(
        id=7,
        title="Suspicious activity",
        status=AlertStatus.NEW,
        priority=Priority.MEDIUM,
        tags=[],
    )


def _recommendation(
    *,
    status_value: RecommendationStatus = RecommendationStatus.PENDING,
) -> TriageRecommendation:
    return TriageRecommendation(
        id=11,
        alert_id=7,
        disposition=TriageDisposition.NEEDS_INVESTIGATION,
        confidence=0.9,
        reasoning_bullets=["Investigate"],
        recommended_actions=[],
        suggested_status=AlertStatus.ESCALATED,
        created_by="triage-agent",
        status=status_value,
    )


def _arrange_enqueue_failure(
    monkeypatch: pytest.MonkeyPatch,
    queue_error: Exception,
    *,
    compensation_read: bool,
) -> tuple[SimpleNamespace, AsyncMock]:
    recommendation = _recommendation(status_value=RecommendationStatus.ACCEPTED)
    db = SimpleNamespace(add=Mock(), flush=AsyncMock(), commit=AsyncMock())

    async def get_setting(_self: object, _key: str) -> str:
        return "flow-1"

    get_recommendation = AsyncMock(
        side_effect=[recommendation, recommendation]
        if compensation_read
        else None,
        return_value=recommendation,
    )
    monkeypatch.setattr("app.services.settings_service.SettingsService.get", get_setting)
    monkeypatch.setattr(triage_service, "_lock_alert", AsyncMock(return_value=_alert()))
    monkeypatch.setattr(triage_service, "get_by_alert_id", get_recommendation)
    monkeypatch.setattr(
        "app.services.task_queue_service.get_task_queue_service",
        lambda: SimpleNamespace(enqueue=AsyncMock(side_effect=queue_error)),
    )
    return db, get_recommendation


async def _invoke_route(operation: str) -> object:
    db = cast(AsyncSession, object())
    user = SimpleNamespace(username="analyst")
    request = cast(Request, None)
    if operation == "enqueue":
        return await triage_routes.enqueue_triage_recommendation(
            alert_id=7,
            http_request=request,
            db=db,
            current_user=user,
        )
    if operation == "accept":
        return await triage_routes.accept_triage_recommendation(
            alert_id=7,
            http_request=request,
            payload=triage_routes.AcceptRecommendationRequest(),
            db=db,
            current_user=user,
        )
    if operation == "reject":
        return await triage_routes.reject_triage_recommendation(
            alert_id=7,
            http_request=request,
            payload=triage_routes.RejectRecommendationRequest(
                category=RejectionCategory.PREFER_MANUAL_REVIEW,
            ),
            db=db,
            current_user=user,
        )
    raise AssertionError(f"Unknown operation: {operation}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "error", "expected_status"),
    [
        (
            "enqueue",
            triage_service.TriageRecommendationValidationError("triage disabled"),
            status.HTTP_400_BAD_REQUEST,
        ),
        (
            "accept",
            triage_service.TriageRecommendationNotFoundError(
                "No triage recommendation found for alert 7"
            ),
            status.HTTP_404_NOT_FOUND,
        ),
        (
            "reject",
            triage_service.TriageRecommendationConflictError(
                "Recommendation already ACCEPTED"
            ),
            status.HTTP_409_CONFLICT,
        ),
    ],
)
async def test_routes_map_only_typed_triage_errors(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    error: Exception,
    expected_status: int,
) -> None:
    method_name = {
        "enqueue": "enqueue_triage",
        "accept": "accept_recommendation",
        "reject": "reject_recommendation",
    }[operation]
    monkeypatch.setattr(
        triage_routes.triage_recommendation_service,
        method_name,
        AsyncMock(side_effect=error),
    )

    with pytest.raises(HTTPException) as exc_info:
        await _invoke_route(operation)

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == str(error)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ValueError("internal value defect"),
        TypeError("internal type defect"),
        RuntimeError("internal runtime defect"),
    ],
)
async def test_routes_propagate_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    monkeypatch.setattr(
        triage_routes.triage_recommendation_service,
        "accept_recommendation",
        AsyncMock(side_effect=error),
    )

    with pytest.raises(type(error), match=str(error)):
        await _invoke_route("accept")


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", [None, "", "   "])
async def test_reject_requires_other_reason_at_service_seam(
    monkeypatch: pytest.MonkeyPatch,
    reason: str | None,
) -> None:
    get_recommendation = AsyncMock()
    monkeypatch.setattr(triage_service, "get_by_alert_id", get_recommendation)

    with pytest.raises(
        triage_service.TriageRecommendationValidationError,
        match="Reason is required when category is OTHER",
    ):
        await triage_service.reject_recommendation(
            cast(AsyncSession, object()),
            alert_id=7,
            category=RejectionCategory.OTHER,
            reason=reason,
            reviewed_by="analyst",
        )

    get_recommendation.assert_not_awaited()


@pytest.mark.asyncio
async def test_acceptance_locks_alert_before_refreshing_recommendation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    initial = _recommendation(status_value=RecommendationStatus.QUEUED)
    refreshed = _recommendation(status_value=RecommendationStatus.PENDING)

    async def get_recommendation(
        _db: AsyncSession,
        _alert_id: int,
        *,
        for_update: bool = False,
    ) -> TriageRecommendation:
        calls.append("recommendation-lock" if for_update else "recommendation-check")
        return refreshed if for_update else initial

    async def lock_alert(_db: AsyncSession, _alert_id: int) -> Alert:
        calls.append("alert-lock")
        return _alert()

    monkeypatch.setattr(triage_service, "get_by_alert_id", get_recommendation)
    monkeypatch.setattr(triage_service, "_lock_alert", lock_alert)

    alert, recommendation = await triage_service._lock_acceptance_state(
        cast(AsyncSession, object()),
        7,
    )

    assert calls == ["recommendation-check", "alert-lock", "recommendation-lock"]
    assert alert.id == 7
    assert recommendation is refreshed


@pytest.mark.asyncio
async def test_acceptance_reports_recommendation_removed_while_waiting_for_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        triage_service,
        "get_by_alert_id",
        AsyncMock(side_effect=[_recommendation(), None]),
    )
    monkeypatch.setattr(triage_service, "_lock_alert", AsyncMock(return_value=_alert()))

    with pytest.raises(
        triage_service.TriageRecommendationNotFoundError,
        match="No triage recommendation found for alert 7",
    ):
        await triage_service._lock_acceptance_state(
            cast(AsyncSession, object()),
            7,
        )


@pytest.mark.asyncio
async def test_replacing_recommendation_clears_all_review_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _recommendation(status_value=RecommendationStatus.REJECTED)
    existing.reviewed_by = "previous-reviewer"
    existing.reviewed_at = datetime.now(timezone.utc)
    existing.rejection_category = RejectionCategory.OTHER
    existing.rejection_reason = "Old reason"
    existing.applied_changes = [{"field": "status"}]
    db = SimpleNamespace(add=Mock(), commit=AsyncMock())
    monkeypatch.setattr(triage_service, "_lock_alert", AsyncMock(return_value=_alert()))
    monkeypatch.setattr(
        triage_service,
        "get_by_alert_id",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(triage_service, "emit_event", AsyncMock())

    result = await triage_service.create_or_replace_recommendation(
        cast(AsyncSession, db),
        alert_id=7,
        data={
            "disposition": TriageDisposition.BENIGN,
            "confidence": 0.8,
            "reasoning_bullets": ["Known activity"],
            "recommended_actions": [],
        },
        created_by="triage-agent",
    )

    assert result.status == RecommendationStatus.PENDING
    assert result.reviewed_by is None
    assert result.reviewed_at is None
    assert result.rejection_category is None
    assert result.rejection_reason is None
    assert result.applied_changes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "queue_error",
    [
        TaskQueueNotInitializedError("queue not initialized"),
        ConnectionError("queue connection failed"),
    ],
)
async def test_enqueue_compensates_expected_queue_failures(
    monkeypatch: pytest.MonkeyPatch,
    queue_error: Exception,
) -> None:
    db, _ = _arrange_enqueue_failure(
        monkeypatch,
        queue_error,
        compensation_read=True,
    )

    result = await triage_service.enqueue_triage(
        cast(AsyncSession, db),
        alert_id=7,
        enqueued_by="analyst",
    )

    assert result.status == RecommendationStatus.FAILED
    assert result.error_message == "Task queue unavailable"
    assert db.commit.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "queue_error",
    [
        RuntimeError("queue programming defect"),
        TypeError("queue payload defect"),
        ValueError("queue value defect"),
    ],
)
async def test_enqueue_propagates_unexpected_queue_errors(
    monkeypatch: pytest.MonkeyPatch,
    queue_error: Exception,
) -> None:
    db, get_recommendation = _arrange_enqueue_failure(
        monkeypatch,
        queue_error,
        compensation_read=False,
    )

    with pytest.raises(type(queue_error), match=str(queue_error)):
        await triage_service.enqueue_triage(
            cast(AsyncSession, db),
            alert_id=7,
            enqueued_by="analyst",
        )

    assert db.commit.await_count == 1
    get_recommendation.assert_awaited_once()


@pytest.mark.asyncio
async def test_mcp_service_maps_typed_triage_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = triage_service.TriageRecommendationValidationError(
        "Invalid disposition: INVALID"
    )
    monkeypatch.setattr(
        triage_service,
        "normalize_recommendation_contract",
        Mock(side_effect=error),
    )
    db = SimpleNamespace(get=AsyncMock(return_value=_alert()))

    with pytest.raises(McpValidationError, match=str(error)):
        await mcp_service.record_triage_decision(
            cast(AsyncSession, db),
            alert_id_str="ALT-0000007",
            disposition="INVALID",
            confidence=0.5,
        )


@pytest.mark.asyncio
async def test_mcp_propagates_unexpected_validation_defect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        triage_service,
        "normalize_recommendation_contract",
        Mock(side_effect=ValueError("normalizer defect")),
    )
    db = SimpleNamespace(get=AsyncMock(return_value=_alert()))

    with pytest.raises(ValueError, match="normalizer defect"):
        await mcp_service.record_triage_decision(
            cast(AsyncSession, db),
            alert_id_str="ALT-0000007",
            disposition="TRUE_POSITIVE",
            confidence=0.5,
        )


@pytest.mark.asyncio
async def test_mcp_tool_preserves_triage_validation_http_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = McpValidationError("Invalid disposition: INVALID")
    service_call = AsyncMock(side_effect=error)

    class _SessionContext:
        async def __aenter__(self) -> AsyncSession:
            return cast(AsyncSession, object())

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(mcp_tools, "async_session_factory", _SessionContext)
    monkeypatch.setattr(mcp_tools, "_get_authenticated_username", lambda: "analyst")
    monkeypatch.setattr(
        mcp_tools.mcp_service,
        "record_triage_decision",
        service_call,
    )

    with pytest.raises(HTTPException) as exc_info:
        await mcp_tools.record_triage_decision_tool(
            alert_id="ALT-0000007",
            disposition="INVALID",
            confidence=0.5,
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == str(error)
