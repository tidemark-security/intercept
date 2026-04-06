# pg_cron Setup for Automated Session Cleanup

## Overview

The Intercept application uses PostgreSQL's `pg_cron` extension to automatically clean up expired sessions and deactivated user credentials, ensuring GDPR compliance and optimal database performance.

## Scheduled Jobs

### 1. cleanup-expired-sessions
- **Schedule**: Daily at 3:00 AM UTC
- **Purpose**: Delete sessions expired more than 90 days ago (GDPR retention policy)
- **Query**: `DELETE FROM sessions WHERE expires_at < NOW() - INTERVAL '90 days'`
- **Retention**: 90 days after expiry for audit/forensic purposes

### 2. vacuum-sessions-table
- **Schedule**: Daily at 3:30 AM UTC
- **Purpose**: Reclaim storage and update statistics after cleanup
- **Query**: `VACUUM ANALYZE sessions`
- **Impact**: Improves query performance and reduces table bloat

### 3. cleanup-deactivated-users
- **Schedule**: Weekly on Sunday at 4:00 AM UTC
- **Purpose**: Purge password hashes 30 days after account deactivation
- **Query**: `UPDATE users SET password_hash = NULL WHERE status = 'DISABLED' AND updated_at < NOW() - INTERVAL '30 days' AND password_hash IS NOT NULL`
- **Retention**: 30-day grace period for account reactivation

## Setup Instructions

### Docker Compose (Development)

The `dev/docker-compose.yml` already configures pg_cron:

```yaml
services:
  postgres:
    build:
      context: ./backend
      dockerfile: Dockerfile.postgres
    command: 
      - "postgres"
      - "-c"
      - "shared_preload_libraries=pg_cron"
      - "-c"
      - "cron.database_name=postgres"  # pg_cron metadata stored in postgres database
```

Jobs are automatically created via `init-pgcron.sql` on first database initialization.
The jobs themselves run against `intercept_case_db` (configured via UPDATE in init script).

### Existing Database (Production)

For existing databases, run the Alembic migration:

```bash
cd backend
alembic upgrade head
```

This executes migration `f2baf0be5a5a_add_pgcron_cleanup_jobs.py` which:
1. Enables `pg_cron` extension
2. Schedules all three cleanup jobs

### Manual Setup (Cloud Providers)

Some managed PostgreSQL services (AWS RDS, Azure Database) may require manual pg_cron configuration.

#### AWS RDS PostgreSQL

1. Add `pg_cron` to parameter group:
   ```
   shared_preload_libraries = pg_cron
   ```

2. Restart database instance

3. Enable extension in your database:
   ```sql
   CREATE EXTENSION pg_cron;
   ```

4. Run Alembic migration or execute SQL from migration file

#### Azure Database for PostgreSQL

1. Enable `pg_cron` in server parameters:
   ```
   shared_preload_libraries = pg_cron
   cron.database_name = intercept_case_db
   ```

2. Restart server

3. Run Alembic migration

## Monitoring

### View Scheduled Jobs

```sql
SELECT * FROM cron.job;
```

Expected output:
```
 jobid |          jobname           | schedule  |                                command                                
-------+----------------------------+-----------+----------------------------------------------------------------------
     1 | cleanup-expired-sessions   | 0 3 * * * | DELETE FROM sessions WHERE expires_at < NOW() - INTERVAL '90 days'
     2 | vacuum-sessions-table      | 30 3 * * *| VACUUM ANALYZE sessions
     3 | cleanup-deactivated-users  | 0 4 * * 0 | UPDATE users SET password_hash = NULL WHERE ...
```

### View Job Run History

```sql
SELECT 
    jobid,
    runid,
    job_pid,
    database,
    username,
    command,
    status,
    return_message,
    start_time,
    end_time
FROM cron.job_run_details
ORDER BY start_time DESC
LIMIT 10;
```

### Check Last Run Status

```sql
SELECT 
    j.jobname,
    d.status,
    d.return_message,
    d.start_time,
    d.end_time,
    d.end_time - d.start_time AS duration
FROM cron.job j
LEFT JOIN cron.job_run_details d ON j.jobid = d.jobid
WHERE d.runid = (
    SELECT MAX(runid) 
    FROM cron.job_run_details 
    WHERE jobid = j.jobid
)
ORDER BY j.jobname;
```

## Troubleshooting

### pg_cron Extension Not Available

**Error**: `extension "pg_cron" is not available`

**Solution**: Install pg_cron extension:
```bash
# Ubuntu/Debian
sudo apt-get install postgresql-15-cron

# Restart PostgreSQL
sudo systemctl restart postgresql
```

### Jobs Not Running

**Check 1**: Verify `shared_preload_libraries` configuration:
```sql
SHOW shared_preload_libraries;
-- Should include 'pg_cron'
```

**Check 2**: Verify `cron.database_name` matches your database:
```sql
SHOW cron.database_name;
-- Should be 'intercept_case_db'
```

**Check 3**: Check job run history for errors:
```sql
SELECT * FROM cron.job_run_details 
WHERE status = 'failed' 
ORDER BY start_time DESC;
```

### Permission Denied Errors

Grant necessary permissions:
```sql
GRANT USAGE ON SCHEMA cron TO intercept_user;
GRANT DELETE ON sessions TO intercept_user;
GRANT UPDATE ON users TO intercept_user;
```

## Manual Cleanup (Emergency)

If pg_cron is unavailable or you need immediate cleanup:

```sql
-- Cleanup expired sessions
DELETE FROM sessions WHERE expires_at < NOW() - INTERVAL '90 days';

-- Vacuum sessions table
VACUUM ANALYZE sessions;

-- Cleanup deactivated user credentials
UPDATE users 
SET password_hash = NULL 
WHERE status = 'DISABLED' 
  AND updated_at < NOW() - INTERVAL '30 days'
  AND password_hash IS NOT NULL;
```

## Modifying Job Schedules

Update job schedule via SQL:

```sql
-- Change cleanup time to 2 AM
SELECT cron.alter_job(
    (SELECT jobid FROM cron.job WHERE jobname = 'cleanup-expired-sessions'),
    schedule := '0 2 * * *'
);
```

Or unschedule and reschedule:

```sql
-- Remove old job
SELECT cron.unschedule('cleanup-expired-sessions');

-- Create new job with different schedule
SELECT cron.schedule(
    'cleanup-expired-sessions',
    '0 2 * * *',  -- New time: 2 AM
    $$DELETE FROM sessions WHERE expires_at < NOW() - INTERVAL '90 days'$$
);
```

## Testing

Manually trigger a job:

```sql
-- Trigger cleanup immediately (for testing)
DELETE FROM sessions WHERE expires_at < NOW() - INTERVAL '90 days';

-- Check row count
SELECT COUNT(*) FROM sessions;

-- Verify VACUUM
VACUUM ANALYZE sessions;
```

## References

- [pg_cron Documentation](https://github.com/citusdata/pg_cron)
- [GDPR Compliance Document](../specs/001-add-username-and/GDPR-COMPLIANCE.md)
- [Research: Session Management](../specs/001-add-username-and/research.md#2-session-management-with-fastapi-and-postgresql)

## Support

For issues or questions:
- Backend README: `/backend/README.md`
- Database migrations: `db_migrations/versions/`
- Docker setup: `dev/docker-compose.yml`
