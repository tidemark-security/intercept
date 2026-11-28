"""Allow organization-wide alert filters to be pinned to navigation."""

from alembic import op
import sqlalchemy as sa


revision = "034_saved_filter_navigation"
down_revision = "033_saved_queue_filters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("saved_queue_filters", sa.Column("navigation_icon", sa.String(length=100)))
    op.create_check_constraint(
        "ck_saved_queue_filters_navigation",
        "saved_queue_filters",
        "navigation_icon IS NULL OR (scope = 'organization' AND queue = 'alerts')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_saved_queue_filters_navigation", "saved_queue_filters", type_="check")
    op.drop_column("saved_queue_filters", "navigation_icon")
