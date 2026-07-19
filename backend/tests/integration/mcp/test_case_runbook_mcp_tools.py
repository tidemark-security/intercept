from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.models.enums import AlertStatus, CaseRunbookStatus, PICERLStage, Priority
from app.models.models import Alert, CaseRunbook, TriageRecommendation
from app.services import mcp_service
from app.services.mcp_errors import McpNotFoundError, McpValidationError


@pytest.mark.asyncio
async def test_search_case_runbooks_returns_only_published_and_matches_task_text(
    session_maker: Any,
) -> None:
    async with session_maker() as session:
        published = CaseRunbook(
            title="DLP Response",
            title_normalized="dlp response",
            description="Data loss response",
            status=CaseRunbookStatus.PUBLISHED,
            case_tags=["dlp"],
            runbook_tasks=[
                {
                    "title": "Collect mailbox evidence",
                    "picerl_stage": PICERLStage.IDENTIFICATION.value,
                }
            ],
            created_by="admin",
            updated_by="admin",
        )
        draft = CaseRunbook(
            title="Draft Only",
            title_normalized="draft only",
            description="Should not appear",
            status=CaseRunbookStatus.DRAFT,
            case_tags=[],
            runbook_tasks=[
                {
                    "title": "Collect mailbox evidence",
                    "picerl_stage": PICERLStage.IDENTIFICATION.value,
                }
            ],
            created_by="admin",
            updated_by="admin",
        )
        session.add_all([published, draft])
        await session.commit()

        result = await mcp_service.search_case_runbooks(
            session,
            query="mailbox",
            limit=10,
        )

    assert [item.title for item in result.items] == ["DLP Response"]
    assert result.items[0].runbook_task_count == 1
    assert result.items[0].picerl_stages == [PICERLStage.IDENTIFICATION.value]


