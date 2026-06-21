"""Add recommended case template to triage recommendations.

Revision ID: 009_triage_recommended_case_template
Revises: 008_case_templates
Create Date: 2026-06-21
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009_triage_recommended_case_template"
down_revision: Union[str, None] = "008_case_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "triage_recommendations" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("triage_recommendations")}
    if "recommended_case_template_id" not in columns:
        op.add_column(
            "triage_recommendations",
            sa.Column("recommended_case_template_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_triage_recommendations_recommended_case_template",
            "triage_recommendations",
            "case_templates",
            ["recommended_case_template_id"],
            ["id"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "triage_recommendations" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("triage_recommendations")}
    if "recommended_case_template_id" not in columns:
        return

    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("triage_recommendations")}
    if "fk_triage_recommendations_recommended_case_template" in foreign_keys:
        op.drop_constraint(
            "fk_triage_recommendations_recommended_case_template",
            "triage_recommendations",
            type_="foreignkey",
        )
    op.drop_column("triage_recommendations", "recommended_case_template_id")
