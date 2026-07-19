from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

import app.services.alert_service as alert_service_module
import app.services.case_service as case_service_module
import app.services.task_service as task_service_module
from app.models.enums import AlertStatus, CaseStatus, TaskStatus
from app.models.models import (
    Alert,
    AlertBulkActionRequest,
    AlertUpdate,
    Case,
    CaseAlertClosureUpdate,
    CaseLinkedAlertResolutionRequest,
    CaseUpdate,
    Task,
    TaskUpdate,
)
from app.services.alert_service import alert_service
from app.services.case_service import case_service
from app.services.task_service import task_service
from app.services.timeline_service import timeline_service


async def _return_committed_fallback(
    _db: object,
    _loader: object,
    fallback: Any,
    **_metadata: object,
) -> Any:
    return fallback


def _isolate_alert_mutation_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(alert_service_module, "emit_event", AsyncMock())
    monkeypatch.setattr(
        alert_service_module,
        "load_committed_response",
        _return_committed_fallback,
    )


def _isolate_case_mutation_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(case_service_module, "emit_event", AsyncMock())
    monkeypatch.setattr(
        case_service_module,
        "load_committed_response",
        _return_committed_fallback,
    )
    monkeypatch.setattr(case_service, "_create_audit_log", AsyncMock())


def _isolate_task_mutation_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_service = SimpleNamespace(log_entity_updated=AsyncMock())
    monkeypatch.setattr(task_service_module, "emit_event", AsyncMock())
    monkeypatch.setattr(
        task_service_module,
        "load_committed_response",
        _return_committed_fallback,
    )
    monkeypatch.setattr(
        task_service_module,
        "get_audit_service",
        lambda _db: audit_service,
    )


