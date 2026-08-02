from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import Alert, Case, Task
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


DUMMY_DATA_TAG = "tmi_dummy_data"


async def _login_analyst(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> str:
    user = analyst_user_factory()
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    session_cookie = response.cookies.get("intercept_session")
    assert session_cookie is not None
    return session_cookie


async def _create_entity(
    session_maker: async_sessionmaker[AsyncSession],
    collection: str,
    tags: list[str],
) -> int:
    if collection == "alerts":
        entity: Any = Alert(title="Protected-tag alert", source="test", tags=tags)
    elif collection == "cases":
        entity = Case(title="Protected-tag case", created_by="seed", tags=tags)
    else:
        entity = Task(
            title="Protected-tag task",
            created_by="seed",
            assignee="seed",
            tags=tags,
        )

    async with session_maker() as session:
        session.add(entity)
        await session.commit()
        assert entity.id is not None
        return entity.id


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", ["alerts", "cases", "tasks"])
@pytest.mark.parametrize(
    ("existing_tags", "submitted_tags"),
    [
        (["keep"], ["keep", DUMMY_DATA_TAG]),
        ([DUMMY_DATA_TAG, "keep"], ["keep"]),
    ],
)
async def test_ordinary_entity_updates_cannot_mutate_protected_dummy_tag(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    collection: str,
    existing_tags: list[str],
    submitted_tags: list[str],
) -> None:
    session_cookie = await _login_analyst(client, session_maker, analyst_user_factory)
    entity_id = await _create_entity(session_maker, collection, existing_tags)

    response = await client.put(
        f"/api/v1/{collection}/{entity_id}",
        json={"tags": submitted_tags},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 400
    assert "protected" in str(response.json()).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", ["cases", "tasks"])
async def test_ordinary_entity_creates_cannot_add_protected_dummy_tag(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    collection: str,
) -> None:
    session_cookie = await _login_analyst(client, session_maker, analyst_user_factory)

    response = await client.post(
        f"/api/v1/{collection}",
        json={
            "title": f"Untrusted protected-tag {collection}",
            "description": "Must not become cleanup-eligible",
            "tags": [DUMMY_DATA_TAG],
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 400
    assert "protected" in str(response.json()).lower()


@pytest.mark.asyncio
async def test_bulk_alert_action_cannot_add_protected_dummy_tag(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    session_cookie = await _login_analyst(client, session_maker, analyst_user_factory)
    alert_id = await _create_entity(session_maker, "alerts", ["keep"])

    response = await client.post(
        "/api/v1/alerts/bulk-actions",
        json={
            "alert_ids": [alert_id],
            "action": "add_tags",
            "tags": [DUMMY_DATA_TAG],
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 400
    assert "protected" in str(response.json()).lower()
