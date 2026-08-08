from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import pytest

from app.models.models import Case
from app.services import mcp_service


@pytest.mark.asyncio
async def test_list_work_total_count_is_stable_across_cursor_pages(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as session:
        session.add_all(
            [Case(title=f"MCP case {index}", created_by="analyst") for index in range(3)]
        )
        await session.commit()

        first_page = await mcp_service.list_work(session, kind="case", limit=1)
        second_page = await mcp_service.list_work(
            session,
            kind="case",
            limit=1,
            cursor=first_page.next_cursor,
        )

    assert len(first_page.items) == 1
    assert first_page.next_cursor is not None
    assert first_page.total_count == 3
    assert len(second_page.items) == 1
    assert second_page.total_count == 3
