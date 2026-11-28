"""Integration tests: add every allowed timeline item type to a Case.

CaseTimelineItem union is the most permissive — 18 types including the
three case-exclusive types: AlertItem, TaskItem, ForensicArtifactItem.
No rejection tests are needed since cases accept all item types.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.models.models import Alert, Case, Task
from tests.fixtures.timeline_api import login_and_get_session_cookie, timeline_values
from tests.fixtures.timeline_payloads import (
    make_alert_ref,
    make_attachment,
    make_case_ref,
    make_email_item,
    make_forensic_artifact,
    make_link,
    make_note,
    make_process,
    make_task_ref,
    make_ttp,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_case(
    client: AsyncClient,
    session_cookie: str,
) -> int:
    response = await client.post(
        "/api/v1/cases",
        json={
            "title": "Timeline-item test case",
            "description": "Case used for timeline item tests",
        },
        cookies={"intercept_session": session_cookie},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _add_timeline_item(
    client: AsyncClient,
    case_id: int,
    payload: dict[str, Any],
    session_cookie: str,
    *,
    expected_status: int = 200,
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/cases/{case_id}/timeline",
        json=payload,
        cookies={"intercept_session": session_cookie},
    )
    assert response.status_code == expected_status, (
        f"Expected {expected_status}, got {response.status_code}: {response.text}"
    )
    body = response.json()
    body["timeline_items"] = timeline_values(body.get("timeline_items"))
    return body


async def _delete_timeline_item(
    client: AsyncClient,
    case_id: int,
    item_id: str,
    session_cookie: str,
) -> dict[str, Any]:
    response = await client.delete(
        f"/api/v1/cases/{case_id}/timeline/{item_id}",
        cookies={"intercept_session": session_cookie},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    body["timeline_items"] = timeline_values(body.get("timeline_items"))
    return body


async def _update_timeline_item(
    client: AsyncClient,
    case_id: int,
    item_id: str,
    payload: dict[str, Any],
    session_cookie: str,
) -> dict[str, Any]:
    response = await client.put(
        f"/api/v1/cases/{case_id}/timeline/{item_id}",
        json=payload,
        cookies={"intercept_session": session_cookie},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    body["timeline_items"] = timeline_values(body.get("timeline_items"))
    return body


# ---------------------------------------------------------------------------
# Simple (non-variant) item types
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload_factory, item_type",
    [
        pytest.param(lambda **_: make_note("note-c1"), "note", id="note"),
        pytest.param(lambda **_: make_attachment("attach-c1"), "attachment", id="attachment"),
        pytest.param(lambda **_: make_ttp("ttp-c1"), "ttp", id="ttp"),
        pytest.param(lambda **_: make_link("link-c1"), "link", id="link"),
        pytest.param(lambda **_: make_email_item("email-c1"), "email", id="email"),
        pytest.param(lambda **_: make_process("proc-c1"), "process", id="process"),
        pytest.param(lambda **_: make_forensic_artifact("forensic-c1"), "forensic_artifact", id="forensic-artifact"),
    ],
)
async def test_add_simple_timeline_item_to_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    payload_factory,
    item_type: str,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    payload = payload_factory()

    body = await _add_timeline_item(client, case_id, payload, session_cookie)

    items = body["timeline_items"]
    assert any(i["type"] == item_type for i in items)


# ---------------------------------------------------------------------------
# Tombstones
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_case_timeline_item_returns_tombstone_when_timeline_is_empty(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    payload = make_note("deleted-note-c1")
    payload["timestamp"] = "2026-01-02T12:00:00+00:00"

    add_body = await _add_timeline_item(client, case_id, payload, session_cookie)
    item_id = add_body["timeline_items"][0]["id"]
    body = await _delete_timeline_item(client, case_id, item_id, session_cookie)

    items = body["timeline_items"]
    assert len(items) == 1
    tombstone = items[0]
    assert tombstone["id"] == item_id
    assert tombstone["type"] == "_deleted"
    assert tombstone["original_type"] == "note"
    assert tombstone["original_timestamp"].startswith("2026-01-02T12:00:00")
    assert tombstone["original_created_at"] is not None
    assert tombstone["deleted_at"] is not None


@pytest.mark.asyncio
async def test_delete_case_timeline_reply_returns_tombstone_under_parent(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    parent_payload = make_note("parent-note-c1")
    reply_payload = make_note("deleted-reply-c1")
    reply_payload["parent_id"] = "parent-note-c1"
    reply_payload["timestamp"] = "2026-01-02T12:15:00+00:00"

    parent_body = await _add_timeline_item(client, case_id, parent_payload, session_cookie)
    parent_id = parent_body["timeline_items"][0]["id"]
    reply_payload["parent_id"] = parent_id
    latest_body = await _add_timeline_item(client, case_id, reply_payload, session_cookie)
    latest_parent = next(item for item in latest_body["timeline_items"] if item["id"] == parent_id)
    reply_id = latest_parent["replies"][-1]["id"]
    body = await _delete_timeline_item(client, case_id, reply_id, session_cookie)

    parent = next(item for item in body["timeline_items"] if item["id"] == parent_id)
    assert len(body["timeline_items"]) == 1
    assert len(parent["replies"]) == 1
    tombstone = parent["replies"][0]
    assert tombstone["id"] == reply_id
    assert tombstone["type"] == "_deleted"
    assert tombstone["parent_id"] == parent_id
    assert tombstone["original_type"] == "note"
    assert tombstone["original_timestamp"].startswith("2026-01-02T12:15:00")


# ---------------------------------------------------------------------------
# Nested reply updates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_case_timeline_reply_description_preserves_parent_structure(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    parent_payload = make_note("parent-update-c1")
    reply_payload = make_note("reply-update-c1")
    reply_payload["parent_id"] = "parent-update-c1"

    parent_body = await _add_timeline_item(client, case_id, parent_payload, session_cookie)
    parent_id = parent_body["timeline_items"][0]["id"]
    reply_payload["parent_id"] = parent_id
    before_body = await _add_timeline_item(client, case_id, reply_payload, session_cookie)
    before_parent = next(item for item in before_body["timeline_items"] if item["id"] == parent_id)
    before_reply = before_parent["replies"][0]

    update_payload = make_note("reply-update-c1")
    update_payload["id"] = before_reply["id"]
    update_payload["parent_id"] = parent_id
    update_payload["description"] = "Edited nested reply"
    body = await _update_timeline_item(
        client,
        case_id,
        before_reply["id"],
        update_payload,
        session_cookie,
    )

    parent = next(item for item in body["timeline_items"] if item["id"] == parent_id)
    assert len(body["timeline_items"]) == 1
    assert len(parent["replies"]) == 1
    reply = parent["replies"][0]
    assert reply["id"] == before_reply["id"]
    assert reply["parent_id"] == parent_id
    assert reply["description"] == "Edited nested reply"
    assert reply["created_at"] == before_reply["created_at"]
    assert reply["created_by"] == before_reply["created_by"]


@pytest.mark.asyncio
async def test_update_case_timeline_reply_flagged_and_highlighted(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    parent_payload = make_note("parent-flags-c1")
    reply_payload = make_note("reply-flags-c1")
    reply_payload["parent_id"] = "parent-flags-c1"

    parent_body = await _add_timeline_item(client, case_id, parent_payload, session_cookie)
    parent_id = parent_body["timeline_items"][0]["id"]
    reply_payload["parent_id"] = parent_id
    before_body = await _add_timeline_item(client, case_id, reply_payload, session_cookie)
    before_parent = next(item for item in before_body["timeline_items"] if item["id"] == parent_id)
    before_reply = before_parent["replies"][0]

    update_payload = make_note("reply-flags-c1")
    update_payload["id"] = before_reply["id"]
    update_payload["parent_id"] = parent_id
    update_payload["flagged"] = True
    update_payload["highlighted"] = True
    body = await _update_timeline_item(
        client,
        case_id,
        before_reply["id"],
        update_payload,
        session_cookie,
    )

    parent = next(item for item in body["timeline_items"] if item["id"] == parent_id)
    reply = parent["replies"][0]
    assert parent["flagged"] is False
    assert parent["highlighted"] is False
    assert reply["flagged"] is True
    assert reply["highlighted"] is True


@pytest.mark.asyncio
async def test_update_deeply_nested_case_timeline_reply(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    parent_payload = make_note("parent-deep-c1")
    first_reply_payload = make_note("reply-deep-c1")
    first_reply_payload["parent_id"] = "parent-deep-c1"
    second_reply_payload = make_note("reply-deep-c2")
    second_reply_payload["parent_id"] = "reply-deep-c1"

    parent_body = await _add_timeline_item(client, case_id, parent_payload, session_cookie)
    parent_id = parent_body["timeline_items"][0]["id"]
    first_reply_payload["parent_id"] = parent_id
    first_body = await _add_timeline_item(client, case_id, first_reply_payload, session_cookie)
    parent = next(item for item in first_body["timeline_items"] if item["id"] == parent_id)
    first_reply_id = parent["replies"][0]["id"]
    second_reply_payload["parent_id"] = first_reply_id
    second_body = await _add_timeline_item(client, case_id, second_reply_payload, session_cookie)
    parent = next(item for item in second_body["timeline_items"] if item["id"] == parent_id)
    second_reply_id = parent["replies"][0]["replies"][0]["id"]

    update_payload = make_note("reply-deep-c2")
    update_payload["id"] = second_reply_id
    update_payload["parent_id"] = first_reply_id
    update_payload["description"] = "Edited deep nested reply"
    body = await _update_timeline_item(
        client,
        case_id,
        second_reply_id,
        update_payload,
        session_cookie,
    )

    parent = next(item for item in body["timeline_items"] if item["id"] == parent_id)
    first_reply = parent["replies"][0]
    second_reply = first_reply["replies"][0]
    assert first_reply["id"] == first_reply_id
    assert second_reply["id"] == second_reply_id
    assert second_reply["parent_id"] == first_reply_id
    assert second_reply["description"] == "Edited deep nested reply"


# ---------------------------------------------------------------------------
# Reference items — case-exclusive types
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_case_ref_to_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    # Seed a second case to reference
    async with session_maker() as session:
        ref_case = Case(title="Ref case", description="For linking", created_by="seed")
        session.add(ref_case)
        await session.commit()
        assert ref_case.id is not None
        ref_case_id = ref_case.id

    case_id = await _create_case(client, session_cookie)
    payload = make_case_ref(ref_case_id, item_id="case-ref-c1")

    body = await _add_timeline_item(client, case_id, payload, session_cookie)

    items = body["timeline_items"]
    assert any(i["type"] == "case" and i["case_id"] == ref_case_id for i in items)


@pytest.mark.asyncio
async def test_add_alert_ref_to_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    # Seed an alert to reference
    async with session_maker() as session:
        alert = Alert(title="Ref alert", description="For linking", source="Test")
        session.add(alert)
        await session.commit()
        assert alert.id is not None
        alert_id = alert.id

    case_id = await _create_case(client, session_cookie)
    payload = make_alert_ref(alert_id, item_id="alert-ref-c1")

    body = await _add_timeline_item(client, case_id, payload, session_cookie)

    items = body["timeline_items"]
    assert any(i["type"] == "alert" and i["alert_id"] == alert_id for i in items)


@pytest.mark.asyncio
async def test_add_task_to_case_creates_task_entity(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    """Adding a task item to a case should auto-create a real Task entity."""
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    payload = make_task_ref(item_id="task-c1")

    body = await _add_timeline_item(client, case_id, payload, session_cookie)

    items = body["timeline_items"]
    task_items = [i for i in items if i["type"] == "task"]
    assert len(task_items) == 1

    # The backend should have auto-created a Task entity
    task_id = task_items[0].get("task_id")
    assert task_id is not None

    async with session_maker() as session:
        task_entity = await session.get(Task, task_id)
        assert task_entity is not None
        assert task_entity.title == "Follow-up investigation task"


@pytest.mark.parametrize("link_description", [None, "Why this task was linked"])
async def test_update_stored_task_reference_preserves_task_description(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    link_description: str | None,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    task_description = "Collect the relevant firewall logs."
    task_response = await client.post(
        "/api/v1/tasks",
        json={"title": "Collect firewall logs", "description": task_description},
        cookies={"intercept_session": session_cookie},
    )
    assert task_response.status_code == 200, task_response.text
    task_id = task_response.json()["id"]
    item_id = "stored-task-reference"
    item = make_task_ref(item_id)
    item.update(task_id=task_id, description=link_description)
    async with session_maker() as session:
        case = await session.get(Case, case_id)
        assert case is not None
        case.timeline_items = {item_id: item}
        await session.commit()

    case_response = await client.get(
        f"/api/v1/cases/{case_id}", cookies={"intercept_session": session_cookie}
    )
    assert case_response.status_code == 200, case_response.text
    stored_item = case_response.json()["timeline_items"][item_id]
    assert stored_item["entity_description"] == task_description
    assert stored_item.get("description") == link_description

    body = await _update_timeline_item(
        client, case_id, item_id, {"type": "task", "flagged": True}, session_cookie
    )
    updated_item = body["timeline_items"][0]
    assert updated_item["flagged"] is True
    assert updated_item["entity_description"] == task_description
    assert updated_item.get("description") == link_description

    updated_item.pop("created_at", None)
    updated_item.update(highlighted=True, description="Updated link notes")
    body = await _update_timeline_item(client, case_id, item_id, updated_item, session_cookie)
    updated_item = body["timeline_items"][0]
    assert updated_item["highlighted"] is True
    assert updated_item["description"] == "Updated link notes"
    assert updated_item["entity_description"] == task_description
