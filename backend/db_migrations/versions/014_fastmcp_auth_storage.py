"""Add native FastMCP auth storage and local authorization handoffs.

Revision ID: 014_fastmcp_auth_storage
Revises: 013_mcp_oauth
Create Date: 2026-07-19
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "014_fastmcp_auth_storage"
down_revision: Union[str, None] = "013_mcp_oauth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FASTMCP_STORAGE_TABLE = "fastmcp_oauth_kv"
FASTMCP_EXPIRY_INDEX = "idx_fastmcp_oauth_kv_expires_at"
PENDING_AUTHORIZATION_TABLE = "mcp_oauth_pending_authorizations"
PROVIDER_REFERENCE_INDEX = "ix_mcp_oauth_consents_provider_reference"
PROVIDER_GRANT_REFERENCE_TABLE = "mcp_oauth_provider_grant_references"


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # This schema is the native py-key-value-aio 0.4.4 PostgreSQLStore
    # contract. Keep it Alembic-managed and construct the runtime store with
    # auto_create=False so application credentials never need DDL privileges.
    if FASTMCP_STORAGE_TABLE not in existing_tables:
        op.create_table(
            FASTMCP_STORAGE_TABLE,
            sa.Column("collection", sa.Text(), nullable=False),
            sa.Column("key", sa.Text(), nullable=False),
            sa.Column(
                "value",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column("ttl", sa.Double(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("collection", "key"),
        )
        op.create_index(
            FASTMCP_EXPIRY_INDEX,
            FASTMCP_STORAGE_TABLE,
            ["expires_at"],
            unique=False,
            postgresql_where=sa.text("expires_at IS NOT NULL"),
        )

    if PENDING_AUTHORIZATION_TABLE not in existing_tables:
        op.create_table(
            PENDING_AUTHORIZATION_TABLE,
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("client_db_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("state", sa.String(length=2048), nullable=True),
            sa.Column(
                "scopes",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column("code_challenge", sa.String(length=256), nullable=False),
            sa.Column("redirect_uri", sa.String(length=2048), nullable=False),
            sa.Column(
                "redirect_uri_provided_explicitly",
                sa.Boolean(),
                nullable=False,
            ),
            sa.Column("resource", sa.String(length=2048), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["client_db_id"],
                ["mcp_oauth_clients.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_mcp_oauth_pending_authorizations_id",
            PENDING_AUTHORIZATION_TABLE,
            ["id"],
            unique=False,
        )
        op.create_index(
            "ix_mcp_oauth_pending_authorizations_client_db_id",
            PENDING_AUTHORIZATION_TABLE,
            ["client_db_id"],
            unique=False,
        )
        op.create_index(
            "ix_mcp_oauth_pending_authorizations_expires_at",
            PENDING_AUTHORIZATION_TABLE,
            ["expires_at"],
            unique=False,
        )

    if "mcp_oauth_consents" in existing_tables:
        consent_columns = _column_names(inspector, "mcp_oauth_consents")
        if "provider_mode" not in consent_columns:
            op.add_column(
                "mcp_oauth_consents",
                sa.Column(
                    "provider_mode",
                    sa.String(length=32),
                    nullable=False,
                    server_default="local",
                ),
            )
        if "provider_reference_hash" not in consent_columns:
            op.add_column(
                "mcp_oauth_consents",
                sa.Column(
                    "provider_reference_hash",
                    sa.String(length=128),
                    nullable=True,
                ),
            )
        if "last_used_at" not in consent_columns:
            op.add_column(
                "mcp_oauth_consents",
                sa.Column(
                    "last_used_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                ),
            )

        if PROVIDER_REFERENCE_INDEX not in _index_names(inspector, "mcp_oauth_consents"):
            op.create_index(
                PROVIDER_REFERENCE_INDEX,
                "mcp_oauth_consents",
                ["provider_mode", "provider_reference_hash"],
                unique=False,
            )

    if PROVIDER_GRANT_REFERENCE_TABLE not in existing_tables:
        op.create_table(
            PROVIDER_GRANT_REFERENCE_TABLE,
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("consent_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "provider_reference_hash",
                sa.String(length=128),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["consent_id"], ["mcp_oauth_consents.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "provider_reference_hash",
                name="uq_mcp_oauth_provider_grant_reference_hash",
            ),
        )
        op.create_index(
            "ix_mcp_oauth_provider_grant_references_id",
            PROVIDER_GRANT_REFERENCE_TABLE,
            ["id"],
            unique=False,
        )
        op.create_index(
            "ix_mcp_oauth_provider_grant_references_consent_id",
            PROVIDER_GRANT_REFERENCE_TABLE,
            ["consent_id"],
            unique=False,
        )
        op.create_index(
            "ix_mcp_oauth_provider_grant_references_consent_active",
            PROVIDER_GRANT_REFERENCE_TABLE,
            ["consent_id", "revoked_at"],
            unique=False,
        )

    # The pre-native credentials cannot be interpreted safely by FastMCP.
    # Preserve their rows for audit while making every live grant unusable.
    if "mcp_oauth_tokens" in existing_tables:
        op.execute(
            "UPDATE mcp_oauth_tokens "
            "SET revoked_at = COALESCE(revoked_at, NOW()) "
            "WHERE revoked_at IS NULL"
        )
    if "mcp_oauth_authorization_codes" in existing_tables:
        op.execute(
            "UPDATE mcp_oauth_authorization_codes "
            "SET consumed_at = COALESCE(consumed_at, NOW()) "
            "WHERE consumed_at IS NULL"
        )
    if "mcp_oauth_consents" in existing_tables:
        op.execute(
            "UPDATE mcp_oauth_consents "
            "SET revoked_at = COALESCE(revoked_at, NOW()) "
            "WHERE revoked_at IS NULL"
        )


def downgrade() -> None:
    # Revoking experimental credentials is intentionally irreversible.
    op.drop_index(
        "ix_mcp_oauth_provider_grant_references_consent_active",
        table_name=PROVIDER_GRANT_REFERENCE_TABLE,
    )
    op.drop_index(
        "ix_mcp_oauth_provider_grant_references_consent_id",
        table_name=PROVIDER_GRANT_REFERENCE_TABLE,
    )
    op.drop_index(
        "ix_mcp_oauth_provider_grant_references_id",
        table_name=PROVIDER_GRANT_REFERENCE_TABLE,
    )
    op.drop_table(PROVIDER_GRANT_REFERENCE_TABLE)

    op.drop_index(
        PROVIDER_REFERENCE_INDEX,
        table_name="mcp_oauth_consents",
    )
    op.drop_column("mcp_oauth_consents", "last_used_at")
    op.drop_column("mcp_oauth_consents", "provider_reference_hash")
    op.drop_column("mcp_oauth_consents", "provider_mode")

    op.drop_index(
        "ix_mcp_oauth_pending_authorizations_expires_at",
        table_name=PENDING_AUTHORIZATION_TABLE,
    )
    op.drop_index(
        "ix_mcp_oauth_pending_authorizations_client_db_id",
        table_name=PENDING_AUTHORIZATION_TABLE,
    )
    op.drop_index(
        "ix_mcp_oauth_pending_authorizations_id",
        table_name=PENDING_AUTHORIZATION_TABLE,
    )
    op.drop_table(PENDING_AUTHORIZATION_TABLE)

    op.drop_index(FASTMCP_EXPIRY_INDEX, table_name=FASTMCP_STORAGE_TABLE)
    op.drop_table(FASTMCP_STORAGE_TABLE)
