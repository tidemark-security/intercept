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


def upgrade() -> None:
    scope_enum.create(op.get_bind(), checkfirst=True)
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
    op.create_index("ix_ai_triage_context_entries_scope_value", "ai_triage_context_entries", ["scope_value"])
    op.create_index("ix_ai_triage_context_scope", "ai_triage_context_entries", ["scope_type", "scope_value"])
    op.create_index("ix_ai_triage_context_active", "ai_triage_context_entries", ["expires_at", "expired_at"])
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


def downgrade() -> None:
    op.drop_column("triage_recommendations", "applied_context_entries")
    op.drop_index("ix_ai_triage_context_active", table_name="ai_triage_context_entries")
    op.drop_index("ix_ai_triage_context_scope", table_name="ai_triage_context_entries")
    op.drop_index("ix_ai_triage_context_entries_scope_value", table_name="ai_triage_context_entries")
    op.drop_table("ai_triage_context_entries")
    scope_enum.drop(op.get_bind(), checkfirst=True)
