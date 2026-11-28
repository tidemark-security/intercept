"""Schema-isolation coverage for incremental authentication migrations."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from db_migrations.v0_6_0 import auth
from tests.fixtures.migrations import run_migration


@pytest.mark.parametrize(
    ("role", "expected_scopes"),
    [
        ("ADMIN", ["api:admin", "api:read", "api:write", "mcp:access"]),
        ("ANALYST", ["api:read", "api:write", "mcp:access"]),
        ("AUDITOR", ["api:read", "mcp:access"]),
    ],
)
async def test_upgrade_backfills_legacy_key_scopes_to_owner_role_ceiling(
    async_engine: AsyncEngine,
    role: str,
    expected_scopes: list[str],
) -> None:
    schema = f"test_scoped_api_keys_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    user_id = uuid4()
    api_key_id = uuid4()
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.execute(
                text(
                    "CREATE TABLE user_accounts ("
                    "id UUID PRIMARY KEY, role TEXT NOT NULL)"
                )
            )
            await connection.execute(
                text(
                    "CREATE TABLE api_keys ("
                    "id UUID PRIMARY KEY, "
                    "user_id UUID NOT NULL REFERENCES user_accounts(id))"
                )
            )
            await connection.execute(
                text("INSERT INTO user_accounts (id, role) VALUES (:id, :role)"),
                {"id": user_id, "role": role},
            )
            await connection.execute(
                text("INSERT INTO api_keys (id, user_id) VALUES (:id, :user_id)"),
                {"id": api_key_id, "user_id": user_id},
            )

            await connection.run_sync(run_migration, auth.add_key_scopes)

            scopes = await connection.scalar(
                text("SELECT scopes FROM api_keys WHERE id = :id"),
                {"id": api_key_id},
            )
            nullable = await connection.scalar(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = :schema AND table_name = 'api_keys' "
                    "AND column_name = 'scopes'"
                ),
                {"schema": schema},
            )

        assert scopes == expected_scopes
        assert nullable == "NO"
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_api_key_scope_upgrade_is_noop_for_fresh_table(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_scoped_api_keys_fresh_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.execute(
                text(
                    "CREATE TABLE api_keys ("
                    "id UUID PRIMARY KEY, scopes JSONB NOT NULL)"
                )
            )

            await connection.run_sync(run_migration, auth.add_key_scopes)
            await connection.run_sync(run_migration, auth.add_key_scopes)

            column_count = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = :schema AND table_name = 'api_keys' "
                    "AND column_name = 'scopes'"
                ),
                {"schema": schema},
            )

        assert column_count == 1
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_upgrade_rejects_existing_ascii_whitespace_only_identities(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_oidc_identity_preflight_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    ascii_whitespace = " \t\n\r\f\v"
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.execute(
                text(
                    "CREATE TABLE user_accounts ("
                    "id UUID PRIMARY KEY, oidc_issuer TEXT, oidc_subject TEXT)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO user_accounts (id, oidc_issuer, oidc_subject) "
                    "VALUES (:issuer_id, :whitespace, 'provider-subject'), "
                    "(:subject_id, 'https://issuer.example', :whitespace)"
                ),
                {
                    "issuer_id": uuid4(),
                    "subject_id": uuid4(),
                    "whitespace": ascii_whitespace,
                },
            )

            with pytest.raises(
                RuntimeError,
                match=r"2 user account\(s\).*partial or blank OIDC identity",
            ):
                await connection.run_sync(run_migration, auth.add_oidc_identity_constraint)
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_constraint_rejects_ascii_whitespace_only_identities(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_oidc_identity_constraint_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    ascii_whitespace = " \t\n\r\f\v"
    invalid_pairs = (
        (ascii_whitespace, "provider-subject"),
        ("https://issuer.example", ascii_whitespace),
    )
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.execute(
                text(
                    "CREATE TABLE user_accounts ("
                    "id UUID PRIMARY KEY, oidc_issuer TEXT, oidc_subject TEXT)"
                )
            )

            await connection.run_sync(run_migration, auth.add_oidc_identity_constraint)

            for issuer, subject in invalid_pairs:
                with pytest.raises(IntegrityError):
                    async with connection.begin_nested():
                        await connection.execute(
                            text(
                                "INSERT INTO user_accounts "
                                "(id, oidc_issuer, oidc_subject) "
                                "VALUES (:id, :issuer, :subject)"
                            ),
                            {
                                "id": uuid4(),
                                "issuer": issuer,
                                "subject": subject,
                            },
                        )
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_upgrade_targets_legacy_table_in_current_schema(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_oidc_abuse_controls_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.execute(
                text(
                    "CREATE TABLE oidc_auth_requests ("
                    "id UUID PRIMARY KEY, created_at TIMESTAMPTZ)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO oidc_auth_requests (id, created_at) "
                    "VALUES (:id, NULL)"
                ),
                {"id": uuid4()},
            )

            await connection.run_sync(run_migration, auth.add_oidc_login_controls)

            source_fingerprint = await connection.scalar(
                text("SELECT source_fingerprint FROM oidc_auth_requests")
            )
            created_at = await connection.scalar(
                text("SELECT created_at FROM oidc_auth_requests")
            )
            nullability_result = await connection.execute(
                text(
                    "SELECT column_name, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = :schema "
                    "AND table_name = 'oidc_auth_requests' "
                    "AND column_name IN ('source_fingerprint', 'created_at')"
                ),
                {"schema": schema},
            )
            nullability = dict(nullability_result.tuples().all())
            indexes = set(
                (
                    await connection.execute(
                        text(
                            "SELECT indexname FROM pg_indexes "
                            "WHERE schemaname = :schema "
                            "AND tablename = 'oidc_auth_requests'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )

        assert source_fingerprint == "legacy-upgrade-020"
        assert created_at is not None
        assert nullability == {
            "created_at": "NO",
            "source_fingerprint": "NO",
        }
        assert {
            "ix_oidc_auth_requests_source_created",
            "ix_oidc_auth_requests_created_at",
        }.issubset(indexes)
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_downgrade_restores_nullable_created_at(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_oidc_down_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.execute(
                text(
                    "CREATE TABLE oidc_auth_requests ("
                    "id UUID PRIMARY KEY, created_at TIMESTAMPTZ)"
                )
            )

            await connection.run_sync(run_migration, auth.add_oidc_login_controls)
            await connection.run_sync(run_migration, auth.remove_oidc_login_controls)

            nullable = await connection.scalar(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = :schema "
                    "AND table_name = 'oidc_auth_requests' "
                    "AND column_name = 'created_at'"
                ),
                {"schema": schema},
            )

        assert nullable == "YES"
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_upgrade_creates_missing_indexes_when_column_exists(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_oidc_partial_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.execute(
                text(
                    "CREATE TABLE oidc_auth_requests ("
                    "id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL, "
                    "source_fingerprint VARCHAR(64) NOT NULL)"
                )
            )

            await connection.run_sync(run_migration, auth.add_oidc_login_controls)

            indexes = set(
                (
                    await connection.execute(
                        text(
                            "SELECT indexname FROM pg_indexes "
                            "WHERE schemaname = :schema "
                            "AND tablename = 'oidc_auth_requests'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )

        assert {
            "ix_oidc_auth_requests_source_created",
            "ix_oidc_auth_requests_created_at",
        }.issubset(indexes)
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


@pytest.mark.parametrize(
    ("existing_index_name", "existing_index_columns"),
    [
        (
            "ix_oidc_auth_requests_source_created",
            "source_fingerprint, created_at",
        ),
        ("ix_oidc_auth_requests_created_at", "created_at"),
    ],
)
async def test_upgrade_creates_each_index_independently(
    async_engine: AsyncEngine,
    existing_index_name: str,
    existing_index_columns: str,
) -> None:
    schema = f"test_oidc_one_index_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.execute(
                text(
                    "CREATE TABLE oidc_auth_requests ("
                    "id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL, "
                    "source_fingerprint VARCHAR(64) NOT NULL)"
                )
            )
            await connection.execute(
                text(
                    f"CREATE INDEX {existing_index_name} "
                    f"ON oidc_auth_requests ({existing_index_columns})"
                )
            )

            await connection.run_sync(run_migration, auth.add_oidc_login_controls)

            indexes = set(
                (
                    await connection.execute(
                        text(
                            "SELECT indexname FROM pg_indexes "
                            "WHERE schemaname = :schema "
                            "AND tablename = 'oidc_auth_requests'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )

        assert {
            "ix_oidc_auth_requests_source_created",
            "ix_oidc_auth_requests_created_at",
        }.issubset(indexes)
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_oidc_login_controls_upgrade_is_noop_for_fresh_table(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_oidc_abuse_controls_fresh_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.execute(
                text(
                    "CREATE TABLE oidc_auth_requests ("
                    "id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL, "
                    "source_fingerprint VARCHAR(64) NOT NULL)"
                )
            )
            await connection.execute(
                text(
                    "CREATE INDEX ix_oidc_auth_requests_source_created "
                    "ON oidc_auth_requests (source_fingerprint, created_at)"
                )
            )
            await connection.execute(
                text(
                    "CREATE INDEX ix_oidc_auth_requests_created_at "
                    "ON oidc_auth_requests (created_at)"
                )
            )

            await connection.run_sync(run_migration, auth.add_oidc_login_controls)
            await connection.run_sync(run_migration, auth.add_oidc_login_controls)

            column_count = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = :schema "
                    "AND table_name = 'oidc_auth_requests' "
                    "AND column_name = 'source_fingerprint'"
                ),
                {"schema": schema},
            )

        assert column_count == 1
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_upgrade_adds_passkey_login_ledger_columns_and_indexes(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_passkey_abuse_controls_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.execute(
                text(
                    "CREATE TABLE webauthn_challenges ("
                    "id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL)"
                )
            )

            await connection.run_sync(run_migration, auth.add_passkey_controls)

            columns = set(
                (
                    await connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = :schema "
                            "AND table_name = 'webauthn_challenges'"
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
                            "AND tablename = 'webauthn_challenges'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )

        assert {"source_fingerprint", "user_fingerprint"}.issubset(columns)
        assert {
            "ix_webauthn_challenges_source_created",
            "ix_webauthn_challenges_user_fingerprint_created",
        }.issubset(indexes)
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_upgrade_is_noop_for_fresh_passkey_challenge_table(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_passkey_fresh_{uuid4().hex}"
    quoted_schema = f'"{schema}"'
    try:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {quoted_schema}"))
            await connection.execute(
                text(
                    "CREATE TABLE webauthn_challenges ("
                    "id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL, "
                    "source_fingerprint VARCHAR(64), "
                    "user_fingerprint VARCHAR(64))"
                )
            )
            await connection.execute(
                text(
                    "CREATE INDEX ix_webauthn_challenges_source_created "
                    "ON webauthn_challenges (source_fingerprint, created_at)"
                )
            )
            await connection.execute(
                text(
                    "CREATE INDEX ix_webauthn_challenges_user_fingerprint_created "
                    "ON webauthn_challenges (user_fingerprint, created_at)"
                )
            )

            await connection.run_sync(run_migration, auth.add_passkey_controls)
            await connection.run_sync(run_migration, auth.add_passkey_controls)

            fingerprint_column_count = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = :schema "
                    "AND table_name = 'webauthn_challenges' "
                    "AND column_name IN ('source_fingerprint', 'user_fingerprint')"
                ),
                {"schema": schema},
            )

        assert fingerprint_column_count == 2
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )
