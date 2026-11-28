"""Build dashboard results and drill-downs from the same record predicates."""

import logging
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from hmac import digest
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from pydantic import ValidationError
from sqlalchemy import DateTime, String, cast, func, literal, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.entity_ids import WORK_ITEM_KIND_TO_PREFIX, format_entity_id
from app.models.dashboard_models import (
    DashboardDate,
    DashboardDrillContext,
    DashboardEvaluate,
    DashboardEvaluation,
    DashboardPoint,
    DashboardRecord,
    DashboardRecords,
    DashboardResult,
)
from app.models.enums import AlertStatus, CaseStatus, TaskStatus
from app.models.models import Alert, Case, Task, UserAccount
from app.services.alert_triage_apply_service import CLOSED_ALERT_STATUSES
from app.services.assignee_filter_utils import append_assignee_filter
from app.services.dashboard_catalog import CATALOG, MEASURES, target_minutes, validate_widget
from app.services.tag_filter_utils import append_tag_filters

logger = logging.getLogger(__name__)
MAX_GROUPS = 50
PAGE_SIZE = 25
DRILL_TTL = 30 * 60
MODELS = {"alerts": Alert, "cases": Case, "tasks": Task}
OPEN_STATES = {
    "alerts": (AlertStatus.NEW, AlertStatus.IN_PROGRESS),
    "cases": (CaseStatus.NEW, CaseStatus.IN_PROGRESS),
    "tasks": (TaskStatus.TODO, TaskStatus.IN_PROGRESS),
}
PRESET_DAYS = {"last_7_days": 7, "last_30_days": 30, "last_90_days": 90}


def resolve_range(date: DashboardDate, now: datetime, zone: str) -> tuple[datetime, datetime]:
    if date.start is not None and date.end is not None:
        return date.start.astimezone(timezone.utc), date.end.astimezone(timezone.utc)
    start = now.astimezone(ZoneInfo(zone)) - timedelta(days=PRESET_DAYS[date.preset])
    return start.astimezone(timezone.utc), now


def _drill_cipher(session_token: str) -> Fernet:
    key = digest(session_token.encode("utf-8"), b"intercept custom dashboard drill v1", "sha256")
    return Fernet(urlsafe_b64encode(key))


def decode_drill(reference: str, session_token: str, viewer: UserAccount) -> DashboardDrillContext:
    try:
        plain = _drill_cipher(session_token).decrypt(reference.encode("ascii"), ttl=DRILL_TTL)
        context = DashboardDrillContext.model_validate_json(plain)
    except (InvalidToken, UnicodeError, ValidationError) as exc:
        raise ValueError("This record link has expired. Refresh the dashboard to open it again.") from exc
    if context.viewer != viewer.id:
        raise ValueError("This record link belongs to another session.")
    validate_widget(context.widget, context.parameters)
    return context


class DashboardQuery:
    def __init__(self, context: DashboardDrillContext, viewer: UserAccount):
        self.context = context
        self.widget = context.widget
        self.measure = MEASURES[self.widget.measure]
        self.model = MODELS[self.measure.entity]
        self.catalog = CATALOG[self.widget.measure]
        self.target = target_minutes(self.widget, context.parameters)
        self.completed = None
        self.valid_duration = None
        self.group = self._group_expression()
        self.filters = self._record_scope(viewer)
        model = self.model

        if self.measure.basis == "current":
            clock = literal(context.evaluated_at, DateTime(timezone=True))
        else:
            clock = getattr(model, self.measure.basis)
            self.filters += [clock >= context.start, clock < context.end]
        self.elapsed = func.extract("epoch", clock - model.created_at)
        if self.measure.basis in {"triaged_at", "closed_at"}:
            self.completed = clock
            self.valid_duration = clock >= model.created_at
        if self.measure.basis == "closed_at":
            self.filters.append(Case.status == CaseStatus.CLOSED)
        if self.measure.basis == "current":
            self.filters.append(model.status.in_(OPEN_STATES[self.measure.entity]))

        kind = self.measure.kind
        minimum = self.widget.parameters.min_age_minutes
        self.contributes = None
        if minimum is not None:
            self.filters.append(model.created_at < context.evaluated_at - timedelta(minutes=minimum))
        if kind == "past_target":
            self.filters.append(Case.created_at < context.evaluated_at - timedelta(minutes=self.target))
        elif kind == "overdue":
            self.filters.append(Task.due_date < context.evaluated_at)
        elif kind == "duplicates":
            self.filters.append(Alert.status == AlertStatus.CLOSED_DUPLICATE)
        elif kind == "false_positive_rate":
            self.filters.append(Alert.status.in_(CLOSED_ALERT_STATUSES - {AlertStatus.CLOSED_DUPLICATE}))
            self.contributes = Alert.status == AlertStatus.CLOSED_FP
        elif kind in {"miss_count", "miss_rate"}:
            self.contributes = self.elapsed > self.target * 60

        for condition in self.widget.filters:
            if condition.field == "tags":
                include = condition.value if condition.op == "contains_all" else None
                exclude = condition.value if condition.op == "excludes_all" else None
                tags = func.coalesce(model.tags, literal([], type_=model.__table__.c.tags.type))
                append_tag_filters(self.filters, tags, include, exclude)
            elif condition.field == "assignee":
                append_assignee_filter(self.filters, model.assignee, condition.value)
            else:
                self.filters.append(getattr(model, condition.field).in_(condition.value))

    @staticmethod
    def _record_scope(viewer: UserAccount) -> list:
        # The existing alert, case and task read routes allow all records in
        # this deployment to an authenticated viewer. Keep the policy here
        # shared between aggregations and record drill-downs.
        if viewer.id is None:
            raise ValueError("Record queries require an authenticated viewer")
        return []

    def _group_expression(self):
        group = self.widget.group_by
        if group in {"day", "week"}:
            stamp = getattr(self.model, self.measure.basis)
            local = func.timezone(self.context.timezone, stamp)
            return func.to_char(func.date_trunc(group, local), "YYYY-MM-DD")
        return cast(getattr(self.model, group), String) if group else None

    async def result(self, db: AsyncSession, cipher: Fernet) -> DashboardResult:
        widget = self.widget
        count = func.count(self.model.id)
        eligible = count
        excluded = literal(0)
        if self.valid_duration is not None:
            eligible = count.filter(self.valid_duration)
            excluded = count - eligible
            count = eligible
        if self.contributes is not None:
            conditions = [self.contributes]
            if self.valid_duration is not None:
                conditions.append(self.valid_duration)
            count = func.count(self.model.id).filter(*conditions)

        kind = self.measure.kind
        rate = kind in {"miss_rate", "false_positive_rate"}
        value = count
        if rate:
            value = count * 100.0 / func.nullif(eligible, 0)
        elif kind == "duration":
            aggregation = widget.aggregation or "p50"
            if aggregation == "mean":
                value = func.avg(self.elapsed).filter(self.valid_duration)
            else:
                percentile = 0.5 if aggregation == "p50" else 0.95
                value = func.percentile_cont(percentile).within_group(self.elapsed).filter(self.valid_duration)

        if widget.display == "table" and self.group is None:
            records = await self.records(db, 1)
            point = self._point(cipher, None, None, records.total, None)
            return DashboardResult(widget_id=widget.id, points=[point], records=records)

        group = self.group if self.group is not None else literal(None, String)
        stmt = select(group, value, count, eligible, excluded).select_from(self.model).where(*self.filters)
        if self.group is not None:
            stmt = stmt.group_by(group)
            if widget.display == "trend":
                stmt = stmt.order_by(group)
            else:
                stmt = stmt.order_by(value.desc().nulls_last(), group.asc().nulls_last()).limit(MAX_GROUPS + 1)
        rows = (await db.execute(stmt)).all()
        truncated = widget.display != "trend" and len(rows) > MAX_GROUPS
        return DashboardResult(
            widget_id=widget.id,
            points=[
                self._point(cipher, key, val, total, denominator if rate else None, invalid)
                for key, val, total, denominator, invalid in (rows[:MAX_GROUPS] if truncated else rows)
            ],
            truncated=truncated,
        )

    def _point(self, cipher: Fernet, key, value, count, denominator, excluded=0) -> DashboardPoint:
        fields = {"grouped": self.group is not None, "group": key, "original_count": count}
        context = self.context.model_copy(update=fields)
        reference = cipher.encrypt(context.model_dump_json().encode()).decode()
        eligible_reference = None
        if denominator is not None:
            eligible = context.model_copy(update={"eligible": True, "original_count": denominator})
            eligible_reference = cipher.encrypt(eligible.model_dump_json().encode()).decode()
        return DashboardPoint(
            group=key, value=value, count=count, eligible_count=denominator, excluded_count=excluded,
            drill=reference, eligible_drill=eligible_reference,
        )

    async def records(self, db: AsyncSession, page: int) -> DashboardRecords:
        model = self.model
        context = self.context
        filters = list(self.filters)
        if self.valid_duration is not None:
            filters.append(self.valid_duration)
        if context.grouped:
            filters.append(self.group.is_not_distinct_from(context.group))
        if self.contributes is not None and not context.eligible:
            filters.append(self.contributes)

        fields = {
            "id": model.id,
            "title": model.title,
            "created_at": model.created_at,
            "status": model.status,
            "priority": model.priority,
            "assignee": model.assignee,
        }
        for field in ("source", "case_id", "due_date"):
            if hasattr(model, field):
                fields[field] = getattr(model, field)
        if self.completed is not None:
            fields["completed_at"] = self.completed
        if "elapsed_seconds" in self.catalog.record_columns:
            fields["elapsed_seconds"] = self.elapsed
        if self.target is not None:
            fields["target_seconds"] = literal(self.target * 60)

        table = self.widget.table
        sort = table.sort if table else None
        sort_name = {"human_id": "id", "case": "case_id"}.get(sort.field, sort.field) if sort else "created_at"
        order_column = fields[sort_name]
        order = order_column.asc() if sort and sort.direction == "asc" else order_column.desc()
        stmt = (
            select(*(column.label(name) for name, column in fields.items()), func.count().over().label("total"))
            .select_from(model).where(*filters)
            .order_by(order.nulls_last(), model.id)
            .limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE)
        )
        rows = (await db.execute(stmt)).mappings().all()
        total = rows[0]["total"] if rows else 0
        if not rows and page > 1:
            total = (await db.execute(select(func.count(model.id)).where(*filters))).scalar_one()
        prefix = WORK_ITEM_KIND_TO_PREFIX[self.measure.entity[:-1]]
        columns = table.columns if table else [
            field for field in ["human_id", "title", "priority", "status", "assignee", "created_at",
                                "completed_at", "elapsed_seconds", "target_seconds", "due_date", "case"]
            if field in self.catalog.record_columns
        ]
        queue_statuses = None
        if (
            self.measure.kind == "open"
            and not context.grouped
            and not self.widget.filters
            and self.widget.parameters.min_age_minutes is None
        ):
            queue_statuses = [state.value for state in OPEN_STATES[self.measure.entity]]
        return DashboardRecords(
            entity=self.measure.entity,
            columns=columns,
            total=total,
            page=page,
            page_size=PAGE_SIZE,
            evaluated_at=context.evaluated_at,
            original_count=context.original_count,
            queue_statuses=queue_statuses,
            items=[
                DashboardRecord(human_id=format_entity_id(row["id"], prefix), **{
                    key: row[key] for key in fields
                })
                for row in rows
            ],
        )


