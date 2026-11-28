"""Allowlisted measures for the dashboard designer and record queries."""

from dataclasses import dataclass

from app.models.dashboard_models import (
    DashboardDefinition,
    DashboardFilterOption,
    DashboardMeasure,
    DashboardParameters,
    DashboardWidget,
    DateBasis,
    Entity,
)
from app.models.enums import AlertStatus, CaseStatus, PICERLStage, Priority, TaskStatus

STATUS = {"alerts": AlertStatus, "cases": CaseStatus, "tasks": TaskStatus}
COMMON_COLUMNS = ["human_id", "title", "created_at", "status", "priority", "assignee"]
GROUPS = {
    "alerts": ["priority", "status", "assignee", "source", "title"],
    "cases": ["priority", "status", "assignee"],
    "tasks": ["priority", "status", "assignee", "picerl_stage"],
}
COLUMNS = {
    "alerts": ["source", "case"],
    "cases": [],
    "tasks": ["due_date", "case"],
}
LABELS = {"picerl_stage": "PICERL stage", "title": "Alert title", "tags": "Tags"}


@dataclass(frozen=True)
class Measure:
    entity: Entity
    label: str
    description: str
    basis: DateBasis
    kind: str = "count"
    parameter: str | None = None

    def describe(self, identifier: str) -> DashboardMeasure:
        dimensions = GROUPS[self.entity]
        values = {
            "priority": [priority.value for priority in Priority],
            "status": [status.value for status in STATUS[self.entity]],
            "picerl_stage": [stage.value for stage in PICERLStage],
        }
        filters = [
            DashboardFilterOption(
                field=field,
                label=LABELS.get(field, field.capitalize()),
                operators=["in"],
                values=values.get(field, []),
            )
            for field in dimensions
        ]
        filters.append(DashboardFilterOption(
            field="tags", label="Tags", operators=["contains_all", "excludes_all"],
        ))
        displays = ["number", "breakdown", "table"]
        if self.basis != "current":
            displays.insert(1, "trend")
        columns = COMMON_COLUMNS + COLUMNS[self.entity]
        if self.basis in {"triaged_at", "closed_at"}:
            columns += ["completed_at"]
        if self.basis in {"triaged_at", "closed_at"} or self.parameter == "min_age_minutes" or self.kind == "past_target":
            columns += ["elapsed_seconds"]
        if self.parameter == "target_minutes":
            columns += ["target_seconds"]
        return DashboardMeasure(
            id=identifier,
            entity=self.entity,
            label=self.label,
            description=self.description,
            date_basis=self.basis,
            unit={"duration": "seconds", "miss_rate": "percent", "false_positive_rate": "percent"}.get(
                self.kind, "count"
            ),
            displays=displays,
            dimensions=dimensions,
            filters=filters,
            parameters=[self.parameter] if self.parameter else [],
            aggregations=["p50", "mean", "p95"] if self.kind == "duration" else [],
            record_columns=columns,
        )


