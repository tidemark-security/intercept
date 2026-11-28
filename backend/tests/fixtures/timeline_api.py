"""Shared HTTP test helpers for entity timelines."""

from typing import Any

from httpx import AsyncClient

from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


def timeline_values(items: Any) -> list[dict[str, Any]]:
    if isinstance(items, dict):
        items = items.values()
    elif not isinstance(items, list):
        return []
    return [
        {**item, "replies": timeline_values(item.get("replies"))}
        for item in items
        if isinstance(item, dict)
    ]


async def login_and_get_session_cookie(
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
