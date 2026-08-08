"""Safety behavior for shared pg_cron migration helpers."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from db_migrations import cron_utils


class _Cursor:
    def __init__(self, fetches: list[tuple[object, ...] | None]) -> None:
        self._fetches = iter(fetches)
        self.executed: list[tuple[str, tuple[str, ...] | None]] = []

    def execute(self, statement: str, params: tuple[str, ...] | None = None) -> None:
        self.executed.append((statement, params))

    def fetchone(self) -> tuple[object, ...] | None:
        return next(self._fetches)

    def close(self) -> None:
        pass


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _Cursor:
        return self._cursor


def _install_connection(
    monkeypatch: pytest.MonkeyPatch,
    connection: _Connection,
) -> None:
    @contextmanager
    def factory():
        yield connection

    monkeypatch.setattr(cron_utils, "_cron_connection", factory)


def test_strict_schedule_verifies_exact_active_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = "DELETE FROM public.example WHERE expired"
    cursor = _Cursor([("* * * * *", command, "custom_database", True)])
    _install_connection(monkeypatch, _Connection(cursor))
    monkeypatch.setattr(cron_utils, "_pg_cron_available", lambda _conn: True)

    cron_utils.schedule_cron_job(
        "cleanup-test",
        "* * * * *",
        command,
        database="custom_database",
        strict=True,
    )

    assert cursor.executed[-1] == (
        "SELECT schedule, command, database, active FROM cron.job "
        "WHERE jobname = %s",
        ("cleanup-test",),
    )


def test_strict_schedule_keeps_database_namespaced_jobs_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = "DELETE FROM public.example WHERE expired"
    cursor = _Cursor(
        [
            ("* * * * *", command, "intercept_one", True),
            ("* * * * *", command, "intercept_two", True),
        ]
    )
    _install_connection(monkeypatch, _Connection(cursor))
    monkeypatch.setattr(cron_utils, "_pg_cron_available", lambda _conn: True)

    for database in ("intercept_one", "intercept_two"):
        cron_utils.schedule_cron_job(
            f"cleanup-test:{database}",
            "* * * * *",
            command,
            database=database,
            strict=True,
        )

    scheduled_names = [
        params[0]
        for statement, params in cursor.executed
        if statement == "SELECT cron.schedule(%s, %s, %s)"
        and params is not None
    ]
    assert scheduled_names == [
        "cleanup-test:intercept_one",
        "cleanup-test:intercept_two",
    ]


def test_strict_schedule_requires_pg_cron(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _Cursor([])
    _install_connection(monkeypatch, _Connection(cursor))
    monkeypatch.setattr(cron_utils, "_pg_cron_available", lambda _conn: False)
    monkeypatch.setattr(cron_utils, "unschedule_cron_job", lambda *args, **kwargs: None)

    with pytest.raises(
        cron_utils.CronJobManagementError,
        match="pg_cron is required",
    ):
        cron_utils.schedule_cron_job(
            "cleanup-test",
            "* * * * *",
            "SELECT 1",
            strict=True,
        )


def test_strict_unschedule_verifies_job_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _Cursor([(1,), None])
    _install_connection(monkeypatch, _Connection(cursor))
    monkeypatch.setattr(cron_utils, "_pg_cron_available", lambda _conn: True)

    cron_utils.unschedule_cron_job("cleanup-test", strict=True)

    assert [statement for statement, _params in cursor.executed] == [
        "SELECT 1 FROM cron.job WHERE jobname = %s",
        "SELECT cron.unschedule(%s)",
        "SELECT 1 FROM cron.job WHERE jobname = %s",
    ]


def test_strict_unschedule_refuses_to_leave_job_scheduled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _Cursor([(1,), (1,)])
    _install_connection(monkeypatch, _Connection(cursor))
    monkeypatch.setattr(cron_utils, "_pg_cron_available", lambda _conn: True)

    with pytest.raises(
        cron_utils.CronJobManagementError,
        match="remains scheduled",
    ):
        cron_utils.unschedule_cron_job("cleanup-test", strict=True)


def test_strict_unschedule_allows_installations_without_pg_cron(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _Cursor([None])
    _install_connection(monkeypatch, _Connection(cursor))
    monkeypatch.setattr(cron_utils, "_pg_cron_available", lambda _conn: False)

    cron_utils.unschedule_cron_job("cleanup-test", strict=True)
