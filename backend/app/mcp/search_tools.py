"""MCP adapters for ranked discovery, queue search, and item-level correlation."""

from datetime import datetime
from typing import Annotated, Literal

from fastmcp.exceptions import ToolError
from pydantic import Field

from app.core.database import async_session_factory
from app.mcp.principal import get_current_mcp_principal
from app.models.enums import ObservableType
from app.models.search_schemas import EntityType, PaginatedSearchResponse
from app.services.date_filter_utils import parse_utc_datetime
from app.services.observable_correlation import observable_occurrences
from app.services.search_service import (
    SearchDateRangeValidationError,
    SearchQueryValidationError,
    SearchQueueValidationError,
    normalize_search_query,
    resolve_search_date_range,
    search_service,
)


PageSize = Annotated[int, Field(ge=1, le=100)]
PageOffset = Annotated[int, Field(ge=0)]


def _query(query: str, *, allow_filter_only: bool = True) -> str:
    try:
        return normalize_search_query(query, allow_filter_only=allow_filter_only)
    except SearchQueryValidationError as exc:
        raise ToolError(str(exc)) from exc


def search_bounds(start_date: str | None, end_date: str | None) -> tuple[datetime | None, datetime | None]:
    try:
        start = parse_utc_datetime(start_date) if start_date is not None else None
        end = parse_utc_datetime(end_date) if end_date is not None else None
    except ValueError as exc:
        raise ToolError("Use ISO-8601 for start_date and end_date") from exc
    if start and end and start > end:
        raise ToolError("Start date must be before end date")
    return start, end


async def search(
    query: str, entity_types: list[EntityType] | None = None, tags: list[str] | None = None,
    start_date: str | None = None, end_date: str | None = None, all_time: bool = False,
    skip: PageOffset = 0, limit: PageSize = 20,
) -> PaginatedSearchResponse:
    """Search ranked alert, case and task records, including timeline content. One hit per parent.
    Defaults to 30 days ending now. Bounds use parent creation time, inclusively. Returns date_range.
    For exact item IDs sharing an IOC use find_observable_occurrences.

    Args:
        query: Search text or IOC (2–200 characters), or * for filter-only discovery.
        entity_types: Parent kinds to include. Defaults to all three.
        tags: Match any of these entity or timeline tags.
        start_date: Inclusive ISO-8601 start. Defaults to 30 days before end_date.
        end_date: Inclusive ISO-8601 end. Defaults to now. Bounded spans may cover up to 365 days.
        all_time: Disable both date bounds. Mutually exclusive with explicit dates.
        skip: Number of ranked results to skip.
        limit: Page size (1–100).
    """
    term = _query(query)
    start, end = search_bounds(start_date, end_date)
    principal = get_current_mcp_principal()
    async with async_session_factory() as db:
        try:
            return await search_service.paginated_search(
                db, term, entity_types or list(EntityType), skip=skip, limit=limit,
                start_date=start, end_date=end, all_time=all_time, tags=tags,
                user_id=str(principal.user.id) if principal else None,
            )
        except SearchDateRangeValidationError as exc:
            raise ToolError(str(exc)) from exc


async def search_queue(
    kind: EntityType, query: str, statuses: list[str] | None = None,
    assignees: list[str] | None = None, include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None, start_date: str | None = None, end_date: str | None = None,
    sort_by: Literal["created_at", "updated_at", "priority", "status"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc", skip: PageOffset = 0, limit: PageSize = 50,
) -> dict:
    """Search a filtered work queue, including timeline content, with the application's queue ordering.
    Dates are unbounded by default. Each supplied bound filters parent creation time. Returns date_range.

    Args:
        kind: Queue to search.
        query: Text or IOC to match (2–200 characters).
        statuses: Status values for the selected queue.
        assignees: Queue assignee filters.
        include_tags: Include queue rows matching these tags.
        exclude_tags: Exclude queue rows matching these tags.
        start_date: Inclusive ISO-8601 lower bound. Defaults to unbounded.
        end_date: Inclusive ISO-8601 upper bound. Defaults to unbounded.
        sort_by: Queue ordering field.
        sort_order: Direction of the queue ordering.
        skip: Number of matching rows to skip.
        limit: Page size (1–100).
    """
    term = _query(query, allow_filter_only=False)
    start, end = search_bounds(start_date, end_date)
    async with async_session_factory() as db:
        try:
            page = await search_service.search_queue(
                db, query=term, entity_type=kind, status=statuses, assignee=assignees,
                include_tags=include_tags, exclude_tags=exclude_tags, start_date=start, end_date=end,
                sort_by=sort_by, sort_order=sort_order, skip=skip, limit=limit,
            )
        except SearchQueueValidationError as exc:
            raise ToolError(str(exc)) from exc
    return {**page.model_dump(mode="json"), "date_range": {"start": start, "end": end}}


async def find_observable_occurrences(
    observable_type: ObservableType, value: Annotated[str, Field(min_length=1, max_length=4096)],
    entity_types: list[EntityType] | None = None, start_date: str | None = None,
    end_date: str | None = None, all_time: bool = False, skip: PageOffset = 0, limit: PageSize = 20,
) -> dict:
    """Find timeline items and replies sharing an exact case-insensitive typed IOC, including mapped
    fields such as source_ip. Each hit includes matched_fields, plus parent and item IDs for get_item.
    Use search for prose mentions.
    Defaults to 30 days by parent creation time, including both bounds.

    Args:
        observable_type: Type of observable to match.
        value: Exact indicator value, e.g. 192.0.2.7.
        entity_types: Parent kinds to include. Defaults to all three.
        start_date: Inclusive ISO-8601 start. Defaults to 30 days before the end.
        end_date: Inclusive ISO-8601 end. Defaults to now. Maximum bounded span is 365 days.
        all_time: Search all parent creation dates. Mutually exclusive with explicit dates.
        skip: Number of matching items to skip.
        limit: Page size (1–100).
    """
    value = value.strip()
    if not value:
        raise ToolError("Supply a non-empty observable value")
    try:
        start, end = resolve_search_date_range(*search_bounds(start_date, end_date), all_time=all_time)
    except SearchDateRangeValidationError as exc:
        raise ToolError(str(exc)) from exc
    async with async_session_factory() as db:
        return await observable_occurrences(
            db, observable_type=observable_type.value, value=value,
            entity_types=entity_types or list(EntityType), start=start, end=end, skip=skip, limit=limit,
        )
