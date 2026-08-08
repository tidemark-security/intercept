"""Upgrade compatibility tests for MCP OAuth causal epochs."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_mock_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import SQLModel

from app.models import models as _models  # noqa: F401


BACKEND_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    BACKEND_ROOT
    / "db_migrations"
    / "versions"
    / "026_mcp_oauth_causal_epochs.py"
)
INITIAL_MIGRATION_PATH = (
    BACKEND_ROOT
    / "db_migrations"
    / "versions"
    / "001_initial_schema.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mcp_oauth_causal_epoch_migration",
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


def _load_initial_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "initial_schema_migration_for_epoch_test",
        INITIAL_MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_baseline_filtered_metadata_does_not_create_epoch_sequence() -> None:
    """Fresh baseline schemas leave the post-baseline epoch sequence to 026."""

    initial_migration = _load_initial_migration()
    baseline_tables = [
        table
        for table in SQLModel.metadata.sorted_tables
        if table.name in initial_migration.BASELINE_TABLE_NAMES
    ]
    emitted_ddl: list[str] = []
    engine = create_mock_engine(
        "postgresql://",
        lambda statement, *args, **kwargs: emitted_ddl.append(
            str(statement.compile(dialect=engine.dialect))
        ),
    )

    SQLModel.metadata.create_all(engine, tables=baseline_tables)

    assert not any(
        "mcp_oauth_grant_epoch_seq" in statement for statement in emitted_ddl
    )


async def test_upgrade_orders_legacy_revocations_after_inflight_authorizations(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_mcp_causal_epoch_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.execute(
                text(
                    """
                    CREATE TABLE mcp_oauth_authorization_capacity (
                        reservation_id VARCHAR(128) PRIMARY KEY,
                        client_id VARCHAR(2048) NOT NULL,
                        provider_mode VARCHAR(32) NOT NULL,
                        source_ip VARCHAR(64) NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    CREATE TABLE mcp_oauth_consents (
                        id UUID PRIMARY KEY,
                        revoked_at TIMESTAMPTZ NULL
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
                        source_ip,
                        created_at,
                        expires_at
                    ) VALUES (
                        'legacy-inflight',
                        'legacy-client',
                        'oidc',
                        '127.0.0.1',
                        NOW(),
                        NOW() + INTERVAL '5 minutes'
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO mcp_oauth_consents (id, revoked_at) VALUES
                        (:active_id, NULL),
                        (:revoked_id, NOW())
                    """
                ),
                {"active_id": uuid4(), "revoked_id": uuid4()},
            )

            await connection.run_sync(_run_upgrade)
            await connection.run_sync(_run_upgrade)

            capacity_epoch = await connection.scalar(
                text(
                    "SELECT authorization_epoch "
                    "FROM mcp_oauth_authorization_capacity "
                    "WHERE reservation_id = 'legacy-inflight'"
                )
            )
            consent_rows = (
                await connection.execute(
                    text(
                        "SELECT revoked_at, last_authorization_epoch, "
                        "revocation_epoch FROM mcp_oauth_consents "
                        "ORDER BY revoked_at NULLS FIRST"
                    )
                )
            ).all()
            next_epoch = await connection.scalar(
                text("SELECT nextval('mcp_oauth_grant_epoch_seq')")
            )
            nullability = dict(
                (
                    await connection.execute(
                        text(
                            "SELECT column_name, is_nullable "
                            "FROM information_schema.columns "
                            "WHERE table_schema = :schema "
                            "AND table_name IN ("
                            "'mcp_oauth_authorization_capacity', "
                            "'mcp_oauth_consents'"
                            ") AND column_name IN ("
                            "'authorization_epoch', "
                            "'last_authorization_epoch'"
                            ")"
                        ),
                        {"schema": schema},
                    )
                ).all()
            )

        active_row, revoked_row = consent_rows
        assert capacity_epoch is not None and capacity_epoch > 0
        assert active_row.last_authorization_epoch == 0
        assert active_row.revocation_epoch is None
        assert revoked_row.last_authorization_epoch == 0
        assert revoked_row.revocation_epoch > capacity_epoch
        assert next_epoch > revoked_row.revocation_epoch
        assert nullability == {
            "authorization_epoch": "NO",
            "last_authorization_epoch": "NO",
        }
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_downgrade_preserves_epoch_high_water_for_reupgrade(
    async_engine: AsyncEngine,
) -> None:
    schema = f"t26_reup_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.execute(
                text(
                    """
                    CREATE TABLE mcp_oauth_authorization_capacity (
                        reservation_id VARCHAR(128) PRIMARY KEY,
                        client_id VARCHAR(2048) NOT NULL,
                        provider_mode VARCHAR(32) NOT NULL,
                        source_ip VARCHAR(64) NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    CREATE TABLE mcp_oauth_consents (
                        id UUID PRIMARY KEY,
                        revoked_at TIMESTAMPTZ NULL
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
                        source_ip,
                        created_at,
                        expires_at
                    ) VALUES (
                        'legacy-inflight',
                        'legacy-client',
                        'oidc',
                        '127.0.0.1',
                        NOW(),
                        NOW() + INTERVAL '5 minutes'
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO mcp_oauth_consents (id, revoked_at) "
                    "VALUES (:id, NOW())"
                ),
                {"id": uuid4()},
            )

            await connection.run_sync(_run_upgrade)
            high_water_before_downgrade = await connection.scalar(
                text("SELECT nextval('mcp_oauth_grant_epoch_seq')")
            )
            assert high_water_before_downgrade is not None

            await connection.run_sync(_run_downgrade)

            sequence_state = (
                await connection.execute(
                    text(
                        "SELECT last_value, is_called "
                        "FROM mcp_oauth_grant_epoch_seq"
                    )
                )
            ).one()
            remaining_epoch_columns = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = :schema "
                    "AND table_name IN ("
                    "'mcp_oauth_authorization_capacity', "
                    "'mcp_oauth_consents'"
                    ") AND column_name IN ("
                    "'authorization_epoch', "
                    "'last_authorization_epoch', "
                    "'revocation_epoch'"
                    ")"
                ),
                {"schema": schema},
            )

            assert sequence_state.last_value == high_water_before_downgrade
            assert sequence_state.is_called is True
            assert remaining_epoch_columns == 0

            await connection.run_sync(_run_upgrade)

            reupgraded_capacity_epoch = await connection.scalar(
                text(
                    "SELECT authorization_epoch "
                    "FROM mcp_oauth_authorization_capacity "
                    "WHERE reservation_id = 'legacy-inflight'"
                )
            )
            reupgraded_revocation_epoch = await connection.scalar(
                text(
                    "SELECT revocation_epoch FROM mcp_oauth_consents "
                    "WHERE revoked_at IS NOT NULL"
                )
            )
            next_epoch = await connection.scalar(
                text("SELECT nextval('mcp_oauth_grant_epoch_seq')")
            )

        assert reupgraded_capacity_epoch > high_water_before_downgrade
        assert reupgraded_revocation_epoch > reupgraded_capacity_epoch
        assert next_epoch > reupgraded_revocation_epoch
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )
