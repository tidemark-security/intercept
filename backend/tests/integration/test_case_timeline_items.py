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
    return response.json()


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
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    payload = payload_factory()

    body = await _add_timeline_item(client, case_id, payload, session_cookie)

    items = body["timeline_items"]
    assert any(i["type"] == item_type for i in items)


# ---------------------------------------------------------------------------
# Reference items — case-exclusive types
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_case_ref_to_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

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
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

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
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
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


# ---------------------------------------------------------------------------
# Observable variants (8 types)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("obs_type, obs_value", OBSERVABLE_VARIANTS)
async def test_add_observable_variant_to_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    obs_type: str,
    obs_value: str,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    payload = make_observable(obs_type, obs_value, item_id=f"obs-{obs_type.lower()}")

    body = await _add_timeline_item(client, case_id, payload, session_cookie)

    items = body["timeline_items"]
    match = [i for i in items if i["type"] == "observable" and i["observable_type"] == obs_type]
    assert len(match) == 1
    assert match[0]["observable_value"] == obs_value


# ---------------------------------------------------------------------------
# System type variants (5 categories)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("system_type", SYSTEM_TYPE_VARIANTS)
async def test_add_system_variant_to_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    system_type: str,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    payload = make_system(system_type, item_id=f"sys-{system_type.lower()}")

    body = await _add_timeline_item(client, case_id, payload, session_cookie)

    items = body["timeline_items"]
    match = [i for i in items if i["type"] == "system" and i["system_type"] == system_type]
    assert len(match) == 1


# ---------------------------------------------------------------------------
# Internal actor variants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", INTERNAL_ACTOR_VARIANTS)
async def test_add_internal_actor_variant_to_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    kwargs: dict[str, Any],
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    payload = make_internal_actor(**kwargs, item_id=f"iactor-{list(kwargs.values())[0]}")

    body = await _add_timeline_item(client, case_id, payload, session_cookie)

    items = body["timeline_items"]
    assert any(i["type"] == "internal_actor" for i in items)


# ---------------------------------------------------------------------------
# External actor variants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", EXTERNAL_ACTOR_VARIANTS)
async def test_add_external_actor_variant_to_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    kwargs: dict[str, Any],
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    payload = make_external_actor(**kwargs, item_id=f"eactor-{list(kwargs.values())[0]}")

    body = await _add_timeline_item(client, case_id, payload, session_cookie)

    items = body["timeline_items"]
    assert any(i["type"] == "external_actor" for i in items)


# ---------------------------------------------------------------------------
# Threat actor variants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", THREAT_ACTOR_VARIANTS)
async def test_add_threat_actor_variant_to_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    kwargs: dict[str, Any],
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    payload = make_threat_actor(**kwargs, item_id=f"tactor-{list(kwargs.values())[0]}")

    body = await _add_timeline_item(client, case_id, payload, session_cookie)

    items = body["timeline_items"]
    assert any(i["type"] == "threat_actor" for i in items)


# ---------------------------------------------------------------------------
# Network traffic protocol variants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", PROTOCOL_VARIANTS)
async def test_add_network_traffic_variant_to_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    protocol: str,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    payload = make_network_traffic(protocol, item_id=f"net-{protocol.lower()}")

    body = await _add_timeline_item(client, case_id, payload, session_cookie)

    items = body["timeline_items"]
    match = [i for i in items if i["type"] == "network_traffic" and i["protocol"] == protocol]
    assert len(match) == 1


# ---------------------------------------------------------------------------
# Registry change operation variants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("operation", REGISTRY_OP_VARIANTS)
async def test_add_registry_change_variant_to_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    operation: str,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(client, session_cookie)
    payload = make_registry_change(operation, item_id=f"reg-{operation.lower()}")

    body = await _add_timeline_item(client, case_id, payload, session_cookie)

    items = body["timeline_items"]
    match = [i for i in items if i["type"] == "registry_change" and i["operation"] == operation]
    assert len(match) == 1
