"""Shared item contracts for alert, case and task timelines."""

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient

from tests.fixtures.timeline_api import login_and_get_session_cookie, timeline_values
from tests.fixtures.timeline_payloads import (
    EXTERNAL_ACTOR_VARIANTS,
    INTERNAL_ACTOR_VARIANTS,
    OBSERVABLE_VARIANTS,
    PROTOCOL_VARIANTS,
    REGISTRY_OP_VARIANTS,
    SYSTEM_TYPE_VARIANTS,
    THREAT_ACTOR_VARIANTS,
    make_external_actor,
    make_internal_actor,
    make_network_traffic,
    make_observable,
    make_registry_change,
    make_system,
    make_threat_actor,
)

PostTimelineItem = Callable[[dict[str, Any]], Awaitable[list[dict[str, Any]]]]
pytestmark = pytest.mark.asyncio


@pytest.fixture(params=["alert", "case", "task"])
async def post_timeline_item(request, client: AsyncClient, session_maker, analyst_user_factory) -> PostTimelineItem:
    cookie = await login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    cookies = {"intercept_session": cookie}
    entity = request.param
    endpoint = f"/api/v1/{entity}s"
    create = {"title": f"Timeline variant {entity}", "description": "Timeline contract test"}
    if entity == "alert":
        create.update(source="IntegrationTest", priority="MEDIUM")
    response = await client.post(endpoint, json=create, cookies=cookies)
    assert response.status_code == 200, response.text
    entity_id = response.json()["id"]

    async def post(payload: dict[str, Any]) -> list[dict[str, Any]]:
        result = await client.post(f"{endpoint}/{entity_id}/timeline", json=payload, cookies=cookies)
        assert result.status_code == 200, result.text
        return timeline_values(result.json()["timeline_items"])

    return post


@pytest.mark.parametrize("obs_type, obs_value", OBSERVABLE_VARIANTS)
async def test_add_observable_variant(
    post_timeline_item: PostTimelineItem,
    obs_type: str,
    obs_value: str,
) -> None:
    payload = make_observable(obs_type, obs_value, item_id=f"obs-{obs_type.lower()}")

    items = await post_timeline_item(payload)
    match = [i for i in items if i["type"] == "observable" and i["observable_type"] == obs_type]
    assert len(match) == 1
    assert match[0]["observable_value"] == obs_value


@pytest.mark.parametrize("system_type", SYSTEM_TYPE_VARIANTS)
async def test_add_system_variant(
    post_timeline_item: PostTimelineItem,
    system_type: str,
) -> None:
    payload = make_system(system_type, item_id=f"sys-{system_type.lower()}")

    items = await post_timeline_item(payload)
    match = [i for i in items if i["type"] == "system" and i["system_type"] == system_type]
    assert len(match) == 1


@pytest.mark.parametrize("kwargs", INTERNAL_ACTOR_VARIANTS)
async def test_add_internal_actor_variant(
    post_timeline_item: PostTimelineItem,
    kwargs: dict[str, Any],
) -> None:
    payload = make_internal_actor(**kwargs, item_id=f"iactor-{list(kwargs.values())[0]}")

    items = await post_timeline_item(payload)
    assert any(i["type"] == "internal_actor" for i in items)


@pytest.mark.parametrize("kwargs", EXTERNAL_ACTOR_VARIANTS)
async def test_add_external_actor_variant(
    post_timeline_item: PostTimelineItem,
    kwargs: dict[str, Any],
) -> None:
    payload = make_external_actor(**kwargs, item_id=f"eactor-{list(kwargs.values())[0]}")

    items = await post_timeline_item(payload)
    assert any(i["type"] == "external_actor" for i in items)


@pytest.mark.parametrize("kwargs", THREAT_ACTOR_VARIANTS)
async def test_add_threat_actor_variant(
    post_timeline_item: PostTimelineItem,
    kwargs: dict[str, Any],
) -> None:
    payload = make_threat_actor(**kwargs, item_id=f"tactor-{list(kwargs.values())[0]}")

    items = await post_timeline_item(payload)
    assert any(i["type"] == "threat_actor" for i in items)


@pytest.mark.parametrize("protocol", PROTOCOL_VARIANTS)
async def test_add_network_traffic_variant(
    post_timeline_item: PostTimelineItem,
    protocol: str,
) -> None:
    payload = make_network_traffic(protocol, item_id=f"net-{protocol.lower()}")

    items = await post_timeline_item(payload)
    match = [i for i in items if i["type"] == "network_traffic" and i["protocol"] == protocol]
    assert len(match) == 1


@pytest.mark.parametrize("operation", REGISTRY_OP_VARIANTS)
async def test_add_registry_change_variant(
    post_timeline_item: PostTimelineItem,
    operation: str,
) -> None:
    payload = make_registry_change(operation, item_id=f"reg-{operation.lower()}")

    items = await post_timeline_item(payload)
    match = [i for i in items if i["type"] == "registry_change" and i["operation"] == operation]
    assert len(match) == 1
