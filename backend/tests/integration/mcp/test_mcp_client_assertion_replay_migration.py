"""PostgreSQL schema coverage for the MCP assertion replay ledger migration."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from db_migrations.v0_6_0 import assertion_replay
from tests.fixtures.migrations import run_migration


async def test_migration_schema_downgrade_guard_and_reupgrade(
    async_engine: AsyncEngine,
    monkeypatch,
) -> None:
    monkeypatch.setattr(assertion_replay, "schedule_cron_job", lambda **kwargs: None)
    monkeypatch.setattr(assertion_replay, "unschedule_cron_job", lambda **kwargs: None)
    schema = f"test_mcp_assertion_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.run_sync(run_migration, assertion_replay.upgrade)

            columns = set(
                (
                    await connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = :schema AND table_name = "
                            "'mcp_oauth_client_assertion_jtis'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )
            indexes = set(
                (
                    await connection.execute(
                        text(
                            "SELECT indexname FROM pg_indexes WHERE schemaname = "
                            ":schema AND tablename = 'mcp_oauth_client_assertion_jtis'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )
            assert columns == {
                "client_id_hash",
                "jti_hash",
                "created_at",
                "expires_at",
            }
            assert "mcp_oauth_client_assertion_jtis_pkey" in indexes
            assert "ix_mcp_oauth_client_assertion_jtis_expires_at" in indexes

            await connection.execute(
                text(
                    "INSERT INTO mcp_oauth_client_assertion_jtis "
                    "(client_id_hash, jti_hash, created_at, expires_at) VALUES "
                    "(:client_hash, :jti_hash, clock_timestamp(), "
                    "clock_timestamp() + INTERVAL '5 minutes')"
                ),
                {"client_hash": "c" * 64, "jti_hash": "j" * 64},
            )
            with pytest.raises(RuntimeError, match="unexpired claims"):
                await connection.run_sync(run_migration, assertion_replay.downgrade)

            await connection.execute(
                text("DELETE FROM mcp_oauth_client_assertion_jtis")
            )
            await connection.run_sync(run_migration, assertion_replay.downgrade)
            await connection.run_sync(run_migration, assertion_replay.upgrade)
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )
