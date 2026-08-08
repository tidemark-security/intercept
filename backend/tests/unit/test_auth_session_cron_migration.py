from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    PROJECT_ROOT
    / "backend"
    / "db_migrations"
    / "versions"
    / "015_auth_session_cron_jobs.py"
)


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("auth_session_cron_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_auth_session_cron_migration_is_next_revision() -> None:
    migration = _load_migration_module()

    assert migration.revision == "015_auth_session_cron_jobs"
    assert migration.down_revision == "014_fastmcp_auth_storage"


def test_auth_session_cron_jobs_target_the_existing_table() -> None:
    migration = _load_migration_module()

    assert migration.AUTH_SESSION_MAINTENANCE_JOBS == (
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
    assert all(
        re.search(r"\bauth_sessions\b", job["command"])
        and re.search(r"\bsessions\b", job["command"]) is None
        for job in migration.AUTH_SESSION_MAINTENANCE_JOBS
    )


def test_upgrade_upserts_each_corrected_job(monkeypatch) -> None:
    migration = _load_migration_module()
    scheduled: list[dict[str, str]] = []
    monkeypatch.setattr(migration, "schedule_cron_job", lambda **job: scheduled.append(job))

    migration.upgrade()

    assert scheduled == list(migration.AUTH_SESSION_MAINTENANCE_JOBS)


def test_downgrade_removes_corrected_jobs_without_restoring_stale_commands(monkeypatch) -> None:
    migration = _load_migration_module()
    unscheduled: list[str] = []
    monkeypatch.setattr(
        migration,
        "unschedule_cron_job",
        lambda *, name: unscheduled.append(name),
    )

    migration.downgrade()

    assert unscheduled == [
        "cleanup-expired-sessions",
        "vacuum-sessions-table",
    ]


def test_pgcron_bootstrap_comment_does_not_reference_a_nonexistent_migration() -> None:
    bootstrap_sql = (PROJECT_ROOT / "backend" / "init-pgcron.sql").read_text()

    assert "002_pgcron_jobs.py" not in bootstrap_sql
    assert "Job scheduling is handled by Alembic migrations" in bootstrap_sql
