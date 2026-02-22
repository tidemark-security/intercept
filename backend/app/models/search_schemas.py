"""Search schemas for the unified search API.

This module defines the Pydantic/SQLModel schemas for the search API
including request/response models and entity types.
"""
from enum import Enum
from typing import List, Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class EntityType(str, Enum):
    """Types of entities that can be searched."""
    ALERT = "alert"
    CASE = "case"
    TASK = "task"


class SearchResultItem(SQLModel):
    """Single search result item."""
    entity_type: EntityType = Field(description="Type of entity (alert, case, task)")
    entity_id: int = Field(description="Numeric ID of the entity")
    human_id: str = Field(description="Human-readable ID (ALT-0000123, CAS-0000045, TSK-0000007)")
    title: str = Field(description="Entity title")
    snippet: str = Field(description="Matched text excerpt with <mark> tags around matches (max 150 chars)")
    score: float = Field(ge=0, le=1, description="Relevance score (higher is more relevant)")
    timeline_item_id: Optional[str] = Field(default=None, description="ID of timeline item if match was in timeline content")
    created_at: datetime = Field(description="When the entity was created")
    tags: List[str] = Field(default_factory=list, description="Top-level entity tags")


class DateRangeApplied(SQLModel):
    """Date range that was applied to the search."""
    start: str = Field(description="Start of date range (ISO8601)")
    end: str = Field(description="End of date range (ISO8601)")


class SearchErrorResponse(SQLModel):
    """Error response for search API."""
    error: str = Field(description="Human-readable error message")
    code: str = Field(description="Error code (INVALID_QUERY, INVALID_DATE_RANGE, INVALID_ENTITY_TYPE, UNAUTHORIZED, SEARCH_ERROR)")
    detail: Optional[str] = Field(default=None, description="Additional error details")


class PaginatedSearchResponse(SQLModel):
    """API response for paginated search (supports multiple entity types)."""
    results: List[SearchResultItem] = Field(default_factory=list, description="Search results sorted by score")
    total: int = Field(description="Total number of matching results")
    skip: int = Field(description="Number of results skipped (offset)")
    limit: int = Field(description="Maximum number of results returned")
    query: str = Field(description="The search query that was executed")
    entity_types: List[EntityType] = Field(description="The entity types that were searched")
    date_range: DateRangeApplied = Field(description="The date range that was applied")
