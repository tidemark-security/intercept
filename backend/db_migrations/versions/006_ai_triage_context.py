"""Add analyst-authored AI triage context.

Revision ID: 006_ai_triage_context
Revises: 005_nhi_assignable
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "006_ai_triage_context"
down_revision = "005_nhi_assignable"
branch_labels = None
depends_on = None


scope_enum = postgresql.ENUM(
    "GLOBAL",
    "ALERT_SOURCE",
    "CASE",
    "USER_ACCOUNT",
    "HOST_SYSTEM",
    "OBSERVABLE",
    "TAG",
    name="aitriagecontextscopetype",
    create_type=False,
)


def _create_context_indexes(inspector: sa.Inspector) -> None:
    existing_indexes = {index["name"] for index in inspector.get_indexes("ai_triage_context_entries")}
    if "ix_ai_triage_context_entries_scope_value" not in existing_indexes:
        op.create_index("ix_ai_triage_context_entries_scope_value", "ai_triage_context_entries", ["scope_value"])
    if "ix_ai_triage_context_scope" not in existing_indexes:
        op.create_index("ix_ai_triage_context_scope", "ai_triage_context_entries", ["scope_type", "scope_value"])
    if "ix_ai_triage_context_active" not in existing_indexes:
        op.create_index("ix_ai_triage_context_active", "ai_triage_context_entries", ["expires_at", "expired_at"])


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    scope_enum.create(bind, checkfirst=True)
    if "ai_triage_context_entries" not in table_names:
        op.create_table(
            "ai_triage_context_entries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("scope_type", scope_enum, nullable=False),
            sa.Column("scope_value", sa.String(length=255), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("author", sa.String(length=100), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
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

    if "ai_triage_context_entries" in table_names:
        existing_indexes = {index["name"] for index in inspector.get_indexes("ai_triage_context_entries")}
        if "ix_ai_triage_context_active" in existing_indexes:
            op.drop_index("ix_ai_triage_context_active", table_name="ai_triage_context_entries")
        if "ix_ai_triage_context_scope" in existing_indexes:
            op.drop_index("ix_ai_triage_context_scope", table_name="ai_triage_context_entries")
        if "ix_ai_triage_context_entries_scope_value" in existing_indexes:
            op.drop_index("ix_ai_triage_context_entries_scope_value", table_name="ai_triage_context_entries")
        op.drop_table("ai_triage_context_entries")

    scope_enum.drop(op.get_bind(), checkfirst=True)
