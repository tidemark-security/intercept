# Development Seeding

How to seed development data into a fresh Intercept environment.

## Overview

The backend currently includes two commonly used seed scripts:

| Script | Purpose | Idempotent behavior |
|--------|---------|---------------------|
| `seed_test_users.py` | Creates or resets the default local test accounts | Resets passwords and account state back to defaults |
| `seed_link_templates.py` | Populates the default link template catalog | Adds missing templates and updates existing template metadata |

The recommended way to run these scripts is inside the running `backend` container so they use the same Python environment, settings, and database connection as the application.

## Prerequisites

Start the application stack first:

```bash
conda activate intercept
cd ~/projects/tmi
docker compose up -d
```

If you want a completely fresh database first:

```bash
conda activate intercept
cd ~/projects/tmi
docker compose rm -fsv postgres backend worker
docker volume rm tmi_postgres_data
docker compose up -d postgres backend worker
```

## Run the Seed Scripts

Run the scripts from the host by exec'ing into the backend container:

```bash
conda activate intercept
cd ~/projects/tmi

docker compose exec -T -e PYTHONPATH=/app backend python /app/scripts/seed_test_users.py
docker compose exec -T -e PYTHONPATH=/app backend python /app/scripts/seed_link_templates.py
```

### Why `PYTHONPATH=/app`?

The scripts import modules from the backend package as `app.*`. Setting `PYTHONPATH=/app` ensures those imports resolve correctly in non-interactive `docker compose exec` sessions.

## What Gets Seeded

### Test users

`seed_test_users.py` creates or resets these accounts:

| Role | Username | Password |
|------|----------|----------|
| `ADMIN` | `admin` | `admin` |
| `ANALYST` | `analyst` | `analyst` |
| `AUDITOR` | `auditor` | `auditor` |

The script also resets each seeded account to a usable local-dev state:

- status set to `ACTIVE`
- password reset to the default listed above
- `must_change_password` cleared
- lockout and failed login counters cleared

### Link templates

`seed_link_templates.py` seeds the default `link_templates` rows used by the UI and backend API.

Expected default behavior:

- organization-agnostic templates such as email, phone, and VirusTotal are enabled
- organization-specific placeholders such as Slack, CMDB, and directory links are created disabled by default
- rerunning the script preserves existing `enabled` choices for templates that already exist

## Verification

Check backend logs if a seed command fails:

```bash
conda activate intercept
cd ~/projects/tmi
docker compose logs --tail=100 backend
```

You can also verify the seeded data directly:

```bash
conda activate intercept
cd ~/projects/tmi

docker compose exec -T postgres psql -U intercept_user -d intercept_case_db \
  -c "SELECT username, role, status FROM user_accounts ORDER BY username;"

docker compose exec -T postgres psql -U intercept_user -d intercept_case_db \
  -c "SELECT template_id, enabled, display_order FROM link_templates ORDER BY display_order;"
```

## Notes

- These scripts are intended for local development and QA bootstrap.
- They are safe to rerun.
- If you add new seed scripts later, prefer documenting them here and using the same `docker compose exec -T -e PYTHONPATH=/app backend ...` pattern.