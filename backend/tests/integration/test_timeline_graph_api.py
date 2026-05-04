from __future__ import annotations

from typing import Any, Callable

import pytest
from httpx import AsyncClient, Response

from app.models.enums import Priority, TaskStatus
from app.models.models import Case, Task
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


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


async def _create_case(session_maker: Any) -> int:
    async with session_maker() as session:
        case = Case(
            title="Graph case",
            description="Graph persistence test",
            priority=Priority.MEDIUM,
            created_by="seed-user",
            timeline_items={},
        )
        session.add(case)
        await session.commit()
        return case.id  # type: ignore[return-value]


async def _create_task(session_maker: Any) -> int:
    async with session_maker() as session:
        task = Task(
            title="Graph task",
            description="Graph persistence test",
            priority=Priority.MEDIUM,
            status=TaskStatus.TODO,
            assignee="seed-user",
            created_by="seed-user",
            timeline_items={},
        )
        session.add(task)
        await session.commit()
        return task.id  # type: ignore[return-value]


def _node_operation(node_id: str, item_id: str, x: int = 10, y: int = 20) -> dict[str, Any]:
    return {
        "type": "add_node",
        "node_id": node_id,
        "item_id": item_id,
        "position": {"x": x, "y": y},
    }


def _edge_operation(edge_id: str = "edge-1") -> dict[str, Any]:
    return {
        "type": "add_edge",
        "edge_id": edge_id,
        "source": "node-item-1",
        "target": "node-item-2",
        "source_handle": "east-source",
        "target_handle": "west-target",
        "label": "initial",
    }


def _detail_message(response: Response) -> str | None:
    detail = response.json().get("detail")
    if isinstance(detail, dict):
        return detail.get("message")
    if isinstance(detail, str):
        return detail
    return None


@pytest.mark.asyncio
async def test_get_returns_empty_graph_for_case_and_task(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(session_maker)
    task_id = await _create_task(session_maker)

    case_response = await client.get(f"/api/v1/cases/{case_id}/timeline-graph", cookies={"intercept_session": session_cookie})
    task_response = await client.get(f"/api/v1/tasks/{task_id}/timeline-graph", cookies={"intercept_session": session_cookie})

    assert case_response.status_code == 200
    assert task_response.status_code == 200
    assert case_response.json()["graph"] == {"nodes": {}, "edges": {}}
    assert task_response.json()["graph"] == {"nodes": {}, "edges": {}}
    assert case_response.json()["revision"] == 0
    assert task_response.json()["revision"] == 0


@pytest.mark.asyncio
async def test_patch_creates_graph_and_increments_revision(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(session_maker)

    response = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": 0, "operations": [_node_operation("node-item-1", "item-1")]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["revision"] == 1
    assert body["graph"]["nodes"]["node-item-1"]["item_id"] == "item-1"


@pytest.mark.asyncio
async def test_stale_patches_to_different_objects_merge(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(session_maker)

    first = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": 0, "operations": [_node_operation("node-item-1", "item-1")]},
    )
    second = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": 0, "operations": [_node_operation("node-item-2", "item-2", 100, 100)]},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert set(second.json()["graph"]["nodes"]) == {"node-item-1", "node-item-2"}


@pytest.mark.asyncio
async def test_concurrent_node_moves_are_last_write_wins(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(session_maker)

    created = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": 0, "operations": [_node_operation("node-item-1", "item-1")]},
    )
    base_revision = created.json()["revision"]

    await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": base_revision, "operations": [{"type": "move_node", "node_id": "node-item-1", "position": {"x": 50, "y": 50}}]},
    )
    final = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": base_revision, "operations": [{"type": "move_node", "node_id": "node-item-1", "position": {"x": 90, "y": 90}}]},
    )

    assert final.status_code == 200
    assert final.json()["graph"]["nodes"]["node-item-1"]["position"] == {"x": 90.0, "y": 90.0}


@pytest.mark.asyncio
async def test_edge_label_conflict_returns_current_graph(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(session_maker)

    created = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={
            "base_revision": 0,
            "operations": [
                _node_operation("node-item-1", "item-1"),
                _node_operation("node-item-2", "item-2", 100, 100),
                _edge_operation(),
            ],
        },
    )
    base_revision = created.json()["revision"]

    await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": base_revision, "operations": [{"type": "update_edge_label", "edge_id": "edge-1", "label": "winner"}]},
    )
    conflict = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": base_revision, "operations": [{"type": "update_edge_label", "edge_id": "edge-1", "label": "loser"}]},
    )

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["conflicting_operation_indexes"] == [0]
    assert conflict.json()["detail"]["graph"]["graph"]["edges"]["edge-1"]["label"] == "winner"


@pytest.mark.asyncio
async def test_remove_node_conflicts_when_incident_edge_changed_then_removes_edges(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(session_maker)

    created = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={
            "base_revision": 0,
            "operations": [
                _node_operation("node-item-1", "item-1"),
                _node_operation("node-item-2", "item-2", 100, 100),
                _edge_operation(),
            ],
        },
    )
    base_revision = created.json()["revision"]

    changed = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": base_revision, "operations": [{"type": "update_edge_label", "edge_id": "edge-1", "label": "changed"}]},
    )
    conflict = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": base_revision, "operations": [{"type": "remove_node", "node_id": "node-item-1"}]},
    )
    removed = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": changed.json()["revision"], "operations": [{"type": "remove_node", "node_id": "node-item-1"}]},
    )

    assert conflict.status_code == 409
    assert removed.status_code == 200
    assert "node-item-1" not in removed.json()["graph"]["nodes"]
    assert removed.json()["graph"]["edges"] == {}


