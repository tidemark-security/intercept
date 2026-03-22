from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import Alert, EnrichmentAlias
from app.models.enums import SettingType
from app.models.models import AppSetting
from app.services.enrichment.providers import register_providers
from app.services.enrichment.service import enrichment_service
from app.services.timeline_service import timeline_service
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _login(client: AsyncClient, username: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200
    session_cookie = response.cookies.get("intercept_session")
    assert session_cookie is not None
    return session_cookie


@pytest.mark.asyncio
async def test_search_aliases_returns_matches_for_authenticated_users(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    analyst = analyst_user_factory(username="analyst.aliases")

    async with session_maker() as session:
        session.add(analyst)
        session.add(
            EnrichmentAlias(
                provider_id="entra_id",
                entity_type="user",
                canonical_value="alice@example.com",
                canonical_display="Alice Analyst",
                alias_type="email",
                alias_value="alice@example.com",
                attributes={"department": "SOC"},
            )
        )
        await session.commit()

    session_cookie = await _login(client, analyst.username)

    response = await client.get(
        "/api/v1/enrichments/aliases/search",
        params={"q": "alice", "entity_type": "user", "limit": 5},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["canonical_value"] == "alice@example.com"
    assert payload[0]["canonical_display"] == "Alice Analyst"


@pytest.mark.asyncio
async def test_enqueue_item_enrichment_returns_task_id(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyst = analyst_user_factory(username="analyst.enqueue")
    alert = Alert(
        title="Alert needing enrichment",
        description="Test alert",
        source="unit-test",
        timeline_items=[
            {
                "id": "item-1",
                "type": "internal_actor",
                "timestamp": "2026-03-14T00:00:00Z",
                "created_at": "2026-03-14T00:00:00Z",
                "created_by": analyst.username,
                "user_id": "alice@example.com",
            }
        ],
        created_by=analyst.username,
    )

    async with session_maker() as session:
        session.add(analyst)
        session.add(alert)
        await session.commit()
        await session.refresh(alert)

    async def fake_enqueue_item_enrichment(db: AsyncSession, *, entity_type: str, entity_id: int, item_id: str) -> str:
        assert entity_type == "alert"
        assert entity_id == alert.id
        assert item_id == "item-1"
        return "task-enrich-123"

    monkeypatch.setattr(enrichment_service, "enqueue_item_enrichment", fake_enqueue_item_enrichment)

    session_cookie = await _login(client, analyst.username)
    response = await client.post(
        f"/api/v1/enrichments/alert/{alert.id}/items/item-1/enqueue",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    assert response.json() == {"enqueued": True, "task_id": "task-enrich-123"}


@pytest.mark.asyncio
async def test_add_internal_actor_auto_enqueues_matching_enrichment(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyst = analyst_user_factory(username="analyst.auto-enqueue")
    alert = Alert(
        title="Alert needing auto enrichment",
        description="Test alert",
        source="unit-test",
        timeline_items=[],
        created_by=analyst.username,
    )
    register_providers()

    async with session_maker() as session:
        session.add(analyst)
        session.add(alert)
        session.add(
            AppSetting(
                key="enrichment.google_workspace.enabled",
                value="true",
                value_type=SettingType.BOOLEAN,
                is_secret=False,
                description="Enable Google Workspace user enrichment provider",
                category="enrichment",
            )
        )
        await session.commit()
        await session.refresh(alert)

    captured_payloads: list[dict[str, object]] = []

    class FakeQueue:
        async def enqueue(self, *, task_name: str, payload: dict[str, object], priority: int = 0) -> str:
            captured_payloads.append(
                {"task_name": task_name, "payload": payload, "priority": priority}
            )
            return "task-auto-123"

    monkeypatch.setattr("app.services.enrichment.service.get_task_queue_service", lambda: FakeQueue())

    session_cookie = await _login(client, analyst.username)
    response = await client.post(
        f"/api/v1/alerts/{alert.id}/timeline",
        json={
            "id": "item-auto-1",
            "type": "internal_actor",
            "user_id": "alice@example.com",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    assert captured_payloads == [
        {
            "task_name": "enrich_item",
            "payload": {
                "entity_type": "alert",
                "entity_id": alert.id,
                "item_id": "item-auto-1",
            },
            "priority": 0,
        }
    ]

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert.id)
        assert refreshed_alert is not None
        stored_item = next(
            item for item in (refreshed_alert.timeline_items or []) if item.get("id") == "item-auto-1"
        )

    assert stored_item["enrichment_status"] == "pending"


@pytest.mark.asyncio
async def test_denormalize_timeline_does_not_overwrite_newer_enrichment_state(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyst = analyst_user_factory(username="analyst.timeline-race")
    alert = Alert(
        title="Alert with timeline race",
        description="Test alert",
        source="unit-test",
        timeline_items=[],
        created_by=analyst.username,
    )
    register_providers()

    async with session_maker() as session:
        session.add(analyst)
        session.add(alert)
        session.add(
            AppSetting(
                key="enrichment.google_workspace.enabled",
                value="true",
                value_type=SettingType.BOOLEAN,
                is_secret=False,
                description="Enable Google Workspace user enrichment provider",
                category="enrichment",
            )
        )
        await session.commit()
        await session.refresh(alert)

    class FakeQueue:
        async def enqueue(self, *, task_name: str, payload: dict[str, object], priority: int = 0) -> str:
            return "task-race-123"

    monkeypatch.setattr("app.services.enrichment.service.get_task_queue_service", lambda: FakeQueue())

    session_cookie = await _login(client, analyst.username)
    response = await client.post(
        f"/api/v1/alerts/{alert.id}/timeline",
        json={
            "id": "item-race-1",
            "type": "internal_actor",
            "user_id": "alice@example.com",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200

    async with session_maker() as stale_session:
        stale_alert = await stale_session.get(Alert, alert.id)
        assert stale_alert is not None

        async with session_maker() as fresh_session:
            fresh_alert = await fresh_session.get(Alert, alert.id)
            assert fresh_alert is not None

            updated_items = []
            for item in fresh_alert.timeline_items or []:
                if item.get("id") == "item-race-1":
                    updated_items.append(
                        {
                            **item,
                            "enrichment_status": "complete",
                            "enrichments": {
                                "google_workspace": {"display_name": "Alice Example"}
                            },
                        }
                    )
                else:
                    updated_items.append(item)

            fresh_alert.timeline_items = updated_items
            await fresh_session.commit()

        denormalized_alert = await timeline_service.denormalize_entity_timeline(
            stale_session,
            stale_alert,
            human_prefix="ALT",
        )
        response_item = next(
            item for item in (denormalized_alert.timeline_items or []) if item.get("id") == "item-race-1"
        )

        assert response_item["enrichment_status"] == "pending"
        await stale_session.commit()

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert.id)
        assert refreshed_alert is not None
        stored_item = next(
            item for item in (refreshed_alert.timeline_items or []) if item.get("id") == "item-race-1"
        )

    assert stored_item["enrichment_status"] == "complete"


@pytest.mark.asyncio
async def test_admin_directory_sync_enqueues_task(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = admin_user_factory(username="admin.enrichment")
    register_providers()

    async with session_maker() as session:
        session.add(admin)
        await session.commit()

    class FakeQueue:
        async def enqueue(self, *, task_name: str, payload: dict[str, Any]) -> str:
            assert task_name == "directory_sync"
            assert payload == {"provider_id": "ldap"}
            return "task-sync-123"

    monkeypatch.setattr(
        "app.services.task_queue_service.get_task_queue_service",
        lambda: FakeQueue(),
    )

    session_cookie = await _login(client, admin.username)
    response = await client.post(
        "/api/v1/admin/enrichments/providers/ldap/directory-sync",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    assert response.json() == {"enqueued": True, "task_id": "task-sync-123"}


@pytest.mark.asyncio
async def test_admin_directory_sync_returns_404_for_unknown_provider(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    admin = admin_user_factory(username="admin.unknown-provider")

    async with session_maker() as session:
        session.add(admin)
        await session.commit()

    session_cookie = await _login(client, admin.username)
    response = await client.post(
        "/api/v1/admin/enrichments/providers/not-a-provider/directory-sync",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Provider not found"