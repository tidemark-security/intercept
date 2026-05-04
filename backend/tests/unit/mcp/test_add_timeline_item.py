"""Unit tests for MCP add_timeline_item behavior."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import Case
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


def test_timeline_lookup_skips_malformed_entries() -> None:
    item = timeline_service._find_item_by_id(
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