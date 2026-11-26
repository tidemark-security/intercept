import pytest
from httpx import AsyncClient

from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", ["alerts", "cases", "tasks"])
async def test_process_tree_round_trip(client: AsyncClient, session_maker, analyst_user_factory, collection):
    user = analyst_user_factory()
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    login = await client.post("/api/v1/auth/login", json={
        "username": user.username,
        "password": DEFAULT_TEST_PASSWORD,
    })
    assert login.status_code == 200
    session_cookie = login.cookies.get("intercept_session")
    assert session_cookie
    headers = {"Cookie": f"intercept_session={session_cookie}"}
    entity_data = {"title": "Process tree timeline test", "priority": "MEDIUM"}
    if collection == "alerts":
        entity_data["source"] = "Test"
    entity = await client.post(f"/api/v1/{collection}", json=entity_data, headers=headers)
    assert entity.status_code == 200, entity.text
    entity_url = f"/api/v1/{collection}/{entity.json()['id']}"
    payload = {
        "type": "process_tree",
        "timestamp": "2026-11-26T09:42:18Z",
        "hostname": "WS-014",
        "processes": [
            {"id": "services", "process_name": "services.exe", "process_id": 624},
            {
                "id": "spool",
                "parent_id": "services",
                "process_name": "spoolsv.exe",
                "process_id": 1560,
                "is_alert_source": True,
                "verdict": "suspicious",
                "verdict_reason": "Flagged by the endpoint sensor",
                "file_writes": 2,
                "network_connections": 0,
                "is_signed": False,
            },
            {"id": "desktop", "process_name": "explorer.exe", "process_id": 4120},
        ],
    }

    created = await client.post(f"{entity_url}/timeline", json=payload, headers=headers)
    assert created.status_code == 200, created.text
    (created_item,) = created.json()["timeline_items"].values()
    item_id = created_item["id"]
    assert created_item["processes"][1]["parent_id"] == "services"
    assert created_item["processes"][1]["is_alert_source"] is True
    assert created_item["processes"][1]["verdict"] == "suspicious"
    assert created_item["processes"][1]["file_writes"] == 2
    assert created_item["processes"][1]["network_connections"] == 0
    assert created_item["timestamp"] == "2026-11-26T09:42:18Z"

    rejected = await client.put(
        f"{entity_url}/timeline/{item_id}",
        json={**payload, "processes": [{**payload["processes"][1], "parent_id": "missing"}]},
        headers=headers,
    )
    assert rejected.status_code == 422
    assert "missing from the snapshot" in rejected.json()["detail"]

    unchanged = await client.get(entity_url, headers=headers)
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["timeline_items"][item_id]["processes"] == created_item["processes"]

    updated = await client.put(
        f"{entity_url}/timeline/{item_id}", json={**payload, "hostname": "WS-015"}, headers=headers,
    )
    assert updated.status_code == 200, updated.text
    reloaded = await client.get(entity_url, headers=headers)
    assert reloaded.status_code == 200, reloaded.text
    item = reloaded.json()["timeline_items"][item_id]
    assert item["hostname"] == "WS-015"
    assert item["processes"] == created_item["processes"]
