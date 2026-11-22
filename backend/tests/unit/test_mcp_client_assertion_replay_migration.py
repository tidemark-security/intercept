"""Migration and pg_cron contract for MCP client assertion replay claims."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from db_migrations.v0_6_0 import assertion_replay


def test_upgrade_creates_ledger_before_scheduling_cleanup(monkeypatch) -> None:
    events: list[tuple[str, object]] = []
    operations = SimpleNamespace(
        create_table=lambda name, *columns: events.append(("create_table", name)),
        create_index=lambda name, *args, **kwargs: events.append(("create_index", name)),
        get_bind=lambda: _Bind(active_claims=0),
    )
    monkeypatch.setattr(assertion_replay, "op", operations)
    monkeypatch.setattr(
        assertion_replay,
        "schedule_cron_job",
        lambda **job: events.append(("schedule", job)),
    )

    assertion_replay.upgrade()

    assert events == [
        ("create_table", "mcp_oauth_client_assertion_jtis"),
        ("create_index", "ix_mcp_oauth_client_assertion_jtis_expires_at"),
        (
            "schedule",
            {
                **assertion_replay.MCP_ASSERTION_REPLAY_CLEANUP_JOB,
                "name": (
                    "cleanup-mcp-client-assertion-jtis:intercept_test"
                ),
                "database": "intercept_test",
                "strict": True,
            },
        ),
    ]
    assert assertion_replay.MCP_ASSERTION_REPLAY_CLEANUP_JOB == {
        "schedule": "* * * * *",
        "command": (
            "WITH expired AS (SELECT ctid FROM "
            "public.mcp_oauth_client_assertion_jtis WHERE expires_at <= "
            "clock_timestamp() ORDER BY expires_at LIMIT 10000 FOR UPDATE "
            "SKIP LOCKED) DELETE FROM public.mcp_oauth_client_assertion_jtis "
            "target USING expired WHERE target.ctid = expired.ctid;"
        ),
    }


def test_cleanup_jobs_are_namespaced_for_shared_pg_cron_catalogs() -> None:
    first = assertion_replay.assertion_replay_cleanup_job("intercept_one")
    second = assertion_replay.assertion_replay_cleanup_job("intercept_two")

    assert first["name"] == (
        "cleanup-mcp-client-assertion-jtis:intercept_one"
    )
    assert second["name"] == (
        "cleanup-mcp-client-assertion-jtis:intercept_two"
    )
    assert first["name"] != second["name"]


class _Bind:
    def __init__(self, active_claims: int) -> None:
        self.active_claims = active_claims

    def execute(self, statement):
        if str(statement).startswith("SELECT current_database"):
            return SimpleNamespace(scalar_one=lambda: "intercept_test")
        if str(statement).startswith("SELECT count"):
            return SimpleNamespace(scalar_one=lambda: self.active_claims)
        return SimpleNamespace()


def test_downgrade_refuses_to_remove_unexpired_replay_claims(monkeypatch) -> None:
    unscheduled: list[str] = []
    monkeypatch.setattr(assertion_replay, "op", SimpleNamespace(get_bind=lambda: _Bind(active_claims=1)))
    monkeypatch.setattr(
        assertion_replay,
        "unschedule_cron_job",
        lambda *, name, strict: unscheduled.append(name),
    )

    with pytest.raises(RuntimeError, match="unexpired claims"):
        assertion_replay.downgrade()

    assert unscheduled == []


def test_downgrade_unschedules_before_dropping_ledger(monkeypatch) -> None:
    events: list[tuple[str, str]] = []
    operations = SimpleNamespace(
        get_bind=lambda: _Bind(active_claims=0),
        drop_index=lambda name, **kwargs: events.append(("drop_index", name)),
        drop_table=lambda name: events.append(("drop_table", name)),
    )
    monkeypatch.setattr(assertion_replay, "op", operations)
    monkeypatch.setattr(
        assertion_replay,
        "unschedule_cron_job",
        lambda *, name, strict: events.append(
            ("unschedule_strict" if strict else "unschedule", name)
        ),
    )

    assertion_replay.downgrade()

    assert events == [
        (
            "unschedule_strict",
            "cleanup-mcp-client-assertion-jtis:intercept_test",
        ),
        ("drop_index", "ix_mcp_oauth_client_assertion_jtis_expires_at"),
        ("drop_table", "mcp_oauth_client_assertion_jtis"),
    ]
