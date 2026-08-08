from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select

import app.services.timeline_add_service as timeline_mutations
from app.models.enums import TaskStatus
from app.models.models import (
    AttachmentItem,
    AuditLog,
    Case,
    EmailItem,
    NoteItem,
    Task,
    TaskItem,
)
from app.services.storage_service import storage_service
from app.services.timeline_add_service import (
    TimelineItemConflict,
    add_timeline_item_and_commit,
    remove_timeline_item_and_commit,
    update_timeline_item_and_commit,
)


def _stored_note(item_id: str, description: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "note",
        "description": description,
        "created_at": "2026-07-19T00:00:00+00:00",
        "timestamp": "2026-07-19T00:00:00+00:00",
        "created_by": "analyst",
        "replies": {},
    }


def _stored_item(item_id: str, item_type: str, **fields: Any) -> dict[str, Any]:
    return {
        **_stored_note(item_id, fields.pop("description", item_type)),
        "type": item_type,
        **fields,
    }


@pytest.mark.asyncio
async def test_concurrent_timeline_adds_refresh_stale_identity_map_rows(
    session_maker: Any,
) -> None:
    async with session_maker() as setup_session:
        case = Case(title="Concurrent timeline adds", created_by="analyst")
        setup_session.add(case)
        await setup_session.commit()
        assert case.id is not None
        case_id = case.id

    async with session_maker() as first_session, session_maker() as second_session:
        # Retain deliberately stale identity-map instances in both sessions. The
        # row-locking read must refresh whichever transaction acquires the lock
        # second instead of writing this empty timeline back over the first add.
        first_stale = await first_session.get(Case, case_id)
        second_stale = await second_session.get(Case, case_id)
        assert first_stale is not None
        assert second_stale is not None

        first_result, second_result = await asyncio.gather(
            add_timeline_item_and_commit(
                first_session,
                entity_id=case_id,
                entity_type="case",
                timeline_item=NoteItem(id="note-one", description="First note"),
                performed_by="first-analyst",
                preserve_item_id=True,
            ),
            add_timeline_item_and_commit(
                second_session,
                entity_id=case_id,
                entity_type="case",
                timeline_item=NoteItem(id="note-two", description="Second note"),
                performed_by="second-analyst",
                preserve_item_id=True,
            ),
        )

    assert first_result is not None
    assert second_result is not None
    async with session_maker() as verification_session:
        stored_case = await verification_session.get(Case, case_id)
        assert stored_case is not None
        assert set((stored_case.timeline_items or {}).keys()) == {"note-one", "note-two"}


@pytest.mark.asyncio
async def test_concurrent_update_and_remove_preserve_both_locked_mutations(
    session_maker: Any,
) -> None:
    async with session_maker() as setup_session:
        case = Case(
            title="Concurrent timeline mutations",
            created_by="analyst",
            timeline_items={
                "note-update": _stored_note("note-update", "Before update"),
                "note-remove": _stored_note("note-remove", "Remove me"),
            },
        )
        setup_session.add(case)
        await setup_session.commit()
        assert case.id is not None
        case_id = case.id

    async with session_maker() as update_session, session_maker() as remove_session:
        update_stale = await update_session.get(Case, case_id)
        remove_stale = await remove_session.get(Case, case_id)
        assert update_stale is not None
        assert remove_stale is not None

        updated_item, removed_item = await asyncio.gather(
            update_timeline_item_and_commit(
                update_session,
                entity_id=case_id,
                entity_type="case",
                item_id="note-update",
                timeline_item=NoteItem(
                    id="note-update",
                    description="After update",
                ),
                performed_by="updating-analyst",
            ),
            remove_timeline_item_and_commit(
                remove_session,
                entity_id=case_id,
                entity_type="case",
                item_id="note-remove",
                performed_by="removing-analyst",
            ),
        )

    assert updated_item is not None
    assert removed_item is not None
    async with session_maker() as verification_session:
        stored_case = await verification_session.get(Case, case_id)
        assert stored_case is not None
        timeline_items = stored_case.timeline_items or {}
        assert timeline_items["note-update"]["description"] == "After update"
        assert "note-remove" not in timeline_items


