"""Verify agent activity persists through the entity timeline APIs."""

import pytest

from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entity_type", "extra_fields"),
    [("alerts", {"source": "test"}), ("cases", {}), ("tasks", {})],
)
async def test_ai_agent_timeline_round_trip(
    client, session_maker, analyst_user_factory, entity_type, extra_fields
):
    user = analyst_user_factory()
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200
    session_cookie = response.cookies.get("intercept_session")
    assert session_cookie
    client.headers["Cookie"] = f"intercept_session={session_cookie}"

    response = await client.post(
        f"/api/v1/{entity_type}",
        json={"title": "Agent activity review", **extra_fields},
    )
    assert response.status_code == 200, response.text
    entity_path = f"/api/v1/{entity_type}/{response.json()['id']}"
    event = {
        "type": "ai_agent",
        "activity": "shell_command",
        "harness": "codex_cli",
        "agent_name": "Workspace assistant",
        "tool_name": "exec_command",
        "command_line": "git status --short",
        "endpoint": "fixture-workstation",
        "source_event_id": "fixture-event-1",
        "outcome": "succeeded",
        "exit_code": 0,
    }
    response = await client.post(f"{entity_path}/timeline", json=event)
    assert response.status_code == 200, response.text
    item_id, item = next(
        (item_id, item)
        for item_id, item in response.json()["timeline_items"].items()
        if item["type"] == "ai_agent"
    )
    assert {key: item[key] for key in event} == event
    assert item["created_by"] == user.username

    response = await client.get(entity_path)
    assert response.status_code == 200, response.text
    saved_item = response.json()["timeline_items"][item_id]
    assert {key: saved_item[key] for key in event} == event

    response = await client.post(
        f"{entity_path}/timeline",
        json={"type": "ai_agent", "activity": "file_read", "file_path": "src/main.py"},
    )
    assert response.status_code == 200, response.text
    assert any(
        item["activity"] == "file_read" and item["file_path"] == "src/main.py" and item["harness"] is None
        for item in response.json()["timeline_items"].values()
        if item["type"] == "ai_agent"
    )

    response = await client.post(f"{entity_path}/timeline", json={**event, "activity": "invalid"})
    assert response.status_code == 400
