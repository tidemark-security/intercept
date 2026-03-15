"""Increase username column to 1024 characters.

Revision ID: 008_username_len_1024
Revises: 007_unified_audit_logs
Create Date: 2026-03-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '008_username_len_1024'
down_revision: Union[str, None] = '007_unified_audit_logs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('user_accounts', 'username',
               existing_type=sa.VARCHAR(length=64),
               type_=sa.String(length=1024),
               existing_nullable=False)


def downgrade() -> None:
    op.alter_column('user_accounts', 'username',
               existing_type=sa.String(length=1024),
               type_=sa.VARCHAR(length=64),
               existing_nullable=False)
