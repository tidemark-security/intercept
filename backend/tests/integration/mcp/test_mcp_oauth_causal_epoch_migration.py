"""Upgrade compatibility tests for MCP OAuth causal epochs."""

from __future__ import annotations

from importlib import import_module
from uuid import uuid4

from sqlalchemy import create_mock_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import SQLModel

from app.models import models as _models  # noqa: F401
from db_migrations.v0_6_0 import oauth
from tests.fixtures.migrations import run_migration


def test_baseline_filtered_metadata_does_not_create_epoch_sequence() -> None:
    """Fresh baseline schemas leave the epoch sequence to the release migration."""

    initial_migration = import_module("db_migrations.versions.001_initial_schema")
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


async def test_oauth_schema_and_epoch_high_water_survive_reupgrade(async_engine: AsyncEngine) -> None:
    schema = f"test_release_oauth_{uuid4().hex}"
    async with async_engine.connect() as connection:
        # Rollback on connection close discards this private schema.
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        await connection.execute(text("CREATE TABLE user_accounts (id uuid PRIMARY KEY)"))
        await connection.run_sync(run_migration, oauth.upgrade)
        issued = await connection.scalar(text("SELECT nextval('mcp_oauth_grant_epoch_seq')"))
        await connection.run_sync(run_migration, oauth.downgrade)
        await connection.run_sync(run_migration, oauth.upgrade)
        assert await connection.scalar(text("SELECT nextval('mcp_oauth_grant_epoch_seq')")) > issued
        columns = dict((await connection.execute(text("""
            SELECT column_name, is_nullable FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'mcp_oauth_authorization_capacity'
        """))).all())
        assert columns["source_ip"] == "NO"
        assert columns["authorization_epoch"] == "NO"
        index = await connection.scalar(text("""
            SELECT pg_get_indexdef('ix_mcp_oauth_authorization_capacity_source_expiry'::regclass)
        """))
        assert "(source_ip, expires_at)" in index
