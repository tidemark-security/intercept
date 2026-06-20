from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import Task, UserAccount
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
    assert payload["timeline_items"] == {}


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
        json={
            "title": "Updated task title",
            "tags": [" Review ", "review", "Null", "escalated"],
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == task_id
    assert payload["title"] == "Updated task title"
    assert payload["tags"] == ["Review", "escalated"]
    assert payload["human_id"].startswith("TSK-")


@pytest.mark.asyncio
async def test_update_task_enqueues_autonomous_execution_for_assignable_nhi(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    enqueued: list[dict[str, Any]] = []

    class FakeQueue:
        async def enqueue(
            self,
            *,
            task_name: str,
            payload: dict[str, object],
            priority: int = 0,
            schedule_at: object = None,
            dedupe_key: str | None = None,
        ) -> str:
            enqueued.append(
                {
                    "task_name": task_name,
                    "payload": payload,
                    "priority": priority,
                    "schedule_at": schedule_at,
                    "dedupe_key": dedupe_key,
                }
            )
            return "autonomous-job-1"

    monkeypatch.setattr("app.services.task_queue_service.get_task_queue_service", lambda: FakeQueue())

    async with session_maker() as session:
        agent = UserAccount(
            username="splunk-agent",
            display_name="Splunk Agent",
            role=UserRole.ANALYST,
            account_type=AccountType.NHI,
            status=UserStatus.ACTIVE,
            assignable=True,
        )
        task = Task(
            title="Investigate Splunk alert",
            description="Use Splunk and Falcon to investigate",
            created_by="seed-user",
            assignee="analyst-user",
        )
        session.add_all([agent, task])
        await session.commit()
        assert task.id is not None
        task_id = task.id

    response = await client.put(
        f"/api/v1/tasks/{task_id}",
        json={"assignee": "splunk-agent"},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    assert enqueued == [
        {
            "task_name": "autonomous_task",
            "payload": {"task_id": task_id, "agent_username": "splunk-agent"},
            "priority": 0,
            "schedule_at": None,
            "dedupe_key": f"autonomous_task:{task_id}:splunk-agent",
        }
    ]


@pytest.mark.asyncio
async def test_update_task_does_not_enqueue_autonomous_execution_for_human_assignee(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    class FakeQueue:
        async def enqueue(self, **_: object) -> str:
            raise AssertionError("Human assignees must not enqueue autonomous execution")

    monkeypatch.setattr("app.services.task_queue_service.get_task_queue_service", lambda: FakeQueue())

    async with session_maker() as session:
        human = UserAccount(
            username="human-analyst",
            display_name="Human Analyst",
            email="human-analyst@example.com",
            role=UserRole.ANALYST,
            account_type=AccountType.HUMAN,
            status=UserStatus.ACTIVE,
            assignable=False,
        )
        task = Task(
            title="Human-handled alert",
            description="Should stay manual",
            created_by="seed-user",
            assignee="seed-user",
        )
        session.add_all([human, task])
        await session.commit()
        assert task.id is not None
        task_id = task.id

    response = await client.put(
        f"/api/v1/tasks/{task_id}",
        json={"assignee": "human-analyst"},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_tasks_filters_unassigned_sentinel(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        unassigned_task = Task(
            title="Unassigned task",
            description="Should match sentinel filter",
            created_by="seed-user",
            assignee=None,
        )
        assigned_task = Task(
            title="Assigned task",
            description="Should not match sentinel filter",
            created_by="seed-user",
            assignee="analyst-user",
        )
        session.add_all([unassigned_task, assigned_task])
        await session.commit()

    response = await client.get(
        "/api/v1/tasks",
        params={"assignee": "__unassigned__"},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    titles = {item["title"] for item in response.json()["items"]}
    assert "Unassigned task" in titles
    assert "Assigned task" not in titles


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
    item_id, item = next(iter(payload["timeline_items"].items()))
    assert item_id == item["id"]
    assert item_id != "task-note-1"
    assert item["type"] == "note"
    assert item["description"] == "Timeline note"
