"""Correct pg_cron maintenance jobs for auth sessions.

Revision ID: 015_auth_session_cron_jobs
Revises: 014_fastmcp_auth_storage
Create Date: 2026-07-19
"""
from __future__ import annotations

from typing import Sequence, Union

from db_migrations.cron_utils import schedule_cron_job, unschedule_cron_job


revision: str = "015_auth_session_cron_jobs"
down_revision: Union[str, None] = "014_fastmcp_auth_storage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


AUTH_SESSION_MAINTENANCE_JOBS = (
    {
        "name": "cleanup-expired-sessions",
        "schedule": "0 3 * * *",
        "command": "DELETE FROM auth_sessions WHERE expires_at < NOW() - INTERVAL '90 days';",
    },
    {
        "name": "vacuum-sessions-table",
        "schedule": "30 3 * * *",
        "command": "VACUUM ANALYZE auth_sessions;",
    },
)


def upgrade() -> None:
    # Named scheduling is an idempotent upsert, so this replaces the stale
    # commands installed by the initial migration without a scheduling gap.
    for job in AUTH_SESSION_MAINTENANCE_JOBS:
        schedule_cron_job(**job)


def downgrade() -> None:
    # Do not restore commands that target the nonexistent `sessions` table.
    for job in AUTH_SESSION_MAINTENANCE_JOBS:
        unschedule_cron_job(name=job["name"])
