"""Add OIDC support models and user linkage

Revision ID: 005_oidc_support
Revises: 004_index_top_level_tags_in_search_vector
Create Date: 2026-03-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect


revision: str = "005_oidc_support"
down_revision: Union[str, None] = "004_tags_in_search_vector"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(index_name: str, table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def _unique_constraint_exists(table_name: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return any(c["name"] == constraint_name for c in inspector.get_unique_constraints(table_name))


def upgrade() -> None:
    if not _column_exists("user_accounts", "oidc_subject"):
        op.add_column("user_accounts", sa.Column("oidc_subject", sa.String(length=255), nullable=True))
    if not _column_exists("user_accounts", "oidc_issuer"):
        op.add_column("user_accounts", sa.Column("oidc_issuer", sa.String(length=500), nullable=True))
    if not _unique_constraint_exists("user_accounts", "uq_user_accounts_oidc_identity"):
        op.create_unique_constraint(
            "uq_user_accounts_oidc_identity",
            "user_accounts",
            ["oidc_issuer", "oidc_subject"],
        )

    if not _table_exists("oidc_auth_requests"):
        op.create_table(
            "oidc_auth_requests",
            sa.Column("state", sa.String(length=255), nullable=False),
            sa.Column("nonce", sa.String(length=255), nullable=False),
            sa.Column("redirect_to", sa.String(length=2048), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("state"),
        )
    if not _index_exists("ix_oidc_auth_requests_expires_at", "oidc_auth_requests"):
        op.create_index("ix_oidc_auth_requests_expires_at", "oidc_auth_requests", ["expires_at"], unique=False)


def downgrade() -> None:
    if _index_exists("ix_oidc_auth_requests_expires_at", "oidc_auth_requests"):
        op.drop_index("ix_oidc_auth_requests_expires_at", table_name="oidc_auth_requests")
    if _table_exists("oidc_auth_requests"):
        op.drop_table("oidc_auth_requests")

    if _unique_constraint_exists("user_accounts", "uq_user_accounts_oidc_identity"):
        op.drop_constraint("uq_user_accounts_oidc_identity", "user_accounts", type_="unique")
    if _column_exists("user_accounts", "oidc_issuer"):
        op.drop_column("user_accounts", "oidc_issuer")
    if _column_exists("user_accounts", "oidc_subject"):
        op.drop_column("user_accounts", "oidc_subject")