"""Add assignable flag for NHI task agents.

Revision ID: 005_nhi_assignable
Revises: 004_timeline_graphs
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa


revision = "005_nhi_assignable"
down_revision = "004_timeline_graphs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "user_accounts" not in inspector.get_table_names():
        return

    existing_columns = {column["name"]: column for column in inspector.get_columns("user_accounts")}
    if "assignable" not in existing_columns:
        op.add_column(
            "user_accounts",
            sa.Column("assignable", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.alter_column("user_accounts", "assignable", server_default=None)
        return

    assignable_column = existing_columns["assignable"]
    if assignable_column.get("nullable") or assignable_column.get("default") is not None:
        op.execute(sa.text("UPDATE user_accounts SET assignable = false WHERE assignable IS NULL"))
        op.alter_column(
            "user_accounts",
            "assignable",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "user_accounts" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("user_accounts")}
    if "assignable" in existing_columns:
        op.drop_column("user_accounts", "assignable")
