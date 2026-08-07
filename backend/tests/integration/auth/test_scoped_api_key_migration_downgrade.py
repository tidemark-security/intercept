"""Fail-closed downgrade coverage for scoped API keys."""

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
    / "018_scoped_api_keys.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "scoped_api_keys_migration_downgrade",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_downgrade(sync_connection: Any) -> None:
    migration = _load_migration()
    migration.op = Operations(MigrationContext.configure(sync_connection))
    migration.downgrade()


async def test_018_downgrade_fails_closed_with_existing_api_keys(
    async_engine: AsyncEngine,
) -> None:
    schema = f"t18_guard_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    api_key_id = uuid4()
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(
                text(f"SET LOCAL search_path TO {quoted_schema}")
            )
            await connection.execute(
                text(
                    "CREATE TABLE api_keys ("
                    "id UUID PRIMARY KEY, scopes JSONB NOT NULL)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO api_keys (id, scopes) "
                    "VALUES (:id, '[\"api:read\"]'::jsonb)"
                ),
                {"id": api_key_id},
            )

            with pytest.raises(
                RuntimeError,
                match=r"Cannot downgrade 018_scoped_api_keys.*api_keys contains rows",
            ):
                await connection.run_sync(_run_downgrade)

            scopes = await connection.scalar(
                text("SELECT scopes FROM api_keys WHERE id = :id"),
                {"id": api_key_id},
            )
            column_count = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = :schema AND table_name = 'api_keys' "
                    "AND column_name = 'scopes'"
                ),
                {"schema": schema},
            )

        assert scopes == ["api:read"]
        assert column_count == 1
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_018_downgrade_drops_scopes_when_no_api_keys_exist(
    async_engine: AsyncEngine,
) -> None:
    schema = f"t18_empty_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(
                text(f"SET LOCAL search_path TO {quoted_schema}")
            )
            await connection.execute(
                text(
                    "CREATE TABLE api_keys ("
                    "id UUID PRIMARY KEY, scopes JSONB NOT NULL)"
                )
            )

            await connection.run_sync(_run_downgrade)

            column_count = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = :schema AND table_name = 'api_keys' "
                    "AND column_name = 'scopes'"
                ),
                {"schema": schema},
            )

        assert column_count == 0
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )
