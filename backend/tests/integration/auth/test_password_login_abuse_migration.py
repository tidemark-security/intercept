"""Migration coverage for the durable password-login admission ledger."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from db_migrations.v0_6_0 import auth
from tests.fixtures.migrations import run_migration


async def test_password_login_abuse_migration_creates_ledger(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_password_login_abuse_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.run_sync(run_migration, auth.create_password_login_attempts)

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

    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )
