"""Versioned custom dashboard definition and query contracts."""

from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

MAX_WIDGETS = 12
MAX_MINUTES = 525_600
MAX_RANGE = timedelta(days=366)
Display = Literal["number", "trend", "breakdown", "table"]
Aggregation = Literal["mean", "p50", "p95"]
Entity = Literal["alerts", "cases", "tasks"]
DateBasis = Literal["created_at", "triaged_at", "closed_at", "current"]
Scope = Literal["starter", "personal", "organization"]
WidgetId = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
FilterValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Minutes = Annotated[int, Field(strict=True, ge=0, le=MAX_MINUTES)]


class DashboardContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DashboardDate(DashboardContract):
    preset: Literal["last_7_days", "last_30_days", "last_90_days", "custom"] = "last_7_days"
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_range(self):
        if self.preset == "custom":
            if self.start is None or self.end is None or not timedelta() < self.end - self.start <= MAX_RANGE:
                raise ValueError("Choose a positive date range of up to 366 days")
        elif self.start is not None or self.end is not None:
            raise ValueError("Only a custom range takes start and end dates")
        return self


class DashboardFilter(DashboardContract):
    field: Literal["priority", "status", "assignee", "source", "title", "tags", "picerl_stage"]
    op: Literal["in", "contains_all", "excludes_all"]
    value: list[FilterValue] = Field(min_length=1, max_length=20)


class DashboardBinding(DashboardContract):
    dashboard_parameter: Literal["resolution_target_minutes"]


class DashboardWidgetParameters(DashboardContract):
    min_age_minutes: Minutes | None = None
    target_minutes: Minutes | DashboardBinding | None = None


class DashboardParameters(DashboardContract):
    resolution_target_minutes: Minutes | None = None


class DashboardLayout(DashboardContract):
    order: int = Field(ge=0, lt=MAX_WIDGETS)
    width: Literal["half", "wide"] = "half"


class DashboardSort(DashboardContract):
    field: str = Field(max_length=30)
    direction: Literal["asc", "desc"] = "asc"


class DashboardTable(DashboardContract):
    columns: list[str] = Field(min_length=1, max_length=10)
    sort: DashboardSort | None = None


class DashboardWidget(DashboardContract):
    id: WidgetId
    title: Label
    measure: str = Field(min_length=1, max_length=64)
    display: Display
    group_by: str | None = Field(default=None, max_length=30)
    aggregation: Aggregation | None = None
    filters: list[DashboardFilter] = Field(default_factory=list, max_length=10)
    parameters: DashboardWidgetParameters = Field(default_factory=DashboardWidgetParameters)
    layout: DashboardLayout
    table: DashboardTable | None = None

    @field_validator("filters")
    @classmethod
    def bound_filter_size(cls, filters: list[DashboardFilter]) -> list[DashboardFilter]:
        if sum(len(value.encode("utf-8")) for condition in filters for value in condition.value) > 3500:
            raise ValueError("This widget has too many filter values")
        return filters


class DashboardDefinition(DashboardContract):
    schema_version: Literal[1] = 1
    date: DashboardDate = Field(default_factory=DashboardDate)
    parameters: DashboardParameters = Field(default_factory=DashboardParameters)
    widgets: list[DashboardWidget] = Field(default_factory=list, max_length=MAX_WIDGETS)

    @model_validator(mode="after")
    def validate_layout(self):
        if len({widget.id for widget in self.widgets}) != len(self.widgets):
            raise ValueError("Widget IDs must be unique")
        if len({widget.layout.order for widget in self.widgets}) != len(self.widgets):
            raise ValueError("Widget positions must be unique")
        return self


class DashboardFilterOption(DashboardContract):
    field: str
    label: str
    operators: list[str]
    values: list[str] = Field(default_factory=list)


class DashboardMeasure(DashboardContract):
    id: str
    entity: Entity
    label: str
    description: str
    date_basis: DateBasis
    unit: Literal["count", "seconds", "percent"]
    displays: list[Display]
    dimensions: list[str]
    filters: list[DashboardFilterOption]
    parameters: list[str]
    aggregations: list[Aggregation]
    record_columns: list[str]


class DashboardSummary(DashboardContract):
    id: str
    title: str
    scope: Scope
    revision: int
    can_edit: bool


class CustomDashboardRead(DashboardSummary):
    definition: DashboardDefinition


class DashboardWrite(DashboardContract):
    title: Label
    definition: DashboardDefinition
    scope: Literal["personal", "organization"] = "personal"


class DashboardUpdate(DashboardWrite):
    revision: int = Field(ge=1)


class DashboardDuplicate(DashboardContract):
    title: Label | None = None


class DashboardEvaluate(DashboardContract):
    definition: DashboardDefinition
    date: DashboardDate | None = None
    timezone: str = Field(default="UTC", max_length=100)
    dashboard_id: str | None = Field(default=None, max_length=40)
    revision: int | None = Field(default=None, ge=0)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Choose a valid IANA timezone") from exc
        return value


class DashboardPoint(DashboardContract):
    group: str | None = None
    value: float | None = None
    count: int
    eligible_count: int | None = None
    excluded_count: int = 0
    drill: str
    eligible_drill: str | None = None


class DashboardRecord(DashboardContract):
    id: int
    human_id: str
    title: str
    created_at: AwareDatetime
    status: str
    priority: str
    assignee: str | None = None
    source: str | None = None
    case_id: int | None = None
    due_date: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    elapsed_seconds: float | None = None
    target_seconds: int | None = None


class DashboardRecords(DashboardContract):
    entity: Entity
    columns: list[str]
    items: list[DashboardRecord]
    total: int
    page: int
    page_size: int
    evaluated_at: AwareDatetime
    original_count: int | None = None
    queue_statuses: list[str] | None = None


class DashboardResult(DashboardContract):
    widget_id: str
    points: list[DashboardPoint] = Field(default_factory=list)
    records: DashboardRecords | None = None
    truncated: bool = False
    error: str | None = None


class DashboardEvaluation(DashboardContract):
    evaluated_at: AwareDatetime
    start: AwareDatetime
    end: AwareDatetime
    results: list[DashboardResult]


class DashboardDrillRequest(DashboardContract):
    reference: str = Field(min_length=1, max_length=32_768)
    page: int = Field(default=1, ge=1, le=100_000)


class DashboardDrillContext(DashboardContract):
    viewer: UUID
    widget: DashboardWidget
    parameters: DashboardParameters
    start: AwareDatetime
    end: AwareDatetime
    evaluated_at: AwareDatetime
    timezone: str
    grouped: bool = False
    group: str | None = None
    eligible: bool = False
    original_count: int | None = None
    dashboard_id: str | None = None
    revision: int | None = None
