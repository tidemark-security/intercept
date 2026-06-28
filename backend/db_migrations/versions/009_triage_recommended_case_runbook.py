"""Add recommended case runbook to triage recommendations.

Revision ID: 009_triage_recommended_case_runbook
Revises: 008_case_runbooks
Create Date: 2026-06-21
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009_triage_recommended_case_runbook"
down_revision: Union[str, None] = "008_case_runbooks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "triage_recommendations" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("triage_recommendations")}
    if "recommended_case_template_id" in columns and "recommended_case_runbook_id" not in columns:
        op.alter_column(
            "triage_recommendations",
            "recommended_case_template_id",
            new_column_name="recommended_case_runbook_id",
            existing_type=sa.Integer(),
        )
        _rename_constraint_if_exists(
            bind,
            "triage_recommendations",
            "fk_triage_recommendations_recommended_case_template",
            "fk_triage_recommendations_recommended_case_runbook",
        )
        return

    if "recommended_case_runbook_id" not in columns:
        op.add_column(
            "triage_recommendations",
            sa.Column("recommended_case_runbook_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_triage_recommendations_recommended_case_runbook",
            "triage_recommendations",
            "case_runbooks",
            ["recommended_case_runbook_id"],
            ["id"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "triage_recommendations" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("triage_recommendations")}
    if "recommended_case_runbook_id" not in columns:
        return

    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("triage_recommendations")}
    if "fk_triage_recommendations_recommended_case_runbook" in foreign_keys:
        op.drop_constraint(
            "fk_triage_recommendations_recommended_case_runbook",
            "triage_recommendations",
            type_="foreignkey",
        )
    op.drop_column("triage_recommendations", "recommended_case_runbook_id")


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
