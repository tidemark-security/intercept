"""Integration tests: add every allowed timeline item type to a Task.

TaskTimelineItem union accepts 15 types — same as AlertTimelineItem
(excludes AlertItem, ForensicArtifactItem, TaskItem).
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.models.models import Alert, Case, Task
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD
from tests.fixtures.timeline_payloads import (
    EXTERNAL_ACTOR_VARIANTS,
    INTERNAL_ACTOR_VARIANTS,
    OBSERVABLE_VARIANTS,
    PROTOCOL_VARIANTS,
    REGISTRY_OP_VARIANTS,
    SYSTEM_TYPE_VARIANTS,
    THREAT_ACTOR_VARIANTS,
    make_alert_ref,
    make_attachment,
    make_case_ref,
    make_email_item,
    make_external_actor,
    make_forensic_artifact,
    make_internal_actor,
    make_link,
    make_network_traffic,
    make_note,
    make_observable,
    make_process,
    make_registry_change,
    make_system,
    make_task_ref,
    make_threat_actor,
    make_ttp,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _timeline_values(items: Any) -> list[dict[str, Any]]:
    if isinstance(items, dict):
        return [
            {
                **item,
                "replies": _timeline_values(item.get("replies")),
            }
            for item in items.values()
            if isinstance(item, dict)
        ]
    if isinstance(items, list):
        return [
            {
                **item,
                "replies": _timeline_values(item.get("replies")),
            }
            for item in items
            if isinstance(item, dict)
        ]
    return []

async def _login_and_get_session_cookie(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> str:
    user = analyst_user_factory()

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200

    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    return session_cookie


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
    body["timeline_items"] = _timeline_values(body.get("timeline_items"))
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
    body["timeline_items"] = _timeline_values(body.get("timeline_items"))
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
    body["timeline_items"] = _timeline_values(body.get("timeline_items"))
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
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
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
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    payload = make_note("deleted-note-t1")
    payload["timestamp"] = "2026-01-02T14:00:00+00:00"
    payload["created_at"] = "2026-01-02T14:00:01+00:00"

    await _add_timeline_item(client, task_id, payload, session_cookie)
    body = await _delete_timeline_item(client, task_id, "deleted-note-t1", session_cookie)

    items = body["timeline_items"]
    assert len(items) == 1
    tombstone = items[0]
    assert tombstone["id"] == "deleted-note-t1"
    assert tombstone["type"] == "_deleted"
    assert tombstone["original_type"] == "note"
    assert tombstone["original_timestamp"].startswith("2026-01-02T14:00:00")
    assert tombstone["original_created_at"].startswith("2026-01-02T14:00:01")
    assert tombstone["deleted_at"] is not None


@pytest.mark.asyncio
async def test_update_task_timeline_reply_description(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    parent_payload = make_note("parent-update-t1")
    reply_payload = make_note("reply-update-t1")
    reply_payload["parent_id"] = "parent-update-t1"

    await _add_timeline_item(client, task_id, parent_payload, session_cookie)
    await _add_timeline_item(client, task_id, reply_payload, session_cookie)

    update_payload = make_note("reply-update-t1")
    update_payload["parent_id"] = "parent-update-t1"
    update_payload["description"] = "Edited task reply"
    body = await _update_timeline_item(
        client,
        task_id,
        "reply-update-t1",
        update_payload,
        session_cookie,
    )

    parent = next(item for item in body["timeline_items"] if item["id"] == "parent-update-t1")
    reply = parent["replies"][0]
    assert reply["id"] == "reply-update-t1"
    assert reply["parent_id"] == "parent-update-t1"
    assert reply["description"] == "Edited task reply"


@pytest.mark.asyncio
async def test_add_case_ref_to_task(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

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
# Observable variants (8 types)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("obs_type, obs_value", OBSERVABLE_VARIANTS)
async def test_add_observable_variant_to_task(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    obs_type: str,
    obs_value: str,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    payload = make_observable(obs_type, obs_value, item_id=f"obs-{obs_type.lower()}")

    body = await _add_timeline_item(client, task_id, payload, session_cookie)

    items = body["timeline_items"]
    match = [i for i in items if i["type"] == "observable" and i["observable_type"] == obs_type]
    assert len(match) == 1
    assert match[0]["observable_value"] == obs_value


# ---------------------------------------------------------------------------
# System type variants (5 categories)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("system_type", SYSTEM_TYPE_VARIANTS)
async def test_add_system_variant_to_task(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    system_type: str,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    payload = make_system(system_type, item_id=f"sys-{system_type.lower()}")

    body = await _add_timeline_item(client, task_id, payload, session_cookie)

    items = body["timeline_items"]
    match = [i for i in items if i["type"] == "system" and i["system_type"] == system_type]
    assert len(match) == 1


# ---------------------------------------------------------------------------
# Internal actor variants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", INTERNAL_ACTOR_VARIANTS)
async def test_add_internal_actor_variant_to_task(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    kwargs: dict[str, Any],
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    payload = make_internal_actor(**kwargs, item_id=f"iactor-{list(kwargs.values())[0]}")

    body = await _add_timeline_item(client, task_id, payload, session_cookie)

    items = body["timeline_items"]
    assert any(i["type"] == "internal_actor" for i in items)


# ---------------------------------------------------------------------------
# External actor variants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", EXTERNAL_ACTOR_VARIANTS)
async def test_add_external_actor_variant_to_task(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    kwargs: dict[str, Any],
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    payload = make_external_actor(**kwargs, item_id=f"eactor-{list(kwargs.values())[0]}")

    body = await _add_timeline_item(client, task_id, payload, session_cookie)

    items = body["timeline_items"]
    assert any(i["type"] == "external_actor" for i in items)


# ---------------------------------------------------------------------------
# Threat actor variants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", THREAT_ACTOR_VARIANTS)
async def test_add_threat_actor_variant_to_task(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    kwargs: dict[str, Any],
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    payload = make_threat_actor(**kwargs, item_id=f"tactor-{list(kwargs.values())[0]}")

    body = await _add_timeline_item(client, task_id, payload, session_cookie)

    items = body["timeline_items"]
    assert any(i["type"] == "threat_actor" for i in items)


# ---------------------------------------------------------------------------
# Network traffic protocol variants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", PROTOCOL_VARIANTS)
async def test_add_network_traffic_variant_to_task(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    protocol: str,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    payload = make_network_traffic(protocol, item_id=f"net-{protocol.lower()}")

    body = await _add_timeline_item(client, task_id, payload, session_cookie)

    items = body["timeline_items"]
    match = [i for i in items if i["type"] == "network_traffic" and i["protocol"] == protocol]
    assert len(match) == 1


# ---------------------------------------------------------------------------
# Registry change operation variants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("operation", REGISTRY_OP_VARIANTS)
async def test_add_registry_change_variant_to_task(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    operation: str,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    payload = make_registry_change(operation, item_id=f"reg-{operation.lower()}")

    body = await _add_timeline_item(client, task_id, payload, session_cookie)

    items = body["timeline_items"]
    match = [i for i in items if i["type"] == "registry_change" and i["operation"] == operation]
    assert len(match) == 1


# ---------------------------------------------------------------------------
# Rejection tests — types NOT in TaskTimelineItem
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_task_rejects_task_item(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    payload = make_task_ref(item_id="task-reject-1")

    await _add_timeline_item(client, task_id, payload, session_cookie, expected_status=400)


@pytest.mark.asyncio
async def test_task_rejects_alert_ref_item(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
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
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    payload = make_forensic_artifact(item_id="forensic-reject-1")

    await _add_timeline_item(client, task_id, payload, session_cookie, expected_status=400)
