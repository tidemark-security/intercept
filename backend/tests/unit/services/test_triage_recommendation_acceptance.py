from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.enums import (
    AlertStatus,
    CaseRunbookStatus,
    Priority,
    RecommendationStatus,
    TriageDisposition,
)
from app.models.models import Alert, CaseRunbook, Task, TriageRecommendation
from app.services import triage_recommendation_service


def _alert(*, case_id: int | None = None) -> Alert:
    return Alert(
        id=7,
        title="Suspicious activity",
        priority=Priority.HIGH,
        status=AlertStatus.NEW,
        case_id=case_id,
        linked_at=(
            datetime(2026, 7, 18, tzinfo=timezone.utc)
            if case_id is not None
            else None
        ),
        tags=[],
    )


def _recommendation(
    *,
    runbook_id: int | None,
    recommended_actions: list[dict[str, str]] | None = None,
) -> TriageRecommendation:
    return TriageRecommendation(
        id=11,
        alert_id=7,
        disposition=TriageDisposition.NEEDS_INVESTIGATION,
        confidence=0.9,
        reasoning_bullets=["Investigate"],
        recommended_actions=recommended_actions or [],
        recommended_case_runbook_id=runbook_id,
        suggested_status=AlertStatus.ESCALATED,
        request_escalate_to_case=True,
        created_by="triage-agent",
        status=RecommendationStatus.PENDING,
    )


def test_acceptance_options_reject_conflicting_runbook_choices() -> None:
    with pytest.raises(
        triage_recommendation_service.TriageRecommendationValidationError,
        match="mutually exclusive",
    ):
        triage_recommendation_service.AcceptRecommendationOptions(
            case_runbook_id=5,
            skip_case_runbook=True,
        )


