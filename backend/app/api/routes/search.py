"""Search API routes for unified full-text search.

This module provides the global search endpoint that searches across
alerts, cases, and tasks with full-text search, entity type filtering,
date range filtering, and fuzzy matching fallback.
"""
from datetime import datetime
from typing import Annotated, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin_auth import require_authenticated_user
from app.core.database import get_db
from app.models.models import UserAccount
from app.models.search_schemas import (
    EntityType,
    PaginatedSearchResponse,
    QueueSearchResponse,
    SearchErrorResponse,
)
from app.services.date_filter_utils import (
    DateFilterValidationError,
    parse_datetime_filter,
)
from app.services.search_service import (
    SearchDateRangeValidationError,
    SearchQueueValidationError,
    SearchQueryValidationError,
    normalize_search_query,
    resolve_search_date_range,
    search_service,
)


router = APIRouter(
    prefix="/search",
    tags=["search"],
    dependencies=[Depends(require_authenticated_user)],
)


def _invalid_search_request(error: str, code: str) -> HTTPException:
    """Build the stable client-error shape used by the search endpoint."""
    return HTTPException(
        status_code=400,
        detail=SearchErrorResponse(error=error, code=code).model_dump(),
    )


def _validate_query(query: str, *, allow_wildcard: bool = True) -> str:
    """Normalize and validate search text while preserving wildcard mode."""
    try:
        return normalize_search_query(query, allow_filter_only=allow_wildcard)
    except SearchQueryValidationError as exc:
        raise _invalid_search_request(str(exc), "INVALID_QUERY") from exc


def _parse_iso_date(date_str: str, param_name: str) -> datetime:
    """Parse ISO8601 date string to datetime."""
    try:
        parsed = parse_datetime_filter(date_str, parameter=param_name)
        if parsed is None:
            raise DateFilterValidationError(f"Invalid {param_name} format")
        return parsed
    except DateFilterValidationError:
        raise _invalid_search_request(
            f"Invalid date format for {param_name}. Use ISO8601 format (e.g., 2024-12-01T00:00:00Z)",
            "INVALID_DATE_RANGE",
        )


def _parse_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
    *,
    all_time: bool = False,
) -> tuple[datetime | None, datetime | None]:
    """Parse optional bounds, apply defaults, and validate the resolved range."""
    parsed_start = _parse_iso_date(start_date, "start_date") if start_date else None
    parsed_end = _parse_iso_date(end_date, "end_date") if end_date else None
    try:
        return resolve_search_date_range(parsed_start, parsed_end, all_time=all_time)
    except SearchDateRangeValidationError as exc:
        raise _invalid_search_request(str(exc), "INVALID_DATE_RANGE") from exc


@router.get(
    "",
    response_model=PaginatedSearchResponse,
    summary="Unified search across all entity types",
    description="""
Performs a paginated full-text search across alerts, cases, and tasks.
Results are ranked by relevance with title matches weighted highest,
followed by description, then timeline content.

Supports fuzzy matching for typo tolerance when exact matches fail.
""",
    responses={
        400: {"model": SearchErrorResponse, "description": "Invalid request parameters"},
        401: {"model": SearchErrorResponse, "description": "Not authenticated"},
        500: {"model": SearchErrorResponse, "description": "Internal server error"},
    },
)
async def unified_search(
    q: str = Query(
        ...,
        min_length=1,
        description="Search query text (2-200 characters), or '*' for filter-only search",
        examples=["phishing"],
    ),
    entity_types: Optional[List[EntityType]] = Query(
        default=None,
        alias="entity_type",
        description="Entity type(s) to search. Can be specified multiple times. Defaults to all types if not provided.",
        examples=["alert"],
    ),
    skip: int = Query(
        default=0,
        ge=0,
        description="Number of results to skip (offset for pagination)",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum results to return (1-100)",
    ),
    start_date: Optional[str] = Query(
        default=None,
        description="Start of date range (ISO8601 with Z suffix). Default: 30 days ago",
        examples=["2024-12-01T00:00:00Z"],
    ),
    end_date: Optional[str] = Query(
        default=None,
        description="End of date range (ISO8601 with Z suffix). Default: now",
        examples=["2024-12-29T23:59:59Z"],
    ),
    all_time: Annotated[bool, Query(
        description="Search all dates without the default 30-day window. Cannot be combined with date bounds.",
    )] = False,
    tags: Optional[List[str]] = Query(
        default=None,
        description="Tag filter values. Can be specified multiple times. Matches top-level and timeline item tags (OR semantics).",
        examples=["SOCI Reportable"],
    ),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
) -> PaginatedSearchResponse:
    """Unified search across all entity types with pagination."""
    sanitized_query = _validate_query(q)
    parsed_start_date, parsed_end_date = _parse_date_range(start_date, end_date, all_time=all_time)

    # Default to all entity types if none specified
    search_entity_types = entity_types if entity_types else list(EntityType)

    return await search_service.paginated_search(
        db=db,
        query=sanitized_query,
        entity_types=search_entity_types,
        skip=skip,
        limit=limit,
        start_date=parsed_start_date,
        end_date=parsed_end_date,
        all_time=all_time,
        tags=tags,
        user_id=str(current_user.id) if current_user else None,
    )


@router.get(
    "/queue",
    response_model=QueueSearchResponse,
    summary="Search within an entity queue",
    responses={400: {"model": SearchErrorResponse}, 401: {"description": "Not authenticated"}},
)
async def queue_search(
    q: str = Query(..., description="Search text (2–200 characters)"),
    entity_type: EntityType = Query(...),
    status: list[str] | None = Query(None),
    assignee: list[str] | None = Query(None),
    include_tags: list[str] | None = Query(None),
    exclude_tags: list[str] | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    sort_by: Literal["created_at", "updated_at", "priority", "status"] = Query("created_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> QueueSearchResponse:
    """Return matching rows with queue filters and ordering, without global defaults."""
    query = _validate_query(q, allow_wildcard=False)
    start = _parse_iso_date(start_date, "start_date") if start_date is not None else None
    end = _parse_iso_date(end_date, "end_date") if end_date is not None else None
    if start is not None and end is not None and start > end:
        raise _invalid_search_request("Start date must be before end date", "INVALID_DATE_RANGE")
    try:
        return await search_service.search_queue(
            db,
            query=query, entity_type=entity_type, status=status, assignee=assignee,
            include_tags=include_tags, exclude_tags=exclude_tags,
            start_date=start, end_date=end, sort_by=sort_by, sort_order=sort_order,
            skip=skip, limit=limit,
        )
    except SearchQueueValidationError as exc:
        raise _invalid_search_request(str(exc), "INVALID_QUEUE_FILTER") from exc
