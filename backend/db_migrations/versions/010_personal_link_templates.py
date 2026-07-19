"""Add personal link templates and template scopes.

Revision ID: 010_personal_link_templates
Revises: 009_triage_recommended_case_runbook
Create Date: 2026-06-28
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "010_personal_link_templates"
down_revision: Union[str, None] = "009_triage_recommended_case_runbook"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "link_templates" in table_names:
        columns = {column["name"] for column in inspector.get_columns("link_templates")}
        if "surface_scopes" not in columns:
            op.add_column(
                "link_templates",
                sa.Column(
                    "surface_scopes",
                    postgresql.JSONB(astext_type=sa.Text()),
                    nullable=False,
                    server_default=sa.text("'[\"timeline_item\"]'::jsonb"),
                ),
            )
            op.alter_column("link_templates", "surface_scopes", server_default=None)
        if "entity_types" not in columns:
            op.add_column(
                "link_templates",
                sa.Column("entity_types", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            )

    if "personal_link_templates" not in table_names:
        op.create_table(
            "personal_link_templates",
            sa.Column("template_id", sa.String(length=100), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("icon_name", sa.String(length=100), nullable=False),
            sa.Column("tooltip_template", sa.Text(), nullable=False),
            sa.Column("url_template", sa.Text(), nullable=False),
            sa.Column("field_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "surface_scopes",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[\"timeline_item\"]'::jsonb"),
            ),
            sa.Column("entity_types", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("display_order", sa.Integer(), nullable=False),
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "template_id", name="uq_personal_link_template_user_template_id"),
        )
        op.create_index("ix_personal_link_templates_template_id", "personal_link_templates", ["template_id"])
        op.create_index("ix_personal_link_templates_user_id", "personal_link_templates", ["user_id"])
        op.alter_column("personal_link_templates", "surface_scopes", server_default=None)

    if "user_link_template_preferences" in set(sa.inspect(bind).get_table_names()):
        existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("user_link_template_preferences")}
        if "ix_user_link_template_preferences_template_id" in existing_indexes:
            op.drop_index("ix_user_link_template_preferences_template_id", table_name="user_link_template_preferences")
        if "ix_user_link_template_preferences_user_id" in existing_indexes:
            op.drop_index("ix_user_link_template_preferences_user_id", table_name="user_link_template_preferences")
        op.drop_table("user_link_template_preferences")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "personal_link_templates" in table_names:
        existing_indexes = {index["name"] for index in inspector.get_indexes("personal_link_templates")}
        if "ix_personal_link_templates_template_id" in existing_indexes:
            op.drop_index("ix_personal_link_templates_template_id", table_name="personal_link_templates")
        if "ix_personal_link_templates_user_id" in existing_indexes:
            op.drop_index("ix_personal_link_templates_user_id", table_name="personal_link_templates")
        op.drop_table("personal_link_templates")

    if "user_link_template_preferences" not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            "user_link_template_preferences",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("template_id", sa.Integer(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["template_id"], ["link_templates.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "template_id", name="uq_user_link_template_preference"),
        )
        op.create_index("ix_user_link_template_preferences_user_id", "user_link_template_preferences", ["user_id"])
        op.create_index("ix_user_link_template_preferences_template_id", "user_link_template_preferences", ["template_id"])

    if "link_templates" in set(sa.inspect(bind).get_table_names()):
        columns = {column["name"] for column in sa.inspect(bind).get_columns("link_templates")}
        if "entity_types" in columns:
            op.drop_column("link_templates", "entity_types")
        if "surface_scopes" in columns:
            op.drop_column("link_templates", "surface_scopes")
