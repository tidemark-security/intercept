"""Upgrade compatibility tests for the durable MCP DCR ledger."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.services.mcp_registration_service import (
    MCPDCRRegistrationService,
    MCPRegistrationPolicy,
)


BACKEND_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    BACKEND_ROOT
    / "db_migrations"
    / "versions"
    / "017_mcp_dcr_abuse_controls.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mcp_dcr_abuse_controls_migration",
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


async def test_upgrade_backfills_pre017_local_and_oidc_clients(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_mcp_dcr_{uuid4().hex}"
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
                    CREATE TABLE mcp_oauth_clients (
                        id UUID PRIMARY KEY,
                        client_id TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMPTZ,
                        revoked_at TIMESTAMPTZ
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    CREATE TABLE fastmcp_oauth_kv (
                        collection TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value JSONB NOT NULL,
                        expires_at TIMESTAMPTZ,
                        PRIMARY KEY (collection, key)
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    CREATE TABLE mcp_oauth_tokens (
                        client_db_id UUID NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        revoked_at TIMESTAMPTZ
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    CREATE TABLE mcp_oauth_authorization_codes (
                        client_db_id UUID NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        consumed_at TIMESTAMPTZ
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO mcp_oauth_clients (
                        id,
                        client_id,
                        created_at,
                        revoked_at
                    )
                    VALUES (
                        '16ad90ad-4cf0-4c56-b4e2-9f39c44ca001',
                        'pre017-local-client',
                        NULL,
                        NULL
                    ), (
                        '16ad90ad-4cf0-4c56-b4e2-9f39c44ca002',
                        'revoked-pre017-local-client',
                        '2026-07-01T00:00:00Z',
                        '2026-07-02T00:00:00Z'
                    ), (
                        '16ad90ad-4cf0-4c56-b4e2-9f39c44ca003',
                        'https://cimd.example/client.json',
                        '2026-07-01T00:00:00Z',
                        NULL
                    ), (
                        '16ad90ad-4cf0-4c56-b4e2-9f39c44ca004',
                        'pre017-oidc-client',
                        '2026-07-01T00:00:00Z',
                        NULL
                    )
                    """
                )
            )
            local_grant_expiry = await connection.scalar(
                text("SELECT NOW() + INTERVAL '90 days'")
            )
            assert local_grant_expiry is not None
            await connection.execute(
                text(
                    """
                    INSERT INTO mcp_oauth_tokens (
                        client_db_id,
                        expires_at,
                        revoked_at
                    )
                    VALUES (
                        '16ad90ad-4cf0-4c56-b4e2-9f39c44ca001',
                        NOW() + INTERVAL '90 days',
                        NULL
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO fastmcp_oauth_kv (
                        collection,
                        key,
                        value,
                        expires_at
                    )
                    VALUES (
                        'mcp-oauth-proxy-clients',
                        'pre017-oidc-client',
                        '{}'::jsonb,
                        NULL
                    ), (
                        'mcp-oauth-proxy-clients',
                        'https://cimd.example/oidc-client.json',
                        '{}'::jsonb,
                        NULL
                    ), (
                        'mcp-oauth-proxy-clients',
                        'expired-pre017-oidc-client',
                        '{}'::jsonb,
                        '2026-07-01T00:00:00Z'
                    ), (
                        'mcp-refresh-tokens',
                        'encrypted-native-grant',
                        '{}'::jsonb,
                        NOW() + INTERVAL '90 days'
                    )
                    """
                )
            )
            oidc_grant_expiry = await connection.scalar(
                text(
                    """
                    SELECT expires_at
                    FROM fastmcp_oauth_kv
                    WHERE key = 'encrypted-native-grant'
                    """
                )
            )
            assert oidc_grant_expiry is not None

            await connection.run_sync(_run_upgrade)

        schema_engine = async_engine.execution_options(
            schema_translate_map={None: schema}
        )
        session_factory = async_sessionmaker(
            bind=schema_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        registration_service = MCPDCRRegistrationService(
            session_factory=session_factory,
            policy=MCPRegistrationPolicy(),
            now=lambda: datetime.now(timezone.utc),
        )

        assert await registration_service.require_valid("pre017-local-client")
        assert await registration_service.require_valid("pre017-oidc-client")
        async with async_engine.connect() as connection:
            adopted = dict(
                (
                    await connection.execute(
                        text(
                            f"""
                            SELECT client_id, provider_mode
                            FROM {quoted_schema}.mcp_oauth_dcr_registrations
                            """
                        )
                    )
                ).all()
            )
            assert adopted == {
                "pre017-local-client": "local",
                "pre017-oidc-client": "oidc",
            }
            lease_expiries = dict(
                (
                    await connection.execute(
                        text(
                            f"""
                            SELECT client_id, expires_at
                            FROM {quoted_schema}.mcp_oauth_dcr_registrations
                            """
                        )
                    )
                ).all()
            )
            assert lease_expiries["pre017-local-client"] >= local_grant_expiry
            assert lease_expiries["pre017-oidc-client"] >= oidc_grant_expiry
            oidc_cimd_projection_count = await connection.scalar(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM {quoted_schema}.fastmcp_oauth_kv
                    WHERE collection = 'mcp-oauth-proxy-clients'
                      AND key ~* '^https://'
                    """
                )
            )
            assert oidc_cimd_projection_count == 0
            authorization_capacity_count = await connection.scalar(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM {quoted_schema}.mcp_oauth_authorization_capacity
                    """
                )
            )
            assert authorization_capacity_count == 0
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )


async def test_downgrade_does_not_reconstruct_removed_cimd_projections(
    async_engine: AsyncEngine,
) -> None:
    schema = f"test_mcp_dcr_downgrade_{uuid4().hex}"
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
                    CREATE TABLE mcp_oauth_clients (
                        id UUID PRIMARY KEY,
                        client_id TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMPTZ,
                        revoked_at TIMESTAMPTZ
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    CREATE TABLE fastmcp_oauth_kv (
                        collection TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value JSONB NOT NULL,
                        expires_at TIMESTAMPTZ,
                        PRIMARY KEY (collection, key)
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    CREATE TABLE mcp_oauth_tokens (
                        client_db_id UUID NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        revoked_at TIMESTAMPTZ
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    CREATE TABLE mcp_oauth_authorization_codes (
                        client_db_id UUID NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        consumed_at TIMESTAMPTZ
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO fastmcp_oauth_kv (
                        collection,
                        key,
                        value,
                        expires_at
                    )
                    VALUES (
                        'mcp-oauth-proxy-clients',
                        'https://cimd.example/client.json',
                        '{}'::jsonb,
                        NULL
                    )
                    """
                )
            )

            await connection.run_sync(_run_upgrade)
            await connection.run_sync(_run_downgrade)

            registration_table = await connection.scalar(
                text("SELECT to_regclass('mcp_oauth_dcr_registrations')")
            )
            capacity_table = await connection.scalar(
                text("SELECT to_regclass('mcp_oauth_authorization_capacity')")
            )
            cimd_projection_count = await connection.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM fastmcp_oauth_kv
                    WHERE collection = 'mcp-oauth-proxy-clients'
                      AND key ~* '^https://'
                    """
                )
            )

        assert registration_table is None
        assert capacity_table is None
        assert cimd_projection_count == 0
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE")
            )
