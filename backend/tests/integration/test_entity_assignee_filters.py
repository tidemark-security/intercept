from datetime import datetime, timezone

import pytest

from app.models.enums import AlertStatus, CaseStatus, TaskStatus
from app.models.models import Alert, Case, Task
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("resource", "model", "new_status", "in_progress", "closed_status"),
    [
        ("alerts", Alert, AlertStatus.NEW, AlertStatus.IN_PROGRESS, AlertStatus.CLOSED_TP),
        ("cases", Case, CaseStatus.NEW, CaseStatus.IN_PROGRESS, CaseStatus.CLOSED),
        ("tasks", Task, TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE),
    ],
)
async def test_assignee_union_combines_with_entity_list_filters(
    client, session_maker, analyst_user_factory, resource, model, new_status, in_progress, closed_status,
):
    analyst = analyst_user_factory()
    other = analyst_user_factory()
    current_date = datetime(2026, 11, 18, tzinfo=timezone.utc)
    old_date = datetime(2026, 11, 14, tzinfo=timezone.utc)
    owner = {"created_by": analyst.username} if model is not Alert else {}

    def make_entity(title, assignee=None, status=new_status, created_at=current_date, tags=("incident",)):
        return model(title=title, assignee=assignee, status=status, created_at=created_at, tags=list(tags), **owner)

    async with session_maker() as session:
        session.add_all([
            analyst,
            other,
            make_entity("Unassigned"),
            make_entity("Analyst A", analyst.username, in_progress),
            make_entity("Analyst B", other.username),
        ])
        await session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login.status_code == 200
    cookie = login.cookies.get("intercept_session")
    assert cookie is not None

    async def result_titles(assignees=(), statuses=(new_status, in_progress), extra=()):
        response = await client.get(
            f"/api/v1/{resource}",
            params=[("assignee", value) for value in assignees]
            + [("status", value.value) for value in statuses]
            + list(extra),
            cookies={"intercept_session": cookie},
        )
        assert response.status_code == 200, response.text
        return {item["title"] for item in response.json()["items"]}

    mixed = ("__unassigned__", analyst.username)
    named = (analyst.username, other.username)
    assert await result_titles() == {"Unassigned", "Analyst A", "Analyst B"}
    assert await result_titles(mixed) == await result_titles(mixed[::-1]) == {"Unassigned", "Analyst A"}
    assert await result_titles(named) == await result_titles(named[::-1]) == {"Analyst A", "Analyst B"}
    assert await result_titles(("__unassigned__",)) == {"Unassigned"}
    assert await result_titles((analyst.username,)) == {"Analyst A"}
    assert await result_titles((other.username,)) == {"Analyst B"}

    async with session_maker() as session:
        session.add_all([
            make_entity("A in date range", analyst.username),
            make_entity("A with excluded status", analyst.username, closed_status),
            make_entity("A outside time range", analyst.username, created_at=old_date),
            make_entity("Unassigned without required tag", tags=("other",)),
            make_entity("Unassigned with excluded tag", tags=("incident", "internal")),
        ])
        await session.commit()

    filters = (
        ("start_date", "2026-11-17T00:00:00Z"),
        ("end_date", "2026-11-19T00:00:00Z"),
        ("include_tags", "incident"),
        ("exclude_tags", "internal"),
    )
    for selection in (mixed, mixed[::-1]):
        assert await result_titles(selection, statuses=(new_status,), extra=filters) == {"Unassigned", "A in date range"}