@pytest.mark.asyncio
async def test_concurrent_alert_updates_preserve_independent_fields(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_alert_mutation_side_effects(monkeypatch)
    async with session_maker() as setup_session:
        alert = Alert(
            title="Original title",
            description="Original description",
        )
        setup_session.add(alert)
        await setup_session.commit()
        assert alert.id is not None
        alert_id = alert.id

    async with session_maker() as first_session, session_maker() as second_session:
        assert await first_session.get(Alert, alert_id) is not None
        assert await second_session.get(Alert, alert_id) is not None

        await asyncio.gather(
            alert_service.update_alert(
                first_session,
                alert_id,
                AlertUpdate(title="Title from first session"),
            ),
            alert_service.update_alert(
                second_session,
                alert_id,
                AlertUpdate(description="Description from second session"),
            ),
        )

    async with session_maker() as verification_session:
        stored_alert = await verification_session.get(Alert, alert_id)

    assert stored_alert is not None
    assert stored_alert.title == "Title from first session"
    assert stored_alert.description == "Description from second session"


@pytest.mark.asyncio
async def test_bulk_alert_mutation_refreshes_stale_tags(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_alert_mutation_side_effects(monkeypatch)
    monkeypatch.setattr(alert_service, "_audit_bulk_alert_update", AsyncMock())
    async with session_maker() as setup_session:
        alert = Alert(title="Bulk locking", tags=[])
        setup_session.add(alert)
        await setup_session.commit()
        assert alert.id is not None
        alert_id = alert.id

    async with session_maker() as bulk_session, session_maker() as writer_session:
        assert await bulk_session.get(Alert, alert_id) is not None
        writer_alert = await writer_session.get(Alert, alert_id)
        assert writer_alert is not None
        writer_alert.tags = ["writer-tag"]
        await writer_session.commit()

        await alert_service.bulk_action(
            bulk_session,
            AlertBulkActionRequest(
                alert_ids=[alert_id],
                action="add_tags",
                tags=["bulk-tag"],
            ),
            performed_by="bulk-analyst",
        )

    async with session_maker() as verification_session:
        stored_alert = await verification_session.get(Alert, alert_id)

    assert stored_alert is not None
    assert set(stored_alert.tags or []) == {"writer-tag", "bulk-tag"}


@pytest.mark.asyncio
async def test_concurrent_case_updates_preserve_independent_fields(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_case_mutation_side_effects(monkeypatch)
    async with session_maker() as setup_session:
        case = Case(
            title="Original title",
            description="Original description",
            created_by="analyst",
        )
        setup_session.add(case)
        await setup_session.commit()
        assert case.id is not None
        case_id = case.id

    async with session_maker() as first_session, session_maker() as second_session:
        assert await first_session.get(Case, case_id) is not None
        assert await second_session.get(Case, case_id) is not None

        await asyncio.gather(
            case_service.update_case(
                first_session,
                case_id,
                CaseUpdate(title="Title from first session"),
                updated_by="first-analyst",
            ),
            case_service.update_case(
                second_session,
                case_id,
                CaseUpdate(description="Description from second session"),
                updated_by="second-analyst",
            ),
        )

    async with session_maker() as verification_session:
        stored_case = await verification_session.get(Case, case_id)

    assert stored_case is not None
    assert stored_case.title == "Title from first session"
    assert stored_case.description == "Description from second session"


@pytest.mark.asyncio
async def test_serialized_repeated_case_close_keeps_first_closed_timestamp(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_case_mutation_side_effects(monkeypatch)
    async with session_maker() as setup_session:
        case = Case(title="Concurrent close", created_by="analyst")
        setup_session.add(case)
        await setup_session.commit()
        assert case.id is not None
        case_id = case.id

    async with session_maker() as first_session, session_maker() as second_session:
        assert await first_session.get(Case, case_id) is not None
        assert await second_session.get(Case, case_id) is not None

        first_result, second_result = await asyncio.gather(
            case_service.update_case(
                first_session,
                case_id,
                CaseUpdate(status=CaseStatus.CLOSED),
                updated_by="first-analyst",
            ),
            case_service.update_case(
                second_session,
                case_id,
                CaseUpdate(status=CaseStatus.CLOSED),
                updated_by="second-analyst",
            ),
        )

    async with session_maker() as verification_session:
        stored_case = await verification_session.get(Case, case_id)

    assert first_result is not None
    assert second_result is not None
    assert stored_case is not None
    assert first_result.closed_at is not None
    assert first_result.closed_at == second_result.closed_at == stored_case.closed_at


@pytest.mark.asyncio
async def test_case_closure_preserves_concurrent_linked_task_timeline_change(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_case_mutation_side_effects(monkeypatch)
    async with session_maker() as setup_session:
        case = Case(title="Closure locking", created_by="analyst")
        setup_session.add(case)
        await setup_session.flush()
        assert case.id is not None
        task = Task(
            title="Linked task",
            created_by="analyst",
            case_id=case.id,
            timeline_items={},
        )
        setup_session.add(task)
        await setup_session.commit()
        assert task.id is not None
        case_id = case.id
        task_id = task.id

    async with session_maker() as closure_session, session_maker() as writer_session:
        assert await closure_session.get(Case, case_id) is not None
        assert await closure_session.get(Task, task_id) is not None

        writer_task = await writer_session.get(Task, task_id)
        assert writer_task is not None
        independent_note = timeline_service.build_note_item(
            description="Independent task note",
            created_by="task-analyst",
        )
        timeline_service.add_timeline_item(
            writer_task,
            independent_note,
            created_by="task-analyst",
        )
        await writer_session.commit()

        await case_service.update_case(
            closure_session,
            case_id,
            CaseUpdate(status=CaseStatus.CLOSED),
            updated_by="closing-analyst",
        )

    async with session_maker() as verification_session:
        stored_task = await verification_session.get(Task, task_id)

    assert stored_task is not None
    assert stored_task.status == TaskStatus.DONE
    descriptions = {
        item["description"]
        for item in (stored_task.timeline_items or {}).values()
    }
    assert "Independent task note" in descriptions
    assert any("closed automatically due to case" in item for item in descriptions)


@pytest.mark.asyncio
async def test_linked_alert_resolution_preserves_concurrent_timeline_change(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_case_mutation_side_effects(monkeypatch)
    monkeypatch.setattr(
        case_service_module.triage_recommendation_service,
        "auto_reject_if_pending",
        AsyncMock(),
    )
    monkeypatch.setattr(case_service, "_audit_alert_resolution", AsyncMock())
    async with session_maker() as setup_session:
        case = Case(title="Resolution locking", created_by="analyst")
        setup_session.add(case)
        await setup_session.flush()
        assert case.id is not None
        alert = Alert(
            title="Linked alert",
            status=AlertStatus.ESCALATED,
            case_id=case.id,
            timeline_items={},
        )
        setup_session.add(alert)
        await setup_session.commit()
        assert alert.id is not None
        case_id = case.id
        alert_id = alert.id

    async with session_maker() as resolution_session, session_maker() as writer_session:
        assert await resolution_session.get(Case, case_id) is not None
        assert await resolution_session.get(Alert, alert_id) is not None

        writer_alert = await writer_session.get(Alert, alert_id)
        assert writer_alert is not None
        independent_note = timeline_service.build_note_item(
            description="Independent alert note",
            created_by="alert-analyst",
        )
        timeline_service.add_timeline_item(
            writer_alert,
            independent_note,
            created_by="alert-analyst",
        )
        await writer_session.commit()

        await case_service.resolve_linked_alerts(
            resolution_session,
            case_id,
            CaseLinkedAlertResolutionRequest(
                alert_updates=[
                    CaseAlertClosureUpdate(
                        alert_id=alert_id,
                        status=AlertStatus.CLOSED_FP,
                    )
                ],
            ),
            resolved_by="resolving-analyst",
        )

    async with session_maker() as verification_session:
        stored_alert = await verification_session.get(Alert, alert_id)

    assert stored_alert is not None
    assert stored_alert.status == AlertStatus.CLOSED_FP
    descriptions = {
        item["description"]
        for item in (stored_alert.timeline_items or {}).values()
    }
    assert "Independent alert note" in descriptions
    assert any("resolved as" in item for item in descriptions)


@pytest.mark.asyncio
async def test_stale_linked_alert_resolution_observes_first_committed_close(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_case_mutation_side_effects(monkeypatch)
    monkeypatch.setattr(
        case_service_module.triage_recommendation_service,
        "auto_reject_if_pending",
        AsyncMock(),
    )
    monkeypatch.setattr(case_service, "_audit_alert_resolution", AsyncMock())
    async with session_maker() as setup_session:
        case = Case(title="Competing resolutions", created_by="analyst")
        setup_session.add(case)
        await setup_session.flush()
        assert case.id is not None
        alert = Alert(
            title="Linked alert",
            status=AlertStatus.ESCALATED,
            case_id=case.id,
        )
        setup_session.add(alert)
        await setup_session.commit()
        assert alert.id is not None
        case_id = case.id
        alert_id = alert.id

    async with session_maker() as first_session, session_maker() as stale_session:
        assert await stale_session.get(Alert, alert_id) is not None

        await case_service.resolve_linked_alerts(
            first_session,
            case_id,
            CaseLinkedAlertResolutionRequest(
                alert_updates=[
                    CaseAlertClosureUpdate(
                        alert_id=alert_id,
                        status=AlertStatus.CLOSED_TP,
                    )
                ]
            ),
            resolved_by="first-analyst",
        )

        with pytest.raises(ValueError, match="already closed"):
            await case_service.resolve_linked_alerts(
                stale_session,
                case_id,
                CaseLinkedAlertResolutionRequest(
                    alert_updates=[
                        CaseAlertClosureUpdate(
                            alert_id=alert_id,
                            status=AlertStatus.CLOSED_FP,
                        )
                    ]
                ),
                resolved_by="second-analyst",
            )

    async with session_maker() as verification_session:
        stored_alert = await verification_session.get(Alert, alert_id)

    assert stored_alert is not None
    assert stored_alert.status == AlertStatus.CLOSED_TP


@pytest.mark.asyncio
async def test_case_closure_and_task_link_share_parent_before_child_lock_order(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_case_mutation_side_effects(monkeypatch)
    _isolate_task_mutation_side_effects(monkeypatch)
    async with session_maker() as setup_session:
        case = Case(title="Task link locking", created_by="analyst")
        task = Task(title="Unlinked task", created_by="analyst")
        setup_session.add(case)
        setup_session.add(task)
        await setup_session.commit()
        assert case.id is not None
        assert task.id is not None
        case_id = case.id
        task_id = task.id

    async with session_maker() as closure_session, session_maker() as link_session:
        assert await closure_session.get(Case, case_id) is not None
        assert await link_session.get(Task, task_id) is not None

        await asyncio.wait_for(
            asyncio.gather(
                case_service.update_case(
                    closure_session,
                    case_id,
                    CaseUpdate(status=CaseStatus.CLOSED),
                    updated_by="closing-analyst",
                ),
                task_service.update_task(
                    link_session,
                    task_id,
                    TaskUpdate(case_id=case_id),
                    updated_by="linking-analyst",
                ),
            ),
            timeout=5,
        )

    async with session_maker() as verification_session:
        stored_case = await verification_session.get(Case, case_id)
        stored_task = await verification_session.get(Task, task_id)

    assert stored_case is not None
    assert stored_case.status == CaseStatus.CLOSED
    assert stored_task is not None
    assert stored_task.case_id == case_id


@pytest.mark.asyncio
async def test_case_closure_and_alert_link_share_parent_before_child_lock_order(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_alert_mutation_side_effects(monkeypatch)
    _isolate_case_mutation_side_effects(monkeypatch)
    monkeypatch.setattr(
        alert_service_module.triage_recommendation_service,
        "auto_reject_if_pending",
        AsyncMock(),
    )
    async with session_maker() as setup_session:
        case = Case(title="Alert link locking", created_by="analyst")
        alert = Alert(title="Unlinked alert")
        setup_session.add(case)
        setup_session.add(alert)
        await setup_session.commit()
        assert case.id is not None
        assert alert.id is not None
        case_id = case.id
        alert_id = alert.id

    async with session_maker() as closure_session, session_maker() as link_session:
        assert await closure_session.get(Case, case_id) is not None
        assert await link_session.get(Alert, alert_id) is not None

        await asyncio.wait_for(
            asyncio.gather(
                case_service.update_case(
                    closure_session,
                    case_id,
                    CaseUpdate(status=CaseStatus.CLOSED),
                    updated_by="closing-analyst",
                ),
                alert_service.link_alert_to_case(
                    link_session,
                    alert_id,
                    case_id,
                    linked_by="linking-analyst",
                ),
            ),
            timeout=5,
        )

    async with session_maker() as verification_session:
        stored_case = await verification_session.get(Case, case_id)
        stored_alert = await verification_session.get(Alert, alert_id)

    assert stored_case is not None
    assert stored_case.status == CaseStatus.CLOSED
    assert stored_alert is not None
    assert stored_alert.case_id == case_id
