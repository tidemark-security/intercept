from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.models import Task
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _note_item(created_by: str, *, item_id: str, description: str) -> dict[str, Any]:
    now = _now_iso()
    return {
        "id": item_id,
        "type": "note",
        "description": description,
        "created_at": now,
        "timestamp": now,
        "created_by": created_by,
        "tags": [],
        "flagged": False,
        "highlighted": False,
        "enrichments": {},
        "replies": [],
    }


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


@pytest.mark.asyncio
async def test_create_task_serializes_response_after_reload(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    response = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Serialized task create",
            "description": "Created through API",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Serialized task create"
    assert payload["human_id"].startswith("TSK-")
    assert payload["timeline_items"] == []


@pytest.mark.asyncio
async def test_update_task_serializes_response_after_reload(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        task = Task(
            title="Original task title",
            description="Original task description",
            created_by="seed-user",
            assignee="seed-user",
        )
        session.add(task)
        await session.commit()
        assert task.id is not None
        task_id = task.id

    response = await client.put(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Updated task title"},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == task_id
    assert payload["title"] == "Updated task title"
    assert payload["human_id"].startswith("TSK-")


@pytest.mark.asyncio
async def test_add_task_timeline_item_serializes_response_after_reload(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        task = Task(
            title="Timeline task",
            description="Task for timeline add",
            created_by="seed-user",
            assignee="seed-user",
            timeline_items=[],
        )
        session.add(task)
        await session.commit()
        assert task.id is not None
        task_id = task.id

    response = await client.post(
        f"/api/v1/tasks/{task_id}/timeline",
        json=_note_item("analyst-user", item_id="task-note-1", description="Timeline note"),
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == task_id
    assert len(payload["timeline_items"]) == 1
    assert payload["timeline_items"][0]["id"] == "task-note-1"