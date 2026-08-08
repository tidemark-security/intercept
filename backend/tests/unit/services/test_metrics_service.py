from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import ProgrammingError

from app.models.models import SOCMetricsWindow
from app.services import metrics_service as metrics_service_module
from app.services.metrics_service import (
    MetricsService,
    _outcome_rate_denominator,
    _resolve_time_range,
)


_START_TIME = datetime(2026, 5, 17, tzinfo=timezone.utc)
_END_TIME = datetime(2026, 5, 24, tzinfo=timezone.utc)
_NEXT_WINDOW = _START_TIME + timedelta(minutes=15)
_NEXT_DAY = _START_TIME + timedelta(days=1)


class _PostgresError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


def _programming_error(sqlstate: str) -> ProgrammingError:
    return ProgrammingError("SELECT 1", {}, _PostgresError(sqlstate))


def _all_rows_result(rows: list[dict[str, object]]) -> MagicMock:
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


def _first_row_result(row: dict[str, object]) -> MagicMock:
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    return result


def _scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar.return_value = value
    return result


def test_outcome_rate_denominator_excludes_duplicate_closures() -> None:
    assert _outcome_rate_denominator(closed=10, duplicates=3) == 7
    assert _outcome_rate_denominator(closed=3, duplicates=3) == 0
    assert _outcome_rate_denominator(closed=2, duplicates=5) == 0


def test_resolve_time_range_aligns_materialized_view_windows() -> None:
    start = datetime(2026, 5, 17, 10, 7, 30, tzinfo=timezone.utc)
    end = datetime(2026, 5, 17, 11, 45, tzinfo=timezone.utc)

    assert _resolve_time_range(start, end, align_to_windows=True) == (
        datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 5, 17, 11, 45, tzinfo=timezone.utc),
    )
    assert _resolve_time_range(start, end, align_to_windows=False) == (start, end)


