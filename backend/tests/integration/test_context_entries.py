from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.enums import ContextCriterionType, Priority, RecommendationStatus, SettingType, TriageDisposition
from app.models.models import Alert, AppSetting, AuditLog, ContextEntry, TriageRecommendation
from app.services.context_service import ContextService
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


def _criterion(criterion_type: ContextCriterionType, value: str) -> dict[str, str]:
    return {"type": criterion_type.value, "value": value}


@pytest.mark.asyncio
async def test_analyst_can_create_edit_and_expire_context_entry_with_audit(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
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
            timeline_items={
                "obs": {
                    "id": "obs",
                    "type": "observable",
                    "observable_value": "bad.example",
                }
            },
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
            ContextEntry(
                criteria=[_criterion(ContextCriterionType.OBSERVABLE, "bad.*")],
                body="Known test observable; validate source before escalation.",
                author="lead",
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        session.add(
            ContextEntry(
                criteria=[_criterion(ContextCriterionType.ALERT_SOURCE, "EDR")],
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
