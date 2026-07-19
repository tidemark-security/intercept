"""Keep SOC case/task metrics at their own aggregation grain.

Revision ID: 016_soc_metrics_work_grain
Revises: 015_auth_session_cron_jobs
Create Date: 2026-07-19
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "016_soc_metrics_work_grain"
down_revision: Union[str, None] = "015_auth_session_cron_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SOC_METRICS_VIEW_SQL = """
    CREATE MATERIALIZED VIEW soc_metrics_15m AS
    WITH alert_metrics AS (
        SELECT
            date_trunc('hour', created_at) +
                INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM created_at) / 15) AS time_window,
            priority,
            source,
            COUNT(*) AS alert_count,
            COUNT(*) FILTER (WHERE status::text LIKE 'CLOSED_%') AS alerts_closed,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED_TP') AS alerts_tp,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED_FP') AS alerts_fp,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED_BP') AS alerts_bp,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED_DUPLICATE') AS alerts_duplicate,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED_UNRESOLVED') AS alerts_unresolved,
            COUNT(*) FILTER (WHERE status::text = 'ESCALATED') AS alerts_escalated,
            COUNT(*) FILTER (
                WHERE status::text IN ('IN_PROGRESS', 'ESCALATED')
                   OR status::text LIKE 'CLOSED_%'
            ) AS alerts_triaged,
            PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY EXTRACT(EPOCH FROM (triaged_at - created_at))
            ) FILTER (WHERE triaged_at IS NOT NULL) AS mttt_p50_seconds,
            AVG(EXTRACT(EPOCH FROM (triaged_at - created_at)))
                FILTER (WHERE triaged_at IS NOT NULL) AS mttt_mean_seconds,
            PERCENTILE_CONT(0.95) WITHIN GROUP (
                ORDER BY EXTRACT(EPOCH FROM (triaged_at - created_at))
            ) FILTER (WHERE triaged_at IS NOT NULL) AS mttt_p95_seconds
        FROM alerts
        WHERE created_at >= NOW() - INTERVAL '90 days'
        GROUP BY 1, 2, 3
    ),
    case_metrics AS (
        SELECT
            date_trunc('hour', created_at) +
                INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM created_at) / 15) AS time_window,
            priority,
            COUNT(*) AS case_count,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED') AS cases_closed,
            COUNT(*) FILTER (WHERE status::text = 'NEW') AS cases_new,
            COUNT(*) FILTER (WHERE status::text = 'IN_PROGRESS') AS cases_in_progress,
            PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY EXTRACT(EPOCH FROM (closed_at - created_at))
            ) FILTER (WHERE closed_at IS NOT NULL) AS mttr_p50_seconds,
            AVG(EXTRACT(EPOCH FROM (closed_at - created_at)))
                FILTER (WHERE closed_at IS NOT NULL) AS mttr_mean_seconds,
            PERCENTILE_CONT(0.95) WITHIN GROUP (
                ORDER BY EXTRACT(EPOCH FROM (closed_at - created_at))
            ) FILTER (WHERE closed_at IS NOT NULL) AS mttr_p95_seconds
        FROM cases
        WHERE created_at >= NOW() - INTERVAL '90 days'
        GROUP BY 1, 2
    ),
    task_metrics AS (
        SELECT
            date_trunc('hour', created_at) +
                INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM created_at) / 15) AS time_window,
            priority,
            COUNT(*) AS task_count,
            COUNT(*) FILTER (WHERE status::text = 'DONE') AS tasks_completed,
            COUNT(*) FILTER (WHERE status::text = 'TODO') AS tasks_todo,
            COUNT(*) FILTER (WHERE status::text = 'IN_PROGRESS') AS tasks_in_progress
        FROM tasks
        WHERE created_at >= NOW() - INTERVAL '90 days'
        GROUP BY 1, 2
    ),
    work_metrics AS (
        SELECT
            COALESCE(c.time_window, t.time_window) AS time_window,
            COALESCE(c.priority, t.priority) AS priority,
            COALESCE(c.case_count, 0) AS case_count,
            COALESCE(c.cases_closed, 0) AS cases_closed,
            COALESCE(c.cases_new, 0) AS cases_new,
            COALESCE(c.cases_in_progress, 0) AS cases_in_progress,
            c.mttr_p50_seconds,
            c.mttr_mean_seconds,
            c.mttr_p95_seconds,
            COALESCE(t.task_count, 0) AS task_count,
            COALESCE(t.tasks_completed, 0) AS tasks_completed,
            COALESCE(t.tasks_todo, 0) AS tasks_todo,
            COALESCE(t.tasks_in_progress, 0) AS tasks_in_progress
        FROM case_metrics c
        FULL OUTER JOIN task_metrics t
          ON c.time_window = t.time_window
         AND c.priority::text = t.priority::text
    )
    SELECT
        a.time_window,
        a.priority,
        'alert'::text AS metric_scope,
        a.source AS alert_source,
        a.alert_count,
        a.alerts_closed,
        a.alerts_tp,
        a.alerts_fp,
        a.alerts_bp,
        a.alerts_duplicate,
        a.alerts_unresolved,
        a.alerts_escalated,
        a.alerts_triaged,
        a.mttt_p50_seconds,
        a.mttt_mean_seconds,
        a.mttt_p95_seconds,
        0::bigint AS case_count,
        0::bigint AS cases_closed,
        0::bigint AS cases_new,
        0::bigint AS cases_in_progress,
        NULL AS mttr_p50_seconds,
        NULL AS mttr_mean_seconds,
        NULL AS mttr_p95_seconds,
        0::bigint AS task_count,
        0::bigint AS tasks_completed,
        0::bigint AS tasks_todo,
        0::bigint AS tasks_in_progress,
        NOW() AS refreshed_at
    FROM alert_metrics a

    UNION ALL

    SELECT
        w.time_window,
        w.priority,
        'work'::text AS metric_scope,
        NULL::text AS alert_source,
        0::bigint AS alert_count,
        0::bigint AS alerts_closed,
        0::bigint AS alerts_tp,
        0::bigint AS alerts_fp,
        0::bigint AS alerts_bp,
        0::bigint AS alerts_duplicate,
        0::bigint AS alerts_unresolved,
        0::bigint AS alerts_escalated,
        0::bigint AS alerts_triaged,
        NULL AS mttt_p50_seconds,
        NULL AS mttt_mean_seconds,
        NULL AS mttt_p95_seconds,
        w.case_count,
        w.cases_closed,
        w.cases_new,
        w.cases_in_progress,
        w.mttr_p50_seconds,
        w.mttr_mean_seconds,
        w.mttr_p95_seconds,
        w.task_count,
        w.tasks_completed,
        w.tasks_todo,
        w.tasks_in_progress,
        NOW() AS refreshed_at
    FROM work_metrics w;
