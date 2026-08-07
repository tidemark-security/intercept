"""Upgrade compatibility tests for MCP authorization source capacity."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


BACKEND_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    BACKEND_ROOT
    / "db_migrations"
    / "versions"
    / "023_mcp_authorization_source_capacity.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mcp_authorization_source_capacity_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(sync_connection: Any) -> None:
    migration = _load_migration()
    migration.op = Operations(MigrationContext.configure(sync_connection))
    migration.upgrade()


async def test_upgrade_backfills_and_indexes_legacy_authorization_capacity(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_mcp_authorization_source_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(
                text(f"SET LOCAL search_path TO {quoted_schema}")
            )
            await connection.execute(
                text(
                    """
                    CREATE TABLE mcp_oauth_authorization_capacity (
                        reservation_id VARCHAR(128) PRIMARY KEY,
                        client_id VARCHAR(2048) NOT NULL,
                        provider_mode VARCHAR(32) NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO mcp_oauth_authorization_capacity (
                        reservation_id,
                        client_id,
                        provider_mode,
                        created_at,
                        expires_at
                    ) VALUES (
                        'legacy-reservation',
                        'legacy-client',
                        'local',
                        NOW(),
                        NOW() + INTERVAL '5 minutes'
                    )
                    """
                )
            )

            await connection.run_sync(_run_upgrade)
            await connection.run_sync(_run_upgrade)

            source_ip = await connection.scalar(
                text(
                    "SELECT source_ip FROM mcp_oauth_authorization_capacity "
                    "WHERE reservation_id = 'legacy-reservation'"
                )
            )
            nullable = await connection.scalar(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = :schema "
                    "AND table_name = 'mcp_oauth_authorization_capacity' "
                    "AND column_name = 'source_ip'"
                ),
                {"schema": schema},
            )
            index_definition = await connection.scalar(
                text(
                    """
                    SELECT pg_get_indexdef(index_class.oid)
                    FROM pg_class AS index_class
                    JOIN pg_namespace AS namespace
                      ON namespace.oid = index_class.relnamespace
                    WHERE namespace.nspname = :schema
                      AND index_class.relname =
                          'ix_mcp_oauth_authorization_capacity_source_expiry'
                    """
                ),
                {"schema": schema},
            )

        assert source_ip == "legacy-upgrade-023"
        assert nullable == "NO"
        assert index_definition is not None
        assert "(source_ip, expires_at)" in index_definition
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )
