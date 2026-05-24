from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.enums import AITriageContextScopeType, Priority, RecommendationStatus, SettingType, TriageDisposition
from app.models.models import AITriageContextEntry, Alert, AppSetting, AuditLog, TriageRecommendation
from app.services.ai_triage_context_service import AITriageContextService
from app.services.tasks import handle_triage_alert
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


@pytest.mark.asyncio
async def test_analyst_can_create_edit_and_expire_context_with_audit(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie, username = await _login_and_get_session_cookie(
        client, session_maker, analyst_user_factory
    )

    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    create_response = await client.post(
        "/api/v1/ai-triage-context",
        json={
            "scope": {"type": "ALERT_SOURCE", "value": "EDR"},
            "body": "Treat EDR rule X as noisy during the current tuning window.",
            "expires_at": expires_at.isoformat(),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["author"] == username
    assert created["scope"] == {"type": "ALERT_SOURCE", "value": "EDR"}
    assert created["expired_at"] is None

    update_response = await client.put(
        f"/api/v1/ai-triage-context/{created['id']}",
        json={
            "scope": {"type": "TAG", "value": "tuning"},
            "body": "Tag tuning means compare against this week's exception list.",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["scope"] == {"type": "TAG", "value": "tuning"}
    assert updated["updated_at"] >= updated["created_at"]

    expire_response = await client.post(
        f"/api/v1/ai-triage-context/{created['id']}/expire",
        cookies={"intercept_session": session_cookie},
    )

    assert expire_response.status_code == 200
    expired = expire_response.json()
    assert expired["expired_at"] is not None

    active_response = await client.get(
        "/api/v1/ai-triage-context",
        cookies={"intercept_session": session_cookie},
    )
    assert active_response.status_code == 200
    assert active_response.json() == []

    async with session_maker() as session:
        result = await session.execute(select(AuditLog).where(AuditLog.entity_type == "ai_triage_context"))
        event_types = {row.event_type for row in result.scalars().all()}

    assert event_types == {
        "ai_triage_context.created",
        "ai_triage_context.updated",
        "ai_triage_context.expired",
    }


@pytest.mark.asyncio
async def test_matching_context_uses_only_alert_scope_candidates(session_maker: Any) -> None:
    async with session_maker() as session:
        alert = Alert(
            title="Suspicious login",
            description="Observed on endpoint",
            priority=Priority.HIGH,
            source="EDR",
            assignee="analyst1",
            tags=["credential-access"],
            timeline_items={
                "host-1": {"id": "host-1", "type": "system", "hostname": "wkstn-7"},
                "obs-1": {"id": "obs-1", "type": "observable", "value": "198.51.100.10"},
            },
        )
        session.add(alert)
        await session.flush()

        future = datetime.now(timezone.utc) + timedelta(days=2)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        entries = [
            AITriageContextEntry(scope_type=AITriageContextScopeType.GLOBAL, body="global", author="a", expires_at=future),
            AITriageContextEntry(scope_type=AITriageContextScopeType.ALERT_SOURCE, scope_value="edr", body="source", author="a", expires_at=future),
            AITriageContextEntry(scope_type=AITriageContextScopeType.HOST_SYSTEM, scope_value="WKSTN-7", body="host", author="a", expires_at=future),
            AITriageContextEntry(scope_type=AITriageContextScopeType.OBSERVABLE, scope_value="198.51.100.10", body="observable", author="a", expires_at=future),
            AITriageContextEntry(scope_type=AITriageContextScopeType.TAG, scope_value="credential-access", body="tag", author="a", expires_at=future),
            AITriageContextEntry(scope_type=AITriageContextScopeType.ALERT_SOURCE, scope_value="siem", body="wrong source", author="a", expires_at=future),
            AITriageContextEntry(scope_type=AITriageContextScopeType.USER_ACCOUNT, scope_value="analyst1", body="expired", author="a", expires_at=past),
        ]
        session.add_all(entries)
        await session.commit()
        assert alert.id is not None
        alert_id = alert.id

    async with session_maker() as session:
        matched = await AITriageContextService(session).get_matching_context_for_alert(alert_id)

    assert {entry["body"] for entry in matched} == {"global", "source", "host", "observable", "tag"}


@pytest.mark.asyncio
async def test_triage_task_injects_matching_context_and_records_snapshot(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_context: dict[str, Any] = {}

    class FakeLangFlowService:
        @classmethod
        async def from_settings(cls, settings_service: Any) -> "FakeLangFlowService":
            return cls()

        async def run_flow_streaming(self, **kwargs: Any) -> dict[str, Any]:
            captured_context.update(kwargs["context"])
            return {"ok": True}

        async def close(self) -> None:
            return None

    monkeypatch.setattr("app.services.tasks.async_session_factory", session_maker)
    monkeypatch.setattr("app.services.tasks.LangFlowService", FakeLangFlowService)

    async with session_maker() as session:
        session.add(
            AppSetting(
                key="langflow.alert_triage_flow_id",
                value="flow-123",
                value_type=SettingType.STRING,
                is_secret=False,
                category="langflow",
            )
        )
        alert = Alert(
            title="Suspicious process",
            priority=Priority.MEDIUM,
            source="SIEM",
            timeline_items={"obs": {"id": "obs", "type": "observable", "value": "bad.example"}},
        )
        session.add(alert)
        await session.flush()
        assert alert.id is not None
        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.UNKNOWN,
            confidence=0.0,
            reasoning_bullets=[],
            recommended_actions=[],
            created_by="analyst",
            status=RecommendationStatus.QUEUED,
        )
        session.add(recommendation)
        session.add(
            AITriageContextEntry(
                scope_type=AITriageContextScopeType.OBSERVABLE,
                scope_value="bad.example",
                body="Known test observable; validate source before escalation.",
                author="lead",
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        session.add(
            AITriageContextEntry(
                scope_type=AITriageContextScopeType.ALERT_SOURCE,
                scope_value="EDR",
                body="Should not match this SIEM alert.",
                author="lead",
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        await session.commit()
        alert_id = alert.id

    await handle_triage_alert({"alert_id": alert_id})

    applied_context = json.loads(captured_context["triage_context_entries"]["input_value"])
    assert [entry["body"] for entry in applied_context] == [
        "Known test observable; validate source before escalation."
    ]

    async with session_maker() as session:
        result = await session.execute(
            select(TriageRecommendation).where(TriageRecommendation.alert_id == alert_id)
        )
        refreshed = result.scalar_one()
        assert [entry["body"] for entry in refreshed.applied_context_entries] == [
            "Known test observable; validate source before escalation."
        ]
