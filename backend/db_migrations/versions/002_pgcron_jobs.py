"""Schedule pg_cron maintenance and refresh jobs

Revision ID: 002_pgcron_jobs
Revises: 001_initial
Create Date: 2026-02-07

Moves pg_cron job scheduling from init-pgcron.sql (which only runs on fresh
Docker volumes) into Alembic so that jobs are automatically created/updated
on every deployment.

This migration opens a separate connection to the `postgres` database (where
pg_cron lives) to call cron.schedule(). The Alembic transaction on
intercept_case_db is unaffected.

Prerequisites (one-time, requires superuser / rds_superuser):
  - CREATE EXTENSION pg_cron;                      -- in postgres database
  - GRANT USAGE ON SCHEMA cron TO intercept_user;  -- in postgres database

These are handled by init-pgcron.sql for Docker deployments.
For AWS RDS/Aurora, an admin must run them manually once (see docs).

If pg_cron is not available (e.g. dev/test without it), the migration logs
a warning and succeeds — it does not block schema migrations.
"""
from typing import Sequence, Union

from db_migrations.cron_utils import schedule_cron_job, unschedule_cron_job

# revision identifiers, used by Alembic.
revision: str = "002_pgcron_jobs"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ============================================================================
# Job definitions — single source of truth for all pg_cron jobs
# ============================================================================

CRON_JOBS = [
    # -- Maintenance jobs --
    {
        "name": "cleanup-expired-sessions",
        "schedule": "0 3 * * *",
        "command": "DELETE FROM sessions WHERE expires_at < NOW() - INTERVAL '90 days';",
    },
    {
        "name": "vacuum-sessions-table",
        "schedule": "30 3 * * *",
        "command": "VACUUM ANALYZE sessions;",
    },
    {
        "name": "cleanup-deactivated-users",
        "schedule": "0 4 * * 0",
        "command": (
            "UPDATE user_accounts SET password_hash = NULL "
            "WHERE status = 'DISABLED' "
            "AND updated_at < NOW() - INTERVAL '30 days' "
            "AND password_hash IS NOT NULL;"
        ),
    },
    # -- Materialized view refresh jobs (staggered every 15 min) --
    {
        "name": "refresh-soc-metrics-15m",
        "schedule": "1,16,31,46 * * * *",
        "command": "REFRESH MATERIALIZED VIEW CONCURRENTLY soc_metrics_15m;",
    },
    {
        "name": "refresh-analyst-metrics-15m",
        "schedule": "2,17,32,47 * * * *",
        "command": "REFRESH MATERIALIZED VIEW CONCURRENTLY analyst_metrics_15m;",
    },
    {
        "name": "refresh-alert-metrics-15m",
        "schedule": "3,18,33,48 * * * *",
        "command": "REFRESH MATERIALIZED VIEW CONCURRENTLY alert_metrics_15m;",
    },
]


def upgrade() -> None:
    for job in CRON_JOBS:
        schedule_cron_job(
            name=job["name"],
            schedule=job["schedule"],
            command=job["command"],
        )


def downgrade() -> None:
    for job in CRON_JOBS:
        unschedule_cron_job(name=job["name"])
