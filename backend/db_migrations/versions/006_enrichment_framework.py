"""Add enrichment cache and alias tables

Revision ID: 006_enrichment_framework
Revises: 005_oidc_support
Create Date: 2026-03-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects import postgresql


revision: str = "006_enrichment_framework"
down_revision: Union[str, None] = "005_oidc_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(index_name: str, table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("enrichment_cache"):
        op.create_table(
            "enrichment_cache",
            sa.Column("provider_id", sa.String(length=100), nullable=False),
            sa.Column("cache_key", sa.String(length=500), nullable=False),
            sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider_id", "cache_key", name="uq_enrichment_cache_provider_key"),
        )

    if not _index_exists("ix_enrichment_cache_provider_id", "enrichment_cache"):
        op.create_index("ix_enrichment_cache_provider_id", "enrichment_cache", ["provider_id"], unique=False)
    if not _index_exists("ix_enrichment_cache_cache_key", "enrichment_cache"):
        op.create_index("ix_enrichment_cache_cache_key", "enrichment_cache", ["cache_key"], unique=False)
    if not _index_exists("ix_enrichment_cache_expires_at", "enrichment_cache"):
        op.create_index("ix_enrichment_cache_expires_at", "enrichment_cache", ["expires_at"], unique=False)

    if not _table_exists("enrichment_aliases"):
        op.create_table(
            "enrichment_aliases",
            sa.Column("provider_id", sa.String(length=100), nullable=False),
            sa.Column("entity_type", sa.String(length=100), nullable=False),
            sa.Column("canonical_value", sa.String(length=500), nullable=False),
            sa.Column("canonical_display", sa.String(length=200), nullable=True),
            sa.Column("alias_type", sa.String(length=100), nullable=False),
            sa.Column("alias_value", sa.String(length=500), nullable=False),
            sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "provider_id",
                "alias_type",
                "alias_value",
                name="uq_enrichment_alias_provider_type_value",
            ),
        )

    if not _index_exists("ix_enrichment_aliases_provider_id", "enrichment_aliases"):
        op.create_index("ix_enrichment_aliases_provider_id", "enrichment_aliases", ["provider_id"], unique=False)
    if not _index_exists("ix_enrichment_aliases_entity_type", "enrichment_aliases"):
        op.create_index("ix_enrichment_aliases_entity_type", "enrichment_aliases", ["entity_type"], unique=False)
    if not _index_exists("ix_enrichment_aliases_canonical_value", "enrichment_aliases"):
        op.create_index("ix_enrichment_aliases_canonical_value", "enrichment_aliases", ["canonical_value"], unique=False)
    if not _index_exists("ix_enrichment_aliases_alias_type", "enrichment_aliases"):
        op.create_index("ix_enrichment_aliases_alias_type", "enrichment_aliases", ["alias_type"], unique=False)
    if not _index_exists("ix_enrichment_aliases_alias_value", "enrichment_aliases"):
        op.create_index("ix_enrichment_aliases_alias_value", "enrichment_aliases", ["alias_value"], unique=False)


def downgrade() -> None:
    for index_name in (
        "ix_enrichment_aliases_alias_value",
        "ix_enrichment_aliases_alias_type",
        "ix_enrichment_aliases_canonical_value",
        "ix_enrichment_aliases_entity_type",
        "ix_enrichment_aliases_provider_id",
    ):
        if _index_exists(index_name, "enrichment_aliases"):
            op.drop_index(index_name, table_name="enrichment_aliases")
    if _table_exists("enrichment_aliases"):
        op.drop_table("enrichment_aliases")

    for index_name in (
        "ix_enrichment_cache_expires_at",
        "ix_enrichment_cache_cache_key",
        "ix_enrichment_cache_provider_id",
    ):
        if _index_exists(index_name, "enrichment_cache"):
            op.drop_index(index_name, table_name="enrichment_cache")
    if _table_exists("enrichment_cache"):
        op.drop_table("enrichment_cache")