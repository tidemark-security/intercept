"""Database-issued causal ordering for MCP authorization state changes."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import MCP_OAUTH_GRANT_EPOCH_SEQUENCE


async def next_mcp_oauth_grant_epoch(db: AsyncSession) -> int:
    """Allocate one worker-clock-independent authorization ordering value."""

    value = await db.scalar(select(MCP_OAUTH_GRANT_EPOCH_SEQUENCE.next_value()))
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError("Unable to allocate an MCP OAuth grant epoch")
    return value
