"""Unit tests for MCP add_timeline_item behavior."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from app.models.models import AuditLog, Case
from app.services import mcp_service
from app.services.timeline_service import timeline_service


@pytest.mark.asyncio
async def test_add_timeline_item_idempotency_supports_mapping_storage(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    timestamp = datetime(2026, 5, 4, 5, 32, 34, tzinfo=timezone.utc).isoformat()
    case = Case(
        title="Case with mapped timeline storage",
        created_by="analyst",
        timeline_items={
            "case-status-mermaid-20260504T053234Z": {
                "id": "case-status-mermaid-20260504T053234Z",
                "type": "note",
                "description": "Existing Mermaid diagram",
                "timestamp": timestamp,
                "created_by": "tidemark_ai",
            }
        },
    )

    async with session_maker() as session:
        session.add(case)
        await session.commit()
        await session.refresh(case)

        assert case.id is not None

        result = await mcp_service.add_timeline_item(
            db=session,
            target_kind="case",
            target_id_str=f"CAS-{case.id:07d}",
            item_id="case-status-mermaid-20260504T053234Z",
            body="Duplicate Mermaid diagram",
            commit=True,
            created_by="tidemark_ai",
        )

    assert result.mode == "already_exists"
    assert result.item_id == "case-status-mermaid-20260504T053234Z"
    assert result.author == "tidemark_ai"
    assert result.created_at == datetime.fromisoformat(timestamp)


@pytest.mark.asyncio
async def test_committed_timeline_item_preserves_id_for_idempotent_retry(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    case = Case(title="MCP idempotency case", created_by="analyst")
    async with session_maker() as session:
        session.add(case)
        await session.commit()
        await session.refresh(case)
        assert case.id is not None
        case_id = case.id

    item_id = "agent-note-20260719"
    async with session_maker() as session:
        first = await mcp_service.add_timeline_item(
            db=session,
            target_kind="case",
            target_id_str=f"CAS-{case_id:07d}",
            item_id=item_id,
            body="Stable agent note",
            commit=True,
            created_by="tidemark_ai",
        )

    async with session_maker() as session:
        retry = await mcp_service.add_timeline_item(
            db=session,
            target_kind="case",
            target_id_str=f"CAS-{case_id:07d}",
            item_id=item_id,
            body="Duplicate agent note",
            commit=True,
            created_by="tidemark_ai",
        )
        stored_case = await session.get(Case, case_id)

    assert first.mode == "committed"
    assert first.item_id == item_id
    assert retry.mode == "already_exists"
    assert stored_case is not None
    assert list((stored_case.timeline_items or {}).keys()) == [item_id]
    assert stored_case.timeline_items[item_id]["description"] == "Stable agent note"


@pytest.mark.asyncio
async def test_concurrent_commits_with_same_item_id_are_idempotent(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    case = Case(title="Concurrent MCP idempotency", created_by="analyst")
    async with session_maker() as session:
        session.add(case)
        await session.commit()
        await session.refresh(case)
        assert case.id is not None
        case_id = case.id

    item_id = "concurrent-agent-note"
    async with session_maker() as first_session, session_maker() as second_session:
        first, second = await asyncio.gather(
            mcp_service.add_timeline_item(
                db=first_session,
                target_kind="case",
                target_id_str=f"CAS-{case_id:07d}",
                item_id=item_id,
                body="First concurrent body",
                commit=True,
                created_by="first-agent",
            ),
            mcp_service.add_timeline_item(
                db=second_session,
                target_kind="case",
                target_id_str=f"CAS-{case_id:07d}",
                item_id=item_id,
                body="Second concurrent body",
                commit=True,
                created_by="second-agent",
            ),
        )

    async with session_maker() as verification_session:
        stored_case = await verification_session.get(Case, case_id)
        audit_logs = (
            await verification_session.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == "case",
                    AuditLog.entity_id == str(case_id),
                    AuditLog.event_type == "timeline.item.added",
                    AuditLog.item_id == item_id,
                )
            )
        ).scalars().all()

    assert {first.mode, second.mode} == {"committed", "already_exists"}
    assert stored_case is not None
    assert list((stored_case.timeline_items or {}).keys()) == [item_id]
    assert len(audit_logs) == 1


def test_timeline_lookup_skips_malformed_entries() -> None:
    item = timeline_service.find_item_by_id(
        {
            "malformed": "not a timeline item",
            "valid-item": {
                "id": "valid-item",
                "type": "note",
                "description": "Valid note",
            },
        },
        "valid-item",
    )

    assert item == {
        "id": "valid-item",
        "type": "note",
        "description": "Valid note",
    }