async def evaluate(
    db: AsyncSession, payload: DashboardEvaluate, viewer: UserAccount, session_token: str,
) -> DashboardEvaluation:
    now = datetime.now(timezone.utc)
    start, end = resolve_range(payload.date or payload.definition.date, now, payload.timezone)
    results = []
    cipher = _drill_cipher(session_token)
    await db.execute(text("SET LOCAL statement_timeout = '2s'"))
    for widget in payload.definition.widgets:
        context = DashboardDrillContext(
            viewer=viewer.id, widget=widget, parameters=payload.definition.parameters,
            start=start, end=end, evaluated_at=now, timezone=payload.timezone,
            dashboard_id=payload.dashboard_id, revision=payload.revision,
        )
        try:
            validate_widget(widget, payload.definition.parameters)
            async with db.begin_nested():
                results.append(await DashboardQuery(context, viewer).result(db, cipher))
        except ValueError as exc:
            results.append(DashboardResult(widget_id=widget.id, error=str(exc)))
        except DBAPIError:
            logger.warning("Dashboard widget query failed for measure %s", widget.measure)
            results.append(DashboardResult(widget_id=widget.id, error="Could not load this widget. Try refreshing."))
    return DashboardEvaluation(evaluated_at=now, start=start, end=end, results=results)


async def drill(db: AsyncSession, context: DashboardDrillContext, viewer: UserAccount, page: int) -> DashboardRecords:
    await db.execute(text("SET LOCAL statement_timeout = '2s'"))
    return await DashboardQuery(context, viewer).records(db, page)
