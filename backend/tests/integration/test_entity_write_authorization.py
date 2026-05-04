from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import pytest
from httpx import AsyncClient, Response

from app.models.enums import (
    AlertStatus,
    CaseStatus,
    Priority,
    RecommendationStatus,
    RejectionCategory,
    TaskStatus,
    TriageDisposition,
)
from app.models.models import Alert, Case, Task, TriageRecommendation
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


def _timeline_values(items: Any) -> list[dict[str, Any]]:
    if isinstance(items, dict):
        return [item for item in items.values() if isinstance(item, dict)]
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


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


def _detail_message(response: Response) -> str | None:
    detail = response.json().get("detail")
    if isinstance(detail, dict):
        return detail.get("message")
    if isinstance(detail, str):
        return detail
    return None


async def _login_and_get_session_cookie(
    client: AsyncClient,
    session_maker: Any,
    user_factory: Callable[..., Any],
) -> tuple[str, str]:
    user = user_factory()

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
    return session_cookie, user.username


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/alerts",
            {"title": "Auditor alert", "description": "blocked", "source": "edr"},
        ),
        ("/api/v1/cases", {"title": "Auditor case", "description": "blocked"}),
        ("/api/v1/tasks", {"title": "Auditor task", "description": "blocked"}),
    ],
)
async def test_auditor_cannot_create_parent_entities(
    client: AsyncClient,
    session_maker: Any,
    auditor_user_factory,
    path: str,
    payload: dict[str, Any],
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(
        client, session_maker, auditor_user_factory
    )

    response = await client.post(
        path, json=payload, cookies={"intercept_session": session_cookie}
    )

    assert response.status_code == 403
    assert _detail_message(response) == "Auditor accounts have read-only access"


@pytest.mark.asyncio
async def test_auditor_cannot_update_parent_entities(
    client: AsyncClient,
    session_maker: Any,
    auditor_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(
        client, session_maker, auditor_user_factory
    )

    async with session_maker() as session:
        alert = Alert(
            title="Alert", description="seed", priority=Priority.MEDIUM, source="edr"
        )
        case = Case(
            title="Case",
            description="seed",
            priority=Priority.MEDIUM,
            status=CaseStatus.NEW,
            created_by="seed-user",
        )
        task = Task(
            title="Task",
            description="seed",
            priority=Priority.MEDIUM,
            status=TaskStatus.TODO,
            created_by="seed-user",
            assignee="seed-user",
        )
        session.add_all([alert, case, task])
        await session.commit()
        alert_id = alert.id
        case_id = case.id
        task_id = task.id

    responses = [
        await client.put(
            f"/api/v1/alerts/{alert_id}",
            json={"title": "Updated alert"},
            cookies={"intercept_session": session_cookie},
        ),
        await client.put(
            f"/api/v1/cases/{case_id}",
            json={"title": "Updated case"},
            cookies={"intercept_session": session_cookie},
        ),
        await client.put(
            f"/api/v1/tasks/{task_id}",
            json={"title": "Updated task"},
            cookies={"intercept_session": session_cookie},
        ),
    ]

    for response in responses:
        assert response.status_code == 403
        assert _detail_message(response) == "Auditor accounts have read-only access"


@pytest.mark.asyncio
async def test_auditor_cannot_bulk_update_cases(
    client: AsyncClient,
    session_maker: Any,
    auditor_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(
        client, session_maker, auditor_user_factory
    )

    async with session_maker() as session:
        case = Case(
            title="Case",
            description="seed",
            priority=Priority.MEDIUM,
            status=CaseStatus.NEW,
            created_by="seed-user",
        )
        session.add(case)
        await session.commit()
        case_id = case.id

    response = await client.post(
        "/api/v1/cases/bulk-update",
        json={
            "case_ids": [str(case_id)],
            "case_update": {"title": "Blocked bulk edit"},
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 403
    assert _detail_message(response) == "Auditor accounts have read-only access"


@pytest.mark.asyncio
async def test_auditor_cannot_delete_case_or_task(
    client: AsyncClient,
    session_maker: Any,
    auditor_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(
        client, session_maker, auditor_user_factory
    )

    async with session_maker() as session:
        case = Case(
            title="Case",
            description="seed",
            priority=Priority.MEDIUM,
            status=CaseStatus.NEW,
            created_by="seed-user",
        )
        task = Task(
            title="Task",
            description="seed",
            priority=Priority.MEDIUM,
            status=TaskStatus.TODO,
            created_by="seed-user",
            assignee="seed-user",
        )
        session.add_all([case, task])
        await session.commit()
        case_id = case.id
        task_id = task.id

    case_response = await client.delete(
        f"/api/v1/cases/{case_id}",
        cookies={"intercept_session": session_cookie},
    )
    task_response = await client.delete(
        f"/api/v1/tasks/{task_id}",
        cookies={"intercept_session": session_cookie},
    )

    assert case_response.status_code == 403
    assert task_response.status_code == 403
    assert _detail_message(case_response) == "Auditor accounts have read-only access"
    assert _detail_message(task_response) == "Auditor accounts have read-only access"


@pytest.mark.asyncio
async def test_auditor_cannot_write_timeline_items(
    client: AsyncClient,
    session_maker: Any,
    auditor_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(
        client, session_maker, auditor_user_factory
    )
    existing_case_note = _note_item(
        "seed-user", item_id="case-note-1", description="Original case note"
    )
    existing_task_note = _note_item(
        "seed-user", item_id="task-note-1", description="Original task note"
    )

    async with session_maker() as session:
        alert = Alert(
            title="Alert", description="seed", priority=Priority.MEDIUM, source="edr"
        )
        case = Case(
            title="Case",
            description="seed",
            priority=Priority.MEDIUM,
            status=CaseStatus.IN_PROGRESS,
            created_by="seed-user",
            timeline_items=[existing_case_note],
        )
        task = Task(
            title="Task",
            description="seed",
            priority=Priority.MEDIUM,
            status=TaskStatus.TODO,
            created_by="seed-user",
            assignee="seed-user",
            timeline_items=[existing_task_note],
        )
        session.add_all([alert, case, task])
        await session.commit()
        alert_id = alert.id
        case_id = case.id
        task_id = task.id

    add_response = await client.post(
        f"/api/v1/alerts/{alert_id}/timeline",
        json=_note_item(
            "auditor-user", item_id="alert-note-2", description="Blocked alert note"
        ),
        cookies={"intercept_session": session_cookie},
    )
    update_response = await client.put(
        f"/api/v1/cases/{case_id}/timeline/{existing_case_note['id']}",
        json={**existing_case_note, "description": "Blocked case edit"},
        cookies={"intercept_session": session_cookie},
    )
    delete_response = await client.delete(
        f"/api/v1/tasks/{task_id}/timeline/{existing_task_note['id']}",
        cookies={"intercept_session": session_cookie},
    )

    for response in (add_response, update_response, delete_response):
        assert response.status_code == 403
        assert _detail_message(response) == "Auditor accounts have read-only access"


@pytest.mark.asyncio
async def test_auditor_cannot_mutate_triage_recommendations(
    client: AsyncClient,
    session_maker: Any,
    auditor_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(
        client, session_maker, auditor_user_factory
    )

    async with session_maker() as session:
        alert = Alert(
            title="Alert",
            description="seed",
            priority=Priority.MEDIUM,
            source="edr",
            status=AlertStatus.NEW,
        )
        session.add(alert)
        await session.flush()
        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.NEEDS_INVESTIGATION,
            confidence=0.8,
            reasoning_bullets=["Needs analyst review"],
            recommended_actions=[],
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
        )
        session.add(recommendation)
        await session.commit()
        alert_id = alert.id

    responses = [
        await client.post(
            f"/api/v1/alerts/{alert_id}/triage-recommendation/enqueue",
            cookies={"intercept_session": session_cookie},
        ),
        await client.post(
            f"/api/v1/alerts/{alert_id}/triage-recommendation/accept",
            json={
                "apply_status": True,
                "apply_priority": True,
                "apply_assignee": True,
                "apply_tags": True,
            },
            cookies={"intercept_session": session_cookie},
        ),
        await client.post(
            f"/api/v1/alerts/{alert_id}/triage-recommendation/reject",
            json={
                "category": RejectionCategory.MISSING_CONTEXT.value,
                "reason": "Blocked auditor write",
            },
            cookies={"intercept_session": session_cookie},
        ),
    ]

    for response in responses:
        assert response.status_code == 403
        assert _detail_message(response) == "Auditor accounts have read-only access"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/dummy-data/populate?cases_count=1&alerts_count=1"),
        ("delete", "/api/v1/dummy-data/clear?confirm=true"),
        ("post", "/api/v1/dummy-data/generate-cases?count=1"),
        ("post", "/api/v1/dummy-data/generate-alerts?count=1"),
    ],
)
async def test_auditor_cannot_mutate_dummy_data(
    client: AsyncClient,
    session_maker: Any,
    auditor_user_factory,
    method: str,
    path: str,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(
        client, session_maker, auditor_user_factory
    )

    response = await getattr(client, method)(
        path, cookies={"intercept_session": session_cookie}
    )

    assert response.status_code == 403
    assert _detail_message(response) == "Auditor accounts have read-only access"


@pytest.mark.asyncio
@pytest.mark.parametrize("entity_type", ["alert", "case", "task"])
async def test_analyst_can_edit_other_users_timeline_items(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    entity_type: str,
) -> None:
    owner = analyst_user_factory(username=f"owner-{entity_type}")
    session_cookie, editor_username = await _login_and_get_session_cookie(
        client,
        session_maker,
        lambda: analyst_user_factory(username=f"editor-{entity_type}"),
    )
    original_item = _note_item(
        owner.username,
        item_id=f"{entity_type}-note-1",
        description="Original description",
    )

    async with session_maker() as session:
        session.add(owner)
        if entity_type == "alert":
            entity = Alert(
                title="Alert",
                description="seed",
                priority=Priority.MEDIUM,
                source="edr",
                timeline_items=[original_item],
            )
            route = "/api/v1/alerts/{entity_id}/timeline/{item_id}"
        elif entity_type == "case":
            entity = Case(
                title="Case",
                description="seed",
                priority=Priority.MEDIUM,
                status=CaseStatus.IN_PROGRESS,
                created_by=owner.username,
                timeline_items=[original_item],
            )
            route = "/api/v1/cases/{entity_id}/timeline/{item_id}"
        else:
            entity = Task(
                title="Task",
                description="seed",
                priority=Priority.MEDIUM,
                status=TaskStatus.TODO,
                created_by=owner.username,
                assignee=owner.username,
                timeline_items=[original_item],
            )
            route = "/api/v1/tasks/{entity_id}/timeline/{item_id}"

        session.add(entity)
        await session.commit()
        entity_id = entity.id

    update_payload = {
        **original_item,
        "description": f"Edited by {editor_username}",
    }
    response = await client.put(
        route.format(entity_id=entity_id, item_id=original_item["id"]),
        json=update_payload,
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    timeline_items = _timeline_values(response.json()["timeline_items"])
    updated_item = next(
        item for item in timeline_items if item["id"] == original_item["id"]
    )
    assert updated_item["description"] == f"Edited by {editor_username}"
