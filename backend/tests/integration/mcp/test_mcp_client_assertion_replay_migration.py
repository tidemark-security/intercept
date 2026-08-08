"""PostgreSQL schema coverage for the MCP assertion replay ledger migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "db_migrations"
    / "versions"
    / "028_mcp_client_assertion_replay.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mcp_client_assertion_replay_schema_migration",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.schedule_cron_job = lambda **kwargs: None
    module.unschedule_cron_job = lambda **kwargs: None
    return module


def _run_upgrade(sync_connection: Any) -> None:
    migration = _load_migration()
    migration.op = Operations(MigrationContext.configure(sync_connection))
    migration.upgrade()


def _run_downgrade(sync_connection: Any) -> None:
    migration = _load_migration()
    migration.op = Operations(MigrationContext.configure(sync_connection))
    migration.downgrade()


async def test_migration_schema_downgrade_guard_and_reupgrade(
    async_engine: AsyncEngine,
) -> None:
    schema = f"t28_mcp_assertion_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.run_sync(_run_upgrade)

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
                await connection.run_sync(_run_downgrade)

            await connection.execute(
                text("DELETE FROM mcp_oauth_client_assertion_jtis")
            )
            await connection.run_sync(_run_downgrade)
            await connection.run_sync(_run_upgrade)
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )
