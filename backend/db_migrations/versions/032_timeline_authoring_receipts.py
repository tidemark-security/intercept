"""Persist parent-scoped timeline authoring retries."""

from alembic import op
import sqlalchemy as sa

revision = "032_timeline_authoring_receipts"
down_revision = "031_timeline_search_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "timeline_authoring_receipts",
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("client_item_id", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("item_type", sa.String(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("entity_type", "entity_id", "client_item_id"),
    )


def downgrade() -> None:
    op.drop_table("timeline_authoring_receipts")