@pytest.mark.asyncio
async def test_concurrent_updates_audit_serialized_locked_before_values(
    session_maker: Any,
) -> None:
    async with session_maker() as setup_session:
        case = Case(
            title="Serialized timeline audit",
            created_by="analyst",
            timeline_items={
                "shared-note": _stored_note("shared-note", "Original description"),
            },
        )
        setup_session.add(case)
        await setup_session.commit()
        assert case.id is not None
        case_id = case.id

    async with session_maker() as first_session, session_maker() as second_session:
        first_stale = await first_session.get(Case, case_id)
        second_stale = await second_session.get(Case, case_id)
        assert first_stale is not None
        assert second_stale is not None

        await asyncio.gather(
            update_timeline_item_and_commit(
                first_session,
                entity_id=case_id,
                entity_type="case",
                item_id="shared-note",
                timeline_item=NoteItem(
                    id="shared-note",
                    description="First contender",
                ),
                performed_by="first-analyst",
            ),
            update_timeline_item_and_commit(
                second_session,
                entity_id=case_id,
                entity_type="case",
                item_id="shared-note",
                timeline_item=NoteItem(
                    id="shared-note",
                    description="Second contender",
                ),
                performed_by="second-analyst",
            ),
        )

    async with session_maker() as verification_session:
        stored_case = await verification_session.get(Case, case_id)
        assert stored_case is not None
        result = await verification_session.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "case",
                AuditLog.entity_id == str(case_id),
                AuditLog.event_type == "timeline.item.updated",
                AuditLog.item_id == "shared-note",
            )
        )
        audit_rows = result.scalars().all()

    assert len(audit_rows) == 2
    transitions = [
        (
            json.loads(row.old_value or "{}").get("description"),
            json.loads(row.new_value or "{}").get("description"),
        )
        for row in audit_rows
    ]
    initial_transition = next(
        transition
        for transition in transitions
        if transition[0] == "Original description"
    )
    subsequent_transition = next(
        transition
        for transition in transitions
        if transition[0] != "Original description"
    )
    assert subsequent_transition[0] == initial_transition[1]
    assert subsequent_transition[1] != initial_transition[1]
    assert (stored_case.timeline_items or {})["shared-note"]["description"] == subsequent_transition[1]


