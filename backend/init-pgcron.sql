-- Initialize pg_cron extension (superuser prerequisites only)
-- This script runs ONCE when the postgres volume is first created.
-- It handles the two operations that require superuser / rds_superuser:
--   1. CREATE EXTENSION pg_cron
--   2. GRANT USAGE ON SCHEMA cron TO intercept_user
--
-- Job scheduling is handled by Alembic migration 002_pgcron_jobs.py,
-- which connects to this database and calls cron.schedule() as intercept_user.
--
-- For AWS RDS/Aurora: These two commands must be run manually once by a
-- user with the rds_superuser role. See docs/database-schema-management.md.

-- Switch to postgres database where pg_cron metadata lives
\c postgres

-- Enable pg_cron extension (requires superuser / rds_superuser)
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Grant cron schema access to the application user so Alembic migrations
-- (and the app itself) can schedule jobs without elevated privileges.
GRANT USAGE ON SCHEMA cron TO intercept_user;
