"""Legacy alias for the removed case templates feature revision.

Revision ID: 008_case_templates
Revises: 007_user_link_template_preferences
Create Date: 2026-06-21
"""
from __future__ import annotations

from typing import Sequence, Union


revision: str = "008_case_templates"
down_revision: Union[str, None] = "007_user_link_template_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