@pytest.mark.parametrize("provided_bound", ["start", "end"])
def test_resolve_time_range_preserves_a_single_provided_bound(
    monkeypatch: pytest.MonkeyPatch,
    provided_bound: str,
) -> None:
    default_start = datetime(2026, 5, 17, tzinfo=timezone.utc)
    default_end = datetime(2026, 5, 24, tzinfo=timezone.utc)
    supplied = datetime(2026, 5, 20, 10, 7, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(
        metrics_service_module,
        "get_default_time_range",
        lambda: (default_start, default_end),
    )

    start = supplied if provided_bound == "start" else None
    end = supplied if provided_bound == "end" else None

    resolved_start, resolved_end = _resolve_time_range(
        start,
        end,
        align_to_windows=True,
    )

    assert resolved_start == (
        datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        if provided_bound == "start"
        else default_start
    )
    assert resolved_end == (
        datetime(2026, 5, 20, 10, 15, tzinfo=timezone.utc)
        if provided_bound == "end"
        else default_end
    )


def test_soc_summary_rates_ignore_duplicate_closures() -> None:
    summary = MetricsService()._calculate_soc_summary(
        [
            SOCMetricsWindow(
                time_window=datetime(2026, 5, 24, tzinfo=timezone.utc),
                alerts_closed=6,
                alerts_tp=2,
                alerts_fp=1,
                alerts_bp=1,
                alerts_duplicate=2,
            )
        ]
    )

    assert summary.total_alerts_closed == 6
    assert summary.tp_rate == 0.5
    assert summary.fp_rate == 0.25
    assert summary.bp_rate == 0.25


def test_soc_summary_counts_work_once_across_multiple_alert_sources() -> None:
    summary = MetricsService()._calculate_soc_summary(
        [
            SOCMetricsWindow(
                time_window=_START_TIME,
                priority="HIGH",
                alert_source="sensor-a",
                alert_count=2,
                case_count=3,
                cases_closed=1,
                mttr_p50_seconds=60.0,
                mttr_mean_seconds=90.0,
                task_count=4,
                tasks_completed=2,
            ),
            SOCMetricsWindow(
                time_window=_START_TIME,
                priority="HIGH",
                alert_source="sensor-b",
                alert_count=5,
                case_count=3,
                cases_closed=1,
                mttr_p50_seconds=60.0,
                mttr_mean_seconds=90.0,
                task_count=4,
                tasks_completed=2,
            ),
            SOCMetricsWindow(
                time_window=_NEXT_WINDOW,
                priority="HIGH",
                alert_source="sensor-a",
                alert_count=1,
                case_count=2,
                cases_closed=2,
                mttr_p50_seconds=180.0,
                mttr_mean_seconds=210.0,
                task_count=3,
                tasks_completed=1,
            ),
        ]
    )

    assert summary.total_alerts == 8
    assert summary.total_cases == 5
    assert summary.total_cases_closed == 3
    assert summary.mttr_p50_seconds == 120.0
    assert summary.mttr_mean_seconds == 150.0
    assert summary.total_tasks == 7
    assert summary.total_tasks_completed == 3


def test_soc_summary_uses_latest_grouped_work_row_for_open_counts() -> None:
    summary = MetricsService()._calculate_soc_summary(
        [
            SOCMetricsWindow(
                time_window=_START_TIME,
                priority="HIGH",
                alert_source=None,
                cases_new=1,
                tasks_todo=2,
            ),
            SOCMetricsWindow(
                time_window=_NEXT_WINDOW,
                priority="HIGH",
                alert_source=None,
                cases_new=3,
                cases_in_progress=4,
                tasks_todo=5,
                tasks_in_progress=6,
            ),
            # The materialized view may return an alert row after the work row
            # because rows at the same timestamp have no secondary ordering.
            SOCMetricsWindow(
                time_window=_NEXT_WINDOW,
                priority="HIGH",
                alert_source="sensor-a",
                alert_count=1,
            ),
        ]
    )

    assert summary.open_cases == 7
    assert summary.open_tasks == 11


@pytest.mark.asyncio
async def test_soc_metrics_build_windows_and_use_live_open_work_counts() -> None:
    db = AsyncMock()
    db.execute.side_effect = [
        _all_rows_result(
            [
                {
                    "time_window": _START_TIME,
                    "refreshed_at": _NEXT_WINDOW,
                    "alert_count": 3,
                    "alerts_closed": 2,
                    "alerts_tp": 1,
                    "alerts_fp": 1,
                    "case_count": 2,
                    "task_count": 4,
                    "tasks_completed": 1,
                }
            ]
        ),
        _scalar_result(7),
        _scalar_result(9),
    ]

    response = await MetricsService().get_soc_metrics(
        db,
        start_time=_START_TIME,
        end_time=_END_TIME,
    )

    assert response.refreshed_at == _NEXT_WINDOW
    assert response.time_series[0].alerts_duplicate == 0
    assert response.summary.total_alerts == 3
    assert response.summary.total_cases == 2
    assert response.summary.total_tasks_completed == 1
    assert response.summary.open_cases == 7
    assert response.summary.open_tasks == 9


@pytest.mark.asyncio
async def test_soc_source_filter_keeps_source_independent_work_row() -> None:
    db = AsyncMock()
    db.execute.side_effect = [
        _all_rows_result([]),
        _scalar_result(0),
        _scalar_result(0),
    ]

    await MetricsService().get_soc_metrics(
        db,
        start_time=_START_TIME,
        end_time=_END_TIME,
        source="sensor-a",
    )

    query = str(db.execute.await_args_list[0].args[0])
    assert "(alert_source = :source OR metric_scope = 'work')" in query
    assert db.execute.await_args_list[0].args[1]["source"] == "sensor-a"


@pytest.mark.asyncio
async def test_analyst_metrics_include_zero_duration_windows_in_averages() -> None:
    result = _all_rows_result([
        {
            "time_window": _START_TIME,
            "analyst": "analyst@example.com",
            "mttt_mean_seconds": 0.0,
            "mttt_p50_seconds": 0.0,
        },
        {
            "time_window": _NEXT_WINDOW,
            "analyst": "analyst@example.com",
            "mttt_mean_seconds": 10.0,
            "mttt_p50_seconds": 6.0,
        },
    ])
    db = AsyncMock()
    db.execute.return_value = result

    response = await MetricsService().get_analyst_metrics(
        db,
        start_time=_START_TIME,
        end_time=_END_TIME,
    )

    assert response.analysts[0].mttt_mean_seconds == 5.0
    assert response.analysts[0].mttt_p50_seconds == 3.0
    assert response.analysts[0].team_mttt_p50_seconds == 3.0


@pytest.mark.asyncio
async def test_alert_metrics_share_consistent_source_aggregates() -> None:
    result = _all_rows_result([
        {
            "time_window": _START_TIME,
            "source": "sensor-a",
            "hour_of_day": 9,
            "alert_count": 4,
            "alerts_closed": 3,
            "alerts_tp": 1,
            "alerts_fp": 1,
            "alerts_bp": 0,
            "alerts_escalated": 1,
            "alerts_duplicate": 1,
        },
        {
            "time_window": _NEXT_DAY,
            "source": "sensor-a",
            "hour_of_day": 9,
            "alert_count": 2,
            "alerts_closed": 2,
            "alerts_tp": 1,
            "alerts_fp": 0,
            "alerts_bp": 1,
            "alerts_escalated": 0,
            "alerts_duplicate": 0,
        },
    ])
    db = AsyncMock()
    db.execute.return_value = result

    response = await MetricsService().get_alert_metrics(
        db,
        start_time=_START_TIME,
        end_time=_END_TIME,
    )

    source = response.by_source[0]
    dimension = response.by_dimension[0]
    assert source.total_alerts == dimension.total_alerts == 6
    assert source.total_closed == dimension.total_closed == 5
    assert source.total_tp == dimension.total_tp == 2
    assert source.total_fp == dimension.total_fp == 1
    assert source.fp_rate == dimension.fp_rate == 0.25
    assert source.escalation_rate == dimension.escalation_rate == pytest.approx(1 / 6)
    assert dimension.total_bp == 1
    assert response.by_hour[9].alert_count == 6
    assert response.by_hour[9].avg_alerts == 3.0


@pytest.mark.asyncio
async def test_ai_triage_metrics_calculate_review_rates_consistently() -> None:
    db = AsyncMock()
    db.execute.side_effect = [
        _first_row_result(
            {
                "total_recommendations": 5,
                "total_accepted": 2,
                "total_rejected": 1,
                "total_pending": 1,
                "avg_confidence": 0.75,
            }
        ),
        _all_rows_result([{"rejection_category": "OTHER", "count": 1}]),
        _all_rows_result(
            [
                {
                    "disposition": "TRUE_POSITIVE",
                    "total": 2,
                    "accepted": 2,
                    "rejected": 0,
                }
            ]
        ),
        _all_rows_result(
            [
                {
                    "confidence_bucket": "0.8-0.9",
                    "total": 1,
                    "accepted": 0,
                    "rejected": 0,
                }
            ]
        ),
        _all_rows_result(
            [
                {
                    "week_start": _START_TIME,
                    "total_recommendations": 2,
                    "accepted": 1,
                    "rejected": 1,
                }
            ]
        ),
    ]

    response = await MetricsService().get_ai_triage_metrics(
        db,
        start_time=_START_TIME,
        end_time=_END_TIME,
    )

    assert response.summary.acceptance_rate == pytest.approx(2 / 3)
    assert response.summary.rejection_rate == pytest.approx(1 / 3)
    assert response.by_category[0].percentage == 1.0
    assert response.by_disposition[0].acceptance_rate == 1.0
    assert response.by_confidence[0].acceptance_rate is None
    assert response.weekly_trend[0].acceptance_rate == 0.5


@pytest.mark.asyncio
async def test_ai_chat_metrics_calculate_feedback_rates_consistently() -> None:
    db = AsyncMock()
    db.execute.side_effect = [
        _first_row_result(
            {
                "total_messages": 4,
                "total_with_feedback": 3,
                "positive_feedback": 2,
                "negative_feedback": 1,
            }
        ),
        _all_rows_result(
            [
                {
                    "week_start": _START_TIME,
                    "total_messages": 4,
                    "positive_feedback": 1,
                    "negative_feedback": 1,
                }
            ]
        ),
    ]

    response = await MetricsService().get_ai_chat_metrics(
        db,
        start_time=_START_TIME,
        end_time=_END_TIME,
    )

    assert response.summary.feedback_rate == 0.75
    assert response.summary.satisfaction_rate == pytest.approx(2 / 3)
    assert response.weekly_trend[0].feedback_rate == 0.5
    assert response.weekly_trend[0].satisfaction_rate == 0.5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "empty_collection_names"),
    [
        ("get_soc_metrics", ("time_series",)),
        ("get_analyst_metrics", ("analysts", "time_series")),
        (
            "get_alert_metrics",
            ("by_source", "by_dimension", "by_hour", "time_series"),
        ),
    ],
)
async def test_optional_metrics_views_return_empty_when_relation_is_absent(
    method_name: str,
    empty_collection_names: tuple[str, ...],
) -> None:
    db = AsyncMock()
    db.execute.side_effect = _programming_error("42P01")

    response = await getattr(MetricsService(), method_name)(
        db,
        start_time=_START_TIME,
        end_time=_END_TIME,
    )

    for collection_name in empty_collection_names:
        assert getattr(response, collection_name) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name",
    ["get_soc_metrics", "get_analyst_metrics", "get_alert_metrics"],
)
async def test_optional_metrics_views_surface_unexpected_failures(
    method_name: str,
) -> None:
    db = AsyncMock()
    failure = RuntimeError("connection was interrupted")
    db.execute.side_effect = failure

    with pytest.raises(RuntimeError, match="connection was interrupted"):
        await getattr(MetricsService(), method_name)(
            db,
            start_time=_START_TIME,
            end_time=_END_TIME,
        )


@pytest.mark.asyncio
async def test_optional_metrics_view_surfaces_other_programming_errors() -> None:
    db = AsyncMock()
    failure = _programming_error("42601")
    db.execute.side_effect = failure

    with pytest.raises(ProgrammingError) as raised:
        await MetricsService().get_soc_metrics(
            db,
            start_time=_START_TIME,
            end_time=_END_TIME,
        )

    assert raised.value is failure


@pytest.mark.asyncio
async def test_alert_dimension_query_surfaces_database_failures() -> None:
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("alerts query failed")

    with pytest.raises(RuntimeError, match="alerts query failed"):
        await MetricsService()._get_alert_metrics_by_dimension(
            db,
            _START_TIME,
            _END_TIME,
            "title",
        )
