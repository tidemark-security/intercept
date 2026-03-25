from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from pgqueuer.errors import MaxRetriesExceeded
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import Alert, EnrichmentAlias
from app.models.enums import RealtimeEventType, SettingType
from app.models.models import AppSetting
from app.services.enrichment.base import EnrichmentResult
from app.services.enrichment.providers import register_providers
from app.services.enrichment.service import enrichment_service
from app.services.tasks import _handle_enrich_item_terminal_failure
from app.services.timeline_service import timeline_service
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD
from tests.fixtures.timeline_payloads import make_observable


def _make_retries_exhausted_error(message: str) -> MaxRetriesExceeded:
    try:
        raise RuntimeError(message)
    except RuntimeError as root_cause:
        try:
            raise MaxRetriesExceeded(4) from root_cause
        except MaxRetriesExceeded as exc:
            return exc


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
            assert task_name == "enrich_item"
            assert payload == {
                "entity_type": "alert",
                "entity_id": alert.id,
                "item_id": "item-1",
            }
            assert priority == 0

            async with session_maker() as session:
                refreshed_alert = await session.get(Alert, alert.id)
                assert refreshed_alert is not None
                stored_item = next(
                    item for item in (refreshed_alert.timeline_items or []) if item.get("id") == "item-1"
                )

            assert stored_item["enrichment_status"] == "pending"
            return "task-enrich-123"

    monkeypatch.setattr("app.services.enrichment.service.get_task_queue_service", lambda: FakeQueue())

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
            async with session_maker() as session:
                refreshed_alert = await session.get(Alert, alert.id)
                assert refreshed_alert is not None
                stored_item = next(
                    item for item in (refreshed_alert.timeline_items or []) if item.get("id") == "item-auto-1"
                )

            assert stored_item["enrichment_status"] == "pending"
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
async def test_update_observable_clears_stale_enrichment_and_reenqueues(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyst = analyst_user_factory(username="analyst.observable-update")
    original_item = make_observable("IP", "1.1.1.1", item_id="item-ip-1")
    original_item["created_by"] = analyst.username
    original_item["enrichment_status"] = "complete"
    original_item["enrichments"] = {
        "maxmind": {
            "results": {
                "1.1.1.1": {
                    "databases": {
                        "GeoLite2-ASN": {
                            "autonomous_system_organization": "Cloudflare"
                        }
                    }
                }
            }
        }
    }

    alert = Alert(
        title="Alert needing observable refresh",
        description="Test alert",
        source="unit-test",
        timeline_items=[original_item],
        created_by=analyst.username,
    )
    register_providers()

    async with session_maker() as session:
        session.add(analyst)
        session.add(alert)
        session.add(
            AppSetting(
                key="enrichment.maxmind.enabled",
                value="true",
                value_type=SettingType.BOOLEAN,
                is_secret=False,
                description="Enable MaxMind enrichment provider",
                category="enrichment",
            )
        )
        await session.commit()
        await session.refresh(alert)

    captured_payloads: list[dict[str, object]] = []

    class FakeQueue:
        async def enqueue(self, *, task_name: str, payload: dict[str, object], priority: int = 0) -> str:
            async with session_maker() as session:
                refreshed_alert = await session.get(Alert, alert.id)
                assert refreshed_alert is not None
                stored_item = next(
                    item for item in (refreshed_alert.timeline_items or []) if item.get("id") == "item-ip-1"
                )

            assert stored_item["observable_value"] == "8.8.8.8"
            assert stored_item["enrichment_status"] == "pending"
            assert stored_item.get("enrichments") == {}
            captured_payloads.append(
                {"task_name": task_name, "payload": payload, "priority": priority}
            )
            return "task-observable-refresh-123"

    monkeypatch.setattr("app.services.enrichment.service.get_task_queue_service", lambda: FakeQueue())

    session_cookie = await _login(client, analyst.username)
    updated_payload = {**original_item, "observable_value": "8.8.8.8"}
    response = await client.put(
        f"/api/v1/alerts/{alert.id}/timeline/{original_item['id']}",
        json=updated_payload,
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    assert captured_payloads == [
        {
            "task_name": "enrich_item",
            "payload": {
                "entity_type": "alert",
                "entity_id": alert.id,
                "item_id": "item-ip-1",
            },
            "priority": 0,
        }
    ]


@pytest.mark.asyncio
async def test_update_without_enrichment_identity_change_does_not_reenqueue(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyst = analyst_user_factory(username="analyst.observable-noop")
    original_item = make_observable("IP", "8.8.8.8", item_id="item-ip-stable")
    original_item["created_by"] = analyst.username
    original_item["enrichment_status"] = "complete"
    original_item["enrichments"] = {
        "maxmind": {
            "results": {
                "8.8.8.8": {
                    "databases": {
                        "GeoLite2-ASN": {
                            "autonomous_system_organization": "Google"
                        }
                    }
                }
            }
        }
    }

    alert = Alert(
        title="Alert with stable observable enrichment",
        description="Test alert",
        source="unit-test",
        timeline_items=[original_item],
        created_by=analyst.username,
    )
    register_providers()

    async with session_maker() as session:
        session.add(analyst)
        session.add(alert)
        session.add(
            AppSetting(
                key="enrichment.maxmind.enabled",
                value="true",
                value_type=SettingType.BOOLEAN,
                is_secret=False,
                description="Enable MaxMind enrichment provider",
                category="enrichment",
            )
        )
        await session.commit()
        await session.refresh(alert)

    class FakeQueue:
        async def enqueue(self, *, task_name: str, payload: dict[str, object], priority: int = 0) -> str:
            raise AssertionError("Enrichment should not be re-enqueued for unrelated timeline edits")

    monkeypatch.setattr("app.services.enrichment.service.get_task_queue_service", lambda: FakeQueue())

    session_cookie = await _login(client, analyst.username)
    updated_payload = {**original_item, "description": "Updated analyst note without changing the IP"}
    response = await client.put(
        f"/api/v1/alerts/{alert.id}/timeline/{original_item['id']}",
        json=updated_payload,
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert.id)
        assert refreshed_alert is not None
        stored_item = next(
            item for item in (refreshed_alert.timeline_items or []) if item.get("id") == "item-ip-stable"
        )

    assert stored_item["enrichment_status"] == "complete"
    assert stored_item["enrichments"]["maxmind"]["results"]["8.8.8.8"]["databases"]["GeoLite2-ASN"][
        "autonomous_system_organization"
    ] == "Google"


@pytest.mark.asyncio
async def test_run_item_enrichment_emits_timeline_updated_event(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyst = analyst_user_factory(username="analyst.worker-event")
    item = {
        "id": "item-worker-1",
        "type": "internal_actor",
        "timestamp": "2026-03-14T00:00:00Z",
        "created_at": "2026-03-14T00:00:00Z",
        "created_by": analyst.username,
        "user_id": "alice@example.com",
        "enrichment_status": "pending",
        "enrichments": {},
    }
    alert = Alert(
        title="Alert needing worker event",
        description="Test alert",
        source="unit-test",
        timeline_items=[item],
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

    async def fake_enrich(*, db: AsyncSession, settings: object, item: dict[str, object], entity_type: str, entity_id: int) -> EnrichmentResult:
        return EnrichmentResult(
            provider_id="google_workspace",
            cache_key="user:alice@example.com",
            enrichment_data={"display_name": "Alice Example"},
        )

    emitted_events: list[dict[str, object]] = []

    async def fake_emit_event(
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        event_type: RealtimeEventType,
        performed_by: str,
        item_id: str | None = None,
    ) -> None:
        emitted_events.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "event_type": event_type,
                "performed_by": performed_by,
                "item_id": item_id,
            }
        )

    monkeypatch.setattr(
        "app.services.enrichment.providers.google_workspace.google_workspace_provider.enrich",
        fake_enrich,
    )
    monkeypatch.setattr("app.services.enrichment.service.emit_event", fake_emit_event)

    async with session_maker() as session:
        await enrichment_service.run_item_enrichment(
            session,
            entity_type="alert",
            entity_id=alert.id,
            item_id="item-worker-1",
        )

    assert emitted_events == [
        {
            "entity_type": "alert",
            "entity_id": alert.id,
            "event_type": RealtimeEventType.TIMELINE_ITEM_UPDATED,
            "performed_by": "system",
            "item_id": "item-worker-1",
        }
    ]


@pytest.mark.asyncio
async def test_run_item_enrichment_keeps_pending_status_on_retryable_failure(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyst = analyst_user_factory(username="analyst.worker-retryable-failure")
    timeline_item = {
        "id": "item-retryable-1",
        "type": "internal_actor",
        "timestamp": "2026-03-14T00:00:00Z",
        "created_at": "2026-03-14T00:00:00Z",
        "created_by": analyst.username,
        "user_id": "retryable.failure@example.com",
        "enrichment_status": "pending",
    }
    alert = Alert(
        title="Alert with retryable enrichment failure",
        description="Test alert",
        source="unit-test",
        timeline_items=[timeline_item],
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

    async def fake_enrich(*, db: AsyncSession, settings: object, item: dict[str, object], entity_type: str, entity_id: int) -> EnrichmentResult:
        raise RuntimeError("provider timeout")

    monkeypatch.setattr(
        "app.services.enrichment.providers.google_workspace.google_workspace_provider.enrich",
        fake_enrich,
    )

    async with session_maker() as session:
        with pytest.raises(RuntimeError, match="provider timeout"):
            await enrichment_service.run_item_enrichment(
                session,
                entity_type="alert",
                entity_id=alert.id,
                item_id="item-retryable-1",
            )

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert.id)
        assert refreshed_alert is not None
        stored_item = next(
            item for item in (refreshed_alert.timeline_items or []) if item.get("id") == "item-retryable-1"
        )
        assert stored_item["enrichment_status"] == "pending"
        assert stored_item.get("enrichments") is None


@pytest.mark.asyncio
async def test_enrich_item_terminal_failure_clears_pending_status(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyst = analyst_user_factory(username="analyst.worker-terminal-failure")
    timeline_item = {
        "id": "item-terminal-1",
        "type": "internal_actor",
        "timestamp": "2026-03-14T00:00:00Z",
        "created_at": "2026-03-14T00:00:00Z",
        "created_by": analyst.username,
        "user_id": "alice@example.com",
        "enrichment_status": "pending",
    }
    alert = Alert(
        title="Alert with terminal enrichment failure",
        description="Test alert",
        source="unit-test",
        timeline_items=[timeline_item],
        created_by=analyst.username,
    )

    async with session_maker() as session:
        session.add(analyst)
        session.add(alert)
        await session.commit()
        await session.refresh(alert)

    emitted_events: list[dict[str, object]] = []

    async def fake_emit_event(
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        event_type: RealtimeEventType,
        performed_by: str,
        item_id: str | None = None,
    ) -> None:
        emitted_events.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "event_type": event_type,
                "performed_by": performed_by,
                "item_id": item_id,
            }
        )

    monkeypatch.setattr("app.services.tasks.async_session_factory", session_maker)
    monkeypatch.setattr("app.services.enrichment.service.emit_event", fake_emit_event)

    await _handle_enrich_item_terminal_failure(
        {"entity_type": "alert", "entity_id": alert.id, "item_id": "item-terminal-1"},
        _make_retries_exhausted_error("provider timeout"),
    )

    assert emitted_events == [
        {
            "entity_type": "alert",
            "entity_id": alert.id,
            "event_type": RealtimeEventType.TIMELINE_ITEM_UPDATED,
            "performed_by": "system",
            "item_id": "item-terminal-1",
        }
    ]

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert.id)
        assert refreshed_alert is not None
        stored_item = next(
            item for item in (refreshed_alert.timeline_items or []) if item.get("id") == "item-terminal-1"
        )
        assert "enrichment_status" not in stored_item
        assert stored_item["enrichments"]["system"]["error"] == "Retries exhausted: provider timeout"


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