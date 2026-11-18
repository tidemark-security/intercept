"""Unit tests for MCP get_item timeline content retrieval."""
from __future__ import annotations

from datetime import datetime, timezone

from mcp import McpError
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.mcp.server import (
    _GET_ITEM_MISSING_SCOPE_MESSAGE,
    _GET_ITEM_MIXED_CONTRACT_MESSAGE,
    _GET_ITEM_OLD_CONTRACT_MESSAGE,
    mcp,
)
from app.models.models import Alert, Case, Task
from app.services import mcp_service
from app.services.mcp_errors import McpNotFoundError, McpValidationError


def _timeline_note(*, item_id: str, content_field: str, content: str) -> dict[str, str]:
    timestamp = datetime(
        2026, 3, 9, 11, 38, 9, 676066, tzinfo=timezone.utc
    ).isoformat()
    return {
        "id": item_id,
        "type": "note",
        "timestamp": timestamp,
        "created_by": "timeline-author",
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
            parent_entity_type="case",
            parent_entity_id=str(case.id),
            item_id="lunch-containment-plan-checklist-v1",
            mode="full",
            max_chars=10000,
        )

    assert result.item_id == "lunch-containment-plan-checklist-v1"
    assert result.content == "Confirm cafeteria isolation and notify facilities."
    assert result.is_truncated is False
    assert result.next_cursor is None
    assert result.metadata.type == "note"
    assert result.metadata.parent_kind == "case"
    assert result.metadata.parent_id == case.id
    assert result.metadata.parent_human_id == "CAS-0000001"
    assert result.metadata.author == "timeline-author"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entity_factory", "parent_entity_type", "content_field", "expected_human_id"),
    [
        (
            lambda: Alert(title="Legacy alert", timeline_items=[]),
            "alert",
            "body",
            "ALT-0000001",
        ),
        (
            lambda: Task(title="Legacy task", created_by="analyst", timeline_items=[]),
            "task",
            "content",
            "TSK-0000001",
        ),
    ],
)
async def test_get_item_preserves_legacy_body_and_content_fallbacks(
    session_maker: async_sessionmaker[AsyncSession],
    entity_factory,
    parent_entity_type: str,
    content_field: str,
    expected_human_id: str,
) -> None:
    entity = entity_factory()
    item_id = f"legacy-{parent_entity_type}-{content_field}"
    legacy_content = f"Legacy {parent_entity_type} text"
    entity.timeline_items = [
        _timeline_note(
            item_id=item_id,
            content_field=content_field,
            content=legacy_content,
        )
    ]

    async with session_maker() as session:
        session.add(entity)
        await session.commit()
        await session.refresh(entity)

        assert entity.id is not None

        result = await mcp_service.get_item(
            db=session,
            parent_entity_type=parent_entity_type,
            parent_entity_id=str(entity.id),
            item_id=item_id,
            mode="full",
            max_chars=10000,
        )

    assert result.content == legacy_content
    assert result.metadata.parent_kind == parent_entity_type
    assert result.metadata.parent_human_id == expected_human_id


@pytest.mark.asyncio
async def test_get_item_tool_explains_old_hint_contract() -> None:
    with pytest.raises(McpError) as exc_info:
        await mcp.call_tool(
            "get_item",
            {
                "item_id": "note-1",
                "hint_kind": "case",
                "hint_parent_id": "CAS-000001",
            },
        )

    assert str(exc_info.value) == _GET_ITEM_OLD_CONTRACT_MESSAGE


@pytest.mark.asyncio
async def test_get_item_tool_explains_missing_parent_scope() -> None:
    with pytest.raises(McpError) as exc_info:
        await mcp.call_tool("get_item", {"item_id": "note-1"})

    assert str(exc_info.value) == _GET_ITEM_MISSING_SCOPE_MESSAGE


@pytest.mark.asyncio
async def test_get_item_tool_explains_mixed_old_and_new_contracts() -> None:
    with pytest.raises(McpError) as exc_info:
        await mcp.call_tool(
            "get_item",
            {
                "parent_entity_type": "case",
                "parent_entity_id": "CAS-000001",
                "item_id": "note-1",
                "hint_kind": "case",
            },
        )

    assert str(exc_info.value) == _GET_ITEM_MIXED_CONTRACT_MESSAGE


