"""Add shared timeline graph persistence.

Revision ID: 004_timeline_graphs
Revises: 003_timeline_obj_store
Create Date: 2026-05-02
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "004_timeline_graphs"
down_revision: Union[str, None] = "003_timeline_obj_store"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "timeline_graphs" in inspector.get_table_names():
        existing_indexes = {index["name"] for index in inspector.get_indexes("timeline_graphs")}
        if "ix_timeline_graphs_entity" not in existing_indexes:
            op.create_index("ix_timeline_graphs_entity", "timeline_graphs", ["entity_type", "entity_id"], unique=False)
        return

    op.create_table(
        "timeline_graphs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("graph", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{\"nodes\": {}, \"edges\": {}}'::jsonb")),
        sa.Column("graph_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{\"nodes\": {}, \"edges\": {}, \"deleted_nodes\": {}, \"deleted_edges\": {}}'::jsonb")),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("updated_by", sa.String(length=100), nullable=True),
        sa.CheckConstraint("entity_type IN ('case', 'task')", name="ck_timeline_graphs_entity_type"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_type", "entity_id", name="uq_timeline_graphs_entity"),
    )
    op.create_index("ix_timeline_graphs_entity", "timeline_graphs", ["entity_type", "entity_id"], unique=False)
    op.alter_column("timeline_graphs", "graph", server_default=None)
    op.alter_column("timeline_graphs", "graph_meta", server_default=None)
    op.alter_column("timeline_graphs", "revision", server_default=None)
    op.alter_column("timeline_graphs", "created_at", server_default=None)
    op.alter_column("timeline_graphs", "updated_at", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_timeline_graphs_entity", table_name="timeline_graphs")
    op.drop_table("timeline_graphs")