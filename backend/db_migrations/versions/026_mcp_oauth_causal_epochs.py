"""Add database-issued causal epochs for MCP OAuth grants.

Revision ID: 026_mcp_oauth_causal_epochs
Revises: 025_api_key_failure_sampling
Create Date: 2026-08-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "026_mcp_oauth_causal_epochs"
down_revision: Union[str, None] = "025_api_key_failure_sampling"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CAPACITY_TABLE = "mcp_oauth_authorization_capacity"
CONSENT_TABLE = "mcp_oauth_consents"
EPOCH_SEQUENCE = "mcp_oauth_grant_epoch_seq"


def _column_exists(table_name: str, column_name: str) -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = :table_name "
            "AND column_name = :column_name"
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.fetchone() is not None


def _sequence_exists() -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_class AS sequence "
            "JOIN pg_namespace AS namespace ON namespace.oid = sequence.relnamespace "
            "WHERE namespace.nspname = current_schema() "
            "AND sequence.relkind = 'S' "
            "AND sequence.relname = :sequence_name"
        ),
        {"sequence_name": EPOCH_SEQUENCE},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    if not _sequence_exists():
        sa.Sequence(EPOCH_SEQUENCE).create(op.get_bind())

    if not _column_exists(CAPACITY_TABLE, "authorization_epoch"):
        op.add_column(
            CAPACITY_TABLE,
            sa.Column("authorization_epoch", sa.BigInteger(), nullable=True),
        )
    if not _column_exists(CONSENT_TABLE, "last_authorization_epoch"):
        op.add_column(
            CONSENT_TABLE,
            sa.Column(
                "last_authorization_epoch",
                sa.BigInteger(),
                server_default=sa.text("0"),
                nullable=True,
            ),
        )
    if not _column_exists(CONSENT_TABLE, "revocation_epoch"):
        op.add_column(
            CONSENT_TABLE,
            sa.Column("revocation_epoch", sa.BigInteger(), nullable=True),
        )

    # In-flight legacy authorizations receive the earliest sequence values.
    # Existing revocation tombstones are deliberately allocated afterwards so
    # no pre-upgrade callback can revive a revoked connected client.
    op.execute(
        sa.text(
            f"UPDATE {CAPACITY_TABLE} "
            f"SET authorization_epoch = nextval('{EPOCH_SEQUENCE}') "
            "WHERE authorization_epoch IS NULL"
        )
    )
    op.execute(
        sa.text(
            f"UPDATE {CONSENT_TABLE} "
            "SET last_authorization_epoch = 0 "
            "WHERE last_authorization_epoch IS NULL"
        )
    )
    op.execute(
        sa.text(
            f"UPDATE {CONSENT_TABLE} "
            f"SET revocation_epoch = nextval('{EPOCH_SEQUENCE}') "
            "WHERE revoked_at IS NOT NULL AND revocation_epoch IS NULL"
        )
    )

    op.alter_column(
        CAPACITY_TABLE,
        "authorization_epoch",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.alter_column(
        CONSENT_TABLE,
        "last_authorization_epoch",
        existing_type=sa.BigInteger(),
        server_default=sa.text("0"),
        nullable=False,
    )


def downgrade() -> None:
    if _column_exists(CONSENT_TABLE, "revocation_epoch"):
        op.drop_column(CONSENT_TABLE, "revocation_epoch")
    if _column_exists(CONSENT_TABLE, "last_authorization_epoch"):
        op.drop_column(CONSENT_TABLE, "last_authorization_epoch")
    if _column_exists(CAPACITY_TABLE, "authorization_epoch"):
        op.drop_column(CAPACITY_TABLE, "authorization_epoch")
    # Causal epochs must never be reused. Preserve the sequence and its
    # high-water mark so a subsequent re-upgrade resumes above every epoch
    # issued before the downgrade.
