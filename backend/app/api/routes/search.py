"""Search API routes for unified full-text search.

This module provides the global search endpoint that searches across
alerts, cases, and tasks with full-text search, entity type filtering,
date range filtering, and fuzzy matching fallback.
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.routes.admin_auth import require_authenticated_user
from app.models.models import UserAccount
from app.models.search_schemas import (
    EntityType,
    SearchErrorResponse,
    PaginatedSearchResponse,
)
from app.services.search_service import search_service


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/search",
    tags=["search"],
    dependencies=[Depends(require_authenticated_user)],
)


def _sanitize_query(query: str) -> str:
    """Sanitize search query by normalizing whitespace."""
    # Strip leading/trailing whitespace
    query = query.strip()
    # Normalize multiple spaces to single space
    query = re.sub(r'\s+', ' ', query)
    return query


def _parse_iso_date(date_str: str, param_name: str) -> datetime:
    """Parse ISO8601 date string to datetime."""
    try:
        # Try parsing with timezone
        if date_str.endswith('Z'):
            date_str = date_str[:-1] + '+00:00'
        return datetime.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=SearchErrorResponse(
                error=f"Invalid date format for {param_name}. Use ISO8601 format (e.g., 2024-12-01T00:00:00Z)",
                code="INVALID_DATE_RANGE",
            ).model_dump(),
        )


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
        max_length=200,
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
    
    # Sanitize query
    sanitized_query = _sanitize_query(q)
    if len(sanitized_query) < 2 and sanitized_query != "*":
        raise HTTPException(
            status_code=400,
            detail=SearchErrorResponse(
                error="Query must be at least 2 characters, or '*' for filter-only search",
                code="INVALID_QUERY",
            ).model_dump(),
        )

    normalized_tags = [tag.strip() for tag in (tags or []) if tag and tag.strip()]
    
    # Parse and validate dates
    parsed_start_date: Optional[datetime] = None
    parsed_end_date: Optional[datetime] = None
    
    if start_date:
        parsed_start_date = _parse_iso_date(start_date, "start_date")
    
    if end_date:
        parsed_end_date = _parse_iso_date(end_date, "end_date")
    
    # Validate date range
    if parsed_start_date and parsed_end_date:
        if parsed_start_date > parsed_end_date:
            raise HTTPException(
                status_code=400,
                detail=SearchErrorResponse(
                    error="Start date must be before end date",
                    code="INVALID_DATE_RANGE",
                ).model_dump(),
            )
        if (parsed_end_date - parsed_start_date).days > 365:
            raise HTTPException(
                status_code=400,
                detail=SearchErrorResponse(
                    error="Date range cannot exceed 1 year",
                    code="INVALID_DATE_RANGE",
                ).model_dump(),
            )
    
    try:
        # Default to all entity types if none specified
        search_entity_types = entity_types if entity_types else list(EntityType)
        
        response = await search_service.paginated_search(
            db=db,
            query=sanitized_query,
            entity_types=search_entity_types,
            skip=skip,
            limit=limit,
            start_date=parsed_start_date,
            end_date=parsed_end_date,
            tags=normalized_tags,
            user_id=str(current_user.id) if current_user else None,
        )
        
        return response
        
    except Exception as e:
        logger.exception(f"Search error for query '{sanitized_query}': {e}")
        raise HTTPException(
            status_code=500,
            detail=SearchErrorResponse(
                error="Search service temporarily unavailable",
                code="SEARCH_ERROR",
                detail=str(e) if logger.isEnabledFor(logging.DEBUG) else None,
            ).model_dump(),
        )