"""


SOC_METRICS_INDEX_SQL = """
    CREATE UNIQUE INDEX soc_metrics_15m_idx
    ON soc_metrics_15m (time_window, priority, metric_scope, alert_source)
    NULLS NOT DISTINCT;
"""


LEGACY_SOC_METRICS_VIEW_SQL = """
    CREATE MATERIALIZED VIEW soc_metrics_15m AS
    WITH alert_metrics AS (
        SELECT
            date_trunc('hour', created_at) +
                INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM created_at) / 15) AS time_window,
            priority,
            source,
            COUNT(*) AS alert_count,
            COUNT(*) FILTER (WHERE status::text LIKE 'CLOSED_%') AS alerts_closed,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED_TP') AS alerts_tp,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED_FP') AS alerts_fp,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED_BP') AS alerts_bp,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED_DUPLICATE') AS alerts_duplicate,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED_UNRESOLVED') AS alerts_unresolved,
            COUNT(*) FILTER (WHERE status::text = 'ESCALATED') AS alerts_escalated,
            COUNT(*) FILTER (
                WHERE status::text IN ('IN_PROGRESS', 'ESCALATED')
                   OR status::text LIKE 'CLOSED_%'
            ) AS alerts_triaged,
            PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY EXTRACT(EPOCH FROM (triaged_at - created_at))
            ) FILTER (WHERE triaged_at IS NOT NULL) AS mttt_p50_seconds,
            AVG(EXTRACT(EPOCH FROM (triaged_at - created_at)))
                FILTER (WHERE triaged_at IS NOT NULL) AS mttt_mean_seconds,
            PERCENTILE_CONT(0.95) WITHIN GROUP (
                ORDER BY EXTRACT(EPOCH FROM (triaged_at - created_at))
            ) FILTER (WHERE triaged_at IS NOT NULL) AS mttt_p95_seconds
        FROM alerts
        WHERE created_at >= NOW() - INTERVAL '90 days'
        GROUP BY 1, 2, 3
    ),
    case_metrics AS (
        SELECT
            date_trunc('hour', created_at) +
                INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM created_at) / 15) AS time_window,
            priority,
            COUNT(*) AS case_count,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED') AS cases_closed,
            COUNT(*) FILTER (WHERE status::text = 'NEW') AS cases_new,
            COUNT(*) FILTER (WHERE status::text = 'IN_PROGRESS') AS cases_in_progress,
            PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY EXTRACT(EPOCH FROM (closed_at - created_at))
            ) FILTER (WHERE closed_at IS NOT NULL) AS mttr_p50_seconds,
            AVG(EXTRACT(EPOCH FROM (closed_at - created_at)))
                FILTER (WHERE closed_at IS NOT NULL) AS mttr_mean_seconds,
            PERCENTILE_CONT(0.95) WITHIN GROUP (
                ORDER BY EXTRACT(EPOCH FROM (closed_at - created_at))
            ) FILTER (WHERE closed_at IS NOT NULL) AS mttr_p95_seconds
        FROM cases
        WHERE created_at >= NOW() - INTERVAL '90 days'
        GROUP BY 1, 2
    ),
    task_metrics AS (
        SELECT
            date_trunc('hour', created_at) +
                INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM created_at) / 15) AS time_window,
            priority,
            COUNT(*) AS task_count,
            COUNT(*) FILTER (WHERE status::text = 'DONE') AS tasks_completed,
            COUNT(*) FILTER (WHERE status::text = 'TODO') AS tasks_todo,
            COUNT(*) FILTER (WHERE status::text = 'IN_PROGRESS') AS tasks_in_progress
        FROM tasks
        WHERE created_at >= NOW() - INTERVAL '90 days'
        GROUP BY 1, 2
    )
    SELECT
        COALESCE(a.time_window, c.time_window, t.time_window) AS time_window,
        COALESCE(a.priority, c.priority, t.priority) AS priority,
        a.source AS alert_source,
        COALESCE(a.alert_count, 0) AS alert_count,
        COALESCE(a.alerts_closed, 0) AS alerts_closed,
        COALESCE(a.alerts_tp, 0) AS alerts_tp,
        COALESCE(a.alerts_fp, 0) AS alerts_fp,
        COALESCE(a.alerts_bp, 0) AS alerts_bp,
        COALESCE(a.alerts_duplicate, 0) AS alerts_duplicate,
        COALESCE(a.alerts_unresolved, 0) AS alerts_unresolved,
        COALESCE(a.alerts_escalated, 0) AS alerts_escalated,
        COALESCE(a.alerts_triaged, 0) AS alerts_triaged,
        a.mttt_p50_seconds,
        a.mttt_mean_seconds,
        a.mttt_p95_seconds,
        COALESCE(c.case_count, 0) AS case_count,
        COALESCE(c.cases_closed, 0) AS cases_closed,
        COALESCE(c.cases_new, 0) AS cases_new,
        COALESCE(c.cases_in_progress, 0) AS cases_in_progress,
        c.mttr_p50_seconds,
        c.mttr_mean_seconds,
        c.mttr_p95_seconds,
        COALESCE(t.task_count, 0) AS task_count,
        COALESCE(t.tasks_completed, 0) AS tasks_completed,
        COALESCE(t.tasks_todo, 0) AS tasks_todo,
        COALESCE(t.tasks_in_progress, 0) AS tasks_in_progress,
        NOW() AS refreshed_at
    FROM alert_metrics a
    FULL OUTER JOIN case_metrics c
      ON a.time_window = c.time_window
     AND a.priority::text = c.priority::text
    FULL OUTER JOIN task_metrics t
      ON COALESCE(a.time_window, c.time_window) = t.time_window
     AND COALESCE(a.priority::text, c.priority::text) = t.priority::text
    WHERE COALESCE(a.time_window, c.time_window, t.time_window) IS NOT NULL;
"""


LEGACY_SOC_METRICS_INDEX_SQL = """
    CREATE UNIQUE INDEX soc_metrics_15m_idx
    ON soc_metrics_15m (time_window, priority, alert_source);
"""


def upgrade() -> None:
    # PostgreSQL applies the replacement transactionally, so readers cannot see
    # a half-created view (queries may wait briefly for the DDL lock).
    op.execute("DROP MATERIALIZED VIEW IF EXISTS soc_metrics_15m;")
    op.execute(SOC_METRICS_VIEW_SQL)
    op.execute(SOC_METRICS_INDEX_SQL)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS soc_metrics_15m;")
    op.execute(LEGACY_SOC_METRICS_VIEW_SQL)
    op.execute(LEGACY_SOC_METRICS_INDEX_SQL)
