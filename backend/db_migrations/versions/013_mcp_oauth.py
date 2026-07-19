"""Add MCP OAuth 2.1 persistence.

Revision ID: 013_mcp_oauth
Revises: 012_nhi_override_timestamps
Create Date: 2026-05-31
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "013_mcp_oauth"
down_revision: Union[str, None] = "012_nhi_override_timestamps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())

    if "mcp_oauth_clients" not in existing_tables:
        op.create_table(
            "mcp_oauth_clients",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("client_id", sa.String(length=2048), nullable=False),
            sa.Column("client_name", sa.String(length=200), nullable=False),
            sa.Column("client_uri", sa.String(length=2048), nullable=True),
            sa.Column("logo_uri", sa.String(length=2048), nullable=True),
            sa.Column("redirect_uris", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("scope", sa.String(length=255), nullable=False),
            sa.Column("grant_types", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("response_types", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("token_endpoint_auth_method", sa.String(length=64), nullable=False),
            sa.Column("contacts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("jwks_uri", sa.String(length=2048), nullable=True),
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_mcp_oauth_clients_id", "mcp_oauth_clients", ["id"], unique=False)
        op.create_index("ix_mcp_oauth_clients_client_id", "mcp_oauth_clients", ["client_id"], unique=True)

    if "mcp_oauth_consents" not in existing_tables:
        op.create_table(
            "mcp_oauth_consents",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("client_db_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("scope", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_authorized_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["client_db_id"], ["mcp_oauth_clients.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "client_db_id", "scope", name="uq_mcp_oauth_consent_user_client_scope"),
        )
        op.create_index("ix_mcp_oauth_consents_id", "mcp_oauth_consents", ["id"], unique=False)
        op.create_index("ix_mcp_oauth_consents_user_id", "mcp_oauth_consents", ["user_id"], unique=False)
        op.create_index("ix_mcp_oauth_consents_client_db_id", "mcp_oauth_consents", ["client_db_id"], unique=False)

    if "mcp_oauth_authorization_codes" not in existing_tables:
        op.create_table(
            "mcp_oauth_authorization_codes",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("code_hash", sa.String(length=128), nullable=False),
            sa.Column("client_db_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("redirect_uri", sa.String(length=2048), nullable=False),
            sa.Column("code_challenge", sa.String(length=256), nullable=False),
            sa.Column("code_challenge_method", sa.String(length=16), nullable=False),
            sa.Column("scope", sa.String(length=255), nullable=False),
            sa.Column("resource", sa.String(length=2048), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["client_db_id"], ["mcp_oauth_clients.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_mcp_oauth_authorization_codes_id", "mcp_oauth_authorization_codes", ["id"], unique=False)
        op.create_index("ix_mcp_oauth_authorization_codes_code_hash", "mcp_oauth_authorization_codes", ["code_hash"], unique=True)
        op.create_index("ix_mcp_oauth_authorization_codes_client_db_id", "mcp_oauth_authorization_codes", ["client_db_id"], unique=False)
        op.create_index("ix_mcp_oauth_authorization_codes_user_id", "mcp_oauth_authorization_codes", ["user_id"], unique=False)
        op.create_index("ix_mcp_oauth_authorization_codes_expires_at", "mcp_oauth_authorization_codes", ["expires_at"], unique=False)

    if "mcp_oauth_tokens" not in existing_tables:
        op.create_table(
            "mcp_oauth_tokens",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("token_type", sa.String(length=16), nullable=False),
            sa.Column("client_db_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("scope", sa.String(length=255), nullable=False),
            sa.Column("resource", sa.String(length=2048), nullable=False),
            sa.Column("refresh_token_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("rotated_from_token_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["client_db_id"], ["mcp_oauth_clients.id"]),
            sa.ForeignKeyConstraint(["refresh_token_id"], ["mcp_oauth_tokens.id"]),
            sa.ForeignKeyConstraint(["rotated_from_token_id"], ["mcp_oauth_tokens.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_mcp_oauth_tokens_id", "mcp_oauth_tokens", ["id"], unique=False)
        op.create_index("ix_mcp_oauth_tokens_token_hash", "mcp_oauth_tokens", ["token_hash"], unique=True)
        op.create_index("ix_mcp_oauth_tokens_client_db_id", "mcp_oauth_tokens", ["client_db_id"], unique=False)
        op.create_index("ix_mcp_oauth_tokens_user_id", "mcp_oauth_tokens", ["user_id"], unique=False)
        op.create_index("ix_mcp_oauth_tokens_refresh_token_id", "mcp_oauth_tokens", ["refresh_token_id"], unique=False)
        op.create_index("ix_mcp_oauth_tokens_expires_at", "mcp_oauth_tokens", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_mcp_oauth_tokens_expires_at", table_name="mcp_oauth_tokens")
    op.drop_index("ix_mcp_oauth_tokens_refresh_token_id", table_name="mcp_oauth_tokens")
    op.drop_index("ix_mcp_oauth_tokens_user_id", table_name="mcp_oauth_tokens")
    op.drop_index("ix_mcp_oauth_tokens_client_db_id", table_name="mcp_oauth_tokens")
    op.drop_index("ix_mcp_oauth_tokens_token_hash", table_name="mcp_oauth_tokens")
    op.drop_index("ix_mcp_oauth_tokens_id", table_name="mcp_oauth_tokens")
    op.drop_table("mcp_oauth_tokens")

    op.drop_index("ix_mcp_oauth_authorization_codes_expires_at", table_name="mcp_oauth_authorization_codes")
    op.drop_index("ix_mcp_oauth_authorization_codes_user_id", table_name="mcp_oauth_authorization_codes")
    op.drop_index("ix_mcp_oauth_authorization_codes_client_db_id", table_name="mcp_oauth_authorization_codes")
    op.drop_index("ix_mcp_oauth_authorization_codes_code_hash", table_name="mcp_oauth_authorization_codes")
    op.drop_index("ix_mcp_oauth_authorization_codes_id", table_name="mcp_oauth_authorization_codes")
    op.drop_table("mcp_oauth_authorization_codes")

    op.drop_index("ix_mcp_oauth_consents_client_db_id", table_name="mcp_oauth_consents")
    op.drop_index("ix_mcp_oauth_consents_user_id", table_name="mcp_oauth_consents")
    op.drop_index("ix_mcp_oauth_consents_id", table_name="mcp_oauth_consents")
    op.drop_table("mcp_oauth_consents")

    op.drop_index("ix_mcp_oauth_clients_client_id", table_name="mcp_oauth_clients")
    op.drop_index("ix_mcp_oauth_clients_id", table_name="mcp_oauth_clients")
    op.drop_table("mcp_oauth_clients")
