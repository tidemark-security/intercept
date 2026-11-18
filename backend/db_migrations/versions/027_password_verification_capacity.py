"""Bound concurrent password verification and serialize failure accounting.

Revision ID: 027_password_verify_capacity
Revises: 026_mcp_oauth_causal_epochs
Create Date: 2026-08-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "027_password_verify_capacity"
down_revision: Union[str, None] = "026_mcp_oauth_causal_epochs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "password_hash_work_leases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_kind", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_password_hash_work_leases_expires_at",
        "password_hash_work_leases",
        ["expires_at"],
        unique=False,
    )
    op.create_table(
        "password_login_failure_counters",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("password_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_accounts.id"],
        ),
        sa.PrimaryKeyConstraint("user_id", "password_fingerprint"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "LOCK TABLE password_hash_work_leases, "
            "password_login_failure_counters IN ACCESS EXCLUSIVE MODE"
        )
    )
    active_leases = bind.execute(
        sa.text(
            "SELECT count(*) FROM password_hash_work_leases "
            "WHERE expires_at > CURRENT_TIMESTAMP"
        )
    ).scalar_one()
    pending_failures = bind.execute(
        sa.text("SELECT count(*) FROM password_login_failure_counters")
    ).scalar_one()
    if int(active_leases or 0) > 0 or int(pending_failures or 0) > 0:
        raise RuntimeError(
            "Refusing to downgrade password-work protections while active "
            "leases or pending failure counters exist"
        )

    op.drop_table("password_login_failure_counters")
    op.drop_index(
        "ix_password_hash_work_leases_expires_at",
        table_name="password_hash_work_leases",
    )
    op.drop_table("password_hash_work_leases")