@pytest.mark.asyncio
async def test_get_item_prefers_top_level_match_before_recursive_replies(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    case = Case(
        title="Top-level wins",
        created_by="analyst",
        timeline_items={
            "shared-id": _timeline_note(
                item_id="shared-id",
                content_field="description",
                content="Top-level content",
            ),
            "parent-note": {
                **_timeline_note(
                    item_id="parent-note",
                    content_field="description",
                    content="Parent note",
                ),
                "replies": {
                    "shared-id": _timeline_note(
                        item_id="shared-id",
                        content_field="description",
                        content="Nested reply content",
                    )
                },
            },
        },
    )

    async with session_maker() as session:
        session.add(case)
        await session.commit()
        await session.refresh(case)

        assert case.id is not None

        result = await mcp_service.get_item(
            db=session,
            parent_entity_type="case",
            parent_entity_id=str(case.id),
            item_id="shared-id",
            mode="full",
            max_chars=10000,
        )

    assert result.content == "Top-level content"


@pytest.mark.asyncio
async def test_get_item_returns_nested_reply_from_scoped_parent(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    case = Case(
        title="Nested reply case",
        created_by="analyst",
        timeline_items={
            "parent-note": {
                **_timeline_note(
                    item_id="parent-note",
                    content_field="description",
                    content="Parent note",
                ),
                "replies": {
                    "reply-note": _timeline_note(
                        item_id="reply-note",
                        content_field="description",
                        content="Nested reply content",
                    )
                },
            }
        },
    )

    async with session_maker() as session:
        session.add(case)
        await session.commit()
        await session.refresh(case)

        assert case.id is not None

        result = await mcp_service.get_item(
            db=session,
            parent_entity_type="case",
            parent_entity_id=f"CAS-{case.id:06d}",
            item_id="reply-note",
            mode="full",
            max_chars=10000,
        )

    assert result.content == "Nested reply content"
    assert result.metadata.parent_kind == "case"
    assert result.metadata.parent_id == case.id


@pytest.mark.asyncio
async def test_get_item_does_not_search_other_parent_entities(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    alert = Alert(
        title="Do not cross scopes",
        timeline_items={
            "cross-scope-item": _timeline_note(
                item_id="cross-scope-item",
                content_field="description",
                content="This belongs to the alert",
            )
        },
    )
    case = Case(title="Empty scoped case", created_by="analyst", timeline_items={})

    async with session_maker() as session:
        session.add(alert)
        session.add(case)
        await session.commit()
        await session.refresh(case)

        assert case.id is not None

        with pytest.raises(McpNotFoundError) as exc_info:
            await mcp_service.get_item(
                db=session,
                parent_entity_type="case",
                parent_entity_id=str(case.id),
                item_id="cross-scope-item",
            )

    assert "no longer searches other alerts, cases, or tasks" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_item_accepts_flexible_parent_entity_ids(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    case = Case(
        title="Flexible IDs",
        created_by="analyst",
        timeline_items={
            "flexible-id-item": _timeline_note(
                item_id="flexible-id-item",
                content_field="description",
                content="Flexible ID content",
            )
        },
    )

    async with session_maker() as session:
        session.add(case)
        await session.commit()
        await session.refresh(case)

        assert case.id is not None

        parent_ids = [f"CAS-{case.id:06d}", str(case.id), f"{case.id:03d}"]
        results = [
            await mcp_service.get_item(
                db=session,
                parent_entity_type="case",
                parent_entity_id=parent_id,
                item_id="flexible-id-item",
            )
            for parent_id in parent_ids
        ]

    assert [result.content for result in results] == ["Flexible ID content"] * 3


@pytest.mark.asyncio
async def test_get_item_rejects_parent_type_prefix_mismatch(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as session:
        with pytest.raises(McpValidationError) as exc_info:
            await mcp_service.get_item(
                db=session,
                parent_entity_type="case",
                parent_entity_id="ALT-000001",
                item_id="note-1",
            )

    assert "has alert prefix but expected 'case'" in str(exc_info.value)
