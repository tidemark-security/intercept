from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.enums import AlertStatus
from app.models.models import Alert, UserAccount
from app.services.audit_service import AuditService
from app.services.auth_service import auth_service
from app.services.realtime_service import CHANNEL
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


async def _saved_filter_audit(client: AsyncClient, admin: dict[str, str]) -> list[dict]:
    response = await client.get(
        "/api/v1/admin/audit",
        headers=admin,
        params={"entity_type": "saved_filter"},
    )
    assert response.status_code == 200, response.text
    return sorted(response.json()["items"], key=lambda event: event["id"])


@pytest.mark.asyncio
async def test_personal_filters_round_trip_for_owner_only(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    auditor_user_factory,
    admin_user_factory,
) -> None:
    owner_account = auditor_user_factory()
    owner = await _login(client, session_maker, owner_account)
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
    response = await client.post(
        SAVED_FILTERS_PATH,
        headers={**owner, "X-Request-ID": "filter-create", "User-Agent": "saved-filter-audit-test"},
        json=payload,
    )
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved == {
        **payload,
        "id": saved["id"],
        "navigation_icon": None,
        "navigation_position": None,
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
    no_op = await client.patch(item, headers=owner, json={"name": " My queue "})
    assert no_op.json() == saved
    rename = await client.patch(item, headers=owner, json={"name": "My follow-up queue"})
    assert rename.status_code == 200, rename.text
    assert rename.json() == {**saved, "name": "My follow-up queue"}
    assert (await client.delete(item, headers=owner)).status_code == 204
    owner_list = await client.get(SAVED_FILTERS_PATH, headers=owner, params={"queue": "alerts"})
    assert owner_list.json() == []

    created, renamed, deleted = await _saved_filter_audit(client, other_user)
    assert [event["event_type"] for event in (created, renamed, deleted)] == [
        "saved_filter.created",
        "saved_filter.renamed",
        "saved_filter.deleted",
    ]
    assert all(event["entity_id"] == saved["id"] for event in (created, renamed, deleted))
    assert all(event["performed_by"] == owner_account.username for event in (created, renamed, deleted))
    assert created["correlation_id"] == "filter-create"
    assert created["user_agent"] == "saved-filter-audit-test"
    before = {"name": "My queue", "queue": "alerts", "scope": "personal"}
    after = {**before, "name": "My follow-up queue"}
    assert created["old_value"] is None
    assert json.loads(created["new_value"]) == before
    assert json.loads(renamed["old_value"]) == before
    assert json.loads(renamed["new_value"]) == after
    assert json.loads(deleted["old_value"]) == after
    assert deleted["new_value"] is None


@pytest.mark.asyncio
async def test_org_filters_shared_with_members_and_managed_by_admins(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    admin_user_factory,
) -> None:
    analyst = await _login(client, session_maker, analyst_user_factory())
    author_account = admin_user_factory()
    manager_account = admin_user_factory()
    author = await _login(client, session_maker, author_account)
    another_admin = await _login(client, session_maker, manager_account)
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

    created, renamed, deleted = await _saved_filter_audit(client, another_admin)
    assert [event["event_type"] for event in (created, renamed, deleted)] == [
        "saved_filter.created",
        "saved_filter.renamed",
        "saved_filter.deleted",
    ]
    assert all(event["entity_id"] == saved["id"] for event in (created, renamed, deleted))
    assert created["performed_by"] == author_account.username
    assert renamed["performed_by"] == deleted["performed_by"] == manager_account.username
    assert json.loads(created["new_value"]) == {
        "name": "Shared task queue",
        "queue": "tasks",
        "scope": "organization",
    }
    assert json.loads(deleted["old_value"]) == {
        "name": "Shared handoff",
        "queue": "tasks",
        "scope": "organization",
    }
    event_types = await client.get("/api/v1/admin/audit/event-types", headers=another_admin)
    assert event_types.status_code == 200, event_types.text
    assert {event["event_type"] for event in (created, renamed, deleted)} <= set(event_types.json())


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_saved_filter_change(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = await _login(client, session_maker, admin_user_factory())
    payload = {"queue": "cases", "scope": "organization", "name": "Original name", "filters": {}}
    created = await client.post(SAVED_FILTERS_PATH, headers=admin, json=payload)
    assert created.status_code == 201, created.text
    original_log_event = AuditService.log_event

    async def fail_after_audit_flush(self, **kwargs):
        await original_log_event(self, **kwargs)
        raise RuntimeError("audit write failed")

    with monkeypatch.context() as patch:
        patch.setattr(AuditService, "log_event", fail_after_audit_flush)
        with pytest.raises(RuntimeError, match="audit write failed"):
            await client.patch(
                f"{SAVED_FILTERS_PATH}/{created.json()['id']}",
                headers=admin,
                json={"name": "Uncommitted name"},
            )

    response = await client.get(SAVED_FILTERS_PATH, headers=admin, params={"queue": "cases"})
    assert response.json() == [created.json()]
    assert [event["event_type"] for event in await _saved_filter_audit(client, admin)] == ["saved_filter.created"]


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


@pytest.mark.asyncio
async def test_pinned_alert_filter_counts_for_members_and_admin_only_management(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    admin_user_factory,
) -> None:
    owner = await _login(client, session_maker, admin_user_factory())
    member = await _login(client, session_maker, analyst_user_factory())

    async def save_filter(**overrides):
        payload = {"queue": "alerts", "scope": "organization", "name": "Identity", "filters": {}}
        response = await client.post(SAVED_FILTERS_PATH, headers=owner, json={**payload, **overrides})
        assert response.status_code == 201, response.text
        return response.json()

    now = datetime.now(timezone.utc)
    recent = now - timedelta(minutes=10)
    async with session_maker() as session:
        # The test database uses ORM metadata and skips migration-owned search columns.
        await session.execute(text("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS search_vector tsvector"))
        session.add_all([
            Alert(title="Identity review A", status=AlertStatus.NEW, tags=["identity"], created_at=recent),
            Alert(title="Identity review B", status=AlertStatus.IN_PROGRESS, tags=["identity"], created_at=recent),
            Alert(title="Identity review assigned", status=AlertStatus.NEW, tags=["identity"], assignee="analyst", created_at=recent),
            Alert(title="Identity review closed", status=AlertStatus.CLOSED_FP, tags=["identity"], created_at=recent),
            Alert(title="Identity review ignored", status=AlertStatus.NEW, tags=["identity", "ignored"], created_at=recent),
            Alert(title="Identity review old", status=AlertStatus.NEW, tags=["identity"], created_at=now - timedelta(days=2)),
            Alert(title="Endpoint review", status=AlertStatus.NEW, tags=["endpoint"], created_at=recent),
        ])
        await session.flush()
        await session.execute(text("UPDATE alerts SET search_vector = to_tsvector('english', title)"))
        await session.commit()

    saved = await save_filter(filters={
        "search": "identity review",
        "status": ["NEW", "IN_PROGRESS", "CLOSED_FP"],
        "assignee": ["__unassigned__", "analyst"],
        "include_tags": ["identity"],
        "exclude_tags": ["ignored"],
        "date_range": {"start": "2020-01-01", "end": "2020-01-02", "preset": "-1h"},
    })
    personal = await save_filter(scope="personal")
    cases = await save_filter(queue="cases")
    path = f"{SAVED_FILTERS_PATH}/{saved['id']}/navigation"
    icon = {"icon_name": "MSTeamsIcon"}
    assert (await client.put(path, json=icon)).status_code == 401
    assert (await client.put(path, headers=member, json=icon)).status_code == 403
    for invalid_target in (personal, cases):
        assert (await client.put(
            f"{SAVED_FILTERS_PATH}/{invalid_target['id']}/navigation", headers=owner, json=icon,
        )).status_code == 404
    assert (await client.put(path, headers=owner, json={"icon_name": "<svg>"})).status_code == 422

    response = await client.put(path, headers=owner, json=icon)
    assert response.status_code == 200, response.text
    pinned = {**saved, "navigation_icon": "MSTeamsIcon", "navigation_position": 0}
    assert response.json() == pinned
    assert (await client.put(path, headers=owner, json=icon)).json() == pinned

    dashboard = "/api/v1/dashboard/sidebar-badge-counts"
    counts = await client.get(dashboard, headers=member)
    assert counts.status_code == 200, counts.text
    assert counts.json()["alerts"] == {"open": 6, "unassigned": 5}
    assert counts.json()["pinned_alert_filters"] == [
        {"filter": pinned, "counts": {"open": 3, "unassigned": 2}},
    ]

    renamed = await client.patch(f"{SAVED_FILTERS_PATH}/{saved['id']}", headers=owner, json={"name": "Identity queue"})
    assert renamed.json()["navigation_icon"] == "MSTeamsIcon"
    assert (await client.put(path, headers=owner, json={"icon_name": "Shield"})).json()["navigation_icon"] == "Shield"
    assert (await client.put(path, headers=owner, json={"icon_name": None})).json()["navigation_icon"] is None
    assert (await client.get(dashboard, headers=member)).json()["pinned_alert_filters"] == []
    assert (await client.get(SAVED_FILTERS_PATH, headers=member, params={"queue": "alerts"})).json()[0]["name"] == "Identity queue"

    await client.put(path, headers=owner, json=icon)
    assert (await client.delete(f"{SAVED_FILTERS_PATH}/{saved['id']}", headers=owner)).status_code == 204
    assert (await client.get(dashboard, headers=member)).json()["pinned_alert_filters"] == []
    events = await _saved_filter_audit(client, owner)
    navigation_events = [event for event in events if event["event_type"] == "saved_filter.navigation_updated"]
    assert len(navigation_events) == 4
    assert json.loads(navigation_events[0]["new_value"])["navigation_icon"] == "MSTeamsIcon"
    assert all("identity review" not in (event["new_value"] or "") for event in navigation_events)


@pytest.mark.asyncio
async def test_pinned_alert_order_is_shared_and_notified_on_commit(
    client: AsyncClient,
    async_engine: AsyncEngine,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin_account = admin_user_factory()
    admin = await _login(client, session_maker, admin_account)
    member = await _login(client, session_maker, analyst_user_factory())
    order_path = f"{SAVED_FILTERS_PATH}/navigation/order"
    dashboard = "/api/v1/dashboard/sidebar-badge-counts"

    async def create_filter(name: str) -> str:
        response = await client.post(SAVED_FILTERS_PATH, headers=admin, json={
            "queue": "alerts", "scope": "organization", "name": name, "filters": {},
        })
        assert response.status_code == 201, response.text
        return response.json()["id"]

    async def set_icon(filter_id: str, icon: str | None) -> dict:
        response = await client.put(
            f"{SAVED_FILTERS_PATH}/{filter_id}/navigation", headers=admin, json={"icon_name": icon},
        )
        assert response.status_code == 200, response.text
        return response.json()

    async def sidebar_order() -> list[str]:
        response = await client.get(dashboard, headers=member)
        assert response.status_code == 200, response.text
        return [entry["filter"]["id"] for entry in response.json()["pinned_alert_filters"]]

    dsn = async_engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    connection = await asyncpg.connect(dsn)
    events: asyncio.Queue[dict] = asyncio.Queue()

    def capture_event(_connection, _pid, _channel, payload):
        events.put_nowait(json.loads(payload))

    async def expect_update() -> None:
        assert await asyncio.wait_for(events.get(), 5) == {
            "entity_type": "saved_filter_navigation",
            "entity_id": 0,
            "event_type": "saved_filter_navigation_updated",
            "performed_by": admin_account.username,
        }

    try:
        await connection.add_listener(CHANNEL, capture_event)
        first = await create_filter("Zulu")
        second = await create_filter("Alpha")
        assert (await set_icon(first, "Bell"))["navigation_position"] == 0
        await expect_update()
        assert (await set_icon(second, "Shield"))["navigation_position"] == 1
        await expect_update()
        assert await sidebar_order() == [first, second]

        order = {"filter_ids": [second, first]}
        assert (await client.put(order_path, json=order)).status_code == 401
        assert (await client.put(order_path, headers=member, json=order)).status_code == 403
        for stale_ids in ([first], [first, first]):
            assert (await client.put(order_path, headers=admin, json={"filter_ids": stale_ids})).status_code == 409

        response = await client.put(order_path, headers=admin, json=order)
        assert response.status_code == 204, response.text
        await expect_update()
        assert await sidebar_order() == [second, first]
        filters = await client.get(SAVED_FILTERS_PATH, headers=member, params={"queue": "alerts"})
        assert {entry["id"]: entry["navigation_position"] for entry in filters.json()} == {first: 1, second: 0}

        assert (await client.put(order_path, headers=admin, json=order)).status_code == 204
        assert (await set_icon(second, "Briefcase"))["navigation_position"] == 0
        await expect_update()
        assert (await set_icon(second, None))["navigation_position"] is None
        await expect_update()
        assert await sidebar_order() == [first]

        response = await client.delete(f"{SAVED_FILTERS_PATH}/{first}", headers=admin)
        assert response.status_code == 204, response.text
        await expect_update()
        assert await sidebar_order() == []
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(events.get(), 0.1)
    finally:
        await connection.close()
