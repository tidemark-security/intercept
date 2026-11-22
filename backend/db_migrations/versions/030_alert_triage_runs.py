"""Store the context delivered to each managed alert triage run."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "030_alert_triage_runs"
down_revision = "029_required_alert_priority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_triage_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary_principal_id", sa.Uuid()),
        sa.Column("context_snapshot", JSONB()),
    )
    op.create_index("ix_alert_triage_runs_alert_id", "alert_triage_runs", ["alert_id"])
    # The baseline migration creates existing tables using current model metadata.
    op.execute("ALTER TABLE triage_recommendations ADD COLUMN IF NOT EXISTS triage_run_id UUID")


def downgrade() -> None:
    op.drop_column("triage_recommendations", "triage_run_id")
    op.drop_table("alert_triage_runs")
