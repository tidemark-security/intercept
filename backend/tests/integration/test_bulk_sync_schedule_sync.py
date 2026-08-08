from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.enrichment.bulk_sync_schedule_sync import (
    _delete_superseded_bulk_sync_jobs,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("preserve_dedupe_key", "expected_removed", "expected_remaining"),
    [
        (None, 3, {"unrelated:job"}),
        (
            "bulk_sync_schedule:entra_id:20260809T020000Z",
            2,
            {
                "bulk_sync_schedule:entra_id:20260809T020000Z",
                "unrelated:job",
            },
        ),
    ],
)
async def test_superseded_bulk_sync_jobs_honor_nullable_preserve_key(
    session_maker: async_sessionmaker[AsyncSession],
    preserve_dedupe_key: str | None,
    expected_removed: int,
    expected_remaining: set[str],
) -> None:
    async with session_maker() as db:
        await db.execute(
            text(
                "CREATE TEMPORARY TABLE pgqueuer ("
                "entrypoint TEXT NOT NULL, "
                "dedupe_key TEXT, "
                "status TEXT NOT NULL"
                ") ON COMMIT DROP"
            )
        )
        await db.execute(
            text(
                "INSERT INTO pgqueuer (entrypoint, dedupe_key, status) VALUES "
                "('directory_sync', 'bulk_sync_schedule:entra_id', 'queued'), "
                "('directory_sync', 'bulk_sync_schedule:entra_id:20260809T010000Z', 'queued'), "
                "('directory_sync', 'bulk_sync_schedule:entra_id:20260809T020000Z', 'queued'), "
                "('directory_sync', 'unrelated:job', 'queued')"
            )
        )

        removed = await _delete_superseded_bulk_sync_jobs(
            db,
            "entra_id",
            preserve_dedupe_key=preserve_dedupe_key,
        )
        remaining = set(
            (
                await db.execute(
                    text("SELECT dedupe_key FROM pgqueuer ORDER BY dedupe_key")
                )
            ).scalars()
        )

        assert removed == expected_removed
        assert remaining == expected_remaining
