from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import HTTPException

from app.models.enums import AlertStatus, Priority
from app.models.models import Alert
from app.services import triage_recommendation_service


async def _create_alert(session: Any) -> Alert:
    alert = Alert(
        title="Service normalization alert",
        description="Direct service caller test",
        priority=Priority.MEDIUM,
        source="SIEM",
        status=AlertStatus.NEW,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(alert)
    await session.flush()
    assert alert.id is not None
    return alert


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("disposition", "input_escalate", "input_status", "expected_escalate", "expected_status"),
    [
        ("BENIGN", True, AlertStatus.ESCALATED.value, False, AlertStatus.CLOSED_BP),
        ("UNKNOWN", False, AlertStatus.CLOSED_UNRESOLVED.value, True, AlertStatus.ESCALATED),
    ],
)
async def test_create_or_replace_recommendation_normalizes_direct_callers(
    session_maker: Any,
    disposition: str,
    input_escalate: bool,
    input_status: str,
    expected_escalate: bool,
    expected_status: AlertStatus,
) -> None:
    async with session_maker() as session:
        alert = await _create_alert(session)

        recommendation = await triage_recommendation_service.create_or_replace_recommendation(
            db=session,
            alert_id=alert.id,
            data={
                "disposition": disposition,
                "confidence": 0.8,
                "reasoning_bullets": ["Direct caller supplied contradictory case-path data"],
                "recommended_actions": [],
                "suggested_status": input_status,
                "request_escalate_to_case": input_escalate,
            },
            created_by="service-test",
        )

    assert recommendation.request_escalate_to_case is expected_escalate
    assert recommendation.suggested_status == expected_status


@pytest.mark.asyncio
async def test_create_or_replace_recommendation_rejects_invalid_suggested_status(
    session_maker: Any,
) -> None:
    async with session_maker() as session:
        alert = await _create_alert(session)

        with pytest.raises(HTTPException) as exc:
            await triage_recommendation_service.create_or_replace_recommendation(
                db=session,
                alert_id=alert.id,
                data={
                    "disposition": "TRUE_POSITIVE",
                    "confidence": 0.8,
                    "reasoning_bullets": [],
                    "recommended_actions": [],
                    "suggested_status": "NOT_A_STATUS",
                    "request_escalate_to_case": False,
                },
                created_by="service-test",
            )

    assert exc.value.status_code == 400
    assert "Invalid suggested_status" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_create_or_replace_recommendation_rejects_dismissal_work(
    session_maker: Any,
) -> None:
    async with session_maker() as session:
        alert = await _create_alert(session)

        with pytest.raises(HTTPException) as exc:
            await triage_recommendation_service.create_or_replace_recommendation(
                db=session,
                alert_id=alert.id,
                data={
                    "disposition": "FALSE_POSITIVE",
                    "confidence": 0.8,
                    "reasoning_bullets": [],
                    "recommended_actions": [{"title": "Investigate anyway"}],
                    "request_escalate_to_case": True,
                },
                created_by="service-test",
            )

    assert exc.value.status_code == 400
    assert "Dismissal recommendations cannot include work recommendations" in str(exc.value.detail)
