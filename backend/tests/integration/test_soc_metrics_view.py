from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.enums import AlertStatus, CaseStatus, Priority, TaskStatus
from app.models.models import Alert, Case, Task
from app.services.metrics_service import MetricsService


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "db_migrations"
    / "versions"
    / "016_soc_metrics_work_grain.py"
)


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "soc_metrics_work_grain_integration_migration",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_soc_metrics_view_does_not_repeat_work_for_each_alert_source(
    async_engine: AsyncEngine,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    migration = _load_migration_module()
    created_at = datetime.now(timezone.utc) - timedelta(minutes=5)

    async with session_maker() as session:
        session.add_all(
            [
                Alert(
                    title="Source A alert",
                    priority=Priority.HIGH,
                    source="sensor-a",
                    status=AlertStatus.NEW,
                    created_at=created_at,
                ),
                Alert(
                    title="Source B alert",
                    priority=Priority.HIGH,
                    source="sensor-b",
                    status=AlertStatus.NEW,
                    created_at=created_at,
                ),
                Case(
                    title="Resolved case",
                    priority=Priority.HIGH,
                    status=CaseStatus.CLOSED,
                    created_by="metrics-test",
                    created_at=created_at,
                    closed_at=created_at + timedelta(minutes=2),
                ),
                Task(
                    title="Completed task",
                    priority=Priority.HIGH,
                    status=TaskStatus.DONE,
                    created_by="metrics-test",
                    created_at=created_at,
                ),
            ]
        )
        await session.commit()

    async with async_engine.begin() as connection:
        await connection.execute(
            text("DROP MATERIALIZED VIEW IF EXISTS soc_metrics_15m;")
        )
        await connection.execute(text(migration.SOC_METRICS_VIEW_SQL))
        await connection.execute(text(migration.SOC_METRICS_INDEX_SQL))

    try:
        async with session_maker() as session:
            response = await MetricsService().get_soc_metrics(
                session,
                start_time=created_at - timedelta(minutes=15),
                end_time=created_at + timedelta(minutes=15),
            )
            source_response = await MetricsService().get_soc_metrics(
                session,
                start_time=created_at - timedelta(minutes=15),
                end_time=created_at + timedelta(minutes=15),
                source="sensor-a",
            )

        assert response.summary.total_alerts == 2
        assert response.summary.total_cases == 1
        assert response.summary.total_cases_closed == 1
        assert response.summary.total_tasks == 1
        assert response.summary.total_tasks_completed == 1
        assert sum(window.case_count for window in response.time_series) == 1
        assert sum(window.task_count for window in response.time_series) == 1
        assert source_response.summary.total_alerts == 1
        assert source_response.summary.total_cases == 1
        assert source_response.summary.total_tasks == 1
    finally:
        async with async_engine.begin() as connection:
            await connection.execute(
                text("DROP MATERIALIZED VIEW IF EXISTS soc_metrics_15m;")
            )
