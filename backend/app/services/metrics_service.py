"""
SOC Metrics Service

Queries materialized views for SOC operational metrics aggregated in 15-minute windows.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
from sqlmodel import col

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
        if start_time is None or end_time is None:
            start_time, end_time = get_default_time_range()
        else:
            start_time = bin_to_15min_floor(start_time)
            end_time = bin_to_15min_ceil(end_time)

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
        params: dict = {"start_time": start_time, "end_time": end_time}
        
        if priority:
            query += " AND priority = :priority"
            params["priority"] = priority.value
        if source:
            query += " AND alert_source = :source"
            params["source"] = source
            
        query += " ORDER BY time_window ASC"

        try:
            result = await db.execute(text(query), params)
            rows = result.mappings().all()
        except Exception as e:
            logger.warning(f"Error querying soc_metrics_15m (view may not exist yet): {e}")
            # Return empty response if view doesn't exist
            return SOCMetricsResponse(
                start_time=start_time,
                end_time=end_time,
                refreshed_at=None,
                summary=SOCMetricsSummary(),
                time_series=[],
            )

        # Build time series
        time_series: List[SOCMetricsWindow] = []
        refreshed_at = None
        
        for row in rows:
            if refreshed_at is None and row.get("refreshed_at"):
                refreshed_at = row["refreshed_at"]
            
            time_series.append(SOCMetricsWindow(
                time_window=row["time_window"],
                priority=row.get("priority"),
                alert_source=row.get("alert_source"),
                alert_count=row.get("alert_count", 0) or 0,
                alerts_closed=row.get("alerts_closed", 0) or 0,
                alerts_tp=row.get("alerts_tp", 0) or 0,
                alerts_fp=row.get("alerts_fp", 0) or 0,
                alerts_bp=row.get("alerts_bp", 0) or 0,
                alerts_duplicate=row.get("alerts_duplicate", 0) or 0,
                alerts_unresolved=row.get("alerts_unresolved", 0) or 0,
                alerts_escalated=row.get("alerts_escalated", 0) or 0,
                alerts_triaged=row.get("alerts_triaged", 0) or 0,
                mttt_p50_seconds=row.get("mttt_p50_seconds"),
                mttt_mean_seconds=row.get("mttt_mean_seconds"),
                mttt_p95_seconds=row.get("mttt_p95_seconds"),
                case_count=row.get("case_count", 0) or 0,
                cases_closed=row.get("cases_closed", 0) or 0,
                cases_new=row.get("cases_new", 0) or 0,
                cases_in_progress=row.get("cases_in_progress", 0) or 0,
                mttr_p50_seconds=row.get("mttr_p50_seconds"),
                mttr_mean_seconds=row.get("mttr_mean_seconds"),
                mttr_p95_seconds=row.get("mttr_p95_seconds"),
                task_count=row.get("task_count", 0) or 0,
                tasks_completed=row.get("tasks_completed", 0) or 0,
                tasks_todo=row.get("tasks_todo", 0) or 0,
                tasks_in_progress=row.get("tasks_in_progress", 0) or 0,
            ))

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

        total_alerts = sum(w.alert_count for w in time_series)
        total_alerts_closed = sum(w.alerts_closed for w in time_series)
        total_alerts_tp = sum(w.alerts_tp for w in time_series)
        total_alerts_fp = sum(w.alerts_fp for w in time_series)
        total_alerts_bp = sum(w.alerts_bp for w in time_series)
        total_escalated = sum(w.alerts_escalated for w in time_series)
        total_triaged = sum(w.alerts_triaged for w in time_series)
        
        total_cases = sum(w.case_count for w in time_series)
        total_cases_closed = sum(w.cases_closed for w in time_series)
        total_tasks = sum(w.task_count for w in time_series)
        total_tasks_completed = sum(w.tasks_completed for w in time_series)

        # Get latest open counts from most recent window
        latest = time_series[-1] if time_series else None
        open_cases = (latest.cases_new if latest else 0) + (latest.cases_in_progress if latest else 0)
        open_tasks = (latest.tasks_todo if latest else 0) + (latest.tasks_in_progress if latest else 0)

        # Calculate rates
        tp_rate = total_alerts_tp / total_alerts_closed if total_alerts_closed > 0 else None
        fp_rate = total_alerts_fp / total_alerts_closed if total_alerts_closed > 0 else None
        bp_rate = total_alerts_bp / total_alerts_closed if total_alerts_closed > 0 else None
        escalation_rate = total_escalated / total_triaged if total_triaged > 0 else None

        # Calculate average timings (weighted average of means)
        mttt_values = [w.mttt_mean_seconds for w in time_series if w.mttt_mean_seconds is not None]
        mttt_p50_values = [w.mttt_p50_seconds for w in time_series if w.mttt_p50_seconds is not None]
        mttr_values = [w.mttr_mean_seconds for w in time_series if w.mttr_mean_seconds is not None]
        mttr_p50_values = [w.mttr_p50_seconds for w in time_series if w.mttr_p50_seconds is not None]

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
            mttt_p50_seconds=sum(mttt_p50_values) / len(mttt_p50_values) if mttt_p50_values else None,
            mttt_mean_seconds=sum(mttt_values) / len(mttt_values) if mttt_values else None,
            mttr_p50_seconds=sum(mttr_p50_values) / len(mttr_p50_values) if mttr_p50_values else None,
            mttr_mean_seconds=sum(mttr_values) / len(mttr_values) if mttr_values else None,
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
        if start_time is None or end_time is None:
            start_time, end_time = get_default_time_range()
        else:
            start_time = bin_to_15min_floor(start_time)
            end_time = bin_to_15min_ceil(end_time)

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
        params: dict = {"start_time": start_time, "end_time": end_time}
        
        if analyst:
            query += " AND analyst = :analyst"
            params["analyst"] = analyst
            
        query += " ORDER BY time_window ASC, analyst ASC"

        try:
            result = await db.execute(text(query), params)
            rows = result.mappings().all()
        except Exception as e:
            logger.warning(f"Error querying analyst_metrics_15m: {e}")
            return AnalystMetricsResponse(
                start_time=start_time,
                end_time=end_time,
                refreshed_at=None,
                analysts=[],
                time_series=[],
            )

        # Build time series and aggregate by analyst
        time_series: List[AnalystMetricsWindow] = []
        analyst_data: dict = {}
        refreshed_at = None

        for row in rows:
            if refreshed_at is None and row.get("refreshed_at"):
                refreshed_at = row["refreshed_at"]

            analyst_name = row["analyst"]
            
            time_series.append(AnalystMetricsWindow(
                time_window=row["time_window"],
                analyst=analyst_name,
                alerts_triaged=row.get("alerts_triaged", 0) or 0,
                alerts_tp=row.get("alerts_tp", 0) or 0,
                alerts_fp=row.get("alerts_fp", 0) or 0,
                alerts_bp=row.get("alerts_bp", 0) or 0,
                alerts_escalated=row.get("alerts_escalated", 0) or 0,
                alerts_duplicate=row.get("alerts_duplicate", 0) or 0,
                mttt_p50_seconds=row.get("mttt_p50_seconds"),
                mttt_mean_seconds=row.get("mttt_mean_seconds"),
                cases_assigned=row.get("cases_assigned", 0) or 0,
                cases_closed=row.get("cases_closed", 0) or 0,
                tasks_assigned=row.get("tasks_assigned", 0) or 0,
                tasks_completed=row.get("tasks_completed", 0) or 0,
            ))

            # Aggregate for summary
            if analyst_name not in analyst_data:
                analyst_data[analyst_name] = {
                    "alerts_triaged": 0,
                    "alerts_tp": 0,
                    "alerts_fp": 0,
                    "alerts_bp": 0,
                    "alerts_escalated": 0,
                    "cases_assigned": 0,
                    "cases_closed": 0,
                    "tasks_completed": 0,
                    "mttt_values": [],
                    "mttt_p50_values": [],
                }
            
            ad = analyst_data[analyst_name]
            ad["alerts_triaged"] += row.get("alerts_triaged", 0) or 0
            ad["alerts_tp"] += row.get("alerts_tp", 0) or 0
            ad["alerts_fp"] += row.get("alerts_fp", 0) or 0
            ad["alerts_bp"] += row.get("alerts_bp", 0) or 0
            ad["alerts_escalated"] += row.get("alerts_escalated", 0) or 0
            ad["cases_assigned"] += row.get("cases_assigned", 0) or 0
            ad["cases_closed"] += row.get("cases_closed", 0) or 0
            ad["tasks_completed"] += row.get("tasks_completed", 0) or 0
            if row.get("mttt_mean_seconds"):
                ad["mttt_values"].append(row["mttt_mean_seconds"])
            if row.get("mttt_p50_seconds"):
                ad["mttt_p50_values"].append(row["mttt_p50_seconds"])

        # Calculate team median MTTT for comparison
        all_mttt_p50 = []
        for ad in analyst_data.values():
            if ad["mttt_p50_values"]:
                all_mttt_p50.append(sum(ad["mttt_p50_values"]) / len(ad["mttt_p50_values"]))
        
        team_mttt_p50 = None
        if all_mttt_p50:
            sorted_mttt = sorted(all_mttt_p50)
            mid = len(sorted_mttt) // 2
            team_mttt_p50 = sorted_mttt[mid] if len(sorted_mttt) % 2 else (sorted_mttt[mid-1] + sorted_mttt[mid]) / 2

        # Build analyst summaries
        analysts: List[AnalystMetricsSummary] = []
        for analyst_name, ad in analyst_data.items():
            triaged = ad["alerts_triaged"]
            closed = ad["alerts_tp"] + ad["alerts_fp"] + ad["alerts_bp"]
            
            analysts.append(AnalystMetricsSummary(
                analyst=analyst_name,
                total_alerts_triaged=triaged,
                total_alerts_tp=ad["alerts_tp"],
                total_alerts_fp=ad["alerts_fp"],
                total_alerts_bp=ad["alerts_bp"],
                total_alerts_escalated=ad["alerts_escalated"],
                tp_rate=ad["alerts_tp"] / closed if closed > 0 else None,
                fp_rate=ad["alerts_fp"] / closed if closed > 0 else None,
                escalation_rate=ad["alerts_escalated"] / triaged if triaged > 0 else None,
                mttt_p50_seconds=sum(ad["mttt_p50_values"]) / len(ad["mttt_p50_values"]) if ad["mttt_p50_values"] else None,
                mttt_mean_seconds=sum(ad["mttt_values"]) / len(ad["mttt_values"]) if ad["mttt_values"] else None,
                team_mttt_p50_seconds=team_mttt_p50,
                total_cases_assigned=ad["cases_assigned"],
                total_cases_closed=ad["cases_closed"],
                total_tasks_completed=ad["tasks_completed"],
            ))

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
        if start_time is None or end_time is None:
            start_time, end_time = get_default_time_range()
        else:
            start_time = bin_to_15min_floor(start_time)
            end_time = bin_to_15min_ceil(end_time)

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
        params: dict = {"start_time": start_time, "end_time": end_time}
        
        if source:
            query += " AND source = :source"
            params["source"] = source
        if priority:
            query += " AND priority = :priority"
            params["priority"] = priority.value
            
        query += " ORDER BY time_window ASC"

        try:
            result = await db.execute(text(query), params)
            rows = result.mappings().all()
        except Exception as e:
            logger.warning(f"Error querying alert_metrics_15m: {e}")
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
        source_data: dict = {}
        hourly_data: dict = {h: {"count": 0, "days": set()} for h in range(24)}
        refreshed_at = None

        for row in rows:
            if refreshed_at is None and row.get("refreshed_at"):
                refreshed_at = row["refreshed_at"]

            time_series.append(AlertMetricsWindow(
                time_window=row["time_window"],
                source=row.get("source"),
                priority=row.get("priority"),
                hour_of_day=row.get("hour_of_day"),
                day_of_week=row.get("day_of_week"),
                alert_count=row.get("alert_count", 0) or 0,
                alerts_closed=row.get("alerts_closed", 0) or 0,
                alerts_tp=row.get("alerts_tp", 0) or 0,
                alerts_fp=row.get("alerts_fp", 0) or 0,
                alerts_bp=row.get("alerts_bp", 0) or 0,
                alerts_escalated=row.get("alerts_escalated", 0) or 0,
                alerts_duplicate=row.get("alerts_duplicate", 0) or 0,
                fp_rate=row.get("fp_rate"),
                escalation_rate=row.get("escalation_rate"),
            ))

            # Aggregate by source (for backwards compatibility)
            src = row.get("source") or "unknown"
            if src not in source_data:
                source_data[src] = {
                    "total": 0,
                    "closed": 0,
                    "tp": 0,
                    "fp": 0,
                    "bp": 0,
                    "escalated": 0,
                }
            source_data[src]["total"] += row.get("alert_count", 0) or 0
            source_data[src]["closed"] += row.get("alerts_closed", 0) or 0
            source_data[src]["tp"] += row.get("alerts_tp", 0) or 0
            source_data[src]["fp"] += row.get("alerts_fp", 0) or 0
            source_data[src]["bp"] += row.get("alerts_bp", 0) or 0
            source_data[src]["escalated"] += row.get("alerts_escalated", 0) or 0

            # Aggregate by hour
            hour = row.get("hour_of_day")
            if hour is not None:
                hourly_data[hour]["count"] += row.get("alert_count", 0) or 0
                # Track unique days for average calculation
                tw = row["time_window"]
                hourly_data[hour]["days"].add(tw.date())

        # Build source summaries (backwards compatible)
        by_source: List[AlertMetricsBySource] = []
        for src, sd in source_data.items():
            closed = sd["closed"]
            triaged = closed + sd["escalated"]
            by_source.append(AlertMetricsBySource(
                source=src,
                total_alerts=sd["total"],
                total_closed=closed,
                total_tp=sd["tp"],
                total_fp=sd["fp"],
                total_escalated=sd["escalated"],
                fp_rate=sd["fp"] / closed if closed > 0 else None,
                escalation_rate=sd["escalated"] / triaged if triaged > 0 else None,
            ))
        by_source.sort(key=lambda s: s.total_alerts, reverse=True)

        # Build dimension breakdown based on group_by parameter
        by_dimension: List[AlertMetricsByDimension] = []
        
        if group_by == "source":
            # Convert source_data to dimension format
            for src, sd in source_data.items():
                closed = sd["closed"]
                triaged = closed + sd["escalated"]
                by_dimension.append(AlertMetricsByDimension(
                    dimension="source",
                    value=src,
                    total_alerts=sd["total"],
                    total_closed=closed,
                    total_tp=sd["tp"],
                    total_fp=sd["fp"],
                    total_bp=sd["bp"],
                    total_escalated=sd["escalated"],
                    fp_rate=sd["fp"] / closed if closed > 0 else None,
                    escalation_rate=sd["escalated"] / triaged if triaged > 0 else None,
                ))
        elif group_by in ("title", "tag"):
            # Query alerts table directly for title/tag grouping
            by_dimension = await self._get_alert_metrics_by_dimension(
                db, start_time, end_time, group_by, source, priority
            )
        
        by_dimension.sort(key=lambda d: d.total_alerts, reverse=True)

        # Build hourly summaries
        by_hour: List[AlertMetricsHourly] = []
        for hour in range(24):
            hd = hourly_data[hour]
            num_days = len(hd["days"]) or 1
            by_hour.append(AlertMetricsHourly(
                hour_of_day=hour,
                alert_count=hd["count"],
                avg_alerts=hd["count"] / num_days,
            ))

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
        params: dict = {"start_time": start_time, "end_time": end_time}
        
        if dimension == "title":
            query = """
                SELECT 
                    title AS dimension_value,
                    COUNT(*) AS total_alerts,
                    COUNT(*) FILTER (WHERE status::text LIKE 'CLOSED_%') AS total_closed,
                    COUNT(*) FILTER (WHERE status::text = 'CLOSED_TP') AS total_tp,
                    COUNT(*) FILTER (WHERE status::text = 'CLOSED_FP') AS total_fp,
                    COUNT(*) FILTER (WHERE status::text = 'CLOSED_BP') AS total_bp,
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
        
        try:
            result = await db.execute(text(query), params)
            rows = result.mappings().all()
        except Exception as e:
            logger.warning(f"Error querying alerts for dimension {dimension}: {e}")
            return []
        
        by_dimension: List[AlertMetricsByDimension] = []
        for row in rows:
            closed = row.get("total_closed", 0) or 0
            escalated = row.get("total_escalated", 0) or 0
            triaged = closed + escalated
            
            by_dimension.append(AlertMetricsByDimension(
                dimension=dimension,
                value=row.get("dimension_value"),
                total_alerts=row.get("total_alerts", 0) or 0,
                total_closed=closed,
                total_tp=row.get("total_tp", 0) or 0,
                total_fp=row.get("total_fp", 0) or 0,
                total_bp=row.get("total_bp", 0) or 0,
                total_escalated=escalated,
                fp_rate=row["total_fp"] / closed if closed > 0 else None,
                escalation_rate=escalated / triaged if triaged > 0 else None,
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
        if start_time is None or end_time is None:
            start_time, end_time = get_default_time_range()
        
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
        result = await db.execute(text(summary_query), {"start_time": start_time, "end_time": end_time})
        summary_row = result.mappings().first()
        
        total = summary_row["total_recommendations"] or 0
        accepted = summary_row["total_accepted"] or 0
        rejected = summary_row["total_rejected"] or 0
        reviewed = accepted + rejected
        
        summary = AITriageMetricsSummary(
            total_recommendations=total,
            total_accepted=accepted,
            total_rejected=rejected,
            total_pending=summary_row["total_pending"] or 0,
            acceptance_rate=accepted / reviewed if reviewed > 0 else None,
            rejection_rate=rejected / reviewed if reviewed > 0 else None,
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
        result = await db.execute(text(category_query), {"start_time": start_time, "end_time": end_time})
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
        result = await db.execute(text(disposition_query), {"start_time": start_time, "end_time": end_time})
        disposition_rows = result.mappings().all()
        
        by_disposition = []
        for row in disposition_rows:
            disp_accepted = row["accepted"] or 0
            disp_rejected = row["rejected"] or 0
            disp_reviewed = disp_accepted + disp_rejected
            by_disposition.append(AITriageByDisposition(
                disposition=row["disposition"],
                total=row["total"],
                accepted=disp_accepted,
                rejected=disp_rejected,
                acceptance_rate=disp_accepted / disp_reviewed if disp_reviewed > 0 else None,
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
        result = await db.execute(text(confidence_query), {"start_time": start_time, "end_time": end_time})
        confidence_rows = result.mappings().all()
        
        by_confidence = []
        for row in confidence_rows:
            conf_accepted = row["accepted"] or 0
            conf_rejected = row["rejected"] or 0
            conf_reviewed = conf_accepted + conf_rejected
            by_confidence.append(AITriageConfidenceCorrelation(
                confidence_bucket=row["confidence_bucket"],
                total=row["total"],
                accepted=conf_accepted,
                rejected=conf_rejected,
                acceptance_rate=conf_accepted / conf_reviewed if conf_reviewed > 0 else None,
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
        result = await db.execute(text(weekly_query), {"start_time": start_time, "end_time": end_time})
        weekly_rows = result.mappings().all()
        
        weekly_trend = []
        for row in weekly_rows:
            week_accepted = row["accepted"] or 0
            week_rejected = row["rejected"] or 0
            week_reviewed = week_accepted + week_rejected
            weekly_trend.append(AITriageWeeklyTrend(
                week_start=row["week_start"],
                total_recommendations=row["total_recommendations"],
                accepted=week_accepted,
                rejected=week_rejected,
                acceptance_rate=week_accepted / week_reviewed if week_reviewed > 0 else None,
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
        if start_time is None or end_time is None:
            start_time, end_time = get_default_time_range()
        
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
        result = await db.execute(text(summary_query), {"start_time": start_time, "end_time": end_time})
        summary_row = result.mappings().first()
        
        total = summary_row["total_messages"] or 0
        with_feedback = summary_row["total_with_feedback"] or 0
        positive = summary_row["positive_feedback"] or 0
        negative = summary_row["negative_feedback"] or 0
        total_feedback = positive + negative
        
        summary = AIChatMetricsSummary(
            total_messages=total,
            total_with_feedback=with_feedback,
            positive_feedback=positive,
            negative_feedback=negative,
            feedback_rate=with_feedback / total if total > 0 else None,
            satisfaction_rate=positive / total_feedback if total_feedback > 0 else None,
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
        result = await db.execute(text(weekly_query), {"start_time": start_time, "end_time": end_time})
        weekly_rows = result.mappings().all()
        
        weekly_trend = []
        for row in weekly_rows:
            week_total = row["total_messages"] or 0
            week_positive = row["positive_feedback"] or 0
            week_negative = row["negative_feedback"] or 0
            week_with_feedback = week_positive + week_negative
            weekly_trend.append(AIChatWeeklyTrend(
                week_start=row["week_start"],
                total_messages=week_total,
                positive_feedback=week_positive,
                negative_feedback=week_negative,
                feedback_rate=week_with_feedback / week_total if week_total > 0 else None,
                satisfaction_rate=week_positive / week_with_feedback if week_with_feedback > 0 else None,
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
        if start_time is None or end_time is None:
            start_time, end_time = get_default_time_range()
        
        # Build WHERE conditions
        conditions = ["tr.created_at >= :start_time", "tr.created_at < :end_time"]
        params: dict = {"start_time": start_time, "end_time": end_time, "limit": limit, "offset": offset}
        
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
                'ALT-' || LPAD(a.id::text, 7, '0') as alert_human_id,
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
                disposition=TriageDisposition(row["disposition"]) if row["disposition"] else None,
                confidence=row["confidence"],
                status=RecommendationStatus(row["status"]) if row["status"] else None,
                reviewed_by=row["reviewed_by"],
                reviewed_at=row["reviewed_at"],
                rejection_category=RejectionCategory(row["rejection_category"]) if row["rejection_category"] else None,
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
        if start_time is None or end_time is None:
            start_time, end_time = get_default_time_range()
        
        # Build WHERE conditions
        conditions = [
            "m.created_at >= :start_time",
            "m.created_at < :end_time",
            "m.role = 'ASSISTANT'",
            "m.feedback IS NOT NULL",
        ]
        params: dict = {"start_time": start_time, "end_time": end_time, "limit": limit, "offset": offset}
        
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
                feedback=MessageFeedback(row["feedback"]) if row["feedback"] else None,
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
