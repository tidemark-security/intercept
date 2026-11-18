from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.fernet import Fernet
from key_value.aio.stores.postgresql import PostgreSQLStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine


BACKEND_ROOT = Path(__file__).resolve().parents[3]
TABLE_NAME = "fastmcp_oauth_kv"


def _load_storage_migration():
    migration_path = BACKEND_ROOT / "db_migrations" / "versions" / "014_fastmcp_auth_storage.py"
    spec = importlib.util.spec_from_file_location("fastmcp_auth_storage_migration", migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(sync_connection: Any) -> None:
    migration = _load_storage_migration()
    migration.op = Operations(MigrationContext.configure(sync_connection))
    migration.upgrade()


def _assert_native_schema(sync_connection: Any) -> None:
    inspector = inspect(sync_connection)
    columns = {column["name"]: column for column in inspector.get_columns(TABLE_NAME)}
    primary_key = inspector.get_pk_constraint(TABLE_NAME)
    indexes = {index["name"]: index for index in inspector.get_indexes(TABLE_NAME)}

    assert set(columns) == {
        "collection",
        "key",
        "value",
        "ttl",
        "created_at",
        "expires_at",
    }
    assert columns["collection"]["nullable"] is False
    assert columns["key"]["nullable"] is False
    assert columns["value"]["nullable"] is False
    assert primary_key["constrained_columns"] == ["collection", "key"]
    assert indexes["idx_fastmcp_oauth_kv_expires_at"]["column_names"] == ["expires_at"]
    assert "expires_at IS NOT NULL" in str(
        indexes["idx_fastmcp_oauth_kv_expires_at"]["dialect_options"]["postgresql_where"]
    )

    pending_columns = {
        column["name"]
        for column in inspector.get_columns("mcp_oauth_pending_authorizations")
    }
    assert pending_columns == {
        "id",
        "client_db_id",
        "state",
        "scopes",
        "code_challenge",
        "redirect_uri",
        "redirect_uri_provided_explicitly",
        "resource",
        "expires_at",
        "consumed_at",
        "created_at",
    }
    assert {
        index["name"]
        for index in inspector.get_indexes("mcp_oauth_pending_authorizations")
    } >= {
        "ix_mcp_oauth_pending_authorizations_id",
        "ix_mcp_oauth_pending_authorizations_client_db_id",
        "ix_mcp_oauth_pending_authorizations_expires_at",
    }

    consent_columns = {
        column["name"]: column
        for column in inspector.get_columns("mcp_oauth_consents")
    }
    assert consent_columns["provider_mode"]["nullable"] is False
    assert consent_columns["provider_reference_hash"]["nullable"] is True
    assert consent_columns["last_used_at"]["nullable"] is True
    assert "ix_mcp_oauth_consents_provider_reference" in {
        index["name"] for index in inspector.get_indexes("mcp_oauth_consents")
    }

    provider_reference_columns = {
        column["name"]
        for column in inspector.get_columns("mcp_oauth_provider_grant_references")
    }
    assert provider_reference_columns == {
        "id",
        "consent_id",
        "provider_reference_hash",
        "created_at",
        "last_used_at",
        "revoked_at",
    }


async def test_migration_provisions_native_encrypted_postgresql_store(async_engine: AsyncEngine) -> None:
    async with async_engine.begin() as connection:
        await connection.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME}"))
        await connection.execute(text("DROP TABLE IF EXISTS mcp_oauth_pending_authorizations"))
        await connection.run_sync(_run_upgrade)
        await connection.run_sync(_assert_native_schema)

    store_url = async_engine.url.render_as_string(hide_password=False).replace(
        "postgresql+asyncpg://",
        "postgresql://",
    )
    postgres_store = PostgreSQLStore(
        url=store_url,
        table_name=TABLE_NAME,
        auto_create=False,
    )
    encrypted_store = FernetEncryptionWrapper(
        postgres_store,
        fernet=Fernet(Fernet.generate_key()),
    )
    secret = "upstream-access-token-must-not-be-plaintext"

    try:
        async with postgres_store:
            await encrypted_store.put(
                "client-registration",
                {"upstream_access_token": secret, "client_id": "vscode"},
                collection="oauth",
                ttl=300,
            )
            assert await encrypted_store.get(
                "client-registration",
                collection="oauth",
            ) == {"upstream_access_token": secret, "client_id": "vscode"}

        async with async_engine.connect() as connection:
            stored_value = await connection.scalar(
                text(
                    f"SELECT value::text FROM {TABLE_NAME} "
                    "WHERE collection = 'oauth' AND key = 'client-registration'"
                )
            )
        assert stored_value is not None
        assert secret not in stored_value
        assert "__encrypted_data__" in stored_value
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME}"))
