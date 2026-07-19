"""Add analyst-authored context entries.

Revision ID: 006_context_entries
Revises: 006_ai_triage_context
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "006_context_entries"
down_revision = "006_ai_triage_context"
branch_labels = None
depends_on = None


def _create_context_indexes(inspector: sa.Inspector) -> None:
    existing_indexes = {index["name"] for index in inspector.get_indexes("context_entries")}
    if "ix_context_entries_active" not in existing_indexes:
        op.create_index("ix_context_entries_active", "context_entries", ["expires_at", "expired_at"])


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "context_entries" not in table_names:
        op.create_table(
            "context_entries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column(
                "criteria",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("author", sa.String(length=100), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.alter_column("context_entries", "criteria", server_default=None)
        inspector = sa.inspect(bind)
    _create_context_indexes(inspector)

    table_names = set(sa.inspect(bind).get_table_names())
    if "triage_recommendations" not in table_names:
        return

    existing_columns = {column["name"]: column for column in sa.inspect(bind).get_columns("triage_recommendations")}
    if "applied_context_entries" not in existing_columns:
        op.add_column(
            "triage_recommendations",
            sa.Column(
                "applied_context_entries",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )
        op.alter_column("triage_recommendations", "applied_context_entries", server_default=None)
        return

    applied_context_column = existing_columns["applied_context_entries"]
    if applied_context_column.get("nullable") or applied_context_column.get("default") is not None:
        op.execute(sa.text("UPDATE triage_recommendations SET applied_context_entries = '[]'::jsonb WHERE applied_context_entries IS NULL"))
        op.alter_column(
            "triage_recommendations",
            "applied_context_entries",
            existing_type=postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    table_names = set(inspector.get_table_names())

    if "triage_recommendations" in table_names:
        existing_columns = {column["name"] for column in inspector.get_columns("triage_recommendations")}
        if "applied_context_entries" in existing_columns:
            op.drop_column("triage_recommendations", "applied_context_entries")

    if "context_entries" in table_names:
        existing_indexes = {index["name"] for index in inspector.get_indexes("context_entries")}
        if "ix_context_entries_active" in existing_indexes:
            op.drop_index("ix_context_entries_active", table_name="context_entries")
        op.drop_table("context_entries")