MEASURES = {
    "alerts.received": Measure("alerts", "Alerts received", "Retained alerts by creation time, including duplicates.", "created_at"),
    "alerts.awaiting_triage": Measure(
        "alerts", "Alerts awaiting triage", "New or in-progress alerts across the current queue.", "current", "open", "min_age_minutes"
    ),
    "alerts.recorded_triage_time": Measure(
        "alerts", "Recorded triage time",
        "From creation to recorded triage. Linking or later actions can change this timestamp. Only valid samples are included.",
        "triaged_at", "duration",
    ),
    "alerts.duplicates": Measure(
        "alerts", "Duplicate closures", "Alerts created in range and currently closed as duplicates.", "created_at", "duplicates"
    ),
    "alerts.false_positive_rate": Measure(
        "alerts", "False positive rate",
        "False positives divided by closed alerts in the creation cohort, excluding duplicate closures.",
        "created_at", "false_positive_rate",
    ),
    "cases.created": Measure("cases", "Cases created", "Retained cases by creation time.", "created_at"),
    "cases.open": Measure("cases", "Open cases", "New and in-progress cases, including reopened cases.", "current", "open"),
    "cases.recorded_resolution_time": Measure(
        "cases", "Time to recorded resolution",
        "Creation to latest recorded closure for currently closed cases with valid timestamps.",
        "closed_at", "duration",
    ),
    "cases.resolution_target_missed_count": Measure(
        "cases", "Resolution target misses",
        "Currently closed cases whose recorded resolution time exceeded the target.",
        "closed_at", "miss_count", "target_minutes",
    ),
    "cases.resolution_target_miss_rate": Measure(
        "cases", "Resolution target miss rate",
        "Share of eligible closed cases whose recorded resolution time exceeded the target.",
        "closed_at", "miss_rate", "target_minutes",
    ),
    "cases.open_past_target": Measure(
        "cases", "Open cases past target", "Current open cases older than the target, measured from creation.",
        "current", "past_target", "target_minutes",
    ),
    "tasks.created": Measure("tasks", "Tasks created", "Retained tasks by creation time.", "created_at"),
    "tasks.open": Measure("tasks", "Open tasks", "Current to-do and in-progress tasks.", "current", "open"),
    "tasks.overdue": Measure(
        "tasks", "Overdue tasks", "Current open tasks with a due date before evaluation time.", "current", "overdue"
    ),
}

CATALOG = {identifier: measure.describe(identifier) for identifier, measure in MEASURES.items()}


def target_minutes(widget: DashboardWidget, parameters: DashboardParameters) -> int | None:
    value = widget.parameters.target_minutes
    return value if isinstance(value, int) else parameters.resolution_target_minutes if value else None


def validate_widget(widget: DashboardWidget, parameters: DashboardParameters) -> None:
    measure = CATALOG.get(widget.measure)
    if measure is None:
        raise ValueError("Choose a supported measure")
    if widget.display not in measure.displays:
        raise ValueError("This measure does not support the selected display")

    group = widget.group_by
    if widget.display == "number" and group is not None:
        raise ValueError("Number widgets display a single value")
    if widget.display == "trend" and group not in {"day", "week"}:
        raise ValueError("Choose a day or week for a trend")
    if widget.display in {"breakdown", "table"} and group not in [None, *measure.dimensions]:
        raise ValueError("Choose a supported grouping")
    if widget.display == "breakdown" and group is None:
        raise ValueError("Choose a grouping for the breakdown")
    if widget.aggregation is not None and widget.aggregation not in measure.aggregations:
        raise ValueError("Choose a supported aggregation")

    filter_options = {option.field: option for option in measure.filters}
    for condition in widget.filters:
        option = filter_options.get(condition.field)
        if option is None or condition.op not in option.operators:
            raise ValueError("Choose a supported filter and operator")
        if option.values and any(value not in option.values for value in condition.value):
            raise ValueError(f"Choose a valid {option.label.lower()} filter value")

    for parameter, value in widget.parameters.model_dump(exclude_none=True).items():
        if parameter not in measure.parameters:
            raise ValueError("This measure does not accept the selected parameter")
    if "target_minutes" in measure.parameters and (target_minutes(widget, parameters) or 0) <= 0:
        raise ValueError("Enter a positive resolution target")

    if widget.table is not None:
        if widget.display != "table" or group is not None:
            raise ValueError("Record columns are only available on ungrouped tables")
        if not set(widget.table.columns).issubset(measure.record_columns):
            raise ValueError("Choose supported record columns")
        if len(set(widget.table.columns)) != len(widget.table.columns):
            raise ValueError("Choose distinct record columns")
        if widget.table.sort is not None and widget.table.sort.field not in measure.record_columns:
            raise ValueError("Choose a supported record sort")


def validate_definition(definition: DashboardDefinition) -> None:
    for widget in definition.widgets:
        try:
            validate_widget(widget, definition.parameters)
        except ValueError as exc:
            raise ValueError(f"{widget.title}: {exc}") from exc
