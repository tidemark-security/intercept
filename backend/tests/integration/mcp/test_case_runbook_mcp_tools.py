from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import HTTPException

from app.models.enums import AlertStatus, CaseRunbookStatus, PICERLStage, Priority
from app.models.models import Alert, CaseRunbook
from app.services import mcp_service


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
        with pytest.raises(HTTPException) as exc:
            await mcp_service.get_case_runbook(session, id_str=f"RUN-{draft_id:07d}")

    assert result.title == "Credential Theft"
    assert result.runbook_tasks[0].title == "Reset password"
    assert result.runbook_tasks[0].picerl_stage == PICERLStage.CONTAINMENT.value
    assert exc.value.status_code == 404


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

        with pytest.raises(HTTPException) as non_escalating:
            await mcp_service.record_triage_decision(
                session,
                alert_id_str=f"ALT-{alert.id:07d}",
                disposition="NEEDS_INVESTIGATION",
                confidence=0.7,
                recommended_case_runbook_id=runbook.id,
                request_escalate_to_case=False,
                commit=True,
            )

        with pytest.raises(HTTPException) as mutually_exclusive:
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
            request_escalate_to_case=True,
            commit=True,
            created_by="mcp-test",
        )

    assert non_escalating.value.status_code == 400
    assert mutually_exclusive.value.status_code == 400
    assert result.recommendation_id is not None
    assert result.suggested_patches[0].new_value == AlertStatus.ESCALATED.value
