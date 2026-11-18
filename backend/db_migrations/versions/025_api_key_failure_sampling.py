"""Add durable sampling for rejected API-key authentication attempts.

Revision ID: 025_api_key_failure_sampling
Revises: 024_password_login_abuse
Create Date: 2026-08-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "025_api_key_failure_sampling"
down_revision: Union[str, None] = "024_password_login_abuse"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_key_failure_samples",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("failure_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_api_key_failure_samples_source_created",
        "api_key_failure_samples",
        ["source_fingerprint", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_api_key_failure_samples_failure_created",
        "api_key_failure_samples",
        ["failure_fingerprint", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_api_key_failure_samples_created_at",
        "api_key_failure_samples",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_api_key_failure_samples_created_at",
        table_name="api_key_failure_samples",
    )
    op.drop_index(
        "ix_api_key_failure_samples_failure_created",
        table_name="api_key_failure_samples",
    )
    op.drop_index(
        "ix_api_key_failure_samples_source_created",
        table_name="api_key_failure_samples",
    )
    op.drop_table("api_key_failure_samples")