def _arrange_acceptance(
    monkeypatch: pytest.MonkeyPatch,
    *,
    alert: Alert,
    recommendation: TriageRecommendation,
    runbook: CaseRunbook | None,
    runbook_task_ids: list[int],
) -> SimpleNamespace:
    added: list[object] = []

    async def get(model: type[object], _entity_id: int) -> object | None:
        if model is Alert:
            return alert
        if model is CaseRunbook:
            return runbook
        return None

    db = SimpleNamespace(
        get=AsyncMock(side_effect=get),
        add=Mock(side_effect=added.append),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    created_case = SimpleNamespace(id=84)
    create_case = AsyncMock(return_value=created_case)
    apply_runbook = AsyncMock(
        return_value=SimpleNamespace(created_task_ids=runbook_task_ids),
    )
    build_note = Mock(wraps=triage_recommendation_service.timeline_service.build_note_item)

    monkeypatch.setattr(
        triage_recommendation_service,
        "_lock_acceptance_state",
        AsyncMock(return_value=(alert, recommendation)),
    )
    monkeypatch.setattr(
        triage_recommendation_service,
        "create_case_from_alert",
        create_case,
    )
    monkeypatch.setattr(
        triage_recommendation_service.case_runbook_service,
        "apply_runbook",
        apply_runbook,
    )
    monkeypatch.setattr(
        triage_recommendation_service.timeline_service,
        "build_note_item",
        build_note,
    )
    monkeypatch.setattr(
        triage_recommendation_service.timeline_service,
        "add_timeline_item",
        Mock(),
    )
    monkeypatch.setattr(
        triage_recommendation_service,
        "emit_event",
        AsyncMock(),
    )

    return SimpleNamespace(
        db=db,
        added=added,
        create_case=create_case,
        apply_runbook=apply_runbook,
        build_note=build_note,
        created_case=created_case,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_case_id", [42, None], ids=["existing-case", "new-case"])
async def test_acceptance_applies_runbook_once_and_uses_one_acceptance_timestamp(
    monkeypatch: pytest.MonkeyPatch,
    existing_case_id: int | None,
) -> None:
    alert = _alert(case_id=existing_case_id)
    recommendation = _recommendation(runbook_id=5)
    runbook = CaseRunbook(
        id=5,
        title="Investigation",
        status=CaseRunbookStatus.PUBLISHED,
        created_by="admin",
        updated_by="admin",
    )
    arranged = _arrange_acceptance(
        monkeypatch,
        alert=alert,
        recommendation=recommendation,
        runbook=runbook,
        runbook_task_ids=[101, 102],
    )

    result = await triage_recommendation_service.accept_recommendation(
        arranged.db,
        alert_id=7,
        options=triage_recommendation_service.AcceptRecommendationOptions(),
        reviewed_by="analyst",
    )

    expected_case_id = existing_case_id or arranged.created_case.id
    assert result.case_id == expected_case_id
    assert result.tasks_created == 2
    arranged.apply_runbook.assert_awaited_once_with(
        arranged.db,
        case_id=expected_case_id,
        runbook_id=5,
        overrides=[],
        user="analyst",
        commit=False,
    )
    assert [
        change
        for change in recommendation.applied_changes
        if change.get("field") == "case_runbook" and change.get("action") == "applied"
    ] == [
        {
            "field": "case_runbook",
            "action": "applied",
            "runbook_id": 5,
            "created_task_ids": [101, 102],
        }
    ]
    task_changes = [
        change
        for change in recommendation.applied_changes
        if change.get("field") == "tasks" and change.get("action") == "created"
    ]
    assert task_changes == (
        []
        if existing_case_id is not None
        else [{"field": "tasks", "action": "created", "count": 2}]
    )

    assert recommendation.reviewed_at is not None
    assert alert.triaged_at == recommendation.reviewed_at
    assert arranged.build_note.call_args.kwargs["timestamp"] == recommendation.reviewed_at
    if existing_case_id is None:
        assert alert.linked_at == recommendation.reviewed_at
        assert arranged.create_case.await_args.kwargs["now"] == recommendation.reviewed_at
    else:
        arranged.create_case.assert_not_awaited()
    arranged.db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_recommended_action_task_uses_acceptance_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alert = _alert()
    recommendation = _recommendation(
        runbook_id=None,
        recommended_actions=[{"title": "Collect volatile evidence"}],
    )
    arranged = _arrange_acceptance(
        monkeypatch,
        alert=alert,
        recommendation=recommendation,
        runbook=None,
        runbook_task_ids=[],
    )

    result = await triage_recommendation_service.accept_recommendation(
        arranged.db,
        alert_id=7,
        options=triage_recommendation_service.AcceptRecommendationOptions(),
        reviewed_by="analyst",
    )

    task = next(item for item in arranged.added if isinstance(item, Task))
    assert result.tasks_created == 1
    assert recommendation.reviewed_at is not None
    assert task.linked_at == task.created_at == task.updated_at == recommendation.reviewed_at
    assert alert.triaged_at == alert.linked_at == recommendation.reviewed_at
    assert arranged.create_case.await_args.kwargs["now"] == recommendation.reviewed_at
    arranged.apply_runbook.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("apply_assignee", "expected_assignee"),
    [(True, "suggested-responder"), (False, "current-owner")],
)
async def test_acceptance_honors_assignee_option(
    monkeypatch: pytest.MonkeyPatch,
    apply_assignee: bool,
    expected_assignee: str,
) -> None:
    alert = _alert()
    alert.assignee = "current-owner"
    recommendation = _recommendation(runbook_id=None)
    recommendation.suggested_assignee = "suggested-responder"
    arranged = _arrange_acceptance(
        monkeypatch,
        alert=alert,
        recommendation=recommendation,
        runbook=None,
        runbook_task_ids=[],
    )

    await triage_recommendation_service.accept_recommendation(
        arranged.db,
        alert_id=7,
        options=triage_recommendation_service.AcceptRecommendationOptions(
            apply_assignee=apply_assignee,
        ),
        reviewed_by="analyst",
    )

    assert alert.assignee == expected_assignee
    assignee_changes = [
        change
        for change in recommendation.applied_changes
        if change.get("field") == "assignee"
    ]
    assert assignee_changes == (
        [{"field": "assignee", "value": "suggested-responder"}]
        if apply_assignee
        else []
    )


@pytest.mark.asyncio
async def test_explicit_runbook_id_does_not_fall_back_when_falsy() -> None:
    recommendation = _recommendation(runbook_id=5)
    db = SimpleNamespace(get=AsyncMock(return_value=None))

    with pytest.raises(
        triage_recommendation_service.TriageRecommendationConflictError,
        match="selected.*no longer published",
    ):
        await triage_recommendation_service._resolve_acceptance_runbook(
            db,
            recommendation,
            triage_recommendation_service.AcceptRecommendationOptions(
                case_runbook_id=0,
            ),
            [],
        )

    db.get.assert_awaited_once_with(CaseRunbook, 0)


@pytest.mark.asyncio
async def test_acceptance_records_only_effective_tag_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alert = _alert()
    alert.tags = ["Existing", "remove-me"]
    recommendation = _recommendation(runbook_id=None)
    recommendation.disposition = TriageDisposition.FALSE_POSITIVE
    recommendation.suggested_status = AlertStatus.CLOSED_FP
    recommendation.request_escalate_to_case = False
    recommendation.suggested_tags_add = ["existing", "new"]
    recommendation.suggested_tags_remove = ["missing", "remove-me"]
    arranged = _arrange_acceptance(
        monkeypatch,
        alert=alert,
        recommendation=recommendation,
        runbook=None,
        runbook_task_ids=[],
    )

    result = await triage_recommendation_service.accept_recommendation(
        arranged.db,
        alert_id=7,
        options=triage_recommendation_service.AcceptRecommendationOptions(),
        reviewed_by="analyst",
    )

    assert result.case_id is None
    assert alert.tags == ["Existing", "new"]
    assert [
        change
        for change in recommendation.applied_changes
        if change.get("field") == "tags"
    ] == [
        {"field": "tags", "action": "add", "value": "new"},
        {"field": "tags", "action": "remove", "value": "remove-me"},
    ]
