"""Add browser binding hash to OIDC auth requests.

Revision ID: 002_oidc_browser_binding_hash
Revises: 001_initial
Create Date: 2026-03-29
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002_oidc_browser_binding_hash"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'oidc_auth_requests' AND column_name = 'browser_binding_hash'"
        )
    )
    if result.fetchone():
        return  # Column already exists (created by 001_initial_schema)

    op.add_column(
        "oidc_auth_requests",
        sa.Column("browser_binding_hash", sa.String(length=64), nullable=False, server_default=""),
    )
    op.alter_column("oidc_auth_requests", "browser_binding_hash", server_default=None)


def downgrade() -> None:
    op.drop_column("oidc_auth_requests", "browser_binding_hash")