@pytest.mark.asyncio
async def test_get_case_runbook_returns_lean_published_payload_and_rejects_draft(
    session_maker: Any,
) -> None:
    async with session_maker() as session:
        published = CaseRunbook(
            title="Credential Theft",
            title_normalized="credential theft",
            description="Credential theft playbook",
            status=CaseRunbookStatus.PUBLISHED,
            case_tags=["identity"],
            runbook_tasks=[
                {
                    "title": "Reset password",
                    "description": "Force password reset",
                    "picerl_stage": PICERLStage.CONTAINMENT.value,
                    "priority": Priority.HIGH.value,
                    "tags": ["containment"],
                }
            ],
            created_by="admin",
            updated_by="admin",
        )
        draft = CaseRunbook(
            title="Draft",
            title_normalized="draft",
            status=CaseRunbookStatus.DRAFT,
            case_tags=[],
            runbook_tasks=[],
            created_by="admin",
            updated_by="admin",
        )
        session.add_all([published, draft])
        await session.flush()
        assert published.id is not None
        assert draft.id is not None
        published_id = published.id
        draft_id = draft.id
        await session.commit()

        result = await mcp_service.get_case_runbook(session, id_str=f"RUN-{published_id:07d}")
        with pytest.raises(McpNotFoundError):
            await mcp_service.get_case_runbook(session, id_str=f"RUN-{draft_id:07d}")

    assert result.title == "Credential Theft"
    assert result.runbook_tasks[0].title == "Reset password"
    assert result.runbook_tasks[0].picerl_stage == PICERLStage.CONTAINMENT.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("disposition", "input_escalate", "input_status", "expected_escalate", "expected_status"),
    [
        ("TRUE_POSITIVE", False, AlertStatus.CLOSED_TP.value, True, AlertStatus.ESCALATED),
        ("FALSE_POSITIVE", True, AlertStatus.ESCALATED.value, False, AlertStatus.CLOSED_FP),
        ("BENIGN", True, AlertStatus.ESCALATED.value, False, AlertStatus.CLOSED_BP),
        ("NEEDS_INVESTIGATION", False, AlertStatus.IN_PROGRESS.value, True, AlertStatus.ESCALATED),
        ("DUPLICATE", True, AlertStatus.ESCALATED.value, False, AlertStatus.CLOSED_DUPLICATE),
        ("UNKNOWN", False, AlertStatus.CLOSED_UNRESOLVED.value, True, AlertStatus.ESCALATED),
    ],
)
async def test_record_triage_decision_derives_case_path_from_disposition(
    session_maker: Any,
    disposition: str,
    input_escalate: bool,
    input_status: str,
    expected_escalate: bool,
    expected_status: AlertStatus,
) -> None:
    async with session_maker() as session:
        alert = Alert(
            title=f"{disposition} alert",
            description="Canonical case path test",
            priority=Priority.MEDIUM,
            source="SIEM",
            status=AlertStatus.NEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(alert)
        await session.flush()
        assert alert.id is not None

        result = await mcp_service.record_triage_decision(
            session,
            alert_id_str=f"ALT-{alert.id:07d}",
            disposition=disposition,
            confidence=0.7,
            suggested_status=input_status,
            request_escalate_to_case=input_escalate,
            commit=True,
            created_by="mcp-test",
        )

        assert result.recommendation_id is not None
        recommendation = await session.get(TriageRecommendation, result.recommendation_id)

    assert recommendation is not None
    assert recommendation.request_escalate_to_case is expected_escalate
    assert recommendation.suggested_status == expected_status
    assert result.suggested_patches[0].new_value == expected_status.value


@pytest.mark.asyncio
async def test_record_triage_decision_runbook_contracts(
    session_maker: Any,
) -> None:
    async with session_maker() as session:
        alert = Alert(
            title="Suspicious download",
            description="DLP alert",
            priority=Priority.MEDIUM,
            source="DLP",
            status=AlertStatus.NEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        runbook = CaseRunbook(
            title="DLP Response",
            title_normalized="dlp response",
            description="DLP response",
            status=CaseRunbookStatus.PUBLISHED,
            case_tags=[],
            runbook_tasks=[
                {
                    "title": "Collect evidence",
                    "picerl_stage": PICERLStage.IDENTIFICATION.value,
                }
            ],
            created_by="admin",
            updated_by="admin",
        )
        session.add_all([alert, runbook])
        await session.flush()
        assert alert.id is not None
        assert runbook.id is not None

        with pytest.raises(McpValidationError) as dismissal_runbook:
            await mcp_service.record_triage_decision(
                session,
                alert_id_str=f"ALT-{alert.id:07d}",
                disposition="BENIGN",
                confidence=0.7,
                recommended_case_runbook_id=runbook.id,
                request_escalate_to_case=True,
                commit=True,
            )

        with pytest.raises(McpValidationError) as dismissal_actions:
            await mcp_service.record_triage_decision(
                session,
                alert_id_str=f"ALT-{alert.id:07d}",
                disposition="FALSE_POSITIVE",
                confidence=0.7,
                recommended_actions=[{"title": "Follow up anyway"}],
                request_escalate_to_case=True,
                commit=True,
            )

        with pytest.raises(McpValidationError) as mutually_exclusive:
            await mcp_service.record_triage_decision(
                session,
                alert_id_str=f"ALT-{alert.id:07d}",
                disposition="NEEDS_INVESTIGATION",
                confidence=0.7,
                recommended_case_runbook_id=runbook.id,
                recommended_actions=[{"title": "Do both"}],
                request_escalate_to_case=True,
                commit=True,
            )

        result = await mcp_service.record_triage_decision(
            session,
            alert_id_str=f"ALT-{alert.id:07d}",
            disposition="NEEDS_INVESTIGATION",
            confidence=0.7,
            recommended_case_runbook_id=f"RUN-{runbook.id:07d}",
            request_escalate_to_case=False,
            commit=True,
            created_by="mcp-test",
        )

    assert "Dismissal recommendations" in str(dismissal_runbook.value)
    assert "Dismissal recommendations" in str(dismissal_actions.value)
    assert "mutually exclusive" in str(mutually_exclusive.value)
    assert result.recommendation_id is not None
    assert result.suggested_patches[0].new_value == AlertStatus.ESCALATED.value
