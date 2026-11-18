"""Add durable passkey authentication initiation abuse controls.

Revision ID: 022_passkey_login_abuse_controls
Revises: 021_credential_cutoff
Create Date: 2026-08-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "022_passkey_login_abuse_controls"
down_revision: Union[str, None] = "021_credential_cutoff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SOURCE_CREATED_INDEX = "ix_webauthn_challenges_source_created"
USER_CREATED_INDEX = "ix_webauthn_challenges_user_fingerprint_created"


def _column_exists(column_name: str) -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'webauthn_challenges' "
            "AND column_name = :column_name"
        ),
        {"column_name": column_name},
    )
    return result.fetchone() is not None


def _index_exists(index_name: str) -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = current_schema() "
            "AND tablename = 'webauthn_challenges' "
            "AND indexname = :index_name"
        ),
        {"index_name": index_name},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    if not _column_exists("source_fingerprint"):
        op.add_column(
            "webauthn_challenges",
            sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
        )
    if not _column_exists("user_fingerprint"):
        op.add_column(
            "webauthn_challenges",
            sa.Column("user_fingerprint", sa.String(length=64), nullable=True),
        )

    if not _index_exists(SOURCE_CREATED_INDEX):
        op.create_index(
            SOURCE_CREATED_INDEX,
            "webauthn_challenges",
            ["source_fingerprint", "created_at"],
            unique=False,
        )
    if not _index_exists(USER_CREATED_INDEX):
        op.create_index(
            USER_CREATED_INDEX,
            "webauthn_challenges",
            ["user_fingerprint", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    if _index_exists(USER_CREATED_INDEX):
        op.drop_index(USER_CREATED_INDEX, table_name="webauthn_challenges")
    if _index_exists(SOURCE_CREATED_INDEX):
        op.drop_index(SOURCE_CREATED_INDEX, table_name="webauthn_challenges")
    if _column_exists("user_fingerprint"):
        op.drop_column("webauthn_challenges", "user_fingerprint")
    if _column_exists("source_fingerprint"):
        op.drop_column("webauthn_challenges", "source_fingerprint")
