"""Create the v0.6.0 OAuth tables in their released form."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def create_native_store() -> None:
    # Native py-key-value-aio PostgreSQLStore contract (runtime auto_create=False).
    op.create_table(
        "fastmcp_oauth_kv",
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
        "idx_fastmcp_oauth_kv_expires_at",
        "fastmcp_oauth_kv",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )


def upgrade() -> None:
    # Rollback retains this sequence so previously issued epochs are never reused.
    op.execute("CREATE SEQUENCE IF NOT EXISTS mcp_oauth_grant_epoch_seq")
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

    op.create_table(
        "mcp_oauth_consents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_db_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_mode", sa.String(32), nullable=False, server_default="local"),
        sa.Column("provider_reference_hash", sa.String(128)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("last_authorization_epoch", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("revocation_epoch", sa.BigInteger()),
        sa.ForeignKeyConstraint(["client_db_id"], ["mcp_oauth_clients.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "client_db_id", "scope", name="uq_mcp_oauth_consent_user_client_scope"),
    )
    op.create_index("ix_mcp_oauth_consents_id", "mcp_oauth_consents", ["id"], unique=False)
    op.create_index("ix_mcp_oauth_consents_user_id", "mcp_oauth_consents", ["user_id"], unique=False)
    op.create_index("ix_mcp_oauth_consents_client_db_id", "mcp_oauth_consents", ["client_db_id"], unique=False)
    op.create_index("ix_mcp_oauth_consents_provider_reference", "mcp_oauth_consents", ["provider_mode", "provider_reference_hash"])

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

    create_native_store()

    op.create_table(
        "mcp_oauth_pending_authorizations",
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
        "mcp_oauth_pending_authorizations",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_oauth_pending_authorizations_client_db_id",
        "mcp_oauth_pending_authorizations",
        ["client_db_id"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_oauth_pending_authorizations_expires_at",
        "mcp_oauth_pending_authorizations",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "mcp_oauth_provider_grant_references",
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
        "mcp_oauth_provider_grant_references",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_oauth_provider_grant_references_consent_id",
        "mcp_oauth_provider_grant_references",
        ["consent_id"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_oauth_provider_grant_references_consent_active",
        "mcp_oauth_provider_grant_references",
        ["consent_id", "revoked_at"],
        unique=False,
    )

    op.create_table(
        "mcp_oauth_dcr_registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.String(length=2048), nullable=False),
        sa.Column("provider_mode", sa.String(length=32), nullable=False),
        sa.Column("source_ip", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
    )
    op.create_index(
        "ix_mcp_oauth_dcr_registrations_expiry",
        "mcp_oauth_dcr_registrations",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_oauth_dcr_registrations_source_created",
        "mcp_oauth_dcr_registrations",
        ["source_ip", "created_at"],
        unique=False,
    )
    op.create_table(
        "mcp_oauth_authorization_capacity",
        sa.Column("reservation_id", sa.String(length=128), nullable=False),
        sa.Column("client_id", sa.String(length=2048), nullable=False),
        sa.Column("provider_mode", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_ip", sa.String(64), nullable=False),
        sa.Column("authorization_epoch", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("reservation_id"),
    )
    op.create_index(
        "ix_mcp_oauth_authorization_capacity_expiry",
        "mcp_oauth_authorization_capacity",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_oauth_authorization_capacity_client_expiry",
        "mcp_oauth_authorization_capacity",
        ["client_id", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_oauth_authorization_capacity_source_expiry",
        "mcp_oauth_authorization_capacity",
        ["source_ip", "expires_at"],
    )


def downgrade() -> None:
    op.drop_table("mcp_oauth_authorization_capacity")
    op.drop_table("mcp_oauth_dcr_registrations")
    op.drop_table("mcp_oauth_provider_grant_references")
    op.drop_table("mcp_oauth_pending_authorizations")
    op.drop_table("fastmcp_oauth_kv")
    op.drop_table("mcp_oauth_tokens")
    op.drop_table("mcp_oauth_authorization_codes")
    op.drop_table("mcp_oauth_consents")
    op.drop_table("mcp_oauth_clients")
