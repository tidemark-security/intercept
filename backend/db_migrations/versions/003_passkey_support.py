"""Add passkey credential and WebAuthn challenge tables

Revision ID: 003_passkey_support
Revises: 002_pgcron_jobs
Create Date: 2026-02-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "003_passkey_support"
down_revision: Union[str, None] = "002_pgcron_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    """Check if a table already exists (e.g. created by metadata.create_all in 001)."""
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(index_name: str, table_name: str) -> bool:
    """Check if an index already exists on a table."""
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("passkey_credentials"):
        op.create_table(
            "passkey_credentials",
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("credential_id", sa.String(length=2048), nullable=False),
            sa.Column("credential_public_key", sa.String(length=8192), nullable=False),
            sa.Column("sign_count", sa.Integer(), nullable=False),
            sa.Column("transports", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("aaguid", sa.String(length=64), nullable=True),
            sa.Column("is_backup_eligible", sa.Boolean(), nullable=False),
            sa.Column("is_backed_up", sa.Boolean(), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_by_admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_accounts.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("credential_id", name="uq_passkey_credentials_credential_id"),
        )
    if not _index_exists("ix_passkey_credentials_id", "passkey_credentials"):
        op.create_index(op.f("ix_passkey_credentials_id"), "passkey_credentials", ["id"], unique=False)
    if not _index_exists("ix_passkey_credentials_user_id", "passkey_credentials"):
        op.create_index(op.f("ix_passkey_credentials_user_id"), "passkey_credentials", ["user_id"], unique=False)

    if not _table_exists("webauthn_challenges"):
        op.create_table(
            "webauthn_challenges",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("challenge", sa.String(length=512), nullable=False),
            sa.Column("flow_type", sa.String(length=32), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_accounts.id"), nullable=True),
            sa.Column("username", sa.String(length=64), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("challenge_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("ix_webauthn_challenges_challenge", "webauthn_challenges"):
        op.create_index(op.f("ix_webauthn_challenges_challenge"), "webauthn_challenges", ["challenge"], unique=False)
    if not _index_exists("ix_webauthn_challenges_expires_at", "webauthn_challenges"):
        op.create_index(op.f("ix_webauthn_challenges_expires_at"), "webauthn_challenges", ["expires_at"], unique=False)
    if not _index_exists("ix_webauthn_challenges_flow_type", "webauthn_challenges"):
        op.create_index(op.f("ix_webauthn_challenges_flow_type"), "webauthn_challenges", ["flow_type"], unique=False)
    if not _index_exists("ix_webauthn_challenges_id", "webauthn_challenges"):
        op.create_index(op.f("ix_webauthn_challenges_id"), "webauthn_challenges", ["id"], unique=False)
    if not _index_exists("ix_webauthn_challenges_user_id", "webauthn_challenges"):
        op.create_index(op.f("ix_webauthn_challenges_user_id"), "webauthn_challenges", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_webauthn_challenges_user_id"), table_name="webauthn_challenges")
    op.drop_index(op.f("ix_webauthn_challenges_id"), table_name="webauthn_challenges")
    op.drop_index(op.f("ix_webauthn_challenges_flow_type"), table_name="webauthn_challenges")
    op.drop_index(op.f("ix_webauthn_challenges_expires_at"), table_name="webauthn_challenges")
    op.drop_index(op.f("ix_webauthn_challenges_challenge"), table_name="webauthn_challenges")
    op.drop_table("webauthn_challenges")

    op.drop_index(op.f("ix_passkey_credentials_user_id"), table_name="passkey_credentials")
    op.drop_index(op.f("ix_passkey_credentials_id"), table_name="passkey_credentials")
    op.drop_table("passkey_credentials")
