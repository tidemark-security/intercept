"""Add a durable account credential-invalidation cutoff.

Revision ID: 021_credential_cutoff
Revises: 020_oidc_login_abuse_controls
Create Date: 2026-08-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "021_credential_cutoff"
down_revision: Union[str, None] = "020_oidc_login_abuse_controls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cutoff_column_exists() -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'user_accounts' "
            "AND column_name = 'credentials_invalidated_at'"
        )
    )
    return result.fetchone() is not None


def upgrade() -> None:
    if _cutoff_column_exists():
        return  # Fresh installs receive the column from 001 metadata creation.

    op.add_column(
        "user_accounts",
        sa.Column(
            "credentials_invalidated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    if not _cutoff_column_exists():
        return

    bind = op.get_bind()
    # Lock before checking so a concurrent credential invalidation cannot land
    # between the check and the destructive ALTER TABLE.
    bind.execute(sa.text("LOCK TABLE user_accounts IN ACCESS EXCLUSIVE MODE"))
    has_active_cutoff = bind.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM user_accounts "
            "WHERE credentials_invalidated_at IS NOT NULL"
            ")"
        )
    ).scalar_one()
    if has_active_cutoff:
        raise RuntimeError(
            "Cannot downgrade 021_credential_cutoff: "
            "user_accounts.credentials_invalidated_at contains non-NULL "
            "values. Dropping those cutoffs could resurrect invalidated local "
            "credentials after a later re-upgrade. Permanently remove the "
            "affected credentials before clearing the cutoffs and downgrading."
        )

    op.drop_column("user_accounts", "credentials_invalidated_at")
