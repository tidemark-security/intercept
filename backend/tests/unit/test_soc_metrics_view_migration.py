from __future__ import annotations

from db_migrations.v0_6_0 import soc_metrics


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


def test_upgrade_replaces_view_and_null_safe_concurrent_refresh_index(
    monkeypatch,
) -> None:
    statements: list[str] = []
    monkeypatch.setattr(soc_metrics.op, "execute", statements.append)

    soc_metrics.upgrade()

    assert statements == [
        "DROP MATERIALIZED VIEW IF EXISTS soc_metrics_15m;",
        soc_metrics.SOC_METRICS_VIEW_SQL,
        soc_metrics.SOC_METRICS_INDEX_SQL,
    ]
    _assert_work_grain_is_separate(soc_metrics.SOC_METRICS_VIEW_SQL)

    compact_index_sql = _compact(soc_metrics.SOC_METRICS_INDEX_SQL)
    assert "metric_scope" in compact_index_sql
    assert "NULLS NOT DISTINCT" in compact_index_sql


def test_downgrade_restores_the_previous_view_and_index(monkeypatch) -> None:
    statements: list[str] = []
    monkeypatch.setattr(soc_metrics.op, "execute", statements.append)

    soc_metrics.downgrade()

    assert statements == [
        "DROP MATERIALIZED VIEW IF EXISTS soc_metrics_15m;",
        soc_metrics.LEGACY_SOC_METRICS_VIEW_SQL,
        soc_metrics.LEGACY_SOC_METRICS_INDEX_SQL,
    ]
    compact_view_sql = _compact(soc_metrics.LEGACY_SOC_METRICS_VIEW_SQL)
    compact_index_sql = _compact(soc_metrics.LEGACY_SOC_METRICS_INDEX_SQL)
    assert "metric_scope" not in compact_view_sql
    assert "FROM alert_metrics a FULL OUTER JOIN case_metrics c" in compact_view_sql
    assert "metric_scope" not in compact_index_sql
    assert "NULLS NOT DISTINCT" not in compact_index_sql
