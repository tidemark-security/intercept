from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


PROJECT_ROOT = Path(__file__).resolve().parents[3]
INITIAL_MIGRATION_PATH = (
    PROJECT_ROOT / "backend" / "db_migrations" / "versions" / "001_initial_schema.py"
)
MIGRATION_PATH = (
    PROJECT_ROOT
    / "backend"
    / "db_migrations"
    / "versions"
    / "016_soc_metrics_work_grain.py"
)


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "soc_metrics_work_grain_migration",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compact(sql: str) -> str:
    return " ".join(sql.split())


def _assert_work_grain_is_separate(sql: str) -> None:
    compact_sql = _compact(sql)

    assert "'alert'::text AS metric_scope" in compact_sql
    assert "'work'::text AS metric_scope" in compact_sql
    assert "FROM alert_metrics a UNION ALL SELECT" in compact_sql
    assert "FROM work_metrics w" in compact_sql
    assert "FROM alert_metrics a FULL OUTER JOIN case_metrics" not in compact_sql
    assert "0::bigint AS case_count" in compact_sql
    assert "0::bigint AS task_count" in compact_sql


def test_soc_metrics_work_grain_migration_is_next_revision() -> None:
    migration = _load_migration_module()

    assert migration.revision == "016_soc_metrics_work_grain"
    assert migration.down_revision == "015_auth_session_cron_jobs"


def test_upgrade_replaces_view_and_null_safe_concurrent_refresh_index(
    monkeypatch,
) -> None:
    migration = _load_migration_module()
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    assert statements == [
        "DROP MATERIALIZED VIEW IF EXISTS soc_metrics_15m;",
        migration.SOC_METRICS_VIEW_SQL,
        migration.SOC_METRICS_INDEX_SQL,
    ]
    _assert_work_grain_is_separate(migration.SOC_METRICS_VIEW_SQL)

    compact_index_sql = _compact(migration.SOC_METRICS_INDEX_SQL)
    assert "metric_scope" in compact_index_sql
    assert "NULLS NOT DISTINCT" in compact_index_sql


def test_fresh_schema_uses_the_same_separate_work_grain() -> None:
    initial_migration = INITIAL_MIGRATION_PATH.read_text()

    _assert_work_grain_is_separate(initial_migration)
    compact_migration = _compact(initial_migration)
    assert (
        "ON soc_metrics_15m (time_window, priority, metric_scope, alert_source) "
        "NULLS NOT DISTINCT"
    ) in compact_migration


def test_downgrade_restores_the_previous_view_and_index(monkeypatch) -> None:
    migration = _load_migration_module()
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.downgrade()

    assert statements == [
        "DROP MATERIALIZED VIEW IF EXISTS soc_metrics_15m;",
        migration.LEGACY_SOC_METRICS_VIEW_SQL,
        migration.LEGACY_SOC_METRICS_INDEX_SQL,
    ]
    compact_view_sql = _compact(migration.LEGACY_SOC_METRICS_VIEW_SQL)
    compact_index_sql = _compact(migration.LEGACY_SOC_METRICS_INDEX_SQL)
    assert "metric_scope" not in compact_view_sql
    assert "FROM alert_metrics a FULL OUTER JOIN case_metrics c" in compact_view_sql
    assert "metric_scope" not in compact_index_sql
    assert "NULLS NOT DISTINCT" not in compact_index_sql
