"""Pydantic output schemas for the explicitly registered MCP tools.

Input schemas are generated from the registered functions in ``server.py``.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================================
# get_summary
# ============================================================================

class ObjectHeader(BaseModel):
    """Object metadata (title, status, priority, etc.)."""
    title: str
    status: str
    priority: Optional[str] = None
    assignee: Optional[str] = None
    source: Optional[str] = None  # Alert only
    created_at: datetime
    updated_at: datetime


class TimelinePreview(BaseModel):
    """Bounded timeline item preview."""
    timeline_id: str  # Client-provided or auto-generated timeline item ID
    type: str  # e.g., "note", "observable", "network_traffic", etc.
    timestamp: datetime
    author: Optional[str] = None
    preview: str  # Truncated content (max ~200 chars)
    is_truncated: bool = False
    full_length_chars: Optional[int] = None
    entity_id: Optional[str] = None  # Human-readable ID for linked alerts/tasks/cases (e.g., ALT-0000123)
    observable_type: Optional[str] = None
    observable_value: Optional[str] = None
    enrichment_status: Optional[str] = None
    enrichments: Optional[Dict[str, Any]] = None


class TimelineSection(BaseModel):
    """Timeline items with bounding metadata."""
    items: List[TimelinePreview]
    total_count: int  # Total items (before bounding)
    omitted_count: int  # How many were omitted
    bounded_by: str = "max_timeline_items"  # or "since"


class ObservableSummary(BaseModel):
    """Deduplicated observable with occurrence count."""
    type: str  # IP, DOMAIN, HASH, etc.
    value: str
    count: int  # Occurrences in timeline


class ObservablesSection(BaseModel):
    """Deduplicated observables extracted from timeline."""
    items: List[ObservableSummary]
    total_count: int
    omitted_count: int


class ContextEntrySummary(BaseModel):
    """Analyst-authored context entry that matched the summarized entity."""
    id: int
    criteria: List[Dict[str, str]]
    body: str
    author: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class ContextSection(BaseModel):
    """Matching temporary context entries with bounding metadata."""
    items: List[ContextEntrySummary]
    total_count: int
    omitted_count: int


class RelatedCounts(BaseModel):
    """Counts of related/linked items."""
    linked_alerts: int = 0
    linked_cases: int = 0
    linked_tasks: int = 0
    similar_alerts: int = 0  # Based on similarity key


class Resource(BaseModel):
    """Link to web UI resource."""
    label: str
    url: str


class GetSummaryOutput(BaseModel):
    """Output schema for get_summary tool."""
    kind: str
    id: int
    human_id: str  # ALT-0000123, CAS-0000456, etc.
    header: ObjectHeader
    timeline: TimelineSection
    observables: ObservablesSection
    context: ContextSection
    related_counts: RelatedCounts
    resources: List[Resource]


# ============================================================================
# record_triage_decision and case runbooks
# ============================================================================

class SuggestedPatch(BaseModel):
    """Suggested change to alert."""
    field: str
    current_value: Optional[str] = None
    new_value: Optional[str] = None


class RecordTriageDecisionOutput(BaseModel):
    """Output schema for record_triage_decision tool."""
    mode: Literal["dry_run", "committed", "replaced"]
    recommendation_id: Optional[int] = None
    suggested_patches: List[SuggestedPatch]
    status: Literal["PENDING", "ACCEPTED", "REJECTED", "SUPERSEDED"]
    message: str


class CaseRunbookSearchResult(BaseModel):
    id: int
    human_id: str
    title: str
    description: Optional[str] = None
    case_tags: List[str] = Field(default_factory=list)
    runbook_task_count: int
    picerl_stages: List[str] = Field(default_factory=list)


class SearchCaseRunbooksOutput(BaseModel):
    items: List[CaseRunbookSearchResult]


class LeanRunbookTask(BaseModel):
    title: str
    description: Optional[str] = None
    picerl_stage: str
    relative_due_seconds: Optional[int] = None
    priority: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class GetCaseRunbookOutput(BaseModel):
    id: int
    human_id: str
    title: str
    description: Optional[str] = None
    case_tags: List[str] = Field(default_factory=list)
    runbook_tasks: List[LeanRunbookTask] = Field(default_factory=list)


# ============================================================================
# list_work
# ============================================================================

class WorkItemPreview(BaseModel):
    """Preview of a work item (alert/case/task)."""
    id: int
    human_id: str
    title: str
    status: str
    priority: Optional[str] = None
    assignee: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    source: Optional[str] = None  # Alert only


class ListWorkOutput(BaseModel):
    """Output schema for list_work tool."""
    items: List[WorkItemPreview]
    next_cursor: Optional[str] = None
    total_count: int


# ============================================================================
# find_related
# ============================================================================

class RelatedMatch(BaseModel):
    """Related item with explainable similarity."""
    kind: str
    id: int
    human_id: str
    title: str
    status: str
    priority: Optional[str] = None
    score: float = Field(ge=0.0, le=1.0)  # Similarity score
    why: List[str]  # Reasons (e.g., ["same_source_title", "shared_ip:10.0.0.1"])


class FindRelatedOutput(BaseModel):
    """Output schema for find_related tool."""
    seed: WorkItemPreview
    matches: List[RelatedMatch]


# ============================================================================
# add_timeline_item
# ============================================================================

class AddTimelineItemOutput(BaseModel):
    """Output schema for add_timeline_item tool."""
    mode: Literal["dry_run", "committed", "already_exists"]
    item_id: str
    created_at: Optional[datetime] = None
    author: Optional[str] = None
    message: str


# ============================================================================
# get_item
# ============================================================================

class ItemMetadata(BaseModel):
    """Metadata about timeline item."""
    type: str
    timestamp: datetime
    author: Optional[str] = None
    parent_kind: str
    parent_id: int
    parent_human_id: str


class GetItemOutput(BaseModel):
    """Output schema for get_item tool."""
    item_id: str
    content: str
    metadata: ItemMetadata
    next_cursor: Optional[str] = None
    is_truncated: bool = False


# ============================================================================
# validate_mermaid
# ============================================================================

class ValidateMermaidOutput(BaseModel):
    """Output schema for validate_mermaid tool."""
    valid: bool
    message: str
    errors: List[str] = Field(default_factory=list)
