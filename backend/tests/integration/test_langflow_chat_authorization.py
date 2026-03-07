from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient

from app.models.enums import MessageRole
from app.models.models import LangFlowMessage, LangFlowSession
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _login_and_get_session_cookie(
    client: AsyncClient,
    session_maker: Any,
    user_factory,
) -> tuple[str, str, UUID]:
    user = user_factory()

    async with session_maker() as session:
        session.add(user)
        await session.commit()
        user_id = user.id

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200

    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    return session_cookie, user.username, user_id


@pytest.mark.asyncio
async def test_non_admin_list_sessions_only_returns_own(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, _analyst_username, analyst_user_id = await _login_and_get_session_cookie(
        client, session_maker, analyst_user_factory
    )

    other_user = analyst_user_factory()

    async with session_maker() as session:
        session.add(other_user)
        await session.flush()

        analyst_session = LangFlowSession(flow_id="general_flow", user_id=analyst_user_id)
        other_session_a = LangFlowSession(flow_id="general_flow", user_id=other_user.id)
        other_session_b = LangFlowSession(flow_id="general_flow", user_id=other_user.id)

        session.add_all([analyst_session, other_session_a, other_session_b])
        await session.commit()

    response = await client.get(
        "/api/v1/langflow/sessions",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["user_id"] == str(analyst_user_id)


@pytest.mark.asyncio
async def test_non_admin_username_query_returns_403(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, _, _ = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    response = await client.get(
        "/api/v1/langflow/sessions",
        params={"username": "someoneelse"},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cross_user_get_session_returns_403(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, _, _ = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    other_user = analyst_user_factory()

    async with session_maker() as session:
        session.add(other_user)
        await session.flush()
        other_session = LangFlowSession(flow_id="general_flow", user_id=other_user.id)
        session.add(other_session)
        await session.commit()
        other_session_id = str(other_session.id)

    response = await client.get(
        f"/api/v1/langflow/sessions/{other_session_id}",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_list_get_and_read_messages_for_target_username(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin_cookie, _, _ = await _login_and_get_session_cookie(client, session_maker, admin_user_factory)
    target_user = analyst_user_factory(username="target_analyst")

    async with session_maker() as session:
        session.add(target_user)
        await session.flush()

        target_session = LangFlowSession(flow_id="general_flow", user_id=target_user.id, title="Target Chat")
        session.add(target_session)
        await session.flush()

        target_message = LangFlowMessage(
            session_id=target_session.id,
            role=MessageRole.ASSISTANT,
            content="Hello from target session",
        )
        session.add(target_message)
        await session.commit()

        target_session_id = str(target_session.id)

    list_response = await client.get(
        "/api/v1/langflow/sessions",
        params={"username": "target_analyst"},
        cookies={"intercept_session": admin_cookie},
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert len(list_payload) == 1
    assert list_payload[0]["id"] == target_session_id

    get_response = await client.get(
        f"/api/v1/langflow/sessions/{target_session_id}",
        params={"username": "target_analyst"},
        cookies={"intercept_session": admin_cookie},
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == target_session_id

    messages_response = await client.get(
        f"/api/v1/langflow/sessions/{target_session_id}/messages",
        params={"username": "target_analyst"},
        cookies={"intercept_session": admin_cookie},
    )
    assert messages_response.status_code == 200
    messages_payload = messages_response.json()
    assert len(messages_payload) == 1
    assert messages_payload[0]["content"] == "Hello from target session"


@pytest.mark.asyncio
async def test_admin_unknown_username_returns_404(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
) -> None:
    admin_cookie, _, _ = await _login_and_get_session_cookie(client, session_maker, admin_user_factory)

    response = await client.get(
        "/api/v1/langflow/sessions",
        params={"username": "missing_user"},
        cookies={"intercept_session": admin_cookie},
    )

    assert response.status_code == 404
