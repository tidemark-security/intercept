"""Add durable alert collector framework tables.

Revision ID: 013_alert_collector_framework
Revises: 012_nhi_override_timestamps
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "013_alert_collector_framework"
down_revision: Union[str, None] = "012_nhi_override_timestamps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collector_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.String(length=100), nullable=False),
        sa.Column("stream_key", sa.String(length=255), nullable=False),
        sa.Column("trigger", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=True),
        sa.Column("checkpoint_before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("checkpoint_after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_summary", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_collector_runs_provider_id", "collector_runs", ["provider_id"])
    op.create_index("ix_collector_runs_provider_stream_created", "collector_runs", ["provider_id", "stream_key", "created_at"])
    op.create_index("ix_collector_runs_status", "collector_runs", ["status"])
    op.create_index("ix_collector_runs_task_id", "collector_runs", ["task_id"], unique=True)

    op.create_table(
        "collector_checkpoints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.String(length=100), nullable=False),
        sa.Column("stream_key", sa.String(length=255), nullable=False),
        sa.Column("cursor", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("high_watermark", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("last_successful_run_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["last_successful_run_id"], ["collector_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "stream_key", name="uq_collector_checkpoints_provider_stream"),
    )
    op.create_index("ix_collector_checkpoints_provider_id", "collector_checkpoints", ["provider_id"])

    op.create_table(
        "collector_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.String(length=100), nullable=False),
        sa.Column("stream_key", sa.String(length=255), nullable=False),
        sa.Column("external_id", sa.String(length=500), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("external_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("normalized_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_schema_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("skip_code", sa.String(length=200), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_summary", sa.String(length=500), nullable=True),
        sa.Column("validation_request", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("validation_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latest_run_id", sa.Integer(), nullable=True),
        sa.Column("processor_version", sa.String(length=200), nullable=False),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["latest_run_id"], ["collector_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "stream_key", "external_id", name="uq_collector_events_external_identity"),
    )
    op.create_index("ix_collector_events_provider_status", "collector_events", ["provider_id", "status"])
    op.create_index("ix_collector_events_reconcile", "collector_events", ["status", "processing_started_at"])
    op.create_index("ix_collector_events_latest_run", "collector_events", ["latest_run_id"])

    op.create_table(
        "collector_event_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collector_event_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("normalized_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("external_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processor_version", sa.String(length=200), nullable=False),
        sa.Column("observed_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collector_event_id"], ["collector_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observed_run_id"], ["collector_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collector_event_id", "revision", name="uq_collector_event_revisions_event_revision"),
    )
    op.create_index(
        "ix_collector_event_revisions_event",
        "collector_event_revisions",
        ["collector_event_id", "revision"],
    )

    op.create_table(
        "collector_findings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collector_event_id", sa.Integer(), nullable=False),
        sa.Column("event_revision", sa.Integer(), nullable=False),
        sa.Column("finding_key", sa.String(length=500), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("alert_projection", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("assessment", sa.String(length=200), nullable=False),
        sa.Column("validation_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validation_report_ref", sa.String(length=1000), nullable=True),
        sa.Column("validator_version", sa.String(length=200), nullable=True),
        sa.Column("alert_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("triage_policy", sa.String(length=30), nullable=False),
        sa.Column("triage_status", sa.String(length=30), nullable=False),
        sa.Column("triage_error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"]),
        sa.ForeignKeyConstraint(["collector_event_id"], ["collector_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alert_id", name="uq_collector_findings_alert_id"),
        sa.UniqueConstraint("collector_event_id", "finding_key", name="uq_collector_findings_event_key"),
    )
    op.create_index("ix_collector_findings_collector_event_id", "collector_findings", ["collector_event_id"])
    op.create_index("ix_collector_findings_status", "collector_findings", ["status"])


def downgrade() -> None:
    op.drop_table("collector_findings")
    op.drop_table("collector_event_revisions")
    op.drop_table("collector_events")
    op.drop_table("collector_checkpoints")
    op.drop_table("collector_runs")
