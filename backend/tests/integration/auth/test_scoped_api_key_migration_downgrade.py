"""Fail-closed downgrade coverage for scoped API keys."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from db_migrations.v0_6_0 import auth
from tests.fixtures.migrations import run_migration


async def test_downgrade_fails_closed_with_existing_api_keys(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_key_guard_{uuid4().hex}"
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
                match=r"Cannot downgrade v0\.6\.0.*api_keys contains rows",
            ):
                await connection.run_sync(run_migration, auth.remove_key_scopes)

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


async def test_downgrade_drops_scopes_when_no_api_keys_exist(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_key_empty_{uuid4().hex}"
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

            await connection.run_sync(run_migration, auth.remove_key_scopes)

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