@pytest.mark.asyncio
async def test_task_reference_removal_rolls_back_with_parent_timeline_mutation(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with session_maker() as setup_session:
        case = Case(title="Atomic task cleanup", created_by="analyst")
        setup_session.add(case)
        await setup_session.flush()
        assert case.id is not None

        task = Task(title="Backing task", created_by="analyst", case_id=case.id)
        setup_session.add(task)
        await setup_session.flush()
        assert task.id is not None
        case.timeline_items = {
            "task-reference": _stored_item(
                "task-reference",
                "task",
                task_id=task.id,
            )
        }
        await setup_session.commit()
        case_id = case.id
        task_id = task.id

    monkeypatch.setattr(
        timeline_mutations,
        "emit_event",
        AsyncMock(side_effect=RuntimeError("event write failed")),
    )
    async with session_maker() as mutation_session:
        with pytest.raises(RuntimeError, match="event write failed"):
            await remove_timeline_item_and_commit(
                mutation_session,
                entity_id=case_id,
                entity_type="case",
                item_id="task-reference",
                performed_by="analyst",
            )
        await mutation_session.rollback()

    async with session_maker() as verification_session:
        stored_case = await verification_session.get(Case, case_id)
        stored_task = await verification_session.get(Task, task_id)
        assert stored_case is not None
        assert "task-reference" in (stored_case.timeline_items or {})
        assert stored_task is not None


@pytest.mark.asyncio
async def test_task_reference_creation_rolls_back_when_parent_event_fails(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with session_maker() as setup_session:
        case = Case(title="Atomic task creation", created_by="analyst")
        setup_session.add(case)
        await setup_session.commit()
        assert case.id is not None
        case_id = case.id

    monkeypatch.setattr(
        timeline_mutations,
        "emit_event",
        AsyncMock(side_effect=RuntimeError("event write failed")),
    )
    async with session_maker() as mutation_session:
        with pytest.raises(RuntimeError, match="event write failed"):
            await add_timeline_item_and_commit(
                mutation_session,
                entity_id=case_id,
                entity_type="case",
                timeline_item=TaskItem(
                    id="new-task-reference",
                    title="Backing task that must roll back",
                ),
                performed_by="analyst",
                preserve_item_id=True,
            )
        await mutation_session.rollback()

    async with session_maker() as verification_session:
        tasks = (
            await verification_session.execute(
                select(Task).where(Task.case_id == case_id)
            )
        ).scalars().all()

    assert tasks == []


@pytest.mark.asyncio
async def test_task_reference_update_rolls_back_when_parent_audit_fails(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with session_maker() as setup_session:
        case = Case(title="Atomic task update", created_by="analyst")
        setup_session.add(case)
        await setup_session.flush()
        assert case.id is not None

        task = Task(
            title="Original task title",
            status=TaskStatus.TODO,
            created_by="analyst",
            case_id=case.id,
        )
        setup_session.add(task)
        await setup_session.flush()
        assert task.id is not None
        case.timeline_items = {
            "task-reference": _stored_item(
                "task-reference",
                "task",
                task_id=task.id,
                title="Original task title",
                status=TaskStatus.TODO.value,
            )
        }
        await setup_session.commit()
        case_id = case.id
        task_id = task.id

    log_timeline_edit = AsyncMock(side_effect=RuntimeError("audit write failed"))
    monkeypatch.setattr(
        timeline_mutations,
        "get_audit_service",
        lambda _db: SimpleNamespace(log_timeline_edit=log_timeline_edit),
    )
    async with session_maker() as mutation_session:
        with pytest.raises(RuntimeError, match="audit write failed"):
            await update_timeline_item_and_commit(
                mutation_session,
                entity_id=case_id,
                entity_type="case",
                item_id="task-reference",
                timeline_item=TaskItem(
                    id="task-reference",
                    task_id=task_id,
                    title="Updated task title",
                    status=TaskStatus.IN_PROGRESS,
                ),
                performed_by="analyst",
            )
        await mutation_session.rollback()

    async with session_maker() as verification_session:
        stored_task = await verification_session.get(Task, task_id)
        task_audits = (
            await verification_session.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == "task",
                    AuditLog.entity_id == str(task_id),
                )
            )
        ).scalars().all()

    assert stored_task is not None
    assert stored_task.title == "Original task title"
    assert stored_task.status == TaskStatus.TODO
    assert task_audits == []


@pytest.mark.asyncio
async def test_companion_timeline_item_rolls_back_with_attachment_update(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attachment_id = "email-attachment"
    async with session_maker() as setup_session:
        case = Case(
            title="Atomic email evidence",
            created_by="analyst",
            timeline_items={
                attachment_id: _stored_item(
                    attachment_id,
                    "attachment",
                    file_name="evidence.eml",
                    mime_type="message/rfc822",
                    file_size=128,
                    storage_key=f"cases/1/attachments/{attachment_id}/evidence.eml",
                    upload_storage_key=f"_uploads/cases/1/attachments/{attachment_id}/upload",
                    upload_status="UPLOADING",
                )
            },
        )
        setup_session.add(case)
        await setup_session.commit()
        assert case.id is not None
        case_id = case.id

    monkeypatch.setattr(
        timeline_mutations,
        "emit_event",
        AsyncMock(side_effect=[None, RuntimeError("companion event failed")]),
    )
    async with session_maker() as mutation_session:
        with pytest.raises(RuntimeError, match="companion event failed"):
            await update_timeline_item_and_commit(
                mutation_session,
                entity_id=case_id,
                entity_type="case",
                item_id=attachment_id,
                timeline_item=AttachmentItem(
                    id=attachment_id,
                    file_name="evidence.eml",
                    mime_type="message/rfc822",
                    file_size=128,
                    storage_key=f"cases/1/attachments/{attachment_id}/evidence.eml",
                    file_hash="a" * 64,
                    upload_status="COMPLETE",
                ),
                companion_timeline_item=EmailItem(
                    id="derived-email",
                    subject="Derived evidence",
                ),
                performed_by="analyst",
            )
        await mutation_session.rollback()

    async with session_maker() as verification_session:
        stored_case = await verification_session.get(Case, case_id)

    assert stored_case is not None
    timeline_items = stored_case.timeline_items or {}
    assert set(timeline_items) == {attachment_id}
    assert timeline_items[attachment_id]["upload_status"] == "UPLOADING"


@pytest.mark.asyncio
async def test_stale_attachment_transition_is_rejected_under_row_lock(
    session_maker: Any,
) -> None:
    attachment_id = "completed-attachment"
    async with session_maker() as setup_session:
        case = Case(
            title="Attachment transition conflict",
            created_by="analyst",
            timeline_items={
                attachment_id: _stored_item(
                    attachment_id,
                    "attachment",
                    file_name="evidence.txt",
                    upload_status="COMPLETE",
                    upload_storage_key=None,
                )
            },
        )
        setup_session.add(case)
        await setup_session.commit()
        assert case.id is not None
        case_id = case.id

    async with session_maker() as mutation_session:
        with pytest.raises(TimelineItemConflict):
            await update_timeline_item_and_commit(
                mutation_session,
                entity_id=case_id,
                entity_type="case",
                item_id=attachment_id,
                timeline_item=AttachmentItem(
                    id=attachment_id,
                    file_name="evidence.txt",
                    upload_status="COMPLETE",
                ),
                performed_by="analyst",
                expected_item_fields={
                    "upload_status": "UPLOADING",
                    "upload_storage_key": "_uploads/stale",
                },
            )
        await mutation_session.rollback()

    async with session_maker() as verification_session:
        stored_case = await verification_session.get(Case, case_id)

    assert stored_case is not None
    stored_item = (stored_case.timeline_items or {})[attachment_id]
    assert stored_item["upload_status"] == "COMPLETE"
    assert stored_item["upload_storage_key"] is None


@pytest.mark.asyncio
async def test_attachment_storage_cleanup_runs_after_committed_removal(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_key = "cases/1/attachments/evidence.txt"
    async with session_maker() as setup_session:
        case = Case(
            title="Deferred attachment cleanup",
            created_by="analyst",
            timeline_items={
                "attachment": _stored_item(
                    "attachment",
                    "attachment",
                    storage_key=storage_key,
                    file_name="evidence.txt",
                )
            },
        )
        setup_session.add(case)
        await setup_session.commit()
        assert case.id is not None
        case_id = case.id

    delete_file = AsyncMock(side_effect=RuntimeError("storage unavailable"))
    monkeypatch.setattr(storage_service, "delete_file", delete_file)
    async with session_maker() as mutation_session:
        removed_item = await remove_timeline_item_and_commit(
            mutation_session,
            entity_id=case_id,
            entity_type="case",
            item_id="attachment",
            performed_by="analyst",
        )

    assert removed_item is not None
    delete_file.assert_awaited_once_with(storage_key)
    async with session_maker() as verification_session:
        stored_case = await verification_session.get(Case, case_id)
        assert stored_case is not None
        assert "attachment" not in (stored_case.timeline_items or {})


@pytest.mark.asyncio
async def test_staged_attachment_cleanup_runs_after_committed_completion(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attachment_id = "completed-attachment"
    staged_storage_key = "_uploads/cases/1/attachments/completed-attachment/upload"
    async with session_maker() as setup_session:
        case = Case(
            title="Deferred staged cleanup",
            created_by="analyst",
            timeline_items={
                attachment_id: _stored_item(
                    attachment_id,
                    "attachment",
                    file_name="evidence.txt",
                    upload_status="UPLOADING",
                    upload_storage_key=staged_storage_key,
                )
            },
        )
        setup_session.add(case)
        await setup_session.commit()
        assert case.id is not None
        case_id = case.id

    delete_file = AsyncMock(side_effect=RuntimeError("storage unavailable"))
    monkeypatch.setattr(storage_service, "delete_file", delete_file)
    async with session_maker() as mutation_session:
        updated_item = await update_timeline_item_and_commit(
            mutation_session,
            entity_id=case_id,
            entity_type="case",
            item_id=attachment_id,
            timeline_item=AttachmentItem(
                id=attachment_id,
                file_name="evidence.txt",
                upload_status="COMPLETE",
                upload_storage_key=None,
            ),
            performed_by="analyst",
        )

    assert updated_item is not None
    delete_file.assert_awaited_once_with(staged_storage_key)
    async with session_maker() as verification_session:
        stored_case = await verification_session.get(Case, case_id)

    assert stored_case is not None
    stored_item = (stored_case.timeline_items or {})[attachment_id]
    assert stored_item["upload_status"] == "COMPLETE"
    assert stored_item["upload_storage_key"] is None
