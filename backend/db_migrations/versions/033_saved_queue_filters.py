"""Add personal and organization-wide saved queue filters."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "033_saved_queue_filters"
down_revision = "032_timeline_authoring_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_queue_filters",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("queue", sa.String(length=6), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("scope", sa.String(length=12), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("user_accounts.id", ondelete="CASCADE")),
        sa.Column("filters", JSONB(), nullable=False),
        sa.CheckConstraint(
            "queue IN ('alerts', 'cases', 'tasks')",
            name="ck_saved_queue_filters_queue",
        ),
        sa.CheckConstraint(
            "(scope = 'personal' AND owner_id IS NOT NULL) OR "
            "(scope = 'organization' AND owner_id IS NULL)",
            name="ck_saved_queue_filters_scope_owner",
        ),
    )
    op.create_index("ix_saved_queue_filters_queue_owner", "saved_queue_filters", ["queue", "owner_id"])


def downgrade() -> None:
    op.drop_table("saved_queue_filters")
