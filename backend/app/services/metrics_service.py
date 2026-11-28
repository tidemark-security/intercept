"""
SOC Metrics Service

Queries materialized views for SOC operational metrics aggregated in 15-minute windows.
"""
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import func, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.entity_ids import ALERT_PREFIX
from app.models.models import (
    Case,
    Task,
    SOCMetricsResponse,
    SOCMetricsSummary,
    SOCMetricsWindow,
    AnalystMetricsResponse,
    AnalystMetricsSummary,
    AnalystMetricsWindow,
    AlertMetricsResponse,
    AlertMetricsBySource,
    AlertMetricsByDimension,
    AlertMetricsHourly,
    AlertMetricsWindow,
    AITriageMetricsResponse,
    AITriageMetricsSummary,
    AITriageByCategory,
    AITriageByDisposition,
    AITriageConfidenceCorrelation,
    AITriageWeeklyTrend,
    AIChatMetricsResponse,
    AIChatMetricsSummary,
    AIChatWeeklyTrend,
    TriageRecommendationDetail,
    TriageRecommendationDrillDownResponse,
    ChatFeedbackMessageDetail,
    ChatFeedbackDrillDownResponse,
)
from app.models.enums import (
    Priority,
    CaseStatus,
    TaskStatus,
    RejectionCategory,
    TriageDisposition,
    RecommendationStatus,
    MessageFeedback,
)

logger = logging.getLogger(__name__)

_UNDEFINED_RELATION_SQLSTATE = "42P01"


def _is_undefined_relation_error(exc: ProgrammingError) -> bool:
    """Return whether PostgreSQL rejected a query because a relation is absent."""
    original = exc.orig
    return (
        getattr(original, "sqlstate", None)
        or getattr(original, "pgcode", None)
    ) == _UNDEFINED_RELATION_SQLSTATE


async def _query_optional_metrics_view(
    db: AsyncSession,
    query: str,
    params: Mapping[str, Any],
    *,
    view_name: str,
) -> Optional[Sequence[Mapping[str, Any]]]:
    """Query an optional metrics view while preserving unexpected DB failures."""
    try:
        result = await db.execute(text(query), params)
    except ProgrammingError as exc:
        if not _is_undefined_relation_error(exc):
            raise
        logger.warning("Metrics view %s is not available", view_name)
        return None
    return result.mappings().all()


def _outcome_rate_denominator(closed: int, duplicates: int = 0) -> int:
    """Return the count of closed alerts that represent analyst dispositions."""
    return max(closed - duplicates, 0)


def _rate_or_none(numerator: int, denominator: int) -> Optional[float]:
    """Return a rate only when its denominator represents a real population."""
    return numerator / denominator if denominator > 0 else None


def _mean_or_none(values: Sequence[float]) -> Optional[float]:
    """Return the arithmetic mean of a non-empty metrics sample."""
    return sum(values) / len(values) if values else None


def _metric_count(row: Mapping[str, Any], name: str) -> int:
    """Normalize a nullable or absent SQL count to zero."""
    return row.get(name) or 0


def _first_refresh_time(
    rows: Sequence[Mapping[str, Any]],
) -> Optional[datetime]:
    """Return the first populated refresh timestamp from a view result."""
    return next(
        (row["refreshed_at"] for row in rows if row.get("refreshed_at")),
        None,
    )


@dataclass
class _AlertSourceTotals:
    """Accumulate one source's alert counts and build its response projections."""

    total: int = 0
    closed: int = 0
    true_positives: int = 0
    false_positives: int = 0
    benign_positives: int = 0
    escalated: int = 0
    duplicates: int = 0

    def add(self, row: Mapping[str, Any]) -> None:
        self.total += _metric_count(row, "alert_count")
        self.closed += _metric_count(row, "alerts_closed")
        self.true_positives += _metric_count(row, "alerts_tp")
        self.false_positives += _metric_count(row, "alerts_fp")
        self.benign_positives += _metric_count(row, "alerts_bp")
        self.escalated += _metric_count(row, "alerts_escalated")
        self.duplicates += _metric_count(row, "alerts_duplicate")

    def to_source_metrics(self, source: str) -> AlertMetricsBySource:
        outcome_closed = _outcome_rate_denominator(self.closed, self.duplicates)
        triaged = self.closed + self.escalated
        return AlertMetricsBySource(
            source=source,
            total_alerts=self.total,
            total_closed=self.closed,
            total_tp=self.true_positives,
            total_fp=self.false_positives,
            total_escalated=self.escalated,
            fp_rate=_rate_or_none(self.false_positives, outcome_closed),
            escalation_rate=_rate_or_none(self.escalated, triaged),
        )

    def to_dimension_metrics(self, source: str) -> AlertMetricsByDimension:
        outcome_closed = _outcome_rate_denominator(self.closed, self.duplicates)
        triaged = self.closed + self.escalated
        return AlertMetricsByDimension(
            dimension="source",
            value=source,
            total_alerts=self.total,
            total_closed=self.closed,
            total_tp=self.true_positives,
            total_fp=self.false_positives,
            total_bp=self.benign_positives,
            total_escalated=self.escalated,
            fp_rate=_rate_or_none(self.false_positives, outcome_closed),
            escalation_rate=_rate_or_none(self.escalated, triaged),
        )


@dataclass
class _AnalystTotals:
    """Accumulate one analyst's materialized-view windows."""

    alerts_triaged: int = 0
    true_positives: int = 0
    false_positives: int = 0
    benign_positives: int = 0
    escalated: int = 0
    duplicates: int = 0
    cases_assigned: int = 0
    cases_closed: int = 0
    tasks_completed: int = 0
    mttt_values: list[float] = field(default_factory=list)
    mttt_p50_values: list[float] = field(default_factory=list)

    def add(self, row: Mapping[str, Any]) -> None:
        self.alerts_triaged += _metric_count(row, "alerts_triaged")
        self.true_positives += _metric_count(row, "alerts_tp")
        self.false_positives += _metric_count(row, "alerts_fp")
        self.benign_positives += _metric_count(row, "alerts_bp")
        self.escalated += _metric_count(row, "alerts_escalated")
        self.duplicates += _metric_count(row, "alerts_duplicate")
        self.cases_assigned += _metric_count(row, "cases_assigned")
        self.cases_closed += _metric_count(row, "cases_closed")
        self.tasks_completed += _metric_count(row, "tasks_completed")

        mttt_mean = row.get("mttt_mean_seconds")
        if mttt_mean is not None:
            self.mttt_values.append(mttt_mean)
        mttt_p50 = row.get("mttt_p50_seconds")
        if mttt_p50 is not None:
            self.mttt_p50_values.append(mttt_p50)

    @property
    def mean_mttt_p50(self) -> Optional[float]:
        return _mean_or_none(self.mttt_p50_values)

    def to_summary(
        self,
        analyst: str,
        team_mttt_p50: Optional[float],
    ) -> AnalystMetricsSummary:
        outcome_closed = _outcome_rate_denominator(
            self.true_positives
            + self.false_positives
            + self.benign_positives
            + self.duplicates,
            self.duplicates,
        )
        return AnalystMetricsSummary(
            analyst=analyst,
            total_alerts_triaged=self.alerts_triaged,
            total_alerts_tp=self.true_positives,
            total_alerts_fp=self.false_positives,
            total_alerts_bp=self.benign_positives,
            total_alerts_escalated=self.escalated,
            tp_rate=_rate_or_none(self.true_positives, outcome_closed),
            fp_rate=_rate_or_none(self.false_positives, outcome_closed),
            escalation_rate=_rate_or_none(self.escalated, self.alerts_triaged),
            mttt_p50_seconds=self.mean_mttt_p50,
            mttt_mean_seconds=_mean_or_none(self.mttt_values),
            team_mttt_p50_seconds=team_mttt_p50,
            total_cases_assigned=self.cases_assigned,
            total_cases_closed=self.cases_closed,
            total_tasks_completed=self.tasks_completed,
        )


@dataclass
class _HourlyAlertTotals:
    """Accumulate alert volume for one hour of day."""

    count: int = 0
    active_days: set[date] = field(default_factory=set)

    def add(self, count: int, time_window: datetime) -> None:
        self.count += count
        self.active_days.add(time_window.date())

    def to_metrics(self, hour: int) -> AlertMetricsHourly:
        active_day_count = len(self.active_days) or 1
        return AlertMetricsHourly(
            hour_of_day=hour,
            alert_count=self.count,
            avg_alerts=self.count / active_day_count,
        )


@dataclass
class _SOCWorkWindowMetrics:
    """Collapse source-repeated case/task values to their real window grain."""

    case_count: int = 0
    cases_closed: int = 0
    cases_new: int = 0
    cases_in_progress: int = 0
    task_count: int = 0
    tasks_completed: int = 0
    tasks_todo: int = 0
    tasks_in_progress: int = 0
    mttr_p50_seconds: Optional[float] = None
    mttr_mean_seconds: Optional[float] = None

    def include(self, window: SOCMetricsWindow) -> None:
        # Older versions of soc_metrics_15m repeated identical work metrics on
        # every alert-source row. The corrected view emits a separate work row,
        # whose values are the only non-zero/non-null values at this grain.
        self.case_count = max(self.case_count, window.case_count)
        self.cases_closed = max(self.cases_closed, window.cases_closed)
        self.cases_new = max(self.cases_new, window.cases_new)
        self.cases_in_progress = max(
            self.cases_in_progress,
            window.cases_in_progress,
        )
        self.task_count = max(self.task_count, window.task_count)
        self.tasks_completed = max(
            self.tasks_completed,
            window.tasks_completed,
        )
        self.tasks_todo = max(self.tasks_todo, window.tasks_todo)
        self.tasks_in_progress = max(
            self.tasks_in_progress,
            window.tasks_in_progress,
        )
        if self.mttr_p50_seconds is None:
            self.mttr_p50_seconds = window.mttr_p50_seconds
        if self.mttr_mean_seconds is None:
            self.mttr_mean_seconds = window.mttr_mean_seconds


def _soc_work_metrics_by_window(
    time_series: Sequence[SOCMetricsWindow],
) -> list[_SOCWorkWindowMetrics]:
    """Return case/task metrics once per materialized-view work grain."""
    grouped: dict[tuple[datetime, Optional[str]], _SOCWorkWindowMetrics] = {}
    for window in time_series:
        work_metrics = grouped.setdefault(
            (window.time_window, window.priority),
            _SOCWorkWindowMetrics(),
        )
        work_metrics.include(window)
    return list(grouped.values())


def _soc_metrics_window(row: Mapping[str, Any]) -> SOCMetricsWindow:
    """Translate one SOC materialized-view row into its response model."""
    return SOCMetricsWindow(
        time_window=row["time_window"],
        priority=row.get("priority"),
        alert_source=row.get("alert_source"),
        alert_count=_metric_count(row, "alert_count"),
        alerts_closed=_metric_count(row, "alerts_closed"),
        alerts_tp=_metric_count(row, "alerts_tp"),
        alerts_fp=_metric_count(row, "alerts_fp"),
        alerts_bp=_metric_count(row, "alerts_bp"),
        alerts_duplicate=_metric_count(row, "alerts_duplicate"),
        alerts_unresolved=_metric_count(row, "alerts_unresolved"),
        alerts_escalated=_metric_count(row, "alerts_escalated"),
        alerts_triaged=_metric_count(row, "alerts_triaged"),
        mttt_p50_seconds=row.get("mttt_p50_seconds"),
        mttt_mean_seconds=row.get("mttt_mean_seconds"),
        mttt_p95_seconds=row.get("mttt_p95_seconds"),
        case_count=_metric_count(row, "case_count"),
        cases_closed=_metric_count(row, "cases_closed"),
        cases_new=_metric_count(row, "cases_new"),
        cases_in_progress=_metric_count(row, "cases_in_progress"),
        mttr_p50_seconds=row.get("mttr_p50_seconds"),
        mttr_mean_seconds=row.get("mttr_mean_seconds"),
        mttr_p95_seconds=row.get("mttr_p95_seconds"),
        task_count=_metric_count(row, "task_count"),
        tasks_completed=_metric_count(row, "tasks_completed"),
        tasks_todo=_metric_count(row, "tasks_todo"),
        tasks_in_progress=_metric_count(row, "tasks_in_progress"),
    )


def _analyst_metrics_window(row: Mapping[str, Any]) -> AnalystMetricsWindow:
    """Translate one analyst materialized-view row into its response model."""
    return AnalystMetricsWindow(
        time_window=row["time_window"],
        analyst=row["analyst"],
        alerts_triaged=_metric_count(row, "alerts_triaged"),
        alerts_tp=_metric_count(row, "alerts_tp"),
        alerts_fp=_metric_count(row, "alerts_fp"),
        alerts_bp=_metric_count(row, "alerts_bp"),
        alerts_escalated=_metric_count(row, "alerts_escalated"),
        alerts_duplicate=_metric_count(row, "alerts_duplicate"),
        mttt_p50_seconds=row.get("mttt_p50_seconds"),
        mttt_mean_seconds=row.get("mttt_mean_seconds"),
        cases_assigned=_metric_count(row, "cases_assigned"),
        cases_closed=_metric_count(row, "cases_closed"),
        tasks_assigned=_metric_count(row, "tasks_assigned"),
        tasks_completed=_metric_count(row, "tasks_completed"),
    )


def _alert_metrics_window(row: Mapping[str, Any]) -> AlertMetricsWindow:
    """Translate one alert materialized-view row into its response model."""
    return AlertMetricsWindow(
        time_window=row["time_window"],
        source=row.get("source"),
        priority=row.get("priority"),
        hour_of_day=row.get("hour_of_day"),
        day_of_week=row.get("day_of_week"),
        alert_count=_metric_count(row, "alert_count"),
        alerts_closed=_metric_count(row, "alerts_closed"),
        alerts_tp=_metric_count(row, "alerts_tp"),
        alerts_fp=_metric_count(row, "alerts_fp"),
        alerts_bp=_metric_count(row, "alerts_bp"),
        alerts_escalated=_metric_count(row, "alerts_escalated"),
        alerts_duplicate=_metric_count(row, "alerts_duplicate"),
        fp_rate=row.get("fp_rate"),
        escalation_rate=row.get("escalation_rate"),
    )


def bin_to_15min_floor(dt: datetime) -> datetime:
    """Round datetime down to nearest 15-minute boundary."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)


def bin_to_15min_ceil(dt: datetime) -> datetime:
    """Round datetime up to nearest 15-minute boundary."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    floored = bin_to_15min_floor(dt)
    if floored < dt:
        return floored + timedelta(minutes=15)
    return floored


def get_default_time_range() -> Tuple[datetime, datetime]:
    """Get default time range (last 7 days)."""
    end_time = bin_to_15min_ceil(datetime.now(timezone.utc))
    start_time = end_time - timedelta(days=7)
    return start_time, end_time


def _resolve_time_range(
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    *,
    align_to_windows: bool,
) -> Tuple[datetime, datetime]:
    """Apply the shared defaulting and optional 15-minute alignment policy."""
    if start_time is None or end_time is None:
        default_start, default_end = get_default_time_range()
        start_time = start_time or default_start
        end_time = end_time or default_end
    if align_to_windows:
        return bin_to_15min_floor(start_time), bin_to_15min_ceil(end_time)
    return start_time, end_time


def _time_range_params(
    start_time: datetime,
    end_time: datetime,
) -> dict[str, Any]:
    """Build the bind parameters shared by metrics range queries."""
    return {"start_time": start_time, "end_time": end_time}