@pytest.mark.asyncio
async def test_node_resize_persists_and_conflicts_on_stale_resize(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(session_maker)

    created = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": 0, "operations": [_node_operation("node-item-1", "item-1")]},
    )
    base_revision = created.json()["revision"]

    resized = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": base_revision, "operations": [{"type": "resize_node", "node_id": "node-item-1", "width": 420, "height": 308}]},
    )
    conflict = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": base_revision, "operations": [{"type": "resize_node", "node_id": "node-item-1", "width": 392, "height": 280}]},
    )

    assert resized.status_code == 200
    assert resized.json()["graph"]["nodes"]["node-item-1"]["width"] == 420.0
    assert resized.json()["graph"]["nodes"]["node-item-1"]["height"] == 308.0
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["conflicting_operation_indexes"] == [0]


@pytest.mark.asyncio
async def test_edge_marker_and_reconnect_persist(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(session_maker)

    created = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={
            "base_revision": 0,
            "operations": [
                _node_operation("node-item-1", "item-1"),
                _node_operation("node-item-2", "item-2", 100, 100),
                _node_operation("node-item-3", "item-3", 200, 100),
                _edge_operation(),
            ],
        },
    )

    marked = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": created.json()["revision"], "operations": [{"type": "update_edge_metadata", "edge_id": "edge-1", "marker": "bidirectional"}]},
    )
    reconnected = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={
            "base_revision": marked.json()["revision"],
            "operations": [{
                "type": "reconnect_edge",
                "edge_id": "edge-1",
                "source": "node-item-2",
                "target": "node-item-3",
                "source_handle": "east-source",
                "target_handle": "west-target",
            }],
        },
    )

    assert marked.status_code == 200
    assert marked.json()["graph"]["edges"]["edge-1"]["marker"] == "bidirectional"
    assert reconnected.status_code == 200
    edge = reconnected.json()["graph"]["edges"]["edge-1"]
    assert edge["source"] == "node-item-2"
    assert edge["target"] == "node-item-3"
    assert edge["marker"] == "bidirectional"


@pytest.mark.asyncio
async def test_group_node_and_parent_assignment_persist(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(session_maker)

    created = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={
            "base_revision": 0,
            "operations": [
                _node_operation("node-item-1", "item-1", 60, 70),
                _node_operation("node-item-2", "item-2", 260, 70),
            ],
        },
    )
    response = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={
            "base_revision": created.json()["revision"],
            "operations": [
                {
                    "type": "add_group",
                    "node_id": "group-1",
                    "position": {"x": 40, "y": 40},
                    "width": 520,
                    "height": 260,
                    "label": "Investigation thread",
                },
                {"type": "move_node", "node_id": "node-item-1", "position": {"x": 20, "y": 30}},
                {"type": "move_node", "node_id": "node-item-2", "position": {"x": 220, "y": 30}},
                {"type": "update_node_metadata", "node_id": "node-item-1", "parent_node_id": "group-1"},
                {"type": "update_node_metadata", "node_id": "node-item-2", "parent_node_id": "group-1"},
            ],
        },
    )

    assert response.status_code == 200
    nodes = response.json()["graph"]["nodes"]
    assert nodes["group-1"]["kind"] == "group"
    assert nodes["group-1"]["label"] == "Investigation thread"
    assert nodes["node-item-1"]["parent_node_id"] == "group-1"
    assert nodes["node-item-2"]["position"] == {"x": 220.0, "y": 30.0}


@pytest.mark.asyncio
async def test_group_node_label_can_be_renamed(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    case_id = await _create_case(session_maker)

    created = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={
            "base_revision": 0,
            "operations": [
                {
                    "type": "add_group",
                    "node_id": "group-1",
                    "position": {"x": 40, "y": 40},
                    "width": 520,
                    "height": 260,
                    "label": "Group",
                },
            ],
        },
    )
    response = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={
            "base_revision": created.json()["revision"],
            "operations": [
                {"type": "update_node_metadata", "node_id": "group-1", "label": "Lateral movement"},
            ],
        },
    )

    assert response.status_code == 200
    nodes = response.json()["graph"]["nodes"]
    assert nodes["group-1"]["label"] == "Lateral movement"


@pytest.mark.asyncio
async def test_auditor_cannot_patch_timeline_graph(
    client: AsyncClient,
    session_maker: Any,
    auditor_user_factory,
) -> None:
    session_cookie, _ = await _login_and_get_session_cookie(client, session_maker, auditor_user_factory)
    case_id = await _create_case(session_maker)

    response = await client.patch(
        f"/api/v1/cases/{case_id}/timeline-graph",
        cookies={"intercept_session": session_cookie},
        json={"base_revision": 0, "operations": [_node_operation("node-item-1", "item-1")]},
    )

    assert response.status_code == 403
    assert _detail_message(response) == "Auditor accounts have read-only access"