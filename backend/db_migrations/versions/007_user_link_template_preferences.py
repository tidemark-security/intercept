"""Add per-user link template preferences.

Revision ID: 007_user_link_template_preferences
Revises: 006_context_entries
Create Date: 2026-06-21
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "007_user_link_template_preferences"
down_revision: Union[str, None] = "006_context_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "user_link_template_preferences" in inspector.get_table_names():
        existing_indexes = {index["name"] for index in inspector.get_indexes("user_link_template_preferences")}
        if "ix_user_link_template_preferences_user_id" not in existing_indexes:
            op.create_index(
                "ix_user_link_template_preferences_user_id",
                "user_link_template_preferences",
                ["user_id"],
            )
        if "ix_user_link_template_preferences_template_id" not in existing_indexes:
            op.create_index(
                "ix_user_link_template_preferences_template_id",
                "user_link_template_preferences",
                ["template_id"],
            )
        return

    op.create_table(
        "user_link_template_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["template_id"], ["link_templates.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "template_id", name="uq_user_link_template_preference"),
    )
    op.create_index("ix_user_link_template_preferences_user_id", "user_link_template_preferences", ["user_id"])
    op.create_index("ix_user_link_template_preferences_template_id", "user_link_template_preferences", ["template_id"])
    op.alter_column("user_link_template_preferences", "enabled", server_default=None)
    op.alter_column("user_link_template_preferences", "values", server_default=None)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "user_link_template_preferences" not in inspector.get_table_names():
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("user_link_template_preferences")}
    if "ix_user_link_template_preferences_template_id" in existing_indexes:
        op.drop_index("ix_user_link_template_preferences_template_id", table_name="user_link_template_preferences")
    if "ix_user_link_template_preferences_user_id" in existing_indexes:
        op.drop_index("ix_user_link_template_preferences_user_id", table_name="user_link_template_preferences")
    op.drop_table("user_link_template_preferences")
