"""Pydantic schemas for MCP tool inputs and outputs.

These schemas define the contract for MCP tools as documented in
specs/004-mcp-server-v1/contracts/mcp-protocol.md
"""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


# ============================================================================
# User Story 1: get_summary
# ============================================================================

class GetSummaryInput(BaseModel):
    """Input schema for get_summary tool."""
    kind: Literal["alert", "case", "task"]
    id: str  # Forgiving format (123, ALT-000123, etc.)
    max_timeline_items: int = Field(default=25, ge=1, le=50)
    max_observables: int = Field(default=20, ge=1, le=50)
    since: Optional[str] = None  # ISO-8601 for incremental refresh


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
    related_counts: RelatedCounts
    resources: List[Resource]


# ============================================================================
# User Story 2: record_triage_decision
# ============================================================================

class RecommendedAction(BaseModel):
    """A recommended action with title and optional description."""
    title: str = Field(max_length=200, description="Short action title (max 200 chars)")
    description: Optional[str] = Field(default=None, description="Detailed action description (markdown supported)")


class RecordTriageDecisionInput(BaseModel):
    """Input schema for record_triage_decision tool."""
    alert_id: str
    disposition: Literal[
        "TRUE_POSITIVE",
        "FALSE_POSITIVE",
        "BENIGN",
        "NEEDS_INVESTIGATION",
        "DUPLICATE",
        "UNKNOWN"
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_bullets: Optional[List[str]] = None
    recommended_actions: Optional[List[RecommendedAction]] = None
    suggested_status: Optional[str] = None
    suggested_priority: Optional[str] = None
    suggested_assignee: Optional[str] = None
    suggested_tags_add: Optional[List[str]] = None
    suggested_tags_remove: Optional[List[str]] = None
    request_escalate_to_case: bool = False
    commit: bool = False  # Dry-run if false


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


# ============================================================================
# User Story 3: list_work
# ============================================================================

class ListWorkInput(BaseModel):
    """Input schema for list_work tool."""
    kind: Literal["alert", "case", "task"]
    statuses: Optional[List[str]] = None
    priorities: Optional[List[str]] = None
    assignees: Optional[List[str]] = None
    contains: Optional[str] = None  # Search in title + description
    time_range_start: Optional[str] = None  # ISO-8601
    time_range_end: Optional[str] = None  # ISO-8601
    limit: int = Field(default=50, ge=1, le=50)
    cursor: Optional[str] = None  # Pagination cursor


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
# User Story 4: find_related
# ============================================================================

class FindRelatedInput(BaseModel):
    """Input schema for find_related tool."""
    seed_kind: Literal["alert", "case", "task"]
    seed_id: str  # Forgiving format
    max_matches: int = Field(default=10, ge=1, le=20)


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
# User Story 5: add_timeline_item
# ============================================================================

class AddTimelineItemInput(BaseModel):
    """Input schema for add_timeline_item tool."""
    target_kind: Literal["alert", "case", "task"]
    target_id: str  # Forgiving format
    item_id: str  # Client-provided unique ID (for idempotency)
    body: str = Field(max_length=16000)
    created_at: Optional[datetime] = Field(
        default=None, 
        description="Timestamp when item was created. Defaults to current time if not specified."
    )
    commit: bool = False  # Dry-run if false


class AddTimelineItemOutput(BaseModel):
    """Output schema for add_timeline_item tool."""
    mode: Literal["dry_run", "committed", "already_exists"]
    item_id: str
    created_at: Optional[datetime] = None
    author: Optional[str] = None
    message: str


# ============================================================================
# User Story 6: get_item
# ============================================================================

class GetItemInput(BaseModel):
    """Input schema for get_item tool."""
    item_id: str
    mode: Literal["full", "head", "tail"] = "full"
    max_chars: int = Field(default=4000, ge=100, le=10000)
    cursor: Optional[str] = None  # Pagination cursor
    hint_kind: Optional[Literal["alert", "case", "task"]] = None
    hint_parent_id: Optional[str] = None


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
# User Story 7: validate_mermaid
# ============================================================================

class ValidateMermaidInput(BaseModel):
    """Input schema for validate_mermaid tool."""
    diagram: str = Field(min_length=1, max_length=100000)


class ValidateMermaidOutput(BaseModel):
    """Output schema for validate_mermaid tool."""
    valid: bool
    message: str
    errors: List[str] = Field(default_factory=list)
