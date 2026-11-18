"""Migration coverage for global password-work capacity state."""

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
    / "027_password_verification_capacity.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "password_verification_capacity_migration",
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


def test_password_work_capacity_migration_follows_causal_epochs() -> None:
    migration = _load_migration()

    assert migration.revision == "027_password_verify_capacity"
    assert migration.down_revision == "026_mcp_oauth_causal_epochs"


async def test_downgrade_refuses_live_security_state_and_reupgrade_is_clean(
    async_engine: AsyncEngine,
) -> None:
    schema = f"t27_password_work_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    user_id = uuid4()
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.execute(
                text("CREATE TABLE user_accounts (id UUID PRIMARY KEY)")
            )
            await connection.run_sync(_run_upgrade)

            await connection.execute(
                text(
                    "INSERT INTO password_hash_work_leases "
                    "(id, work_kind, created_at, expires_at) "
                    "VALUES (:id, 'login_verify', NOW(), NOW() + INTERVAL '5 minutes')"
                ),
                {"id": uuid4()},
            )
            with pytest.raises(RuntimeError, match="active leases or pending failure"):
                await connection.run_sync(_run_downgrade)

            await connection.execute(text("DELETE FROM password_hash_work_leases"))
            await connection.execute(
                text("INSERT INTO user_accounts (id) VALUES (:id)"),
                {"id": user_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO password_login_failure_counters "
                    "(user_id, password_fingerprint, failed_attempts, updated_at) "
                    "VALUES (:user_id, :fingerprint, 3, NOW())"
                ),
                {"user_id": user_id, "fingerprint": "f" * 64},
            )
            with pytest.raises(RuntimeError, match="active leases or pending failure"):
                await connection.run_sync(_run_downgrade)

            await connection.execute(
                text("DELETE FROM password_login_failure_counters")
            )
            await connection.run_sync(_run_downgrade)
            await connection.run_sync(_run_upgrade)

            tables = set(
                (
                    await connection.execute(
                        text(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = :schema AND table_name IN "
                            "('password_hash_work_leases', "
                            "'password_login_failure_counters')"
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
                            "WHERE schemaname = :schema AND tablename = "
                            "'password_hash_work_leases'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )

        assert tables == {
            "password_hash_work_leases",
            "password_login_failure_counters",
        }
        assert "ix_password_hash_work_leases_expires_at" in indexes
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )
