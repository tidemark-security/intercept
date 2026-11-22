"""Integration tests: add every allowed timeline item type to a Task.

TaskTimelineItem union accepts 15 types — same as AlertTimelineItem
(excludes AlertItem, ForensicArtifactItem, TaskItem).
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


async def _create_task(
    client: AsyncClient,
    session_cookie: str,
) -> int:
    response = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Timeline-item test task",
            "description": "Task used for timeline item tests",
        },
        cookies={"intercept_session": session_cookie},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _add_timeline_item(
    client: AsyncClient,
    task_id: int,
    payload: dict[str, Any],
    session_cookie: str,
    *,
    expected_status: int = 200,
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/tasks/{task_id}/timeline",
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
    task_id: int,
    item_id: str,
    session_cookie: str,
) -> dict[str, Any]:
    response = await client.delete(
        f"/api/v1/tasks/{task_id}/timeline/{item_id}",
        cookies={"intercept_session": session_cookie},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    body["timeline_items"] = timeline_values(body.get("timeline_items"))
    return body


async def _update_timeline_item(
    client: AsyncClient,
    task_id: int,
    item_id: str,
    payload: dict[str, Any],
    session_cookie: str,
) -> dict[str, Any]:
    response = await client.put(
        f"/api/v1/tasks/{task_id}/timeline/{item_id}",
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
        pytest.param(lambda **_: make_note("note-t1"), "note", id="note"),
        pytest.param(lambda **_: make_attachment("attach-t1"), "attachment", id="attachment"),
        pytest.param(lambda **_: make_ttp("ttp-t1"), "ttp", id="ttp"),
        pytest.param(lambda **_: make_link("link-t1"), "link", id="link"),
        pytest.param(lambda **_: make_email_item("email-t1"), "email", id="email"),
        pytest.param(lambda **_: make_process("proc-t1"), "process", id="process"),
    ],
)
async def test_add_simple_timeline_item_to_task(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    payload_factory,
    item_type: str,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    payload = payload_factory()

    body = await _add_timeline_item(client, task_id, payload, session_cookie)

    items = body["timeline_items"]
    assert any(i["type"] == item_type for i in items)


# ---------------------------------------------------------------------------
# Tombstones
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_task_timeline_item_returns_tombstone_when_timeline_is_empty(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    payload = make_note("deleted-note-t1")
    payload["timestamp"] = "2026-01-02T14:00:00+00:00"

    add_body = await _add_timeline_item(client, task_id, payload, session_cookie)
    item_id = add_body["timeline_items"][0]["id"]
    body = await _delete_timeline_item(client, task_id, item_id, session_cookie)

    items = body["timeline_items"]
    assert len(items) == 1
    tombstone = items[0]
    assert tombstone["id"] == item_id
    assert tombstone["type"] == "_deleted"
    assert tombstone["original_type"] == "note"
    assert tombstone["original_timestamp"].startswith("2026-01-02T14:00:00")
    assert tombstone["original_created_at"] is not None
    assert tombstone["deleted_at"] is not None


@pytest.mark.asyncio
async def test_update_task_timeline_reply_description(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    parent_payload = make_note("parent-update-t1")
    reply_payload = make_note("reply-update-t1")
    reply_payload["parent_id"] = "parent-update-t1"

    parent_body = await _add_timeline_item(client, task_id, parent_payload, session_cookie)
    parent_id = parent_body["timeline_items"][0]["id"]
    reply_payload["parent_id"] = parent_id
    before_body = await _add_timeline_item(client, task_id, reply_payload, session_cookie)
    before_parent = next(item for item in before_body["timeline_items"] if item["id"] == parent_id)
    before_reply = before_parent["replies"][0]

    update_payload = make_note("reply-update-t1")
    update_payload["id"] = before_reply["id"]
    update_payload["parent_id"] = parent_id
    update_payload["description"] = "Edited task reply"
    body = await _update_timeline_item(
        client,
        task_id,
        before_reply["id"],
        update_payload,
        session_cookie,
    )

    parent = next(item for item in body["timeline_items"] if item["id"] == parent_id)
    reply = parent["replies"][0]
    assert reply["id"] == before_reply["id"]
    assert reply["parent_id"] == parent_id
    assert reply["description"] == "Edited task reply"


@pytest.mark.asyncio
async def test_add_case_ref_to_task(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    # Seed a case to reference
    async with session_maker() as session:
        case = Case(title="Ref case", description="For linking", created_by="seed")
        session.add(case)
        await session.commit()
        assert case.id is not None
        case_id = case.id

    task_id = await _create_task(client, session_cookie)
    payload = make_case_ref(case_id, item_id="case-ref-t1")

    body = await _add_timeline_item(client, task_id, payload, session_cookie)

    items = body["timeline_items"]
    assert any(i["type"] == "case" and i["case_id"] == case_id for i in items)


# ---------------------------------------------------------------------------
# Rejection tests — types NOT in TaskTimelineItem
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_task_rejects_task_item(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    payload = make_task_ref(item_id="task-reject-1")

    await _add_timeline_item(client, task_id, payload, session_cookie, expected_status=400)


@pytest.mark.asyncio
async def test_task_rejects_alert_ref_item(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)

    # Create an alert to reference
    async with session_maker() as session:
        alert = Alert(title="Ref alert", description="ref target", source="Test")
        session.add(alert)
        await session.commit()
        assert alert.id is not None
        alert_id = alert.id

    payload = make_alert_ref(alert_id, item_id="alert-reject-1")

    await _add_timeline_item(client, task_id, payload, session_cookie, expected_status=400)


@pytest.mark.asyncio
async def test_task_rejects_forensic_artifact_item(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    payload = make_forensic_artifact(item_id="forensic-reject-1")

    await _add_timeline_item(client, task_id, payload, session_cookie, expected_status=400)
