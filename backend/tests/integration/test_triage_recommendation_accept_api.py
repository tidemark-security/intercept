from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.enums import AlertStatus, CaseStatus, CaseTemplateStatus, PICERLStage, Priority, RecommendationStatus, TriageDisposition
from app.models.models import Alert, Case, CaseTemplate, Task, TriageRecommendation
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


def _timeline_values(items: Any) -> list[dict[str, Any]]:
    if isinstance(items, dict):
        return [item for item in items.values() if isinstance(item, dict)]
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


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
async def test_accept_manual_recommendation_creates_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        alert = Alert(
            title="Suspicious command execution",
            description="Unknown command chain on endpoint",
            priority=Priority.MEDIUM,
            source="EDR",
            status=AlertStatus.NEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(alert)
        await session.flush()
        assert alert.id is not None

        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.NEEDS_INVESTIGATION,
            confidence=0.42,
            reasoning_bullets=["Signal is ambiguous and needs analyst validation"],
            recommended_actions=[{"title": "Collect host triage artifacts"}],
            suggested_status=AlertStatus.IN_PROGRESS,
            request_escalate_to_case=False,
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()
        alert_id = alert.id

    response = await client.post(
        f"/api/v1/alerts/{alert_id}/triage-recommendation/accept",
        json={
            "apply_status": True,
            "apply_priority": True,
            "apply_assignee": True,
            "apply_tags": True,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] is not None
    assert data["case_human_id"].startswith("CAS-")
    assert data["recommendation"]["status"] == RecommendationStatus.ACCEPTED.value

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert_id)
        assert refreshed_alert is not None
        assert refreshed_alert.case_id == data["case_id"]
        assert refreshed_alert.status == AlertStatus.ESCALATED
        assert refreshed_alert.triaged_at is not None
        assert refreshed_alert.assignee is not None
        timeline_items = _timeline_values(refreshed_alert.timeline_items)
        note_items = [item for item in timeline_items if item.get("type") == "note"]
        assert any(
            "accepted AI recommendation" in (item.get("description") or "")
            and "linked alert to case" in (item.get("description") or "")
            for item in note_items
        )


@pytest.mark.asyncio
async def test_accept_closed_recommendation_closes_without_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        alert = Alert(
            title="Known scanner noise",
            description="Expected vulnerability scan traffic",
            priority=Priority.LOW,
            source="SIEM",
            status=AlertStatus.NEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(alert)
        await session.flush()
        assert alert.id is not None

        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.FALSE_POSITIVE,
            confidence=0.91,
            reasoning_bullets=["Matched known scanner signatures"],
            recommended_actions=[],
            suggested_status=AlertStatus.CLOSED_FP,
            request_escalate_to_case=False,
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()
        alert_id = alert.id

    response = await client.post(
        f"/api/v1/alerts/{alert_id}/triage-recommendation/accept",
        json={
            "apply_status": True,
            "apply_priority": True,
            "apply_assignee": True,
            "apply_tags": True,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] is None

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert_id)
        assert refreshed_alert is not None
        assert refreshed_alert.case_id is None
        assert refreshed_alert.status == AlertStatus.CLOSED_FP
        assert refreshed_alert.triaged_at is not None
        assert refreshed_alert.assignee is not None
        timeline_items = _timeline_values(refreshed_alert.timeline_items)
        note_items = [item for item in timeline_items if item.get("type") == "note"]
        assert any(
            "accepted AI recommendation" in (item.get("description") or "")
            and "set status to CLOSED_FP" in (item.get("description") or "")
            for item in note_items
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("disposition", "expected_closed_status"),
    [
        (TriageDisposition.FALSE_POSITIVE, AlertStatus.CLOSED_FP),
        (TriageDisposition.BENIGN, AlertStatus.CLOSED_BP),
        (TriageDisposition.DUPLICATE, AlertStatus.CLOSED_DUPLICATE),
    ],
)
async def test_accept_dismiss_disposition_without_suggested_status_closes_without_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    disposition: TriageDisposition,
    expected_closed_status: AlertStatus,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        alert = Alert(
            title="Alert with inferred close status",
            description="Recommendation omits suggested_status",
            priority=Priority.LOW,
            source="SIEM",
            status=AlertStatus.NEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(alert)
        await session.flush()
        assert alert.id is not None

        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=disposition,
            confidence=0.9,
            reasoning_bullets=["Disposition implies dismissal"],
            recommended_actions=[],
            suggested_status=None,
            request_escalate_to_case=False,
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()
        alert_id = alert.id

    response = await client.post(
        f"/api/v1/alerts/{alert_id}/triage-recommendation/accept",
        json={
            "apply_status": True,
            "apply_priority": True,
            "apply_assignee": True,
            "apply_tags": True,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] is None
    assert data["case_human_id"] is None

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert_id)
        assert refreshed_alert is not None
        assert refreshed_alert.case_id is None
        assert refreshed_alert.status == expected_closed_status


@pytest.mark.asyncio
async def test_accept_closed_recommendation_with_status_patch_disabled_escalates(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        alert = Alert(
            title="Potential false positive event",
            description="Needs confirmation",
            priority=Priority.LOW,
            source="SIEM",
            status=AlertStatus.NEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(alert)
        await session.flush()
        assert alert.id is not None

        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.FALSE_POSITIVE,
            confidence=0.88,
            reasoning_bullets=["Likely benign scanner behavior"],
            recommended_actions=[],
            suggested_status=AlertStatus.CLOSED_FP,
            request_escalate_to_case=False,
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()
        alert_id = alert.id

    response = await client.post(
        f"/api/v1/alerts/{alert_id}/triage-recommendation/accept",
        json={
            "apply_status": False,
            "apply_priority": True,
            "apply_assignee": True,
            "apply_tags": True,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] is not None
    assert data["case_human_id"].startswith("CAS-")

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert_id)
        assert refreshed_alert is not None
        assert refreshed_alert.case_id == data["case_id"]
        assert refreshed_alert.status == AlertStatus.ESCALATED


@pytest.mark.asyncio
async def test_accept_escalation_on_already_linked_alert_reuses_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        existing_case = Case(
            title="Active investigation",
            description="Existing case",
            priority=Priority.HIGH,
            status=CaseStatus.IN_PROGRESS,
            assignee="analyst",
            created_by="analyst",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            timeline_items=[],
            tags=[],
        )
        session.add(existing_case)
        await session.flush()

        alert = Alert(
            title="Alert already linked",
            description="Linked alert should not create new case",
            priority=Priority.HIGH,
            source="EDR",
            status=AlertStatus.IN_PROGRESS,
            case_id=existing_case.id,
            linked_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(alert)
        await session.flush()
        assert alert.id is not None

        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.TRUE_POSITIVE,
            confidence=0.95,
            reasoning_bullets=["Clear malicious behavior"],
            recommended_actions=[{"title": "Isolate host"}],
            suggested_status=AlertStatus.ESCALATED,
            request_escalate_to_case=True,
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()

        alert_id = alert.id
        existing_case_id = existing_case.id

    response = await client.post(
        f"/api/v1/alerts/{alert_id}/triage-recommendation/accept",
        json={
            "apply_status": True,
            "apply_priority": True,
            "apply_assignee": True,
            "apply_tags": True,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == existing_case_id

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert_id)
        assert refreshed_alert is not None
        assert refreshed_alert.case_id == existing_case_id
        assert refreshed_alert.status == AlertStatus.ESCALATED


@pytest.mark.asyncio
async def test_accept_recommendation_with_published_case_template_applies_tasks(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        alert = Alert(
            title="DLP exfiltration",
            description="Possible sensitive file download",
            priority=Priority.HIGH,
            source="DLP",
            status=AlertStatus.NEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            tags=["dlp"],
        )
        template = CaseTemplate(
            title="DLP Response",
            title_normalized="dlp response",
            description="DLP response steps",
            status=CaseTemplateStatus.PUBLISHED,
            case_tags=["exfiltration"],
            template_tasks=[
                {
                    "title": "Collect evidence",
                    "picerl_stage": PICERLStage.IDENTIFICATION.value,
                },
                {
                    "title": "Contain account",
                    "picerl_stage": PICERLStage.CONTAINMENT.value,
                    "priority": Priority.CRITICAL.value,
                },
            ],
            created_by="admin",
            updated_by="admin",
        )
        session.add_all([alert, template])
        await session.flush()
        assert alert.id is not None
        assert template.id is not None

        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.NEEDS_INVESTIGATION,
            confidence=0.88,
            reasoning_bullets=["Template response is appropriate"],
            recommended_actions=[],
            recommended_case_template_id=template.id,
            suggested_status=AlertStatus.ESCALATED,
            request_escalate_to_case=True,
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()
        alert_id = alert.id
        template_id = template.id

    response = await client.post(
        f"/api/v1/alerts/{alert_id}/triage-recommendation/accept",
        json={
            "apply_status": True,
            "apply_priority": True,
            "apply_assignee": True,
            "apply_tags": True,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] is not None
    assert data["tasks_created"] == 2

    async with session_maker() as session:
        tasks = (
            await session.execute(
                select(Task).where(Task.case_id == data["case_id"]).order_by(Task.linked_at.asc())
            )
        ).scalars().all()
        assert [task.title for task in tasks] == ["Collect evidence", "Contain account"]
        assert all(task.source_tpl == template_id for task in tasks)
        assert tasks[0].assignee is None
        assert tasks[0].picerl_stage == PICERLStage.IDENTIFICATION
        assert tasks[1].priority == Priority.CRITICAL

        case = await session.get(Case, data["case_id"])
        assert case is not None
        assert case.tags == ["dlp", "exfiltration"]
        notes = _timeline_values(case.timeline_items)
        assert any("Applied Case Template" in (item.get("description") or "") for item in notes)


@pytest.mark.asyncio
async def test_accept_stale_case_template_recommendation_allows_skip_or_replacement(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        stale_template = CaseTemplate(
            title="Retired Response",
            title_normalized="retired response",
            description="No longer active",
            status=CaseTemplateStatus.DISABLED,
            case_tags=["retired"],
            template_tasks=[
                {"title": "Retired task", "picerl_stage": PICERLStage.IDENTIFICATION.value},
            ],
            created_by="admin",
            updated_by="admin",
        )
        replacement_template = CaseTemplate(
            title="Replacement Response",
            title_normalized="replacement response",
            description="Active response",
            status=CaseTemplateStatus.PUBLISHED,
            case_tags=["replacement"],
            template_tasks=[
                {"title": "Replacement task", "picerl_stage": PICERLStage.CONTAINMENT.value},
            ],
            created_by="admin",
            updated_by="admin",
        )
        blocked_alert = Alert(
            title="Blocked stale recommendation",
            description="Recommended template has been disabled",
            priority=Priority.HIGH,
            source="EDR",
            status=AlertStatus.NEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        replacement_alert = Alert(
            title="Replacement stale recommendation",
            description="Analyst selects a different template",
            priority=Priority.HIGH,
            source="EDR",
            status=AlertStatus.NEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add_all([stale_template, replacement_template, blocked_alert, replacement_alert])
        await session.flush()
        assert stale_template.id is not None
        assert replacement_template.id is not None
        assert blocked_alert.id is not None
        assert replacement_alert.id is not None

        session.add_all([
            TriageRecommendation(
                alert_id=blocked_alert.id,
                disposition=TriageDisposition.NEEDS_INVESTIGATION,
                confidence=0.77,
                reasoning_bullets=["Template was available when recommended"],
                recommended_actions=[],
                recommended_case_template_id=stale_template.id,
                suggested_status=AlertStatus.ESCALATED,
                request_escalate_to_case=True,
                created_by="test-ai",
                status=RecommendationStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            ),
            TriageRecommendation(
                alert_id=replacement_alert.id,
                disposition=TriageDisposition.NEEDS_INVESTIGATION,
                confidence=0.79,
                reasoning_bullets=["Template was available when recommended"],
                recommended_actions=[],
                recommended_case_template_id=stale_template.id,
                suggested_status=AlertStatus.ESCALATED,
                request_escalate_to_case=True,
                created_by="test-ai",
                status=RecommendationStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            ),
        ])
        await session.commit()
        blocked_alert_id = blocked_alert.id
        replacement_alert_id = replacement_alert.id
        replacement_template_id = replacement_template.id

    blocked_response = await client.post(
        f"/api/v1/alerts/{blocked_alert_id}/triage-recommendation/accept",
        json={},
        cookies={"intercept_session": session_cookie},
    )

    assert blocked_response.status_code == 409
    assert "continue without a template" in blocked_response.json()["detail"]

    skip_response = await client.post(
        f"/api/v1/alerts/{blocked_alert_id}/triage-recommendation/accept",
        json={"skip_case_template": True},
        cookies={"intercept_session": session_cookie},
    )

    assert skip_response.status_code == 200
    assert skip_response.json()["case_id"] is not None
    assert skip_response.json()["tasks_created"] == 0

    replacement_response = await client.post(
        f"/api/v1/alerts/{replacement_alert_id}/triage-recommendation/accept",
        json={"case_template_id": replacement_template_id},
        cookies={"intercept_session": session_cookie},
    )

    assert replacement_response.status_code == 200
    replacement_data = replacement_response.json()
    assert replacement_data["tasks_created"] == 1

    async with session_maker() as session:
        tasks = (
            await session.execute(
                select(Task).where(Task.case_id == replacement_data["case_id"])
            )
        ).scalars().all()
        assert [task.title for task in tasks] == ["Replacement task"]
        assert tasks[0].source_tpl == replacement_template_id
        assert tasks[0].picerl_stage == PICERLStage.CONTAINMENT
