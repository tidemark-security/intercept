"""Upgrade Intercept from v0.5.x to v0.6.0."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from db_migrations.v0_6_0 import assertion_replay, auth, oauth, soc_metrics, timeline_search

# Keep the former branch head so fully migrated development databases stay current.
revision = "032_timeline_authoring_receipts"
down_revision = "012_nhi_override_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Concurrent index builds commit independently. Run them first so a retry
    # can repair an interrupted build before starting the transactional DDL.
    timeline_search.upgrade()

    auth.add_key_scopes()
    auth.add_oidc_identity_constraint()
    auth.add_credential_cutoff()
    auth.add_oidc_login_controls()
    auth.add_passkey_controls()
    auth.create_password_login_attempts()
    auth.create_password_work_tables()
    auth.create_api_key_failure_samples()
    oauth.upgrade()

    # Take the table lock before the backfill so concurrent writes cannot add NULLs.
    # Non-HOT updates can also evaluate the new timeline expression index.
    op.execute("SET LOCAL jit = off")
    op.alter_column("alerts", "priority", server_default=sa.text("'MEDIUM'"))
    op.execute("UPDATE alerts SET priority = 'MEDIUM' WHERE priority IS NULL")
    op.alter_column("alerts", "priority", nullable=False)
    soc_metrics.upgrade()

    op.create_table(
        "alert_triage_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary_principal_id", sa.Uuid()),
        sa.Column("context_snapshot", JSONB()),
    )
    op.create_index("ix_alert_triage_runs_alert_id", "alert_triage_runs", ["alert_id"])
    # Fresh installs receive this column from the baseline's SQLModel metadata.
    op.execute("ALTER TABLE triage_recommendations ADD COLUMN IF NOT EXISTS triage_run_id UUID")
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

    # pg_cron uses a separate connection. Schedule jobs after application DDL.
    auth.schedule_session_jobs()
    assertion_replay.upgrade()


def downgrade() -> None:
    # Each guard locks the affected tables. Complete the guarded changes in
    # one transaction before removing any jobs on the separate cron connection.
    auth.remove_key_scopes()
    auth.remove_credential_cutoff()
    auth.remove_password_work_tables()

    op.drop_table("timeline_authoring_receipts")
    op.drop_column("triage_recommendations", "triage_run_id")
    op.drop_table("alert_triage_runs")
    op.alter_column("alerts", "priority", nullable=True, server_default=None)
    soc_metrics.downgrade()
    timeline_search.downgrade()

    oauth.downgrade()
    op.drop_table("api_key_failure_samples")
    op.drop_table("password_login_attempts")
    op.drop_column("webauthn_challenges", "user_fingerprint")
    op.drop_column("webauthn_challenges", "source_fingerprint")
    auth.remove_oidc_login_controls()
    auth.remove_oidc_identity_constraint()
    assertion_replay.downgrade()
    auth.remove_session_jobs()
