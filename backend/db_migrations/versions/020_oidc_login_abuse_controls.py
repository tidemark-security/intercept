"""Add durable main-application OIDC login abuse controls.

Revision ID: 020_oidc_login_abuse_controls
Revises: 019_oidc_identity_pair
Create Date: 2026-08-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "020_oidc_login_abuse_controls"
down_revision: Union[str, None] = "019_oidc_identity_pair"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SOURCE_CREATED_INDEX = "ix_oidc_auth_requests_source_created"
CREATED_AT_INDEX = "ix_oidc_auth_requests_created_at"


def _source_fingerprint_column_exists() -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'oidc_auth_requests' "
            "AND column_name = 'source_fingerprint'"
        )
    )
    return result.fetchone() is not None


def _created_at_is_nullable() -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'oidc_auth_requests' "
            "AND column_name = 'created_at'"
        )
    )
    return result.scalar_one() == "YES"


def _index_exists(index_name: str) -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = current_schema() "
            "AND tablename = 'oidc_auth_requests' "
            "AND indexname = :index_name"
        ),
        {"index_name": index_name},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    if not _source_fingerprint_column_exists():
        op.add_column(
            "oidc_auth_requests",
            sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
        )
        op.execute(
            sa.text(
                "UPDATE oidc_auth_requests "
                "SET source_fingerprint = 'legacy-upgrade-020' "
                "WHERE source_fingerprint IS NULL"
            )
        )
        op.alter_column(
            "oidc_auth_requests",
            "source_fingerprint",
            nullable=False,
        )

    op.execute(
        sa.text(
            "UPDATE oidc_auth_requests "
            "SET created_at = CURRENT_TIMESTAMP "
            "WHERE created_at IS NULL"
        )
    )
    if _created_at_is_nullable():
        op.alter_column(
            "oidc_auth_requests",
            "created_at",
            nullable=False,
        )

    if not _index_exists(SOURCE_CREATED_INDEX):
        op.create_index(
            SOURCE_CREATED_INDEX,
            "oidc_auth_requests",
            ["source_fingerprint", "created_at"],
            unique=False,
        )
    if not _index_exists(CREATED_AT_INDEX):
        op.create_index(
            CREATED_AT_INDEX,
            "oidc_auth_requests",
            ["created_at"],
            unique=False,
        )


def downgrade() -> None:
    if _index_exists(CREATED_AT_INDEX):
        op.drop_index(
            CREATED_AT_INDEX,
            table_name="oidc_auth_requests",
        )
    if _index_exists(SOURCE_CREATED_INDEX):
        op.drop_index(
            SOURCE_CREATED_INDEX,
            table_name="oidc_auth_requests",
        )
    if _source_fingerprint_column_exists():
        op.drop_column("oidc_auth_requests", "source_fingerprint")
    if not _created_at_is_nullable():
        op.alter_column(
            "oidc_auth_requests",
            "created_at",
            nullable=True,
        )
