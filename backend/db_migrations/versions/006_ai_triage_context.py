"""Compatibility marker for removed AI triage context migration.

Revision ID: 006_ai_triage_context
Revises: 005_nhi_assignable
Create Date: 2026-05-24
"""

revision = "006_ai_triage_context"
down_revision = "005_nhi_assignable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Keep existing databases stamped at this removed revision upgradeable."""


def downgrade() -> None:
    """No-op compatibility marker."""
