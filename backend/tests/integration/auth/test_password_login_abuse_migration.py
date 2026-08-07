"""Migration coverage for the durable password-login admission ledger."""

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


MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "db_migrations"
    / "versions"
    / "024_password_login_abuse_controls.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "password_login_abuse_controls_migration",
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


def test_password_login_abuse_migration_follows_mcp_source_capacity() -> None:
    migration = _load_migration()

    assert migration.revision == "024_password_login_abuse"
    assert migration.down_revision == "023_mcp_auth_source_capacity"


async def test_password_login_abuse_migration_creates_and_removes_ledger(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_password_login_abuse_{uuid4().hex}"
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
                            "WHERE table_schema = :schema "
                            "AND table_name = 'password_login_attempts'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )
            indexes = set(
                (
                    await connection.execute(
                        text(
                            "SELECT indexname FROM pg_indexes "
                            "WHERE schemaname = :schema "
                            "AND tablename = 'password_login_attempts'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )

            assert columns == {"id", "source_fingerprint", "created_at"}
            assert {
                "ix_password_login_attempts_source_created",
                "ix_password_login_attempts_created_at",
            }.issubset(indexes)

            await connection.run_sync(_run_downgrade)
            table_exists = await connection.scalar(
                text(
                    "SELECT to_regclass(:qualified_name) IS NOT NULL"
                ),
                {"qualified_name": f"{schema}.password_login_attempts"},
            )
            assert table_exists is False
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )
