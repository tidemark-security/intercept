"""Upgrade compatibility tests for the account credential cutoff."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


BACKEND_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    BACKEND_ROOT
    / "db_migrations"
    / "versions"
    / "021_credential_invalidation_cutoff.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "credential_invalidation_cutoff_migration",
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


def _run_downgrade(sync_connection: Any) -> None:
    migration = _load_migration()
    migration.op = Operations(MigrationContext.configure(sync_connection))
    migration.downgrade()


async def test_upgrade_adds_cutoff_to_legacy_user_accounts_table(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_credential_cutoff_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(
                text(f"SET LOCAL search_path TO {quoted_schema}")
            )
            await connection.execute(
                text("CREATE TABLE user_accounts (id UUID PRIMARY KEY)")
            )
            await connection.run_sync(_run_upgrade)

            columns = set(
                (
                    await connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = :schema "
                            "AND table_name = 'user_accounts'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )
        assert columns == {"id", "credentials_invalidated_at"}
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_upgrade_is_noop_for_fresh_user_accounts_table(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_credential_cutoff_fresh_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(
                text(f"SET LOCAL search_path TO {quoted_schema}")
            )
            await connection.execute(
                text(
                    "CREATE TABLE user_accounts ("
                    "id UUID PRIMARY KEY, "
                    "credentials_invalidated_at TIMESTAMPTZ)"
                )
            )

            await connection.run_sync(_run_upgrade)
            await connection.run_sync(_run_upgrade)

            column_count = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = :schema "
                    "AND table_name = 'user_accounts' "
                    "AND column_name = 'credentials_invalidated_at'"
                ),
                {"schema": schema},
            )

        assert column_count == 1
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_downgrade_fails_closed_with_active_credential_cutoff(
    async_engine: AsyncEngine,
) -> None:
    schema = f"t21_guard_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    user_id = uuid4()
    cutoff = datetime(2026, 8, 8, 1, 2, 3, tzinfo=timezone.utc)
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(
                text(f"SET LOCAL search_path TO {quoted_schema}")
            )
            await connection.execute(
                text(
                    "CREATE TABLE user_accounts ("
                    "id UUID PRIMARY KEY, "
                    "credentials_invalidated_at TIMESTAMPTZ)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO user_accounts "
                    "(id, credentials_invalidated_at) VALUES (:id, :cutoff)"
                ),
                {"id": user_id, "cutoff": cutoff},
            )

            with pytest.raises(
                RuntimeError,
                match=(
                    r"Cannot downgrade 021_credential_cutoff.*"
                    r"credentials_invalidated_at contains non-NULL values"
                ),
            ):
                await connection.run_sync(_run_downgrade)

            stored_cutoff = await connection.scalar(
                text(
                    "SELECT credentials_invalidated_at FROM user_accounts "
                    "WHERE id = :id"
                ),
                {"id": user_id},
            )
            column_count = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = :schema "
                    "AND table_name = 'user_accounts' "
                    "AND column_name = 'credentials_invalidated_at'"
                ),
                {"schema": schema},
            )

        assert stored_cutoff == cutoff
        assert column_count == 1
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_downgrade_drops_unused_credential_cutoff_column(
    async_engine: AsyncEngine,
) -> None:
    schema = f"t21_empty_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    user_id = uuid4()
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(
                text(f"SET LOCAL search_path TO {quoted_schema}")
            )
            await connection.execute(
                text(
                    "CREATE TABLE user_accounts ("
                    "id UUID PRIMARY KEY, "
                    "credentials_invalidated_at TIMESTAMPTZ)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO user_accounts "
                    "(id, credentials_invalidated_at) VALUES (:id, NULL)"
                ),
                {"id": user_id},
            )

            await connection.run_sync(_run_downgrade)

            columns = set(
                (
                    await connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = :schema "
                            "AND table_name = 'user_accounts'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )
            stored_user_id = await connection.scalar(
                text("SELECT id FROM user_accounts WHERE id = :id"),
                {"id": user_id},
            )

        assert columns == {"id"}
        assert stored_user_id == user_id
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )
