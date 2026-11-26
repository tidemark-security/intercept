"""Public API contracts for named queue filters."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.models.enums import AlertStatus, CaseStatus, TaskStatus
from app.services.date_filter_utils import parse_datetime_filter
from app.services.search_service import normalize_search_query


class SavedFilterQueue(str, Enum):
    ALERTS = "alerts"
    CASES = "cases"
    TASKS = "tasks"


class SavedFilterScope(str, Enum):
    PERSONAL = "personal"
    ORGANIZATION = "organization"


_QUEUE_STATUSES = {
    SavedFilterQueue.ALERTS: {status.value for status in AlertStatus},
    SavedFilterQueue.CASES: {status.value for status in CaseStatus},
    SavedFilterQueue.TASKS: {status.value for status in TaskStatus},
}
_RELATIVE_PRESET = re.compile(r"-([0-9]+)(m|min|h|hr|d)")
_MINUTES_PER_UNIT = {"m": 1, "min": 1, "h": 60, "hr": 60, "d": 1440}

FilterValue = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1024, pattern=r"^[^\x00]+$")
]
FilterName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[^\x00]+$")
]


class SavedFilterDateRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str = Field(max_length=64)
    end: str = Field(max_length=64)
    preset: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=16)] | None = None

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        start = parse_datetime_filter(self.start, parameter="start date")
        end = parse_datetime_filter(self.end, parameter="end date")
        if self.preset in (None, "", "custom"):
            if start is None and end is None:
                raise ValueError("A custom date range needs a start or end date")
        elif self.preset != "now":
            match = _RELATIVE_PRESET.fullmatch(self.preset)
            if not match:
                raise ValueError("Invalid relative date preset")
            amount, unit = match.groups()
            minutes = int(amount) * _MINUTES_PER_UNIT[unit]
            try:
                datetime.now(timezone.utc) - timedelta(minutes=minutes)
            except OverflowError as exc:
                raise ValueError("Relative date preset is out of range") from exc
        if start is not None and end is not None and start > end:
            raise ValueError("Start date must be before end date")
        return self

    def resolve_bounds(self, now: datetime) -> tuple[datetime | None, datetime | None]:
        """Resolve rolling presets at count time."""
        if self.preset == "now":
            return now, now
        match = _RELATIVE_PRESET.fullmatch(self.preset or "")
        if match:
            amount, unit = match.groups()
            return now - timedelta(minutes=int(amount) * _MINUTES_PER_UNIT[unit]), now
        return (
            parse_datetime_filter(self.start, parameter="start date"),
            parse_datetime_filter(self.end, parameter="end date"),
        )


class SavedFilterSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search: str = Field(default="", max_length=200, pattern=r"^[^\x00]*$")
    status: list[FilterValue] | None = Field(default=None, max_length=100)
    assignee: list[FilterValue] | None = Field(default=None, max_length=100)
    include_tags: list[FilterValue] | None = Field(default=None, max_length=100)
    exclude_tags: list[FilterValue] | None = Field(default=None, max_length=100)
    date_range: SavedFilterDateRange | None = None
    sort_by: Literal["created_at", "updated_at", "priority", "status"] | None = None
    sort_order: Literal["asc", "desc"] | None = None

    @field_validator("search")
    @classmethod
    def validate_search(cls, search: str) -> str:
        return normalize_search_query(search, allow_filter_only=False) if search.strip() else ""


class SavedFilterRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: FilterName


class SavedFilterCreate(SavedFilterRename):
    queue: SavedFilterQueue
    scope: SavedFilterScope
    filters: SavedFilterSnapshot

    @model_validator(mode="after")
    def validate_queue_statuses(self) -> Self:
        if set(self.filters.status or ()) - _QUEUE_STATUSES[self.queue]:
            raise ValueError("One or more statuses are invalid for this queue")
        return self


class SavedFilterRead(SavedFilterCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    navigation_icon: str | None = None


class SavedFilterNavigationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    icon_name: Annotated[str, StringConstraints(max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9]*$")] | None
