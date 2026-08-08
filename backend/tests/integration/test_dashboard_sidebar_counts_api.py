from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.models.enums import AlertStatus, CaseStatus, TaskStatus
from app.models.models import Alert, Case, Task
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


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
async def test_sidebar_badge_counts_returns_open_and_unassigned_counts(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(
        client,
        session_maker,
        analyst_user_factory,
    )

    async with session_maker() as session:
        session.add_all(
            [
                Alert(title="New unassigned alert", status=AlertStatus.NEW),
                Alert(
                    title="In-progress assigned alert",
                    status=AlertStatus.IN_PROGRESS,
                    assignee="analyst-a",
                ),
                Alert(title="Escalated unassigned alert", status=AlertStatus.ESCALATED),
                Alert(title="Closed unassigned alert", status=AlertStatus.CLOSED_FP),
                Case(
                    title="New unassigned case",
                    status=CaseStatus.NEW,
                    created_by="seed-user",
                ),
                Case(
                    title="In-progress assigned case",
                    status=CaseStatus.IN_PROGRESS,
                    assignee="analyst-a",
                    created_by="seed-user",
                ),
                Case(
                    title="Closed unassigned case",
                    status=CaseStatus.CLOSED,
                    created_by="seed-user",
                ),
                Task(
                    title="Todo unassigned task",
                    status=TaskStatus.TODO,
                    created_by="seed-user",
                ),
                Task(
                    title="In-progress assigned task",
                    status=TaskStatus.IN_PROGRESS,
                    assignee="analyst-a",
                    created_by="seed-user",
                ),
                Task(
                    title="Done unassigned task",
                    status=TaskStatus.DONE,
                    created_by="seed-user",
                ),
            ]
        )
        await session.commit()

    response = await client.get(
        "/api/v1/dashboard/sidebar-badge-counts",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "alerts": {"open": 2, "unassigned": 1},
        "cases": {"open": 2, "unassigned": 1},
        "tasks": {"open": 2, "unassigned": 1},
    }
