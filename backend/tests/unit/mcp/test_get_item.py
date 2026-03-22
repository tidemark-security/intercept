"""Unit tests for MCP get_item timeline content retrieval."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import Alert, Case, Task
from app.services import mcp_service


def _timeline_note(*, item_id: str, content_field: str, content: str) -> dict[str, str]:
    timestamp = datetime(2026, 3, 9, 11, 38, 9, 676066, tzinfo=timezone.utc).isoformat()
    return {
        "id": item_id,
        "type": "note",
        "timestamp": timestamp,
        content_field: content,
    }


@pytest.mark.asyncio
async def test_get_item_returns_case_note_description_content(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    case = Case(
        title="Lunch containment plan",
        created_by="analyst",
        timeline_items=[
            _timeline_note(
                item_id="lunch-containment-plan-checklist-v1",
                content_field="description",
                content="Confirm cafeteria isolation and notify facilities.",
            )
        ],
    )

    async with session_maker() as session:
        session.add(case)
        await session.commit()
        await session.refresh(case)

        assert case.id is not None

        result = await mcp_service.get_item(
            db=session,
            item_id="lunch-containment-plan-checklist-v1",
            mode="full",
            max_chars=10000,
            hint_kind="case",
            hint_parent_id=str(case.id),
        )

    assert result.item_id == "lunch-containment-plan-checklist-v1"
    assert result.content == "Confirm cafeteria isolation and notify facilities."
    assert result.is_truncated is False
    assert result.next_cursor is None
    assert result.metadata.type == "note"
    assert result.metadata.parent_kind == "case"
    assert result.metadata.parent_id == case.id
    assert result.metadata.parent_human_id == "CAS-0000001"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entity_factory", "hint_kind", "content_field", "expected_human_id"),
    [
        (lambda: Alert(title="Legacy alert", timeline_items=[]), "alert", "body", "ALT-0000001"),
        (lambda: Task(title="Legacy task", created_by="analyst", timeline_items=[]), "task", "content", "TSK-0000001"),
    ],
)
async def test_get_item_preserves_legacy_body_and_content_fallbacks(
    session_maker: async_sessionmaker[AsyncSession],
    entity_factory,
    hint_kind: str,
    content_field: str,
    expected_human_id: str,
) -> None:
    entity = entity_factory()
    item_id = f"legacy-{hint_kind}-{content_field}"
    legacy_content = f"Legacy {hint_kind} text"
    entity.timeline_items = [
        _timeline_note(item_id=item_id, content_field=content_field, content=legacy_content)
    ]

    async with session_maker() as session:
        session.add(entity)
        await session.commit()
        await session.refresh(entity)

        assert entity.id is not None

        result = await mcp_service.get_item(
            db=session,
            item_id=item_id,
            mode="full",
            max_chars=10000,
            hint_kind=hint_kind,
            hint_parent_id=str(entity.id),
        )

    assert result.content == legacy_content
    assert result.metadata.parent_kind == hint_kind
    assert result.metadata.parent_human_id == expected_human_id