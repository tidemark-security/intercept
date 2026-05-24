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
    op.add_column(
        "user_accounts",
        sa.Column("assignable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("user_accounts", "assignable", server_default=None)


def downgrade() -> None:
    op.drop_column("user_accounts", "assignable")
