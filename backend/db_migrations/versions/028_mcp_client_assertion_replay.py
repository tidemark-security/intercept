"""Persist FastMCP private_key_jwt replay claims across workers.

Revision ID: 028_mcp_assertion_replay
Revises: 027_password_verify_capacity
Create Date: 2026-08-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from db_migrations.cron_utils import schedule_cron_job, unschedule_cron_job


revision: str = "028_mcp_assertion_replay"
down_revision: Union[str, None] = "027_password_verify_capacity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MCP_ASSERTION_REPLAY_CLEANUP_JOB = {
    "schedule": "* * * * *",
    "command": (
        "WITH expired AS ("
        "SELECT ctid FROM public.mcp_oauth_client_assertion_jtis "
        "WHERE expires_at <= clock_timestamp() "
        "ORDER BY expires_at LIMIT 10000 FOR UPDATE SKIP LOCKED"
        ") DELETE FROM public.mcp_oauth_client_assertion_jtis target "
        "USING expired WHERE target.ctid = expired.ctid;"
    ),
}
MCP_ASSERTION_REPLAY_CLEANUP_JOB_NAME_PREFIX = (
    "cleanup-mcp-client-assertion-jtis"
)


def assertion_replay_cleanup_job(target_database: str) -> dict[str, str]:
    """Return a pg_cron job name isolated to one target database."""

    return {
        **MCP_ASSERTION_REPLAY_CLEANUP_JOB,
        "name": (
            f"{MCP_ASSERTION_REPLAY_CLEANUP_JOB_NAME_PREFIX}:"
            f"{target_database}"
        ),
    }


def upgrade() -> None:
    op.create_table(
        "mcp_oauth_client_assertion_jtis",
        sa.Column("client_id_hash", sa.String(length=64), nullable=False),
        sa.Column("jti_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("client_id_hash", "jti_hash"),
    )
    op.create_index(
        "ix_mcp_oauth_client_assertion_jtis_expires_at",
        "mcp_oauth_client_assertion_jtis",
        ["expires_at"],
        unique=False,
    )
    target_database = str(
        op.get_bind().execute(sa.text("SELECT current_database()"))
        .scalar_one()
    )
    schedule_cron_job(
        **assertion_replay_cleanup_job(target_database),
        database=target_database,
        strict=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    target_database = str(
        bind.execute(sa.text("SELECT current_database()"))
        .scalar_one()
    )
    bind.execute(
        sa.text(
            "LOCK TABLE mcp_oauth_client_assertion_jtis "
            "IN ACCESS EXCLUSIVE MODE"
        )
    )
    active_claims = bind.execute(
        sa.text(
            "SELECT count(*) FROM mcp_oauth_client_assertion_jtis "
            "WHERE expires_at > clock_timestamp()"
        )
    ).scalar_one()
    if int(active_claims or 0) > 0:
        raise RuntimeError(
            "Refusing to downgrade MCP client assertion replay protection "
            "while unexpired claims exist"
        )

    unschedule_cron_job(
        name=assertion_replay_cleanup_job(target_database)["name"],
        strict=True,
    )
    op.drop_index(
        "ix_mcp_oauth_client_assertion_jtis_expires_at",
        table_name="mcp_oauth_client_assertion_jtis",
    )
    op.drop_table("mcp_oauth_client_assertion_jtis")
