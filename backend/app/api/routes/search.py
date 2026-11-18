"""Search API routes for unified full-text search.

This module provides the global search endpoint that searches across
alerts, cases, and tasks with full-text search, entity type filtering,
date range filtering, and fuzzy matching fallback.
"""
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin_auth import require_authenticated_user
from app.core.database import get_db
from app.models.models import UserAccount
from app.models.search_schemas import (
    EntityType,
    PaginatedSearchResponse,
    SearchErrorResponse,
)
from app.services.date_filter_utils import (
    DateFilterValidationError,
    parse_datetime_filter,
)
from app.services.search_service import (
    SearchDateRangeValidationError,
    resolve_search_date_range,
    search_service,
)


router = APIRouter(
    prefix="/search",
    tags=["search"],
    dependencies=[Depends(require_authenticated_user)],
)


def _sanitize_query(query: str) -> str:
    """Sanitize search query by normalizing whitespace."""
    return re.sub(r"\s+", " ", query.strip())


def _invalid_search_request(error: str, code: str) -> HTTPException:
    """Build the stable client-error shape used by the search endpoint."""
    return HTTPException(
        status_code=400,
        detail=SearchErrorResponse(error=error, code=code).model_dump(),
    )


def _validate_query(query: str) -> str:
    """Normalize and validate search text while preserving wildcard mode."""
    sanitized_query = _sanitize_query(query)
    if len(sanitized_query) < 2 and sanitized_query != "*":
        raise _invalid_search_request(
            "Query must be at least 2 characters, or '*' for filter-only search",
            "INVALID_QUERY",
        )
    if len(sanitized_query) > 200:
        raise _invalid_search_request(
            "Query cannot exceed 200 characters",
            "INVALID_QUERY",
        )
    return sanitized_query


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
) -> tuple[datetime, datetime]:
    """Parse optional bounds, apply defaults, and validate the resolved range."""
    parsed_start = _parse_iso_date(start_date, "start_date") if start_date else None
    parsed_end = _parse_iso_date(end_date, "end_date") if end_date else None
    try:
        return resolve_search_date_range(parsed_start, parsed_end)
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
    parsed_start_date, parsed_end_date = _parse_date_range(start_date, end_date)

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
        tags=tags,
        user_id=str(current_user.id) if current_user else None,
    )
