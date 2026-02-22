"""Utilities for managing pg_cron jobs from Alembic migrations.

pg_cron's extension and metadata live in the `postgres` database, but Alembic
connects to `intercept_case_db`. This module opens a separate psycopg2
connection to the cron database so migrations can schedule/unschedule jobs.

Prerequisites (one-time, requires superuser / rds_superuser):
  1. CREATE EXTENSION pg_cron;          -- in the postgres database
  2. GRANT USAGE ON SCHEMA cron TO intercept_user;

These are handled by init-pgcron.sql (Docker) or manually on RDS/Aurora.
Once granted, intercept_user can call cron.schedule() without elevated privileges.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator
from urllib.parse import urlparse, urlunparse

import psycopg2

logger = logging.getLogger("db_migrations.cron_utils")


def _get_cron_database_url() -> str:
    """Derive a psycopg2 connection URL for the pg_cron database.

    Takes DATABASE_URL (which targets intercept_case_db) and swaps the
    database name to the cron database. The cron database can be overridden
    via PGCRON_DATABASE env var (defaults to ``postgres``).

    This supports both self-hosted Docker deployments and managed services
    like AWS RDS / Aurora where pg_cron always lives in ``postgres``.
    """
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        # Fallback to alembic.ini default
        database_url = (
            "postgresql://intercept_user:intercept_password"
            "@localhost:5432/intercept_case_db"
        )

    # Convert asyncpg URL to psycopg2
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    cron_database = os.environ.get("PGCRON_DATABASE", "postgres")

    parsed = urlparse(sync_url)
    cron_url = urlunparse(parsed._replace(path=f"/{cron_database}"))
    return cron_url


@contextmanager
def _cron_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Context manager for a connection to the pg_cron database."""
    url = _get_cron_database_url()
    parsed = urlparse(url)
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        dbname=parsed.path.lstrip("/"),
    )
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


def _pg_cron_available(conn: psycopg2.extensions.connection) -> bool:
    """Check if the pg_cron extension is installed and accessible."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT 1 FROM pg_extension WHERE extname = 'pg_cron'"
        )
        if cursor.fetchone() is None:
            return False
        # Check schema access
        cursor.execute("SELECT 1 FROM cron.job LIMIT 0")
        return True
    except psycopg2.Error:
        conn.rollback()
        return False
    finally:
        cursor.close()


def schedule_cron_job(
    name: str,
    schedule: str,
    command: str,
    database: str = "intercept_case_db",
) -> None:
    """Schedule a pg_cron job (idempotent — upserts by name).

    Uses the named cron.schedule() overload which upserts: if a job with
    the same name already exists, its schedule/command are updated in place.
    Then sets the target database via UPDATE (compatible with all pg_cron
    versions and AWS RDS).

    Args:
        name: Unique job name (e.g. 'refresh-soc-metrics-15m').
        schedule: Cron expression (e.g. '1,16,31,46 * * * *').
        command: SQL command to execute.
        database: Target database for the job. Defaults to intercept_case_db.
    """
    try:
        with _cron_connection() as conn:
            if not _pg_cron_available(conn):
                logger.warning(
                    "pg_cron not available — skipping job '%s'. "
                    "Install pg_cron and GRANT USAGE ON SCHEMA cron to enable.",
                    name,
                )
                return

            cursor = conn.cursor()
            try:
                # Named cron.schedule() upserts: creates or updates by name
                cursor.execute(
                    "SELECT cron.schedule(%s, %s, %s)",
                    (name, schedule, command),
                )
                # Set target database (separate UPDATE for RDS compatibility —
                # avoids needing cron.schedule_in_database which is v1.4+)
                cursor.execute(
                    "UPDATE cron.job SET database = %s WHERE jobname = %s",
                    (database, name),
                )
                logger.info("Scheduled pg_cron job '%s' [%s]", name, schedule)
            finally:
                cursor.close()

    except psycopg2.Error as e:
        logger.warning(
            "Failed to schedule pg_cron job '%s': %s. "
            "This is non-fatal — schedule manually if needed.",
            name,
            e,
        )


def unschedule_cron_job(name: str) -> None:
    """Remove a pg_cron job by name (idempotent — no-op if not found).

    Args:
        name: The job name to remove.
    """
    try:
        with _cron_connection() as conn:
            if not _pg_cron_available(conn):
                logger.warning(
                    "pg_cron not available — skipping unschedule of '%s'.",
                    name,
                )
                return

            cursor = conn.cursor()
            try:
                # Check if job exists before unscheduling to avoid errors
                cursor.execute(
                    "SELECT 1 FROM cron.job WHERE jobname = %s",
                    (name,),
                )
                if cursor.fetchone() is not None:
                    cursor.execute("SELECT cron.unschedule(%s)", (name,))
                    logger.info("Unscheduled pg_cron job '%s'", name)
                else:
                    logger.info(
                        "pg_cron job '%s' not found — nothing to unschedule",
                        name,
                    )
            finally:
                cursor.close()

    except psycopg2.Error as e:
        logger.warning(
            "Failed to unschedule pg_cron job '%s': %s. "
            "This is non-fatal — remove manually if needed.",
            name,
            e,
        )
