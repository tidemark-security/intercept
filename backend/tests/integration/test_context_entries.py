from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select

from app.mcp import tools as mcp_tools
from app.models.enums import ContextCriterionType, Priority, RealtimeEventType, RecommendationStatus, SettingType
from app.models.models import Alert, AlertTriageRun, AppSetting, AuditLog, ContextEntry
from app.services.context_service import ContextService
from app.services.realtime_service import emit_event
from app.services.tasks import _mark_triage_failed, handle_triage_alert
from app.services.triage_recommendation_service import TRIAGE_RUN_HEADER
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _login_and_get_session_cookie(
    client: AsyncClient,
    session_maker: Any,
    user_factory: Callable[..., Any],
) -> tuple[str, str]:
    user = user_factory()
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
    return session_cookie, user.username


def _criterion(criterion_type: ContextCriterionType, value: str) -> dict[str, str]:
    return {"type": criterion_type.value, "value": value}


@pytest.mark.asyncio
async def test_analyst_can_create_edit_and_expire_context_entry_with_audit(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish = AsyncMock(wraps=emit_event)
    monkeypatch.setattr("app.services.context_service.emit_event", publish)
    session_cookie, username = await _login_and_get_session_cookie(
        client, session_maker, analyst_user_factory
    )

    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    create_response = await client.post(
        "/api/v1/context-entries",
        json={
            "criteria": [_criterion(ContextCriterionType.ALERT_SOURCE, "EDR-*")],
            "body": "Treat EDR rule X as noisy during the current tuning window.",
            "expires_at": expires_at.isoformat(),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["author"] == username
    assert created["criteria"] == [{"type": "ALERT_SOURCE", "value": "EDR-*"}]
    assert created["expired_at"] is None

    update_response = await client.put(
        f"/api/v1/context-entries/{created['id']}",
        json={
            "criteria": [_criterion(ContextCriterionType.TAG, "tuning-?")],
            "body": "Tag tuning means compare against this week's exception list.",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["criteria"] == [{"type": "TAG", "value": "tuning-?"}]
    assert updated["updated_at"] >= updated["created_at"]

    expire_response = await client.post(
        f"/api/v1/context-entries/{created['id']}/expire",
        cookies={"intercept_session": session_cookie},
    )

    assert expire_response.status_code == 200
    expired = expire_response.json()
    assert expired["expired_at"] is not None

    active_response = await client.get(
        "/api/v1/context-entries",
        cookies={"intercept_session": session_cookie},
    )
    assert active_response.status_code == 200
    assert active_response.json() == []

    async with session_maker() as session:
        result = await session.execute(select(AuditLog).where(AuditLog.entity_type == "context_entry"))
        event_types = {row.event_type for row in result.scalars().all()}

    assert event_types == {
        "context_entry.created",
        "context_entry.updated",
        "context_entry.expired",
    }
    assert publish.await_count == 3
    for event in publish.await_args_list:
        assert event.kwargs == {
            "entity_type": "context_entry",
            "entity_id": created["id"],
            "event_type": RealtimeEventType.ENTITY_UPDATED,
            "performed_by": username,
        }


@pytest.mark.asyncio
async def test_analyst_can_create_global_context_entry_with_empty_criteria(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, username = await _login_and_get_session_cookie(
        client, session_maker, analyst_user_factory
    )

    expires_at = datetime.now(timezone.utc) + timedelta(days=3)
    response = await client.post(
        "/api/v1/context-entries",
        json={
            "criteria": [],
            "body": "Apply this global context to every triage workflow.",
            "expires_at": expires_at.isoformat(),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 201
    created = response.json()
    assert created["author"] == username
    assert created["criteria"] == []
    assert created["body"] == "Apply this global context to every triage workflow."

    list_response = await client.get(
        "/api/v1/context-entries",
        cookies={"intercept_session": session_cookie},
    )
    assert list_response.status_code == 200
    assert [entry["id"] for entry in list_response.json()] == [created["id"]]

    async with session_maker() as session:
        result = await session.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "context_entry",
                AuditLog.entity_id == str(created["id"]),
                AuditLog.event_type == "context_entry.created",
            )
        )
        assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_removed_context_criterion_types_are_rejected(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, _username = await _login_and_get_session_cookie(
        client, session_maker, analyst_user_factory
    )

    response = await client.post(
        "/api/v1/context-entries",
        json={
            "criteria": [{"type": "CASE", "value": "42"}],
            "body": "Invalid old criterion type.",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_matching_context_uses_optional_and_wildcard_criteria(session_maker: Any) -> None:
    async with session_maker() as session:
        alert = Alert(
            title="Suspicious login",
            description="Observed on endpoint",
            priority=Priority.HIGH,
            source="EDR-Primary",
            tags=["credential-access", "tuning-a"],
            timeline_items={
                "system-1": {
                    "id": "system-1",
                    "type": "system",
                    "hostname": "WKSTN-7.corp.local",
                    "ip_address": "10.0.0.7",
                },
                "obs-1": {
                    "id": "obs-1",
                    "type": "observable",
                    "observable_value": "198.51.100.10",
                },
                "actor-1": {
                    "id": "actor-1",
                    "type": "internal_actor",
                    "user_id": "alice.admin",
                    "contact_email": "alice@example.com",
                },
            },
        )
        session.add(alert)
        await session.flush()

        future = datetime.now(timezone.utc) + timedelta(days=2)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        entries = [
            ContextEntry(criteria=[], body="global", author="a", expires_at=future),
            ContextEntry(criteria=[_criterion(ContextCriterionType.ALERT_SOURCE, "edr-*")], body="source wildcard", author="a", expires_at=future),
            ContextEntry(criteria=[_criterion(ContextCriterionType.SYSTEM, "wkstn-?.corp.local")], body="system wildcard", author="a", expires_at=future),
            ContextEntry(criteria=[_criterion(ContextCriterionType.OBSERVABLE, "198.51.100.10")], body="observable exact", author="a", expires_at=future),
            ContextEntry(criteria=[_criterion(ContextCriterionType.TAG, "credential-*")], body="tag wildcard", author="a", expires_at=future),
            ContextEntry(criteria=[_criterion(ContextCriterionType.ACTOR, "ALICE.*")], body="actor wildcard", author="a", expires_at=future),
            ContextEntry(
                criteria=[
                    _criterion(ContextCriterionType.ALERT_SOURCE, "EDR-*"),
                    _criterion(ContextCriterionType.TAG, "tuning-?"),
                ],
                body="and criteria",
                author="a",
                expires_at=future,
            ),
            ContextEntry(criteria=[_criterion(ContextCriterionType.ALERT_SOURCE, "siem-*")], body="wrong source", author="a", expires_at=future),
            ContextEntry(criteria=[_criterion(ContextCriterionType.SYSTEM, "server-?")], body="wrong system", author="a", expires_at=future),
            ContextEntry(criteria=[_criterion(ContextCriterionType.ACTOR, "bob*")], body="wrong actor", author="a", expires_at=future),
            ContextEntry(criteria=[_criterion(ContextCriterionType.TAG, "credential-*")], body="expired", author="a", expires_at=past),
        ]
        session.add_all(entries)
        await session.commit()
        assert alert.id is not None
        alert_id = alert.id

    async with session_maker() as session:
        matched = await ContextService(session).get_matching_context_for_alert(alert_id)

    assert {entry["body"] for entry in matched} == {
        "global",
        "source wildcard",
        "system wildcard",
        "observable exact",
        "tag wildcard",
        "actor wildcard",
        "and criteria",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_context", [True, False], ids=["edited-entry", "initially-empty"])
async def test_triage_freezes_context_delivered_to_langflow(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
    initial_context: bool,
) -> None:
    cookie, username = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    cookies = {"intercept_session": cookie}
    enqueue = AsyncMock()
    monkeypatch.setattr(
        "app.services.task_queue_service.get_task_queue_service",
        lambda: SimpleNamespace(enqueue=enqueue),
    )
    monkeypatch.setattr("app.services.tasks.async_session_factory", session_maker)
    monkeypatch.setattr(mcp_tools, "async_session_factory", session_maker)
    principal = SimpleNamespace(username="triage-agent", id=uuid4())
    monkeypatch.setattr(mcp_tools, "_get_authenticated_user", lambda: principal)
    request_headers: dict[str, str] = {}
    monkeypatch.setattr(mcp_tools, "get_http_request", lambda: SimpleNamespace(headers=request_headers))
    snapshots: list[dict[str, Any]] = []

    expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    async with session_maker() as session:
        session.add(AppSetting(
            key="langflow.alert_triage_flow_id",
            value="flow-123",
            value_type=SettingType.STRING,
            is_secret=False,
            category="langflow",
        ))
        alert = Alert(title="Test context revisions", source="SIEM", priority=Priority.MEDIUM)
        session.add(alert)
        session.add(ContextEntry(
            criteria=[_criterion(ContextCriterionType.ALERT_SOURCE, "EDR")],
            body="Unmatched entry",
            author=username,
            expires_at=expires_at,
        ))
        entry = ContextEntry(criteria=[], body="Original entry", author=username, expires_at=expires_at)
        if initial_context:
            session.add(entry)
        await session.commit()
        alert_id, entry_id = alert.id, entry.id
    assert alert_id is not None

    class FakeLangFlowService:
        @classmethod
        async def from_settings(cls, settings_service: Any) -> "FakeLangFlowService":
            return cls()

        async def run_flow_streaming(self, **kwargs: Any) -> dict[str, Any]:
            summary_headers = kwargs["context"]["triage_summary_mcp"]["headers"]
            decision_headers = kwargs["context"]["triage_agent_mcp"]["headers"]
            assert summary_headers == decision_headers
            request_headers.update(summary_headers)
            summary = await mcp_tools.get_summary_tool("alert", str(alert_id))
            snapshot = summary["context"]
            snapshots.append(snapshot)
            if len(snapshots) == 1:
                assert [item["body"] for item in snapshot["items"]] == (["Original entry"] if initial_context else [])
                if entry_id is not None:
                    edited = await client.put(
                        f"/api/v1/context-entries/{entry_id}",
                        json={"body": "Edited entry"},
                        cookies=cookies,
                    )
                    assert edited.status_code == 200, edited.text
                else:
                    created = await client.post(
                        "/api/v1/context-entries",
                        json={"body": "Edited entry", "expires_at": expires_at.isoformat()},
                        cookies=cookies,
                    )
                    assert created.status_code == 201, created.text
                assert (await mcp_tools.get_summary_tool("alert", str(alert_id)))["context"] == snapshot
            await mcp_tools.record_triage_decision_tool(str(alert_id), "BENIGN", 0.8, commit=True)
            return {"ok": True}

        async def close(self) -> None:
            return None

    monkeypatch.setattr("app.services.tasks.LangFlowService", FakeLangFlowService)
    enqueue_url = f"/api/v1/alerts/{alert_id}/triage-recommendation/enqueue"
    alert_url = f"/api/v1/alerts/{alert_id}"
    queued = await client.post(enqueue_url, cookies=cookies)
    assert queued.status_code == 200, queued.text
    first_payload = enqueue.await_args.kwargs["payload"]
    await handle_triage_alert(first_payload)

    detail = (await client.get(alert_url, cookies=cookies)).json()
    first_recommendation = detail["triage_recommendation"]
    assert first_recommendation["context_snapshot_verified"] is True
    assert first_recommendation["applied_context_entries"] == snapshots[0]["items"]
    assert detail["triage_context_changed"] is True
    assert detail["context"]["items"][0]["body"] == "Edited entry"

    rerun = await client.post(
        enqueue_url,
        json={"expected_recommendation_created_at": first_recommendation["created_at"]},
        cookies=cookies,
    )
    assert rerun.status_code == 200, rerun.text
    second_payload = enqueue.await_args.kwargs["payload"]
    assert second_payload["run_id"] != first_payload["run_id"]

    # The old Langflow callback and old worker failure can only address the old run.
    request_headers[TRIAGE_RUN_HEADER] = first_payload["run_id"]
    with pytest.raises(HTTPException, match="no longer queued"):
        await mcp_tools.record_triage_decision_tool(str(alert_id), "BENIGN", 0.8, commit=True)
    request_headers.clear()
    with pytest.raises(HTTPException, match="requires its run ID"):
        await mcp_tools.record_triage_decision_tool(str(alert_id), "BENIGN", 0.8, commit=True)
    await _mark_triage_failed(alert_id, "Old worker failure", UUID(first_payload["run_id"]))
    await handle_triage_alert(second_payload)

    detail = (await client.get(alert_url, cookies=cookies)).json()
    second_recommendation = detail["triage_recommendation"]
    assert second_recommendation["status"] == RecommendationStatus.PENDING
    assert second_recommendation["applied_context_entries"] == snapshots[1]["items"]
    assert snapshots[1]["items"][0]["body"] == "Edited entry"
    assert detail["triage_context_changed"] is False
    async with session_maker() as session:
        first_run = await session.get(AlertTriageRun, UUID(first_payload["run_id"]))
        assert first_run.context_snapshot == snapshots[0]

    rejected = await client.post(
        f"/api/v1/alerts/{alert_id}/triage-recommendation/reject",
        json={"category": "PREFER_MANUAL_REVIEW"},
        cookies=cookies,
    )
    assert rejected.status_code == 200, rejected.text
    stale_rerun = await client.post(
        enqueue_url,
        json={"expected_recommendation_created_at": second_recommendation["created_at"]},
        cookies=cookies,
    )
    assert stale_rerun.status_code == 409, stale_rerun.text
    assert enqueue.await_count == 2
