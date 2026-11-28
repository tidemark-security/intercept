"""Add revisioned custom dashboard definitions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "034_custom_dashboards"
down_revision = "033_saved_queue_filters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_dashboards",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("user_accounts.id", ondelete="CASCADE")),
        sa.Column("scope", sa.String(length=12), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("definition", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(scope = 'personal' AND owner_id IS NOT NULL) OR "
            "(scope = 'organization' AND owner_id IS NULL)",
            name="ck_custom_dashboards_scope_owner",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_custom_dashboards_revision"),
    )
    op.create_index("ix_custom_dashboards_scope_owner", "custom_dashboards", ["scope", "owner_id"])


def downgrade() -> None:
    op.drop_table("custom_dashboards")
