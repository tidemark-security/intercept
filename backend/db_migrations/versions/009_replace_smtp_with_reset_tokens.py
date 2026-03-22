"""Replace SMTP credential delivery with reset tokens.

Revision ID: 009_reset_tokens
Revises: 008_username_len_1024
Create Date: 2026-03-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "009_reset_tokens"
down_revision: Union[str, None] = "008_username_len_1024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "admin_reset_requests",
        sa.Column("token_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_admin_reset_requests_token_hash"),
        "admin_reset_requests",
        ["token_hash"],
        unique=False,
    )
    op.execute(
        "UPDATE admin_reset_requests SET token_hash = temporary_secret_hash WHERE token_hash IS NULL"
    )
    op.alter_column("admin_reset_requests", "token_hash", nullable=False)
    op.drop_column("admin_reset_requests", "delivery_reference")
    op.drop_column("admin_reset_requests", "delivery_channel")
    op.drop_column("admin_reset_requests", "temporary_secret_hash")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS resetdeliverychannel")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        resetdeliverychannel = sa.Enum("SECURE_EMAIL", name="resetdeliverychannel")
        resetdeliverychannel.create(bind, checkfirst=True)
        delivery_channel_type: sa.types.TypeEngine[str] = resetdeliverychannel
    else:
        delivery_channel_type = sa.String(length=32)

    op.add_column(
        "admin_reset_requests",
        sa.Column("temporary_secret_hash", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "admin_reset_requests",
        sa.Column("delivery_channel", delivery_channel_type, nullable=True),
    )
    op.add_column(
        "admin_reset_requests",
        sa.Column("delivery_reference", sa.String(length=255), nullable=True),
    )
    op.execute(
        "UPDATE admin_reset_requests SET temporary_secret_hash = token_hash, delivery_channel = 'SECURE_EMAIL' WHERE temporary_secret_hash IS NULL"
    )
    op.alter_column("admin_reset_requests", "temporary_secret_hash", nullable=False)
    op.drop_index(op.f("ix_admin_reset_requests_token_hash"), table_name="admin_reset_requests")
    op.drop_column("admin_reset_requests", "token_hash")