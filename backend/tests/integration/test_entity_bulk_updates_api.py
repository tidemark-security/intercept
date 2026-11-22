import pytest
from sqlalchemy import select

from app.models.enums import AlertStatus, CaseStatus, TaskStatus
from app.models.models import Alert, AuditLog, Case, Task
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def sign_in(client, session_maker, user):
    async with session_maker() as session:
        session.add(user)
        await session.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login.status_code == 200
    return {"intercept_session": login.cookies["intercept_session"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resource, model, old_status, new_status",
    [
        ("cases", Case, CaseStatus.NEW, CaseStatus.CLOSED),
        ("tasks", Task, TaskStatus.TODO, TaskStatus.DONE),
    ],
)
async def test_bulk_update_merges_tags_and_appends_notes_only_to_selected_entities(
    client, session_maker, analyst_user_factory, resource, model, old_status, new_status,
):
    actor = analyst_user_factory()
    cookies = await sign_in(client, session_maker, actor)
    async with session_maker() as session:
        entities = [
            model(title=f"Selected row {i}", created_by=actor.username, tags=[f"original-{i}"])
            for i in range(3)
        ]
        session.add_all(entities)
        await session.flush()
        first, second, other = [entity.id for entity in entities]
        await session.commit()

    update = {
        "status": new_status.value,
        "assignee": actor.username,
        "tags": ["reviewed"],
        "note": "  Reviewed in bulk.  ",
    }
    # A missing row must not leave the rows that were processed earlier changed.
    result = await client.post(
        f"/api/v1/{resource}/bulk-actions",
        json={"entity_ids": [first, second, 999999], **update},
        cookies=cookies,
    )
    assert result.status_code == 404, result.text
    async with session_maker() as session:
        before = await session.get(model, first)
        assert before.status == old_status
        assert before.tags == ["original-0"]
        assert not before.timeline_items

    result = await client.post(
        f"/api/v1/{resource}/bulk-actions",
        json={"entity_ids": [second, first, second], **update},
        cookies=cookies,
    )
    assert result.status_code == 200, result.text
    assert result.json() == {"updated_count": 2}

    async with session_maker() as session:
        note_ids = set()
        for i, entity_id in enumerate([first, second]):
            entity = await session.get(model, entity_id)
            assert entity.status == new_status
            assert entity.assignee == actor.username
            assert entity.tags == [f"original-{i}", "reviewed"]
            notes = [item for item in entity.timeline_items.values() if item["description"] == "Reviewed in bulk."]
            assert len(notes) == 1
            assert notes[0]["created_by"] == actor.username
            assert notes[0].get("activity_kind") is None
            note_ids.add(notes[0]["id"])
            assert await session.scalar(select(AuditLog).where(
                AuditLog.event_type == "timeline.item.added", AuditLog.item_id == notes[0]["id"]
            ))
        assert len(note_ids) == 2
        untouched = await session.get(model, other)
        assert untouched.status == old_status
        assert untouched.assignee is None
        assert untouched.tags == ["original-2"]
        assert not untouched.timeline_items

    detail = await client.get(f"/api/v1/{resource}/{first}", cookies=cookies)
    assert detail.status_code == 200, detail.text
    timeline = detail.json()["timeline_items"].values()
    bulk_note, = [item for item in timeline if item.get("description") == "Reviewed in bulk."]
    assert bulk_note.get("activity_kind") is None
    if resource == "tasks":
        status_note, = [item for item in timeline if item.get("activity_kind") == "status_changed"]
        assert status_note["type"] == "note"
        assert status_note["created_by"] == actor.username
        assert status_note["description"] == "Task marked as Done (from To Do)"


@pytest.mark.asyncio
async def test_bulk_case_closure_runs_existing_linked_entity_rules(
    client, session_maker, analyst_user_factory,
):
    actor = analyst_user_factory()
    cookies = await sign_in(client, session_maker, actor)
    async with session_maker() as session:
        cases = [Case(title=f"Case {i}", created_by=actor.username) for i in range(2)]
        session.add_all(cases)
        await session.flush()
        case_ids = [case.id for case in cases]
        task = Task(title="Linked task", created_by=actor.username, case_id=case_ids[0])
        alert = Alert(title="Linked alert", case_id=case_ids[1])
        session.add_all([task, alert])
        await session.flush()
        task_id, alert_id = task.id, alert.id
        await session.commit()

    response = await client.post(
        "/api/v1/cases/bulk-actions",
        json={"entity_ids": case_ids, "status": "CLOSED"},
        cookies=cookies,
    )
    assert response.status_code == 200, response.text
    async with session_maker() as session:
        task = await session.get(Task, task_id)
        alert = await session.get(Alert, alert_id)
        assert task.status == TaskStatus.DONE
        assert alert.status == AlertStatus.CLOSED_UNRESOLVED
        for entity in (task, alert):
            note, = entity.timeline_items.values()
            assert note["activity_kind"] == "closed_with_case"
            assert note["created_by"] == actor.username


@pytest.mark.asyncio
async def test_timeline_clients_cannot_set_or_replace_activity_kind(client, session_maker, analyst_user_factory):
    actor = analyst_user_factory()
    cookies = await sign_in(client, session_maker, actor)
    async with session_maker() as session:
        task = Task(title="Activity classification", created_by=actor.username)
        session.add(task)
        await session.flush()
        task_id = task.id
        await session.commit()

    result = await client.post(
        "/api/v1/tasks/bulk-actions",
        json={"entity_ids": [task_id], "status": "DONE"},
        cookies=cookies,
    )
    assert result.status_code == 200, result.text
    timeline_url = f"/api/v1/tasks/{task_id}/timeline"
    client_note = {"type": "note", "description": "A comment", "activity_kind": "automation_failed"}
    result = await client.post(
        timeline_url,
        json={**client_note, "replies": {"reply": {**client_note, "id": "reply"}}},
        cookies=cookies,
    )
    assert result.status_code == 200, result.text
    items = result.json()["timeline_items"].values()
    activity, = [item for item in items if item.get("activity_kind") == "status_changed"]
    comment, = [item for item in items if item["description"] == "A comment"]
    reply, = comment["replies"].values()
    assert comment.get("activity_kind") is None
    assert reply.get("activity_kind") is None

    result = await client.put(f"{timeline_url}/{activity['id']}", json=client_note, cookies=cookies)
    assert result.status_code == 200, result.text
    edited = result.json()["timeline_items"][activity["id"]]
    assert edited["description"] == "A comment"
    assert edited["activity_kind"] == "status_changed"
    assert edited["created_by"] == actor.username
