from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import UserAccount
from app.services.auth_service import auth_service
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


SAVED_FILTERS_PATH = "/api/v1/saved-filters"


async def _login(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    user: UserAccount,
) -> dict[str, str]:
    async with session_maker() as session:
        session.add(user)
        await session.commit()
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("intercept_session")
    assert token
    client.cookies.clear()
    return {"Cookie": f"intercept_session={token}"}


@pytest.mark.asyncio
async def test_personal_filters_round_trip_for_owner_only(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    auditor_user_factory,
    admin_user_factory,
) -> None:
    owner = await _login(client, session_maker, auditor_user_factory())
    other_user = await _login(client, session_maker, admin_user_factory())
    snapshot = {
        "search": "spoofed  login",
        "status": ["NEW", "IN_PROGRESS"],
        "assignee": ["__unassigned__"],
        "include_tags": ["identity"],
        "exclude_tags": ["triaged"],
        "date_range": {
            "start": "2026-11-17T08:00:00Z",
            "end": "2026-11-24T08:00:00Z",
            "preset": "-7d",
        },
        "sort_by": "priority",
        "sort_order": "asc",
    }
    payload = {"queue": "alerts", "scope": "personal", "name": "  My queue  ", "filters": snapshot}
    response = await client.post(SAVED_FILTERS_PATH, headers=owner, json=payload)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved == {
        **payload,
        "id": saved["id"],
        "name": "My queue",
        "filters": {**snapshot, "search": "spoofed login"},
    }
    item = f"{SAVED_FILTERS_PATH}/{saved['id']}"
    owner_list = await client.get(SAVED_FILTERS_PATH, headers=owner, params={"queue": "alerts"})
    assert owner_list.json() == [saved]
    other_list = await client.get(SAVED_FILTERS_PATH, headers=other_user, params={"queue": "alerts"})
    assert other_list.json() == []
    different_queue_list = await client.get(SAVED_FILTERS_PATH, headers=owner, params={"queue": "cases"})
    assert different_queue_list.json() == []

    rename = await client.patch(item, headers=other_user, json={"name": "Renamed"})
    assert rename.status_code == 404
    assert (await client.delete(item, headers=other_user)).status_code == 404
    rename = await client.patch(item, headers=owner, json={"name": "My follow-up queue"})
    assert rename.status_code == 200, rename.text
    assert rename.json() == {**saved, "name": "My follow-up queue"}
    assert (await client.delete(item, headers=owner)).status_code == 204
    owner_list = await client.get(SAVED_FILTERS_PATH, headers=owner, params={"queue": "alerts"})
    assert owner_list.json() == []


@pytest.mark.asyncio
async def test_org_filters_shared_with_members_and_managed_by_admins(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    admin_user_factory,
) -> None:
    analyst = await _login(client, session_maker, analyst_user_factory())
    author = await _login(client, session_maker, admin_user_factory())
    another_admin = await _login(client, session_maker, admin_user_factory())
    payload = {
        "queue": "tasks",
        "scope": "organization",
        "name": "Shared task queue",
        "filters": {"search": "handoff", "status": ["TODO"]},
    }
    response = await client.post(SAVED_FILTERS_PATH, headers=analyst, json=payload)
    assert response.status_code == 403
    response = await client.post(SAVED_FILTERS_PATH, headers=author, json=payload)
    assert response.status_code == 201, response.text
    saved = response.json()
    item = f"{SAVED_FILTERS_PATH}/{saved['id']}"

    member_list = await client.get(SAVED_FILTERS_PATH, headers=analyst, params={"queue": "tasks"})
    assert member_list.json() == [saved]
    anonymous_list = await client.get(SAVED_FILTERS_PATH, params={"queue": "tasks"})
    assert anonymous_list.status_code == 401
    assert (await client.patch(item, headers=analyst, json={"name": "Renamed"})).status_code == 403
    assert (await client.delete(item, headers=analyst)).status_code == 403

    rename = await client.patch(item, headers=another_admin, json={"name": "Shared handoff"})
    assert rename.status_code == 200, rename.text
    assert rename.json() == {**saved, "name": "Shared handoff"}
    assert (await client.delete(item, headers=another_admin)).status_code == 204
    member_list = await client.get(SAVED_FILTERS_PATH, headers=analyst, params={"queue": "tasks"})
    assert member_list.json() == []


@pytest.mark.asyncio
async def test_invalid_snapshots_and_names_are_rejected(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    analyst = await _login(client, session_maker, analyst_user_factory())
    payload = {"queue": "cases", "scope": "personal", "name": "Cases to review", "filters": {}}
    invalid_payloads = [
        {**payload, "queue": "other"},
        {**payload, "name": " "},
        {**payload, "name": "a" * 101},
        {**payload, "owner_id": "c727ef67-7edb-4300-8a63-f96962119503"},
        {**payload, "filters": {"status": ["TODO"]}},
        {**payload, "filters": {"search": "*"}},
        {**payload, "filters": {"search": "q" * 201}},
        {**payload, "filters": {"sort_by": "name"}},
        {**payload, "filters": {"date_range": {"start": "invalid", "end": ""}}},
        {**payload, "filters": {"date_range": {"start": "", "end": "", "preset": "latest"}}},
        {**payload, "filters": {"date_range": {"start": "", "end": "", "preset": "-999999999d"}}},
    ]
    for invalid in invalid_payloads:
        response = await client.post(SAVED_FILTERS_PATH, headers=analyst, json=invalid)
        assert response.status_code == 422, response.text
    response = await client.post(SAVED_FILTERS_PATH, headers=analyst, json=payload)
    assert response.status_code == 201, response.text
    item = f"{SAVED_FILTERS_PATH}/{response.json()['id']}"
    response = await client.patch(item, headers=analyst, json={"name": "Rename", "scope": "organization"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_saved_filter_writes_can_overlap_authenticated_queue_reads(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    analyst = await _login(client, session_maker, analyst_user_factory())
    token = analyst["Cookie"].removeprefix("intercept_session=")
    async with session_maker() as queue_read_session:
        await auth_service.validate_session(queue_read_session, session_token=token, shared_lock=True)
        created = await client.post(
            SAVED_FILTERS_PATH,
            headers=analyst,
            json={"queue": "alerts", "scope": "personal", "name": "Follow-up", "filters": {}},
        )
        assert created.status_code == 201, created.text
        item = f"{SAVED_FILTERS_PATH}/{created.json()['id']}"
        renamed = await client.patch(item, headers=analyst, json={"name": "Follow-up alerts"})
        assert renamed.status_code == 200, renamed.text
        deleted = await client.delete(item, headers=analyst)
        assert deleted.status_code == 204, deleted.text
