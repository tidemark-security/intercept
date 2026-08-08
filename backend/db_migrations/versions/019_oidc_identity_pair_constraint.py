"""Require complete, non-blank OIDC identity pairs.

Revision ID: 019_oidc_identity_pair
Revises: 018_scoped_api_keys
Create Date: 2026-08-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "019_oidc_identity_pair"
down_revision: Union[str, None] = "018_scoped_api_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINT_NAME = "ck_user_accounts_oidc_identity_pair"
OIDC_IDENTITY_PAIR_EXPRESSION = (
    "(oidc_issuer IS NULL AND oidc_subject IS NULL) OR "
    "(oidc_issuer IS NOT NULL AND oidc_subject IS NOT NULL "
    "AND length(btrim(oidc_issuer, E' \\011\\012\\013\\014\\015')) > 0 "
    "AND length(btrim(oidc_subject, E' \\011\\012\\013\\014\\015')) > 0)"
)


def _constraint_exists() -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_constraint "
            "WHERE conname = :constraint_name "
            "AND conrelid = to_regclass('user_accounts')"
        ),
        {"constraint_name": CONSTRAINT_NAME},
    )
    return result.fetchone() is not None


def _invalid_identity_count() -> int:
    result = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM user_accounts "
            "WHERE (oidc_issuer IS NULL) <> (oidc_subject IS NULL) "
            "OR (oidc_issuer IS NOT NULL "
            "AND length(btrim(oidc_issuer, E' \\011\\012\\013\\014\\015')) = 0) "
            "OR (oidc_subject IS NOT NULL "
            "AND length(btrim(oidc_subject, E' \\011\\012\\013\\014\\015')) = 0)"
        )
    )
    return int(result.scalar_one())


def upgrade() -> None:
    if _constraint_exists():
        return  # Fresh installs receive the constraint from 001 metadata creation.

    invalid_count = _invalid_identity_count()
    if invalid_count:
        raise RuntimeError(
            "Cannot add OIDC identity-pair constraint: "
            f"{invalid_count} user account(s) have a partial or blank OIDC identity"
        )

    op.create_check_constraint(
        CONSTRAINT_NAME,
        "user_accounts",
        OIDC_IDENTITY_PAIR_EXPRESSION,
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"ALTER TABLE user_accounts DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}"
        )
    )
