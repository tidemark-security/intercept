"""Add durable password-login abuse controls.

Revision ID: 024_password_login_abuse
Revises: 023_mcp_auth_source_capacity
Create Date: 2026-08-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "024_password_login_abuse"
down_revision: Union[str, None] = "023_mcp_auth_source_capacity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "password_login_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_password_login_attempts_source_created",
        "password_login_attempts",
        ["source_fingerprint", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_password_login_attempts_created_at",
        "password_login_attempts",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_login_attempts_created_at",
        table_name="password_login_attempts",
    )
    op.drop_index(
        "ix_password_login_attempts_source_created",
        table_name="password_login_attempts",
    )
    op.drop_table("password_login_attempts")
