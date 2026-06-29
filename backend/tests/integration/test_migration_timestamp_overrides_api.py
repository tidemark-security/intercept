from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import Alert, Case, Task, UserAccount
from app.services.api_key_service import api_key_service
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


MIGRATED_CREATED_AT = "2024-01-02T03:04:05+10:00"
MIGRATED_CLOSED_AT = "2024-01-05T16:30:00+10:00"


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _timeline_values(items: Any) -> list[dict[str, Any]]:
    if isinstance(items, dict):
        return [item for item in items.values() if isinstance(item, dict)]
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


async def _create_nhi_api_key(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    override_timestamps: bool,
    role: UserRole = UserRole.ANALYST,
) -> str:
    user = UserAccount(
        username=f"svc.migration.{uuid4().hex[:8]}",
        role=role,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
        description="Migration test service account",
        override_timestamps=override_timestamps,
    )

    async with session_maker() as session:
        session.add(user)
        await session.flush()
        _, raw_key = await api_key_service.create_api_key(
            session,
            user_id=user.id,
            name="migration-test-key",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        await session.commit()

    return raw_key


async def _login_and_get_cookie(
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
    assert response.status_code == 200
    session_cookie = response.cookies.get("intercept_session")
    assert session_cookie is not None
    return session_cookie


async def _create_timeline_targets(
    session_maker: async_sessionmaker[AsyncSession],
) -> dict[str, int]:
    async with session_maker() as session:
        alert = Alert(title="Migration timeline alert", description="seed", source="test")
        case = Case(title="Migration timeline case", description="seed", created_by="seed")
        task = Task(
            title="Migration timeline task",
            description="seed",
            created_by="seed",
            assignee="seed",
        )
        session.add_all([alert, case, task])
        await session.commit()
        assert alert.id is not None
        assert case.id is not None
        assert task.id is not None
        return {"alerts": alert.id, "cases": case.id, "tasks": task.id}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/alerts", {"title": "Migrated alert", "description": "seed", "source": "edr"}),
        ("/api/v1/cases", {"title": "Migrated case", "description": "seed"}),
        ("/api/v1/tasks", {"title": "Migrated task", "description": "seed"}),
    ],
)
async def test_authorized_nhi_can_backdate_parent_entity_creates(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    path: str,
    payload: dict[str, Any],
) -> None:
    raw_key = await _create_nhi_api_key(session_maker, override_timestamps=True)

    response = await client.post(
        f"{path}?migration=true",
        json={**payload, "created_at": MIGRATED_CREATED_AT},
        headers={"Authorization": f"Bearer {raw_key}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert _parse_datetime(body["created_at"]) == _parse_datetime(MIGRATED_CREATED_AT)
    assert _parse_datetime(body["updated_at"]) > _parse_datetime(body["created_at"])


@pytest.mark.asyncio
async def test_authorized_nhi_can_set_case_closed_at_on_create(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    raw_key = await _create_nhi_api_key(session_maker, override_timestamps=True)

    response = await client.post(
        "/api/v1/cases?migration=true",
        json={
            "title": "Migrated closed case",
            "description": "seed",
            "created_at": MIGRATED_CREATED_AT,
            "closed_at": MIGRATED_CLOSED_AT,
        },
        headers={"Authorization": f"Bearer {raw_key}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert _parse_datetime(body["created_at"]) == _parse_datetime(MIGRATED_CREATED_AT)
    assert _parse_datetime(body["closed_at"]) == _parse_datetime(MIGRATED_CLOSED_AT)


@pytest.mark.asyncio
async def test_authorized_nhi_can_set_case_closed_at_on_update(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    raw_key = await _create_nhi_api_key(session_maker, override_timestamps=True)

    async with session_maker() as session:
        case = Case(title="Migrated case update", description="seed", created_by="seed")
        session.add(case)
        await session.commit()
        assert case.id is not None
        case_id = case.id

    response = await client.put(
        f"/api/v1/cases/{case_id}?migration=true",
        json={"closed_at": MIGRATED_CLOSED_AT},
        headers={"Authorization": f"Bearer {raw_key}"},
    )

    assert response.status_code == 200, response.text
    assert _parse_datetime(response.json()["closed_at"]) == _parse_datetime(MIGRATED_CLOSED_AT)


@pytest.mark.asyncio
async def test_created_at_without_migration_flag_is_rejected(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    raw_key = await _create_nhi_api_key(session_maker, override_timestamps=True)

    response = await client.post(
        "/api/v1/alerts",
        json={
            "title": "Rejected alert",
            "description": "seed",
            "source": "edr",
            "created_at": MIGRATED_CREATED_AT,
        },
        headers={"Authorization": f"Bearer {raw_key}"},
    )

    assert response.status_code == 400
    assert "migration=true" in response.json()["detail"]


@pytest.mark.asyncio
async def test_case_closed_at_without_migration_flag_is_rejected(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    raw_key = await _create_nhi_api_key(session_maker, override_timestamps=True)

    response = await client.post(
        "/api/v1/cases",
        json={
            "title": "Rejected closed case",
            "description": "seed",
            "closed_at": MIGRATED_CLOSED_AT,
        },
        headers={"Authorization": f"Bearer {raw_key}"},
    )

    assert response.status_code == 400
    assert "migration=true" in response.json()["detail"]


@pytest.mark.asyncio
async def test_migration_flag_requires_nhi_override_permission(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    raw_key = await _create_nhi_api_key(session_maker, override_timestamps=False)

    nhi_response = await client.post(
        "/api/v1/alerts?migration=true",
        json={
            "title": "Rejected NHI alert",
            "description": "seed",
            "source": "edr",
            "created_at": MIGRATED_CREATED_AT,
        },
        headers={"Authorization": f"Bearer {raw_key}"},
    )

    assert nhi_response.status_code == 403

    session_cookie = await _login_and_get_cookie(client, session_maker, analyst_user_factory)
    human_response = await client.post(
        "/api/v1/alerts?migration=true",
        json={
            "title": "Rejected human alert",
            "description": "seed",
            "source": "edr",
            "created_at": MIGRATED_CREATED_AT,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert human_response.status_code == 403


@pytest.mark.asyncio
async def test_migration_created_at_must_be_timezone_aware(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    raw_key = await _create_nhi_api_key(session_maker, override_timestamps=True)

    response = await client.post(
        "/api/v1/alerts?migration=true",
        json={
            "title": "Naive timestamp alert",
            "description": "seed",
            "source": "edr",
            "created_at": "2024-01-02T03:04:05",
        },
        headers={"Authorization": f"Bearer {raw_key}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_migration_closed_at_must_be_timezone_aware(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    raw_key = await _create_nhi_api_key(session_maker, override_timestamps=True)

    response = await client.post(
        "/api/v1/cases?migration=true",
        json={
            "title": "Naive closed timestamp case",
            "description": "seed",
            "closed_at": "2024-01-05T16:30:00",
        },
        headers={"Authorization": f"Bearer {raw_key}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", ["alerts", "cases", "tasks"])
async def test_authorized_nhi_can_backdate_timeline_adds(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    collection: str,
) -> None:
    raw_key = await _create_nhi_api_key(session_maker, override_timestamps=True)
    targets = await _create_timeline_targets(session_maker)

    response = await client.post(
        f"/api/v1/{collection}/{targets[collection]}/timeline?migration=true",
        json={
            "id": f"migration-note-{collection}",
            "type": "note",
            "description": "Migrated note",
            "created_at": MIGRATED_CREATED_AT,
        },
        headers={"Authorization": f"Bearer {raw_key}"},
    )

    assert response.status_code == 200, response.text
    items = _timeline_values(response.json()["timeline_items"])
    note = next(item for item in items if item["description"] == "Migrated note")
    assert _parse_datetime(note["created_at"]) == _parse_datetime(MIGRATED_CREATED_AT)
    assert _parse_datetime(note["timestamp"]) > _parse_datetime(note["created_at"])


@pytest.mark.asyncio
async def test_normal_timeline_add_cannot_supply_created_at(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_cookie(client, session_maker, analyst_user_factory)
    targets = await _create_timeline_targets(session_maker)

    response = await client.post(
        f"/api/v1/alerts/{targets['alerts']}/timeline",
        json={
            "id": "normal-note-created-at",
            "type": "note",
            "description": "Rejected note",
            "created_at": MIGRATED_CREATED_AT,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 400
    assert "migration=true" in response.json()["detail"]


@pytest.mark.asyncio
async def test_timeline_update_rejects_created_at_changes(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_cookie(client, session_maker, analyst_user_factory)
    targets = await _create_timeline_targets(session_maker)

    add_response = await client.post(
        f"/api/v1/alerts/{targets['alerts']}/timeline",
        json={
            "id": "immutable-created-at-note",
            "type": "note",
            "description": "Original note",
        },
        cookies={"intercept_session": session_cookie},
    )
    assert add_response.status_code == 200, add_response.text

    response = await client.put(
        f"/api/v1/alerts/{targets['alerts']}/timeline/immutable-created-at-note",
        json={
            "id": "immutable-created-at-note",
            "type": "note",
            "description": "Edited note",
            "created_at": MIGRATED_CREATED_AT,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 400
    assert "immutable" in response.json()["detail"].lower()