class MetricsService:
    """Service for querying SOC metrics from materialized views."""

    async def get_soc_metrics(
        self,
        db: AsyncSession,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        priority: Optional[Priority] = None,
        source: Optional[str] = None,
    ) -> SOCMetricsResponse:
        """
        Get SOC-level metrics from the soc_metrics_15m materialized view.
        
        Args:
            db: Database session
            start_time: Query start (binned to 15-min floor)
            end_time: Query end (binned to 15-min ceiling)
            priority: Optional priority filter
            source: Optional alert source filter
            
        Returns:
            SOCMetricsResponse with summary and time series data
        """
        # Set defaults and bin to 15-minute boundaries
        start_time, end_time = _resolve_time_range(
            start_time,
            end_time,
            align_to_windows=True,
        )

        # Build query with optional filters
        query = """
            SELECT 
                time_window,
                priority,
                alert_source,
                alert_count,
                alerts_closed,
                alerts_tp,
                alerts_fp,
                alerts_bp,
                alerts_duplicate,
                alerts_unresolved,
                alerts_escalated,
                alerts_triaged,
                mttt_p50_seconds,
                mttt_mean_seconds,
                mttt_p95_seconds,
                case_count,
                cases_closed,
                cases_new,
                cases_in_progress,
                mttr_p50_seconds,
                mttr_mean_seconds,
                mttr_p95_seconds,
                task_count,
                tasks_completed,
                tasks_todo,
                tasks_in_progress,
                refreshed_at
            FROM soc_metrics_15m
            WHERE time_window >= :start_time
              AND time_window < :end_time
        """
        params = _time_range_params(start_time, end_time)
        
        if priority:
            query += " AND priority = :priority"
            params["priority"] = priority.value
        if source:
            # Source is an alert-only dimension. Keep the independent work row
            # so filtering alerts does not discard global case/task metrics.
            query += " AND (alert_source = :source OR metric_scope = 'work')"
            params["source"] = source
            
        query += " ORDER BY time_window ASC"

        rows = await _query_optional_metrics_view(
            db,
            query,
            params,
            view_name="soc_metrics_15m",
        )
        if rows is None:
            return SOCMetricsResponse(
                start_time=start_time,
                end_time=end_time,
                refreshed_at=None,
                summary=SOCMetricsSummary(),
                time_series=[],
            )

        # Build time series
        time_series: List[SOCMetricsWindow] = []
        refreshed_at = _first_refresh_time(rows)
        
        for row in rows:
            time_series.append(_soc_metrics_window(row))

        # Calculate summary aggregates
        summary = self._calculate_soc_summary(time_series)

        # Use live entity status counts for "currently open" values.
        # These should represent current state, independent of the selected time window.
        open_cases, open_tasks = await self._get_current_open_work_counts(db, priority)
        summary.open_cases = open_cases
        summary.open_tasks = open_tasks

        return SOCMetricsResponse(
            start_time=start_time,
            end_time=end_time,
            refreshed_at=refreshed_at,
            summary=summary,
            time_series=time_series,
        )

    async def _get_current_open_work_counts(
        self,
        db: AsyncSession,
        priority: Optional[Priority] = None,
    ) -> Tuple[int, int]:
        """Get current open case/task counts from live tables."""
        case_query = select(func.count(Case.id)).where(
            col(Case.status).in_([CaseStatus.NEW, CaseStatus.IN_PROGRESS])
        )
        task_query = select(func.count(Task.id)).where(
            col(Task.status).in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS])
        )

        if priority:
            case_query = case_query.where(col(Case.priority) == priority)
            task_query = task_query.where(col(Task.priority) == priority)

        case_result = await db.execute(case_query)
        task_result = await db.execute(task_query)

        open_cases = case_result.scalar() or 0
        open_tasks = task_result.scalar() or 0
        return open_cases, open_tasks

    def _calculate_soc_summary(self, time_series: List[SOCMetricsWindow]) -> SOCMetricsSummary:
        """Calculate aggregated summary from time series data."""
        if not time_series:
            return SOCMetricsSummary()

        total_alerts = sum(window.alert_count for window in time_series)
        total_alerts_closed = sum(window.alerts_closed for window in time_series)
        total_alerts_tp = sum(window.alerts_tp for window in time_series)
        total_alerts_fp = sum(window.alerts_fp for window in time_series)
        total_alerts_bp = sum(window.alerts_bp for window in time_series)
        total_escalated = sum(window.alerts_escalated for window in time_series)
        total_triaged = sum(window.alerts_triaged for window in time_series)
        
        work_metrics = _soc_work_metrics_by_window(time_series)
        total_cases = sum(window.case_count for window in work_metrics)
        total_cases_closed = sum(window.cases_closed for window in work_metrics)
        total_tasks = sum(window.task_count for window in work_metrics)
        total_tasks_completed = sum(
            window.tasks_completed for window in work_metrics
        )

        # Get latest open counts from the work grain. Alert rows can follow the
        # work row at the same timestamp and intentionally carry zero work data.
        latest_work = work_metrics[-1] if work_metrics else _SOCWorkWindowMetrics()
        open_cases = latest_work.cases_new + latest_work.cases_in_progress
        open_tasks = latest_work.tasks_todo + latest_work.tasks_in_progress

        # Calculate rates. Duplicate closures are operationally useful to count,
        # but they are not TP/FP/BP dispositions and should not dilute outcome rates.
        outcome_closed = _outcome_rate_denominator(
            total_alerts_closed,
            sum(window.alerts_duplicate for window in time_series),
        )
        tp_rate = _rate_or_none(total_alerts_tp, outcome_closed)
        fp_rate = _rate_or_none(total_alerts_fp, outcome_closed)
        bp_rate = _rate_or_none(total_alerts_bp, outcome_closed)
        escalation_rate = _rate_or_none(total_escalated, total_triaged)

        # Average the timing values reported by each materialized-view window.
        mttt_values = [
            window.mttt_mean_seconds
            for window in time_series
            if window.mttt_mean_seconds is not None
        ]
        mttt_p50_values = [
            window.mttt_p50_seconds
            for window in time_series
            if window.mttt_p50_seconds is not None
        ]
        mttr_values = [
            window.mttr_mean_seconds
            for window in work_metrics
            if window.mttr_mean_seconds is not None
        ]
        mttr_p50_values = [
            window.mttr_p50_seconds
            for window in work_metrics
            if window.mttr_p50_seconds is not None
        ]

        return SOCMetricsSummary(
            total_alerts=total_alerts,
            total_alerts_closed=total_alerts_closed,
            total_alerts_tp=total_alerts_tp,
            total_alerts_fp=total_alerts_fp,
            total_alerts_bp=total_alerts_bp,
            tp_rate=tp_rate,
            fp_rate=fp_rate,
            bp_rate=bp_rate,
            escalation_rate=escalation_rate,
            mttt_p50_seconds=_mean_or_none(mttt_p50_values),
            mttt_mean_seconds=_mean_or_none(mttt_values),
            mttr_p50_seconds=_mean_or_none(mttr_p50_values),
            mttr_mean_seconds=_mean_or_none(mttr_values),
            total_cases=total_cases,
            total_cases_closed=total_cases_closed,
            open_cases=open_cases,
            total_tasks=total_tasks,
            total_tasks_completed=total_tasks_completed,
            open_tasks=open_tasks,
        )

    async def get_analyst_metrics(
        self,
        db: AsyncSession,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        analyst: Optional[str] = None,
    ) -> AnalystMetricsResponse:
        """
        Get per-analyst metrics from the analyst_metrics_15m materialized view.
        
        Args:
            db: Database session
            start_time: Query start (binned to 15-min floor)
            end_time: Query end (binned to 15-min ceiling)
            analyst: Optional analyst username filter
            
        Returns:
            AnalystMetricsResponse with per-analyst summaries and time series
        """
        start_time, end_time = _resolve_time_range(
            start_time,
            end_time,
            align_to_windows=True,
        )

        query = """
            SELECT 
                time_window,
                analyst,
                alerts_triaged,
                alerts_tp,
                alerts_fp,
                alerts_bp,
                alerts_escalated,
                alerts_duplicate,
                mttt_p50_seconds,
                mttt_mean_seconds,
                cases_assigned,
                cases_closed,
                tasks_assigned,
                tasks_completed,
                refreshed_at
            FROM analyst_metrics_15m
            WHERE time_window >= :start_time
              AND time_window < :end_time
        """
        params = _time_range_params(start_time, end_time)
        
        if analyst:
            query += " AND analyst = :analyst"
            params["analyst"] = analyst
            
        query += " ORDER BY time_window ASC, analyst ASC"

        rows = await _query_optional_metrics_view(
            db,
            query,
            params,
            view_name="analyst_metrics_15m",
        )
        if rows is None:
            return AnalystMetricsResponse(
                start_time=start_time,
                end_time=end_time,
                refreshed_at=None,
                analysts=[],
                time_series=[],
            )

        # Build time series and aggregate by analyst
        time_series: List[AnalystMetricsWindow] = []
        analyst_data: defaultdict[str, _AnalystTotals] = defaultdict(_AnalystTotals)
        refreshed_at = _first_refresh_time(rows)

        for row in rows:
            analyst_name = row["analyst"]
            
            time_series.append(_analyst_metrics_window(row))

            analyst_data[analyst_name].add(row)

        # Calculate team median MTTT for comparison
        analyst_mttt_p50_values = [
            analyst_mean
            for totals in analyst_data.values()
            if (analyst_mean := totals.mean_mttt_p50) is not None
        ]
        team_mttt_p50 = (
            median(analyst_mttt_p50_values)
            if analyst_mttt_p50_values
            else None
        )

        # Build analyst summaries
        analysts = [
            totals.to_summary(analyst_name, team_mttt_p50)
            for analyst_name, totals in analyst_data.items()
        ]

        # Sort by alerts triaged descending
        analysts.sort(key=lambda a: a.total_alerts_triaged, reverse=True)

        return AnalystMetricsResponse(
            start_time=start_time,
            end_time=end_time,
            refreshed_at=refreshed_at,
            analysts=analysts,
            time_series=time_series,
        )

    async def get_alert_metrics(
        self,
        db: AsyncSession,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        source: Optional[str] = None,
        priority: Optional[Priority] = None,
        group_by: str = "source",
    ) -> AlertMetricsResponse:
        """
        Get alert performance metrics from the alert_metrics_15m materialized view.
        
        Args:
            db: Database session
            start_time: Query start (binned to 15-min floor)
            end_time: Query end (binned to 15-min ceiling)
            source: Optional source filter
            priority: Optional priority filter
            group_by: Dimension to group by: 'source', 'title', or 'tag'
            
        Returns:
            AlertMetricsResponse with dimension breakdown, hourly patterns, and time series
        """
        start_time, end_time = _resolve_time_range(
            start_time,
            end_time,
            align_to_windows=True,
        )

        query = """
            SELECT 
                time_window,
                source,
                priority,
                hour_of_day,
                day_of_week,
                alert_count,
                alerts_closed,
                alerts_tp,
                alerts_fp,
                alerts_bp,
                alerts_escalated,
                alerts_duplicate,
                fp_rate,
                escalation_rate,
                refreshed_at
            FROM alert_metrics_15m
            WHERE time_window >= :start_time
              AND time_window < :end_time
        """
        params = _time_range_params(start_time, end_time)
        
        if source:
            query += " AND source = :source"
            params["source"] = source
        if priority:
            query += " AND priority = :priority"
            params["priority"] = priority.value
            
        query += " ORDER BY time_window ASC"

        rows = await _query_optional_metrics_view(
            db,
            query,
            params,
            view_name="alert_metrics_15m",
        )
        if rows is None:
            return AlertMetricsResponse(
                start_time=start_time,
                end_time=end_time,
                refreshed_at=None,
                group_by=group_by,
                by_source=[],
                by_dimension=[],
                by_hour=[],
                time_series=[],
            )

        # Build time series and aggregates
        time_series: List[AlertMetricsWindow] = []
        source_data: defaultdict[str, _AlertSourceTotals] = defaultdict(
            _AlertSourceTotals
        )
        hourly_data = {hour: _HourlyAlertTotals() for hour in range(24)}
        refreshed_at = _first_refresh_time(rows)

        for row in rows:
            time_series.append(_alert_metrics_window(row))

            # Aggregate by source (for backwards compatibility)
            src = row.get("source") or "unknown"
            source_data[src].add(row)

            # Aggregate by hour
            hour = row.get("hour_of_day")
            if hour is not None:
                hourly_data[hour].add(
                    _metric_count(row, "alert_count"),
                    row["time_window"],
                )

        # Build source summaries (backwards compatible)
        by_source = [
            totals.to_source_metrics(src)
            for src, totals in source_data.items()
        ]
        by_source.sort(key=lambda s: s.total_alerts, reverse=True)

        # Build dimension breakdown based on group_by parameter
        by_dimension: List[AlertMetricsByDimension] = []
        
        if group_by == "source":
            by_dimension = [
                totals.to_dimension_metrics(src)
                for src, totals in source_data.items()
            ]
        elif group_by in ("title", "tag"):
            # Query alerts table directly for title/tag grouping
            by_dimension = await self._get_alert_metrics_by_dimension(
                db, start_time, end_time, group_by, source, priority
            )
        
        by_dimension.sort(key=lambda d: d.total_alerts, reverse=True)

        # Build hourly summaries
        by_hour = [
            hourly_data[hour].to_metrics(hour)
            for hour in range(24)
        ]

        return AlertMetricsResponse(
            start_time=start_time,
            end_time=end_time,
            refreshed_at=refreshed_at,
            group_by=group_by,
            by_source=by_source,
            by_dimension=by_dimension,
            by_hour=by_hour,
            time_series=time_series,
        )

    async def _get_alert_metrics_by_dimension(
        self,
        db: AsyncSession,
        start_time: datetime,
        end_time: datetime,
        dimension: str,
        source: Optional[str] = None,
        priority: Optional[Priority] = None,
    ) -> List[AlertMetricsByDimension]:
        """
        Query alerts table directly to get metrics grouped by title or tag.
        
        For tags, we unnest the JSON array to count each tag separately.
        """
        params = _time_range_params(start_time, end_time)
        
        if dimension == "title":
            query = """
                SELECT 
                    title AS dimension_value,
                    COUNT(*) AS total_alerts,
                    COUNT(*) FILTER (WHERE status::text LIKE 'CLOSED_%') AS total_closed,
                    COUNT(*) FILTER (WHERE status::text = 'CLOSED_TP') AS total_tp,
                    COUNT(*) FILTER (WHERE status::text = 'CLOSED_FP') AS total_fp,
                    COUNT(*) FILTER (WHERE status::text = 'CLOSED_BP') AS total_bp,
                    COUNT(*) FILTER (WHERE status::text = 'CLOSED_DUPLICATE') AS total_duplicate,
                    COUNT(*) FILTER (WHERE status::text = 'ESCALATED') AS total_escalated
                FROM alerts
                WHERE created_at >= :start_time
                  AND created_at < :end_time
            """
        elif dimension == "tag":
            query = """
                SELECT 
                    tag AS dimension_value,
                    COUNT(*) AS total_alerts,
                    COUNT(*) FILTER (WHERE status::text LIKE 'CLOSED_%') AS total_closed,
                    COUNT(*) FILTER (WHERE status::text = 'CLOSED_TP') AS total_tp,
                    COUNT(*) FILTER (WHERE status::text = 'CLOSED_FP') AS total_fp,
                    COUNT(*) FILTER (WHERE status::text = 'CLOSED_BP') AS total_bp,
                    COUNT(*) FILTER (WHERE status::text = 'CLOSED_DUPLICATE') AS total_duplicate,
                    COUNT(*) FILTER (WHERE status::text = 'ESCALATED') AS total_escalated
                FROM alerts, jsonb_array_elements_text(COALESCE(tags, '[]'::jsonb)) AS tag
                WHERE created_at >= :start_time
                  AND created_at < :end_time
            """
        else:
            return []
        
        if source:
            query += " AND source = :source"
            params["source"] = source
        if priority:
            query += " AND priority = :priority"
            params["priority"] = priority.value
        
        query += " GROUP BY dimension_value ORDER BY total_alerts DESC LIMIT 100"
        
        result = await db.execute(text(query), params)
        rows = result.mappings().all()
        
        by_dimension: List[AlertMetricsByDimension] = []
        for row in rows:
            closed = _metric_count(row, "total_closed")
            outcome_closed = _outcome_rate_denominator(
                closed,
                _metric_count(row, "total_duplicate"),
            )
            escalated = _metric_count(row, "total_escalated")
            triaged = closed + escalated
            
            by_dimension.append(AlertMetricsByDimension(
                dimension=dimension,
                value=row.get("dimension_value"),
                total_alerts=_metric_count(row, "total_alerts"),
                total_closed=closed,
                total_tp=_metric_count(row, "total_tp"),
                total_fp=_metric_count(row, "total_fp"),
                total_bp=_metric_count(row, "total_bp"),
                total_escalated=escalated,
                fp_rate=_rate_or_none(
                    _metric_count(row, "total_fp"),
                    outcome_closed,
                ),
                escalation_rate=_rate_or_none(escalated, triaged),
            ))
        
        return by_dimension

    async def get_ai_triage_metrics(
        self,
        db: AsyncSession,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> AITriageMetricsResponse:
        """
        Get AI triage accuracy metrics.
        
        Args:
            db: Database session
            start_time: Query start time
            end_time: Query end time
            
        Returns:
            AITriageMetricsResponse with summary, category breakdown, and weekly trend
        """
        # Set defaults
        start_time, end_time = _resolve_time_range(
            start_time,
            end_time,
            align_to_windows=False,
        )
        params = _time_range_params(start_time, end_time)
        
        # Get summary statistics
        summary_query = """
            SELECT
                COUNT(*) as total_recommendations,
                COUNT(*) FILTER (WHERE status = 'ACCEPTED') as total_accepted,
                COUNT(*) FILTER (WHERE status = 'REJECTED') as total_rejected,
                COUNT(*) FILTER (WHERE status = 'PENDING') as total_pending,
                AVG(confidence) as avg_confidence
            FROM triage_recommendations
            WHERE created_at >= :start_time AND created_at < :end_time
        """
        result = await db.execute(text(summary_query), params)
        summary_row = result.mappings().first()
        
        total = _metric_count(summary_row, "total_recommendations")
        accepted = _metric_count(summary_row, "total_accepted")
        rejected = _metric_count(summary_row, "total_rejected")
        reviewed = accepted + rejected
        
        summary = AITriageMetricsSummary(
            total_recommendations=total,
            total_accepted=accepted,
            total_rejected=rejected,
            total_pending=_metric_count(summary_row, "total_pending"),
            acceptance_rate=_rate_or_none(accepted, reviewed),
            rejection_rate=_rate_or_none(rejected, reviewed),
            avg_confidence=summary_row["avg_confidence"],
        )
        
        # Get rejection breakdown by category
        category_query = """
            SELECT
                rejection_category,
                COUNT(*) as count
            FROM triage_recommendations
            WHERE status = 'REJECTED'
                AND created_at >= :start_time AND created_at < :end_time
            GROUP BY rejection_category
            ORDER BY count DESC
        """
        result = await db.execute(text(category_query), params)
        category_rows = result.mappings().all()
        
        total_rejected_for_pct = rejected if rejected > 0 else 1
        by_category = [
            AITriageByCategory(
                category=row["rejection_category"],
                count=row["count"],
                percentage=row["count"] / total_rejected_for_pct,
            )
            for row in category_rows
        ]
        
        # Get breakdown by disposition
        disposition_query = """
            SELECT
                disposition,
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'ACCEPTED') as accepted,
                COUNT(*) FILTER (WHERE status = 'REJECTED') as rejected
            FROM triage_recommendations
            WHERE created_at >= :start_time AND created_at < :end_time
            GROUP BY disposition
            ORDER BY total DESC
        """
        result = await db.execute(text(disposition_query), params)
        disposition_rows = result.mappings().all()
        
        by_disposition = []
        for row in disposition_rows:
            disp_accepted = _metric_count(row, "accepted")
            disp_rejected = _metric_count(row, "rejected")
            disp_reviewed = disp_accepted + disp_rejected
            by_disposition.append(AITriageByDisposition(
                disposition=row["disposition"],
                total=row["total"],
                accepted=disp_accepted,
                rejected=disp_rejected,
                acceptance_rate=_rate_or_none(disp_accepted, disp_reviewed),
            ))
        
        # Get confidence correlation
        confidence_query = """
            SELECT
                CASE
                    WHEN confidence < 0.5 THEN '0.0-0.5'
                    WHEN confidence < 0.6 THEN '0.5-0.6'
                    WHEN confidence < 0.7 THEN '0.6-0.7'
                    WHEN confidence < 0.8 THEN '0.7-0.8'
                    WHEN confidence < 0.9 THEN '0.8-0.9'
                    ELSE '0.9-1.0'
                END as confidence_bucket,
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'ACCEPTED') as accepted,
                COUNT(*) FILTER (WHERE status = 'REJECTED') as rejected
            FROM triage_recommendations
            WHERE created_at >= :start_time AND created_at < :end_time
            GROUP BY confidence_bucket
            ORDER BY confidence_bucket
        """
        result = await db.execute(text(confidence_query), params)
        confidence_rows = result.mappings().all()
        
        by_confidence = []
        for row in confidence_rows:
            conf_accepted = _metric_count(row, "accepted")
            conf_rejected = _metric_count(row, "rejected")
            conf_reviewed = conf_accepted + conf_rejected
            by_confidence.append(AITriageConfidenceCorrelation(
                confidence_bucket=row["confidence_bucket"],
                total=row["total"],
                accepted=conf_accepted,
                rejected=conf_rejected,
                acceptance_rate=_rate_or_none(conf_accepted, conf_reviewed),
            ))
        
        # Get weekly trend
        weekly_query = """
            SELECT
                date_trunc('week', created_at) as week_start,
                COUNT(*) as total_recommendations,
                COUNT(*) FILTER (WHERE status = 'ACCEPTED') as accepted,
                COUNT(*) FILTER (WHERE status = 'REJECTED') as rejected
            FROM triage_recommendations
            WHERE created_at >= :start_time AND created_at < :end_time
            GROUP BY week_start
            ORDER BY week_start
        """
        result = await db.execute(text(weekly_query), params)
        weekly_rows = result.mappings().all()
        
        weekly_trend = []
        for row in weekly_rows:
            week_accepted = _metric_count(row, "accepted")
            week_rejected = _metric_count(row, "rejected")
            week_reviewed = week_accepted + week_rejected
            weekly_trend.append(AITriageWeeklyTrend(
                week_start=row["week_start"],
                total_recommendations=row["total_recommendations"],
                accepted=week_accepted,
                rejected=week_rejected,
                acceptance_rate=_rate_or_none(week_accepted, week_reviewed),
            ))
        
        return AITriageMetricsResponse(
            start_time=start_time,
            end_time=end_time,
            summary=summary,
            by_category=by_category,
            by_disposition=by_disposition,
            by_confidence=by_confidence,
            weekly_trend=weekly_trend,
        )

    async def get_ai_chat_metrics(
        self,
        db: AsyncSession,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> AIChatMetricsResponse:
        """
        Get AI chat feedback metrics.
        
        Args:
            db: Database session
            start_time: Query start time
            end_time: Query end time
            
        Returns:
            AIChatMetricsResponse with summary and weekly trend
        """
        # Set defaults
        start_time, end_time = _resolve_time_range(
            start_time,
            end_time,
            align_to_windows=False,
        )
        params = _time_range_params(start_time, end_time)
        
        # Get summary statistics (only count assistant messages)
        summary_query = """
            SELECT
                COUNT(*) as total_messages,
                COUNT(*) FILTER (WHERE feedback IS NOT NULL) as total_with_feedback,
                COUNT(*) FILTER (WHERE feedback = 'POSITIVE') as positive_feedback,
                COUNT(*) FILTER (WHERE feedback = 'NEGATIVE') as negative_feedback
            FROM langflow_messages
            WHERE role = 'ASSISTANT'
                AND created_at >= :start_time AND created_at < :end_time
        """
        result = await db.execute(text(summary_query), params)
        summary_row = result.mappings().first()
        
        total = _metric_count(summary_row, "total_messages")
        with_feedback = _metric_count(summary_row, "total_with_feedback")
        positive = _metric_count(summary_row, "positive_feedback")
        negative = _metric_count(summary_row, "negative_feedback")
        total_feedback = positive + negative
        
        summary = AIChatMetricsSummary(
            total_messages=total,
            total_with_feedback=with_feedback,
            positive_feedback=positive,
            negative_feedback=negative,
            feedback_rate=_rate_or_none(with_feedback, total),
            satisfaction_rate=_rate_or_none(positive, total_feedback),
        )
        
        # Get weekly trend
        weekly_query = """
            SELECT
                date_trunc('week', created_at) as week_start,
                COUNT(*) as total_messages,
                COUNT(*) FILTER (WHERE feedback = 'POSITIVE') as positive_feedback,
                COUNT(*) FILTER (WHERE feedback = 'NEGATIVE') as negative_feedback
            FROM langflow_messages
            WHERE role = 'ASSISTANT'
                AND created_at >= :start_time AND created_at < :end_time
            GROUP BY week_start
            ORDER BY week_start
        """
        result = await db.execute(text(weekly_query), params)
        weekly_rows = result.mappings().all()
        
        weekly_trend = []
        for row in weekly_rows:
            week_total = _metric_count(row, "total_messages")
            week_positive = _metric_count(row, "positive_feedback")
            week_negative = _metric_count(row, "negative_feedback")
            week_with_feedback = week_positive + week_negative
            weekly_trend.append(AIChatWeeklyTrend(
                week_start=row["week_start"],
                total_messages=week_total,
                positive_feedback=week_positive,
                negative_feedback=week_negative,
                feedback_rate=_rate_or_none(week_with_feedback, week_total),
                satisfaction_rate=_rate_or_none(week_positive, week_with_feedback),
            ))
        
        return AIChatMetricsResponse(
            start_time=start_time,
            end_time=end_time,
            summary=summary,
            weekly_trend=weekly_trend,
        )

    async def get_triage_recommendations_drilldown(
        self,
        db: AsyncSession,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        disposition: Optional[TriageDisposition] = None,
        rejection_category: Optional[RejectionCategory] = None,
        status: Optional[RecommendationStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TriageRecommendationDrillDownResponse:
        """
        Get detailed triage recommendations for drill-down view.
        
        Args:
            db: Database session
            start_time: Query start time
            end_time: Query end time
            disposition: Filter by disposition
            rejection_category: Filter by rejection category
            status: Filter by recommendation status
            limit: Max results per page
            offset: Pagination offset
            
        Returns:
            TriageRecommendationDrillDownResponse with paginated results
        """
        start_time, end_time = _resolve_time_range(
            start_time,
            end_time,
            align_to_windows=False,
        )
        
        # Build WHERE conditions
        conditions = ["tr.created_at >= :start_time", "tr.created_at < :end_time"]
        params = _time_range_params(start_time, end_time)
        params.update(limit=limit, offset=offset)
        
        if disposition:
            conditions.append("tr.disposition = :disposition")
            params["disposition"] = disposition.value
        if rejection_category:
            conditions.append("tr.rejection_category = :rejection_category")
            params["rejection_category"] = rejection_category.value
        if status:
            conditions.append("tr.status = :status")
            params["status"] = status.value
        
        where_clause = " AND ".join(conditions)
        
        # Count total
        count_query = f"""
            SELECT COUNT(*) as total
            FROM triage_recommendations tr
            WHERE {where_clause}
        """
        result = await db.execute(text(count_query), params)
        total = result.scalar() or 0
        
        # Get paginated results with alert info
        query = f"""
            SELECT 
                tr.id,
                tr.alert_id,
                tr.disposition,
                tr.confidence,
                tr.status,
                tr.reviewed_by,
                tr.reviewed_at,
                tr.rejection_category,
                tr.rejection_reason,
                tr.created_at,
                a.title as alert_title,
                '{ALERT_PREFIX}-' || LPAD(a.id::text, 7, '0') as alert_human_id,
                a.source as alert_source
            FROM triage_recommendations tr
            JOIN alerts a ON tr.alert_id = a.id
            WHERE {where_clause}
            ORDER BY tr.created_at DESC
            LIMIT :limit OFFSET :offset
        """
        result = await db.execute(text(query), params)
        rows = result.mappings().all()
        
        items = []
        for row in rows:
            items.append(TriageRecommendationDetail(
                id=row["id"],
                alert_id=row["alert_id"],
                alert_title=row["alert_title"],
                alert_human_id=row["alert_human_id"],
                alert_source=row["alert_source"],
                disposition=TriageDisposition(row["disposition"]),
                confidence=row["confidence"],
                status=RecommendationStatus(row["status"]),
                reviewed_by=row["reviewed_by"],
                reviewed_at=row["reviewed_at"],
                rejection_category=(
                    RejectionCategory(row["rejection_category"])
                    if row["rejection_category"]
                    else None
                ),
                rejection_reason=row["rejection_reason"],
                created_at=row["created_at"],
            ))
        
        return TriageRecommendationDrillDownResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_chat_feedback_drilldown(
        self,
        db: AsyncSession,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        feedback: Optional[MessageFeedback] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ChatFeedbackDrillDownResponse:
        """
        Get detailed chat messages with feedback for drill-down view.
        
        Args:
            db: Database session
            start_time: Query start time
            end_time: Query end time
            feedback: Filter by feedback type (POSITIVE/NEGATIVE)
            limit: Max results per page
            offset: Pagination offset
            
        Returns:
            ChatFeedbackDrillDownResponse with paginated results
        """
        start_time, end_time = _resolve_time_range(
            start_time,
            end_time,
            align_to_windows=False,
        )
        
        # Build WHERE conditions
        conditions = [
            "m.created_at >= :start_time",
            "m.created_at < :end_time",
            "m.role = 'ASSISTANT'",
            "m.feedback IS NOT NULL",
        ]
        params = _time_range_params(start_time, end_time)
        params.update(limit=limit, offset=offset)
        
        if feedback:
            conditions.append("m.feedback = :feedback")
            params["feedback"] = feedback.value
        
        where_clause = " AND ".join(conditions)
        
        # Count total
        count_query = f"""
            SELECT COUNT(*) as total
            FROM langflow_messages m
            WHERE {where_clause}
        """
        result = await db.execute(text(count_query), params)
        total = result.scalar() or 0
        
        # Get paginated results with session and user info
        query = f"""
            SELECT 
                m.id as id,
                m.session_id,
                m.content,
                m.feedback,
                m.created_at,
                s.title as session_title,
                s.flow_id,
                s.user_id,
                u.username
            FROM langflow_messages m
            JOIN langflow_sessions s ON m.session_id = s.id
            JOIN user_accounts u ON s.user_id = u.id
            WHERE {where_clause}
            ORDER BY m.created_at DESC
            LIMIT :limit OFFSET :offset
        """
        result = await db.execute(text(query), params)
        rows = result.mappings().all()
        
        items = []
        for row in rows:
            # Truncate content for preview (first 200 chars)
            content = row["content"] or ""
            content_preview = content[:200] + "..." if len(content) > 200 else content
            
            items.append(ChatFeedbackMessageDetail(
                id=row["id"],
                session_id=row["session_id"],
                session_title=row["session_title"],
                flow_id=row["flow_id"],
                user_id=row["user_id"],
                username=row["username"],
                display_name=None,
                content=content_preview,
                feedback=MessageFeedback(row["feedback"]),
                created_at=row["created_at"],
            ))
        
        return ChatFeedbackDrillDownResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )


# Singleton instance
metrics_service = MetricsService()
