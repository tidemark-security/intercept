"""Add durable per-source MCP authorization capacity.

Revision ID: 023_mcp_auth_source_capacity
Revises: 022_passkey_login_abuse_controls
Create Date: 2026-08-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "023_mcp_auth_source_capacity"
down_revision: Union[str, None] = "022_passkey_login_abuse_controls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SOURCE_EXPIRY_INDEX = "ix_mcp_oauth_authorization_capacity_source_expiry"
TABLE_NAME = "mcp_oauth_authorization_capacity"


def _column_exists(column_name: str) -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = :table_name "
            "AND column_name = :column_name"
        ),
        {"table_name": TABLE_NAME, "column_name": column_name},
    )
    return result.fetchone() is not None


def _index_exists(index_name: str) -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = current_schema() "
            "AND tablename = :table_name "
            "AND indexname = :index_name"
        ),
        {"table_name": TABLE_NAME, "index_name": index_name},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    if not _column_exists("source_ip"):
        op.add_column(
            TABLE_NAME,
            sa.Column("source_ip", sa.String(length=64), nullable=True),
        )

    op.execute(
        sa.text(
            f"UPDATE {TABLE_NAME} "
            "SET source_ip = 'legacy-upgrade-023' "
            "WHERE source_ip IS NULL OR source_ip = ''"
        )
    )
    op.alter_column(
        TABLE_NAME,
        "source_ip",
        existing_type=sa.String(length=64),
        nullable=False,
    )

    if not _index_exists(SOURCE_EXPIRY_INDEX):
        op.create_index(
            SOURCE_EXPIRY_INDEX,
            TABLE_NAME,
            ["source_ip", "expires_at"],
            unique=False,
        )


def downgrade() -> None:
    if _index_exists(SOURCE_EXPIRY_INDEX):
        op.drop_index(SOURCE_EXPIRY_INDEX, table_name=TABLE_NAME)
    if _column_exists("source_ip"):
        op.drop_column(TABLE_NAME, "source_ip")
