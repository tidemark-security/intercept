from __future__ import annotations

import re
from pathlib import Path

from db_migrations.v0_6_0 import auth


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_auth_session_cron_jobs_target_the_existing_table() -> None:
    assert auth.AUTH_SESSION_MAINTENANCE_JOBS == (
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
        for job in auth.AUTH_SESSION_MAINTENANCE_JOBS
    )


def test_upgrade_upserts_each_corrected_job(monkeypatch) -> None:
    scheduled: list[dict[str, str]] = []
    monkeypatch.setattr(auth, "schedule_cron_job", lambda **job: scheduled.append(job))

    auth.schedule_session_jobs()

    assert scheduled == list(auth.AUTH_SESSION_MAINTENANCE_JOBS)


def test_downgrade_removes_corrected_jobs_without_restoring_stale_commands(monkeypatch) -> None:
    unscheduled: list[str] = []
    monkeypatch.setattr(
        auth,
        "unschedule_cron_job",
        lambda *, name: unscheduled.append(name),
    )

    auth.remove_session_jobs()

    assert unscheduled == [
        "cleanup-expired-sessions",
        "vacuum-sessions-table",
    ]


def test_pgcron_bootstrap_comment_does_not_reference_a_nonexistent_migration() -> None:
    bootstrap_sql = (PROJECT_ROOT / "backend" / "init-pgcron.sql").read_text()

    assert "002_pgcron_jobs.py" not in bootstrap_sql
    assert "Job scheduling is handled by Alembic migrations" in bootstrap_sql
