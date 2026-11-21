"""Default unprioritized alerts to Medium and require a stored priority.

Revision ID: 029_required_alert_priority
Revises: 028_mcp_assertion_replay
"""

from alembic import op
import sqlalchemy as sa


revision = "029_required_alert_priority"
down_revision = "028_mcp_assertion_replay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Setting the default takes the table lock before the backfill, so a
    # concurrent write cannot introduce another NULL before SET NOT NULL.
    op.alter_column("alerts", "priority", server_default=sa.text("'MEDIUM'"))
    op.execute("UPDATE alerts SET priority = 'MEDIUM' WHERE priority IS NULL")
    op.alter_column("alerts", "priority", nullable=False)


def downgrade() -> None:
    op.alter_column("alerts", "priority", nullable=True, server_default=None)
