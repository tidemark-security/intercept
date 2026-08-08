"""Add explicit scopes to API keys.

Revision ID: 018_scoped_api_keys
Revises: 017_mcp_dcr_abuse_controls
Create Date: 2026-08-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "018_scoped_api_keys"
down_revision: Union[str, None] = "017_mcp_dcr_abuse_controls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ADMIN_LEGACY_SCOPES = '["api:admin", "api:read", "api:write", "mcp:access"]'
ANALYST_LEGACY_SCOPES = '["api:read", "api:write", "mcp:access"]'
AUDITOR_LEGACY_SCOPES = '["api:read", "mcp:access"]'


def _scopes_column_exists() -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'api_keys' AND column_name = 'scopes'"
        )
    )
    return result.fetchone() is not None


def upgrade() -> None:
    if _scopes_column_exists():
        return  # Fresh installs receive the column from 001 metadata creation.

    op.add_column(
        "api_keys",
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # Legacy keys inherited their owner's authority. Preserve that behavior
    # without introducing a stored scope above the owner's current role ceiling.
    # An unknown role or orphaned key remains NULL so the NOT NULL transition
    # fails closed instead of guessing at a safe permission set.
    op.execute(
        sa.text(
            """
            UPDATE api_keys AS api_key
            SET scopes = CASE CAST(owner.role AS text)
                WHEN 'ADMIN' THEN CAST(:admin_scopes AS jsonb)
                WHEN 'ANALYST' THEN CAST(:analyst_scopes AS jsonb)
                WHEN 'AUDITOR' THEN CAST(:auditor_scopes AS jsonb)
            END
            FROM user_accounts AS owner
            WHERE owner.id = api_key.user_id
              AND api_key.scopes IS NULL
            """
        ).bindparams(
            admin_scopes=ADMIN_LEGACY_SCOPES,
            analyst_scopes=ANALYST_LEGACY_SCOPES,
            auditor_scopes=AUDITOR_LEGACY_SCOPES,
        )
    )
    op.alter_column("api_keys", "scopes", nullable=False)


def downgrade() -> None:
    if not _scopes_column_exists():
        return

    bind = op.get_bind()
    # Keep the row check and destructive schema change atomic with respect to
    # API-key creation. ALTER TABLE will take this lock too; acquiring it first
    # closes the gap between the safety check and dropping the column.
    bind.execute(sa.text("LOCK TABLE api_keys IN ACCESS EXCLUSIVE MODE"))
    has_api_keys = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM api_keys)")
    ).scalar_one()
    if has_api_keys:
        raise RuntimeError(
            "Cannot downgrade 018_scoped_api_keys: api_keys contains rows. "
            "Dropping explicit scopes could widen existing keys to their "
            "owner's role authority after a later re-upgrade. Revoke and "
            "delete every API key before downgrading."
        )

    op.drop_column("api_keys", "scopes")
