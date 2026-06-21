"""Add case templates and PICERL task metadata.

Revision ID: 008_case_templates
Revises: 007_user_link_template_preferences
Create Date: 2026-06-21
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "008_case_templates"
down_revision: Union[str, None] = "007_user_link_template_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


case_template_status = postgresql.ENUM(
    "DRAFT",
    "PUBLISHED",
    "DISABLED",
    "DELETED",
    name="casetemplatestatus",
    create_type=False,
)
picerl_stage = postgresql.ENUM(
    "Preparation",
    "Identification",
    "Containment",
    "Eradication",
    "Recovery",
    "Lessons Learned",
    name="picerlstage",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    case_template_status.create(bind, checkfirst=True)
    picerl_stage.create(bind, checkfirst=True)

    if "case_templates" not in inspector.get_table_names():
        op.create_table(
            "case_templates",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=True),
            sa.Column("title_normalized", sa.String(length=200), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", case_template_status, nullable=False),
            sa.Column("case_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("template_tasks", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.String(length=100), nullable=False),
            sa.Column("updated_by", sa.String(length=100), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_case_templates_status", "case_templates", ["status"])
        op.create_index("ix_case_templates_title_normalized", "case_templates", ["title_normalized"])
        op.create_index(
            "uq_case_templates_active_title_normalized",
            "case_templates",
            ["title_normalized"],
            unique=True,
            postgresql_where=sa.text("status != 'DELETED' AND title_normalized IS NOT NULL"),
        )
        op.alter_column("case_templates", "case_tags", server_default=None)
        op.alter_column("case_templates", "template_tasks", server_default=None)

    task_columns = {column["name"] for column in inspector.get_columns("tasks")}
    if "picerl_stage" not in task_columns:
        op.add_column("tasks", sa.Column("picerl_stage", picerl_stage, nullable=True))
    if "source_tpl" not in task_columns:
        op.add_column("tasks", sa.Column("source_tpl", sa.Integer(), nullable=True))
        op.create_index("ix_tasks_source_tpl", "tasks", ["source_tpl"])
        op.create_foreign_key(
            "fk_tasks_source_tpl_case_templates",
            "tasks",
            "case_templates",
            ["source_tpl"],
            ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "tasks" in inspector.get_table_names():
        task_columns = {column["name"] for column in inspector.get_columns("tasks")}
        if "source_tpl" in task_columns:
            existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("tasks")}
            if "fk_tasks_source_tpl_case_templates" in existing_fks:
                op.drop_constraint("fk_tasks_source_tpl_case_templates", "tasks", type_="foreignkey")
            existing_indexes = {index["name"] for index in inspector.get_indexes("tasks")}
            if "ix_tasks_source_tpl" in existing_indexes:
                op.drop_index("ix_tasks_source_tpl", table_name="tasks")
            op.drop_column("tasks", "source_tpl")
        if "picerl_stage" in task_columns:
            op.drop_column("tasks", "picerl_stage")

    if "case_templates" in inspector.get_table_names():
        existing_indexes = {index["name"] for index in inspector.get_indexes("case_templates")}
        if "uq_case_templates_active_title_normalized" in existing_indexes:
            op.drop_index("uq_case_templates_active_title_normalized", table_name="case_templates")
        if "ix_case_templates_title_normalized" in existing_indexes:
            op.drop_index("ix_case_templates_title_normalized", table_name="case_templates")
        if "ix_case_templates_status" in existing_indexes:
            op.drop_index("ix_case_templates_status", table_name="case_templates")
        op.drop_table("case_templates")

    picerl_stage.drop(bind, checkfirst=True)
    case_template_status.drop(bind, checkfirst=True)
