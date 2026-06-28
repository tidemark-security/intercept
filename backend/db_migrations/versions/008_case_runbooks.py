"""Add case runbooks and PICERL task metadata.

Revision ID: 008_case_runbooks
Revises: 009_triage_recommended_case_template
Create Date: 2026-06-21
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "008_case_runbooks"
down_revision: Union[str, None] = "009_triage_recommended_case_template"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


case_runbook_status = postgresql.ENUM(
    "DRAFT",
    "PUBLISHED",
    "DISABLED",
    "DELETED",
    name="caserunbookstatus",
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

    if _pg_type_exists(bind, "casetemplatestatus") and not _pg_type_exists(bind, "caserunbookstatus"):
        op.execute(sa.text("ALTER TYPE casetemplatestatus RENAME TO caserunbookstatus"))

    case_runbook_status.create(bind, checkfirst=True)
    picerl_stage.create(bind, checkfirst=True)

    table_names = set(inspector.get_table_names())
    if "case_templates" in table_names and "case_runbooks" not in table_names:
        op.rename_table("case_templates", "case_runbooks")
        inspector = sa.inspect(bind)
        _rename_relation_if_exists(bind, "case_templates_pkey", "case_runbooks_pkey")
        _rename_relation_if_exists(bind, "ix_case_templates_status", "ix_case_runbooks_status")
        _rename_relation_if_exists(bind, "ix_case_templates_title_normalized", "ix_case_runbooks_title_normalized")
        _rename_relation_if_exists(
            bind,
            "uq_case_templates_active_title_normalized",
            "uq_case_runbooks_active_title_normalized",
        )

    if "case_runbooks" in inspector.get_table_names():
        runbook_columns = {column["name"] for column in inspector.get_columns("case_runbooks")}
        if "template_tasks" in runbook_columns and "runbook_tasks" not in runbook_columns:
            op.alter_column(
                "case_runbooks",
                "template_tasks",
                new_column_name="runbook_tasks",
                existing_type=postgresql.JSONB(astext_type=sa.Text()),
            )
            inspector = sa.inspect(bind)

    if "case_runbooks" not in inspector.get_table_names():
        op.create_table(
            "case_runbooks",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=True),
            sa.Column("title_normalized", sa.String(length=200), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", case_runbook_status, nullable=False),
            sa.Column("case_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("runbook_tasks", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.String(length=100), nullable=False),
            sa.Column("updated_by", sa.String(length=100), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_case_runbooks_status", "case_runbooks", ["status"])
        op.create_index("ix_case_runbooks_title_normalized", "case_runbooks", ["title_normalized"])
        op.create_index(
            "uq_case_runbooks_active_title_normalized",
            "case_runbooks",
            ["title_normalized"],
            unique=True,
            postgresql_where=sa.text("status != 'DELETED' AND title_normalized IS NOT NULL"),
        )
        op.alter_column("case_runbooks", "case_tags", server_default=None)
        op.alter_column("case_runbooks", "runbook_tasks", server_default=None)

    task_columns = {column["name"] for column in inspector.get_columns("tasks")}
    if "source_tpl" in task_columns and "source_runbook" not in task_columns:
        op.alter_column(
            "tasks",
            "source_tpl",
            new_column_name="source_runbook",
            existing_type=sa.Integer(),
        )
        _rename_relation_if_exists(bind, "ix_tasks_source_tpl", "ix_tasks_source_runbook")
        _rename_constraint_if_exists(
            bind,
            "tasks",
            "fk_tasks_source_tpl_case_templates",
            "fk_tasks_source_runbook_case_runbooks",
        )
        inspector = sa.inspect(bind)
        task_columns = {column["name"] for column in inspector.get_columns("tasks")}

    if "picerl_stage" not in task_columns:
        op.add_column("tasks", sa.Column("picerl_stage", picerl_stage, nullable=True))
    if "source_runbook" not in task_columns:
        op.add_column("tasks", sa.Column("source_runbook", sa.Integer(), nullable=True))
        op.create_index("ix_tasks_source_runbook", "tasks", ["source_runbook"])
        op.create_foreign_key(
            "fk_tasks_source_runbook_case_runbooks",
            "tasks",
            "case_runbooks",
            ["source_runbook"],
            ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "tasks" in inspector.get_table_names():
        task_columns = {column["name"] for column in inspector.get_columns("tasks")}
        if "source_runbook" in task_columns:
            existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("tasks")}
            if "fk_tasks_source_runbook_case_runbooks" in existing_fks:
                op.drop_constraint("fk_tasks_source_runbook_case_runbooks", "tasks", type_="foreignkey")
            existing_indexes = {index["name"] for index in inspector.get_indexes("tasks")}
            if "ix_tasks_source_runbook" in existing_indexes:
                op.drop_index("ix_tasks_source_runbook", table_name="tasks")
            op.drop_column("tasks", "source_runbook")
        if "picerl_stage" in task_columns:
            op.drop_column("tasks", "picerl_stage")

    if "case_runbooks" in inspector.get_table_names():
        existing_indexes = {index["name"] for index in inspector.get_indexes("case_runbooks")}
        if "uq_case_runbooks_active_title_normalized" in existing_indexes:
            op.drop_index("uq_case_runbooks_active_title_normalized", table_name="case_runbooks")
        if "ix_case_runbooks_title_normalized" in existing_indexes:
            op.drop_index("ix_case_runbooks_title_normalized", table_name="case_runbooks")
        if "ix_case_runbooks_status" in existing_indexes:
            op.drop_index("ix_case_runbooks_status", table_name="case_runbooks")
        op.drop_table("case_runbooks")

    picerl_stage.drop(bind, checkfirst=True)
    case_runbook_status.drop(bind, checkfirst=True)


def _pg_type_exists(bind: sa.Connection, name: str) -> bool:
    return bool(bind.execute(sa.text("SELECT to_regtype(:name) IS NOT NULL"), {"name": name}).scalar())


def _relation_exists(bind: sa.Connection, name: str) -> bool:
    return bool(bind.execute(sa.text("SELECT to_regclass(:name) IS NOT NULL"), {"name": name}).scalar())


def _rename_relation_if_exists(bind: sa.Connection, old: str, new: str) -> None:
    if _relation_exists(bind, old) and not _relation_exists(bind, new):
        op.execute(sa.text(f'ALTER INDEX "{old}" RENAME TO "{new}"'))


def _constraint_exists(bind: sa.Connection, table: str, name: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                """
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = to_regclass(:table_name)
                  AND conname = :constraint_name
                """
            ),
            {"table_name": table, "constraint_name": name},
        ).scalar()
    )


def _rename_constraint_if_exists(bind: sa.Connection, table: str, old: str, new: str) -> None:
    if _constraint_exists(bind, table, old) and not _constraint_exists(bind, table, new):
        op.execute(sa.text(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{old}" TO "{new}"'))
