"""Add override timestamps flag for NHI migration imports.

Revision ID: 012_nhi_override_timestamps
Revises: 011_link_template_single_surface
Create Date: 2026-06-28
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "012_nhi_override_timestamps"
down_revision: Union[str, None] = "011_link_template_single_surface"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "user_accounts" not in inspector.get_table_names():
        return

    existing_columns = {column["name"]: column for column in inspector.get_columns("user_accounts")}
    if "override_timestamps" not in existing_columns:
        op.add_column(
            "user_accounts",
            sa.Column("override_timestamps", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.alter_column("user_accounts", "override_timestamps", server_default=None)
        return

    override_column = existing_columns["override_timestamps"]
    if override_column.get("nullable") or override_column.get("default") is not None:
        op.execute(sa.text("UPDATE user_accounts SET override_timestamps = false WHERE override_timestamps IS NULL"))
        op.alter_column(
            "user_accounts",
            "override_timestamps",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "user_accounts" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("user_accounts")}
    if "override_timestamps" in existing_columns:
        op.drop_column("user_accounts", "override_timestamps")
