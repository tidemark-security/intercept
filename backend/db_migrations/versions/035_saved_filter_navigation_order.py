"""Persist the order of pinned organization alert filters."""

from alembic import op
import sqlalchemy as sa


revision = "035_saved_filter_pin_order"
down_revision = "034_saved_filter_navigation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("saved_queue_filters", sa.Column("navigation_position", sa.Integer()))
    op.execute("""
        WITH positions AS (
            SELECT id, row_number() OVER (ORDER BY name, id) - 1 AS position
            FROM saved_queue_filters
            WHERE navigation_icon IS NOT NULL
        )
        UPDATE saved_queue_filters AS filters
        SET navigation_position = positions.position
        FROM positions
        WHERE filters.id = positions.id
    """)
    op.create_check_constraint(
        "ck_saved_queue_filters_navigation_position",
        "saved_queue_filters",
        "(navigation_icon IS NULL) = (navigation_position IS NULL) "
        "AND (navigation_position IS NULL OR navigation_position >= 0)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_saved_queue_filters_navigation_position", "saved_queue_filters", type_="check")
    op.drop_column("saved_queue_filters", "navigation_position")
