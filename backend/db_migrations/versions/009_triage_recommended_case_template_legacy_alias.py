"""Legacy alias for the removed case templates triage revision.

Revision ID: 009_triage_recommended_case_template
Revises: 008_case_templates
Create Date: 2026-06-21
"""
from __future__ import annotations

from typing import Sequence, Union


revision: str = "009_triage_recommended_case_template"
down_revision: Union[str, None] = "008_case_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
