import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union, Literal
from uuid import UUID, uuid4

from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import DateTime, UniqueConstraint, String, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator
from pydantic import EmailStr, computed_field, field_validator, model_validator
from app.models.enums import (
    CaseStatus,
    Priority,
    AlertStatus,
    ObservableType,
    TaskStatus,
    ActorType,
    SystemType,
    Protocol,
    UserRole,
    UserStatus,
    ResetDeliveryChannel,
    SessionRevokedReason,
    UploadStatus,
    SettingType,
    SessionStatus,
    MessageRole,
    AccountType,
    RecommendationStatus,
    TriageDisposition,
    RejectionCategory,
    MessageFeedback,
)


USERNAME_REGEX = re.compile(r"^[a-z0-9._@-]{3,64}$")
PASSWORD_POLICY_REGEX = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).{12,}$"
)


class InetType(TypeDecorator):
    """Portable INET implementation for Postgres + SQLite."""

    impl = String(45)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import INET  # type: ignore

            return dialect.type_descriptor(INET())
        return dialect.type_descriptor(String(45))


class UTCDateTime(TypeDecorator):
    """Timezone-aware DateTime that round-trips cleanly on SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(64))
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if dialect.name == "sqlite":
            return value.astimezone(timezone.utc).isoformat()
        return value

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if dialect.name == "sqlite":
            return datetime.fromisoformat(value).astimezone(timezone.utc)
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


# Timeline Item Models - strongly typed with first-class attributes
class ItemBase(SQLModel):
    """Base class for all timeline items."""

    id: str = Field(default=None, description="Unique identifier for timeline item")
    type: str = Field(description="Type of timeline item")
    description: Optional[str] = Field(default=None, description="Free text description of the timeline item")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), 
        description="Timestamp when item was created",
        sa_column=Column(DateTime(timezone=True))
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), 
        description="Timestamp when event occurred",
        sa_column=Column(DateTime(timezone=True))
    )
    created_by: str = Field(default=None, description="User who created this timeline item")
    tags: Optional[List[str]] = Field(default_factory=list)
    flagged: bool = Field(default=False, description="Whether this item is flagged as significant")
    highlighted: bool = Field(default=False, description="Whether this item is highlighted for attention")
    enrichment_status: Optional[str] = Field(default=None, description="Background enrichment status")
    enrichments: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Provider enrichment payloads keyed by provider identifier",
    )
    # Reply support: parent_id references another timeline item's id for threaded conversations
    parent_id: Optional[str] = Field(default=None, description="ID of parent timeline item for replies (null for top-level items)")
    # Replies use Dict[str, Any] in base for JSON storage, but typed in Union definitions below
    replies: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Optional nested timeline items as replies (typed in Union definitions)")


class NoteItem(ItemBase):
    """Timeline item for notes/comments."""

    type: Literal["note"] = "note"  # type: ignore


class AttachmentItem(ItemBase):
    """Timeline item for file attachments."""

    type: Literal["attachment"] = "attachment"  # type: ignore
    
    # Display metadata
    file_name: Optional[str] = None       # Original filename for display
    mime_type: Optional[str] = None       # MIME type (detected server-side)
    file_size: Optional[int] = None       # File size in bytes
    
    # Storage metadata (NEW)
    storage_key: Optional[str] = Field(
        default=None,
        description="Object storage key (e.g., alerts/123/attachments/abc/uuid.pdf)"
    )
    file_hash: Optional[str] = Field(
        default=None,
        description="SHA256 hash of file content for integrity verification"
    )
    uploaded_by: Optional[str] = Field(
        default=None,
        description="Username of user who uploaded the file"
    )
    upload_status: UploadStatus = Field(
        default=UploadStatus.COMPLETE,
        description="Current upload state"
    )
    
    # Legacy support
    url: Optional[str] = None  # External URL for non-storage attachments


class TTPItem(ItemBase):
    """Timeline item for linking to MITRE ATT&CK TTPs."""

    type: Literal["ttp"] = "ttp"  # type: ignore
    # TTP-specific fields
    mitre_id: Optional[str] = None  # e.g., "T1059"
    title: Optional[str] = None  # e.g., "Command and Scripting Interpreter"
    url: Optional[str] = None  # Link to MITRE ATT&CK page
    tactic: Optional[str] = None  # e.g., "Execution"
    technique: Optional[str] = None  # e.g., "Command and Scripting Interpreter"
    mitre_description: Optional[str] = None  # Official MITRE ATT&CK description


class SystemItem(ItemBase):
    """Timeline item for affected systems (e.g. servers, workstations)."""

    type: Literal["system"] = "system"  # type: ignore
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    system_type: Optional[SystemType] = None
    cmdb_id: Optional[str] = None  # Reference to CMDB (e.g. ServiceNow)
    
    # System characterization flags
    is_critical: bool = Field(default=False, description="Critical business system")
    is_internet_facing: bool = Field(default=False, description="System exposed to internet")
    is_high_risk: bool = Field(default=False, description="System poses elevated security risk")
    is_legacy: bool = Field(default=False, description="Legacy/end-of-life system")
    is_privileged: bool = Field(default=False, description="System with elevated privileges/access")


class InternalActorItem(ItemBase):
    """Timeline item for tracking internal actors (employees, contractors)."""

    type: Literal["internal_actor"] = "internal_actor"  # type: ignore
    # Normalized reference to Actor table (database PK)
    # Optional for inbound API requests - if missing, an id is created on first sighting
    actor_id: Optional[int] = None
    # Optional content hash to pin the timeline entry to a historical view of the actor
    snapshot_hash: Optional[str] = None
    
    # Internal actor specific fields
    user_id: Optional[str] = None  # UPN, samaccountname, etc.
    manager_id: Optional[int] = None  # Reference to another internal actor
    
    # Optional denormalized fields for client contract (server normalizes on write)
    name: Optional[str] = None
    title: Optional[str] = None
    org: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    
    # Actor characterization flags
    is_vip: bool = Field(default=False, description="High-profile individual (executive, board member)")
    is_privileged: bool = Field(default=False, description="User with elevated system privileges")
    is_high_risk: bool = Field(default=False, description="User poses elevated security risk")
    is_contractor: bool = Field(default=False, description="External contractor or temporary worker")
    is_service_account: bool = Field(default=False, description="Non-human service or system account")

    @model_validator(mode='after')
    def validate_identity(self) -> 'InternalActorItem':
        """Ensure either actor_id or user_id is provided for internal actors."""
        if self.actor_id is None and not self.user_id:
            raise ValueError(
                "Either 'actor_id' or 'user_id' must be provided for internal actors. "
                "When actor_id is omitted, user_id is used to find or create the actor on first sighting."
            )
        return self


class ExternalActorItem(ItemBase):
    """Timeline item for tracking external actors (customers, vendors, partners)."""

    type: Literal["external_actor"] = "external_actor"  # type: ignore
    # Normalized reference to Actor table (database PK)
    # Optional for inbound API requests - if missing, an id is created on first sighting
    actor_id: Optional[int] = None
    # Optional content hash to pin the timeline entry to a historical view of the actor
    snapshot_hash: Optional[str] = None
    
    # Optional denormalized fields for client contract (server normalizes on write)
    name: Optional[str] = None
    title: Optional[str] = None
    org: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None

    @model_validator(mode='after')
    def validate_identity(self) -> 'ExternalActorItem':
        """Ensure either actor_id or name is provided for external actors."""
        if self.actor_id is None and not self.name:
            raise ValueError(
                "Either 'actor_id' or 'name' must be provided for external actors. "
                "When actor_id is omitted, name (and optionally org) are used to find or create the actor on first sighting."
            )
        return self


class ThreatActorItem(ItemBase):
    """Timeline item for tracking threat actors (malicious external entities)."""

    type: Literal["threat_actor"] = "threat_actor"  # type: ignore
    # Normalized reference to Actor table (database PK)
    # Optional for inbound API requests - if missing, an id is created on first sighting
    actor_id: Optional[int] = None
    # Optional content hash to pin the timeline entry to a historical view of the actor
    snapshot_hash: Optional[str] = None
    
    # Threat actor specific fields
    tag_id: Optional[str] = None  # Threat intelligence tag/identifier
    confidence: Optional[int] = None  # 0-100 confidence in identity
    
    # Optional denormalized fields for client contract (server normalizes on write)
    name: Optional[str] = None
    title: Optional[str] = None
    org: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None

    @model_validator(mode='after')
    def validate_identity(self) -> 'ThreatActorItem':
        """Ensure either actor_id or identifying fields are provided for threat actors."""
        if self.actor_id is None and not (self.name or self.tag_id):
            raise ValueError(
                "Either 'actor_id', 'name', or 'tag_id' must be provided for threat actors. "
                "When actor_id is omitted, name/tag_id are used to find or create the actor on first sighting."
            )
        return self


class ObservableItem(ItemBase):
    """Timeline item for observables (IOCs)."""

    type: Literal["observable"] = "observable"  # type: ignore
    # Observable-specific fields
    observable_type: Optional[ObservableType] = None
    observable_value: Optional[str] = None


class LinkItem(ItemBase):
    """Timeline item for links/URLs."""

    type: Literal["link"] = "link"  # type: ignore
    # Link-specific fields
    url: Optional[str] = None


class AlertItem(ItemBase):
    """Timeline item for alerts linked to the case."""

    type: Literal["alert"] = "alert"  # type: ignore
    # Alert-specific fields
    # Use alert primary key (alerts.id)
    alert_id: Optional[int] = None
    # Optional denormalized fields for client contract (server normalizes on write)
    title: Optional[str] = None
    status: Optional[AlertStatus] = None
    priority: Optional[Priority] = None
    assignee: Optional[str] = None  # unified field for assignee
    # Optionally embedded timeline items from the linked alert (populated when include_linked_timelines=true)
    source_timeline_items: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Timeline items from the linked alert (populated on read with include_linked_timelines=true)"
    )


class CaseItem(ItemBase):
    """Timeline item for linking to another case."""

    type: Literal["case"] = "case"  # type: ignore
    # Case-specific fields
    case_id: int
    # Optional denormalized fields for client contract (server normalizes on write)
    title: Optional[str] = None
    status: Optional[CaseStatus] = None
    priority: Optional[Priority] = None
    assignee: Optional[str] = None  # unified field for assignee
    # Optionally embedded timeline items from the linked case (populated when include_linked_timelines=true)
    source_timeline_items: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Timeline items from the linked case (populated on read with include_linked_timelines=true)"
    )


class TaskItem(ItemBase):
    """Timeline item for tasks."""

    type: Literal["task"] = "task"  # type: ignore
    # Task-specific fields
    task_id: Optional[int] = None
    task_human_id: Optional[str] = None
    title: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[Priority] = None
    assignee: Optional[str] = None
    due_date: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    # Optionally embedded timeline items from the linked task (populated when include_linked_timelines=true)
    source_timeline_items: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Timeline items from the linked task (populated on read with include_linked_timelines=true)"
    )


class ForensicArtifactItem(ItemBase):
    """Timeline item for forensic artifacts."""

    type: Literal["forensic_artifact"] = "forensic_artifact"  # type: ignore
    # Forensic artifact-specific fields
    hash: Optional[str] = None  # File hash
    hash_typoe: Optional[str] = None  # e.g. 'md5', 'sha256'
    url: Optional[str] = None  # Evidence location


class EmailItem(ItemBase):
    """Timeline item for email communications."""

    type: Literal["email"] = "email"  # type: ignore
    # Email-specific fields
    sender: Optional[str] = None
    recipient: Optional[str] = None
    subject: Optional[str] = None
    message_id: Optional[str] = None


class NetworkTrafficItem(ItemBase):
    """Timeline item for network traffic events."""

    type: Literal["network_traffic"] = "network_traffic"  # type: ignore
    # Network traffic-specific fields
    source_ip: Optional[str] = None
    destination_ip: Optional[str] = None
    source_port: Optional[int] = None
    destination_port: Optional[int] = None
    protocol: Optional[Protocol] = None
    bytes_sent: Optional[int] = None
    bytes_received: Optional[int] = None
    duration: Optional[int] = None  # Duration in seconds


class ProcessItem(ItemBase):
    """Timeline item for process execution events."""

    type: Literal["process"] = "process"  # type: ignore
    # Process-specific fields
    process_name: Optional[str] = None
    process_id: Optional[int] = None
    parent_process_id: Optional[int] = None
    command_line: Optional[str] = None
    user_account: Optional[str] = None
    duration: Optional[int] = None  # Duration in seconds
    exit_code: Optional[int] = None


class RegistryChangeItem(ItemBase):
    """Timeline item for Windows registry modifications."""

    type: Literal["registry_change"] = "registry_change"  # type: ignore
    # Registry-specific fields
    registry_key: Optional[str] = None
    registry_value: Optional[str] = None
    old_data: Optional[str] = None
    new_data: Optional[str] = None
    operation: Optional[str] = None  # CREATE, MODIFY, DELETE
    user_account: Optional[str] = None


# Union types for timeline items
# Note: The 'replies' field in ItemBase stores List[Dict[str, Any]] at runtime for JSON serialization,
# but semantically these dicts represent nested items of the same union type.
# The frontend and type generation tools should treat replies as recursive timeline items.

AlertTimelineItem = Union[
    InternalActorItem,
    ExternalActorItem,
    ThreatActorItem,
    AttachmentItem,
    CaseItem,
    EmailItem,
    LinkItem,
    NetworkTrafficItem,
    NoteItem,
    ObservableItem,
    ProcessItem,
    RegistryChangeItem,
    SystemItem,
    TTPItem,
]

CaseTimelineItem = Union[
    InternalActorItem,
    ExternalActorItem,
    ThreatActorItem,
    AlertItem,
    AttachmentItem,
    CaseItem,
    EmailItem,
    ForensicArtifactItem,
    LinkItem,
    NetworkTrafficItem,
    NoteItem,
    ObservableItem,
    ProcessItem,
    RegistryChangeItem,
    SystemItem,
    TaskItem,
    TTPItem,
]

TaskTimelineItem = Union[
    InternalActorItem,
    ExternalActorItem,
    ThreatActorItem,
    AttachmentItem,
    CaseItem,
    EmailItem,
    LinkItem,
    NetworkTrafficItem,
    NoteItem,
    ObservableItem,
    ProcessItem,
    RegistryChangeItem,
    SystemItem,
    TTPItem,
]


# Base SQLModel classes that can be used for both API and DB
class CaseBase(SQLModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    priority: Priority = Priority.MEDIUM
    # incident_type: Optional[str] = None
    # affected_systems: Optional[str] = None
    # impact_assessment: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)


class Case(CaseBase, table=True):
    """Case table model for database."""

    __tablename__ = "cases"  # type: ignore

    id: Optional[int] = Field(default=None, primary_key=True)
    status: CaseStatus = Field(default=CaseStatus.NEW)

    # Assignment and ownership
    assignee: Optional[str] = Field(default=None, max_length=100)
    created_by: str = Field(max_length=100)

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )
    closed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )

    # Timeline items stored as JSONB for flexibility
    timeline_items: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list, sa_column=Column(JSONB)
    )

    # Tags stored as JSON array
    tags: Optional[List[str]] = Field(default_factory=list, sa_column=Column(JSONB))

    # Relationships
    alerts: List["Alert"] = Relationship(back_populates="case")
    tasks: List["Task"] = Relationship(back_populates="case")
    audit_logs: List["CaseAuditLog"] = Relationship(back_populates="case")


class CaseCreate(CaseBase):
    """Schema for creating a case."""
    assignee: Optional[str] = None


class CaseAlertClosureUpdate(SQLModel):
    """Per-alert closure status to apply when closing a case."""

    alert_id: int
    status: AlertStatus


class CaseUpdate(SQLModel):
    """Schema for updating a case."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[CaseStatus] = None
    priority: Optional[Priority] = None
    assignee: Optional[str] = None
    # incident_type: Optional[str] = None
    # affected_systems: Optional[str] = None
    # impact_assessment: Optional[str] = None
    tags: Optional[List[str]] = None
    timeline_items: Optional[List[CaseTimelineItem]] = None
    # Array of per-alert closure status updates to apply when closing the case
    # Only used when status is being set to CLOSED
    alert_closure_updates: Optional[List[CaseAlertClosureUpdate]] = None


class CaseRead(CaseBase):
    """Schema for reading a case."""

    id: int
    status: CaseStatus
    assignee: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    timeline_items: Optional[List[CaseTimelineItem]] = None
    tags: Optional[List[str]] = None

    @computed_field
    @property
    def human_id(self) -> str:
        return f"CAS-{self.id:07d}"


# Alert models
class AlertBase(SQLModel):
    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = None
    priority: Optional[Priority] = None
    source: Optional[str] = None  # General source field from frontend



class Alert(AlertBase, table=True):
    """Alert table model for database."""

    __tablename__ = "alerts"  # type: ignore

    id: Optional[int] = Field(default=None, primary_key=True)
    status: AlertStatus = Field(default=AlertStatus.NEW)

    # Assignment
    assignee: Optional[str] = Field(default=None, max_length=100)
    triaged_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    triage_notes: Optional[str] = Field(default=None)

    # Case relationship
    case_id: Optional[int] = Field(default=None, foreign_key="cases.id")
    case: Optional[Case] = Relationship(back_populates="alerts")
    linked_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )

    # Timeline items stored as JSONB for flexibility
    timeline_items: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list, sa_column=Column(JSONB)
    )

    # Tags stored as JSON array
    tags: Optional[List[str]] = Field(default_factory=list, sa_column=Column(JSONB))
    
    # Triage recommendation relationship (1:1)
    triage_recommendation: Optional["TriageRecommendation"] = Relationship(
        back_populates="alert",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "uselist": False}
    )


class AlertCreate(AlertBase):
    """Schema for creating an alert."""


class AlertUpdate(SQLModel):
    """Schema for updating an alert."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[AlertStatus] = None
    priority: Optional[Priority] = None
    source: Optional[str] = None
    assignee: Optional[str] = Field(None, max_length=100)
    timeline_items: Optional[List[AlertTimelineItem]] = None
    tags: Optional[List[str]] = None


class AlertTriageRequest(SQLModel):
    """Schema for triaging an alert."""

    status: AlertStatus
    triage_notes: Optional[str] = None
    escalate_to_case: bool = False
    case_title: Optional[str] = None
    case_description: Optional[str] = None


class AlertRead(AlertBase):
    """Schema for reading an alert."""

    id: int
    status: AlertStatus
    assignee: Optional[str] = None
    triaged_at: Optional[datetime] = None
    triage_notes: Optional[str] = None
    case_id: Optional[int] = None
    linked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    timeline_items: Optional[List[AlertTimelineItem]] = None
    tags: Optional[List[str]] = None
    triage_recommendation: Optional["TriageRecommendationRead"] = None

    @computed_field
    @property
    def human_id(self) -> str:
        return f"ALT-{self.id:07d}"


# Triage Recommendation model
class TriageRecommendation(SQLModel, table=True):
    """AI-generated triage recommendation for an alert (one per alert)."""
    
    __tablename__ = "triage_recommendations"  # type: ignore
    
    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Foreign key to alert (1:1 relationship)
    alert_id: int = Field(foreign_key="alerts.id", unique=True, index=True)
    alert: Optional[Alert] = Relationship(back_populates="triage_recommendation")
    
    # Recommendation details
    disposition: TriageDisposition = Field(sa_column=Column(SAEnum(TriageDisposition)))
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_bullets: List[str] = Field(default_factory=list, sa_column=Column(JSONB))
    recommended_actions: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB))
    
    # Suggested patches (all optional)
    suggested_status: Optional[AlertStatus] = Field(default=None, sa_column=Column(SAEnum(AlertStatus), nullable=True))
    suggested_priority: Optional[Priority] = Field(default=None, sa_column=Column(SAEnum(Priority), nullable=True))
    suggested_assignee: Optional[str] = Field(default=None, max_length=100)
    suggested_tags_add: List[str] = Field(default_factory=list, sa_column=Column(JSONB))
    suggested_tags_remove: List[str] = Field(default_factory=list, sa_column=Column(JSONB))
    request_escalate_to_case: bool = Field(default=False)
    
    # Creation tracking
    created_by: str = Field(max_length=100)  # API key identifier
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True)
    )
    
    # Acceptance tracking
    status: RecommendationStatus = Field(
        default=RecommendationStatus.PENDING,
        sa_column=Column(SAEnum(RecommendationStatus), index=True)
    )
    reviewed_by: Optional[str] = Field(default=None, max_length=100)
    reviewed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    rejection_category: Optional[RejectionCategory] = Field(
        default=None,
        sa_column=Column(SAEnum(RejectionCategory), nullable=True)
    )
    rejection_reason: Optional[str] = Field(default=None, max_length=500)
    applied_changes: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB))
    error_message: Optional[str] = Field(default=None, max_length=1000, description="Error message if triage failed")


class TriageRecommendationRead(SQLModel):
    """Schema for reading a triage recommendation."""
    
    id: int
    alert_id: int
    disposition: TriageDisposition
    confidence: float
    reasoning_bullets: List[str] = []
    recommended_actions: List[Any] = []  # Supports both legacy str and new {title, description} format
    suggested_status: Optional[AlertStatus] = None
    suggested_priority: Optional[Priority] = None
    suggested_assignee: Optional[str] = None
    suggested_tags_add: List[str] = []
    suggested_tags_remove: List[str] = []
    request_escalate_to_case: bool = False
    created_by: str
    created_at: datetime
    status: RecommendationStatus
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    rejection_category: Optional[RejectionCategory] = None
    rejection_reason: Optional[str] = None
    applied_changes: List[Dict[str, Any]] = []
    error_message: Optional[str] = None


# Audit Log model
class CaseAuditLog(SQLModel, table=True):
    """Case audit log table model."""

    __tablename__ = "case_audit_logs"  # type: ignore

    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="cases.id")
    action: str = Field(max_length=100)
    description: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    performed_by: str = Field(max_length=100)
    performed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )

    # Relationship
    case: Optional[Case] = Relationship(back_populates="audit_logs")


class CaseAuditLogRead(SQLModel):
    """Schema for reading audit logs."""

    id: int
    action: str
    description: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    performed_by: str
    performed_at: datetime


# Response schemas with relationships
class CaseReadWithAlerts(CaseRead):
    """Case with alerts and audit logs."""

    alerts: List[AlertRead] = []
    audit_logs: List[CaseAuditLogRead] = []


class AlertReadWithCase(AlertRead):
    """Alert with case information."""

    case: Optional[CaseRead] = None


# Task models
class TaskBase(SQLModel):
    """Base task model for API and DB."""

    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    priority: Priority = Field(
        default=Priority.MEDIUM,
        sa_column=Column(
            SAEnum(Priority, name="priority", create_type=False)
        )
    )
    due_date: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )


class Task(TaskBase, table=True):
    """Task table model for database."""

    __tablename__ = "tasks"  # type: ignore

    id: Optional[int] = Field(default=None, primary_key=True)
    status: TaskStatus = Field(
        default=TaskStatus.TODO,
        sa_column=Column(
            SAEnum(TaskStatus, name="taskstatus", create_type=False)
        )
    )

    # Assignment and ownership
    assignee: Optional[str] = Field(default=None, max_length=100)
    created_by: str = Field(max_length=100)

    # Case relationship (optional - tasks can be standalone)
    case_id: Optional[int] = Field(default=None, foreign_key="cases.id")
    case: Optional[Case] = Relationship(back_populates="tasks")
    linked_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )

    # Timeline items stored as JSONB for flexibility (like alerts/cases)
    timeline_items: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list, sa_column=Column(JSONB)
    )

    # Tags stored as JSON array
    tags: Optional[List[str]] = Field(default_factory=list, sa_column=Column(JSONB))


class TaskCreate(TaskBase):
    """Schema for creating a task."""
    assignee: Optional[str] = None
    case_id: Optional[int] = None
    status: Optional[TaskStatus] = None


class TaskUpdate(SQLModel):
    """Schema for updating a task."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[Priority] = None
    assignee: Optional[str] = None
    due_date: Optional[datetime] = None
    case_id: Optional[int] = None
    timeline_items: Optional[List[TaskTimelineItem]] = None
    tags: Optional[List[str]] = None


class TaskRead(TaskBase):
    """Schema for reading a task."""

    id: int
    status: TaskStatus
    assignee: Optional[str] = None
    created_by: str
    case_id: Optional[int] = None
    linked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    timeline_items: Optional[List[TaskTimelineItem]] = None
    tags: Optional[List[str]] = None

    @computed_field
    @property
    def human_id(self) -> str:
        return f"TSK-{self.id:07d}"


# Normalized Actor models with versioned snapshots
class ActorBase(SQLModel):
    """Shared fields for actor records."""

    actor_type: ActorType
    # For internal actors: stable identity keys (UPN, samaccountname, etc.)
    user_id: Optional[str] = None
    manager_id: Optional[int] = None

    # For external threat actors
    tag_id: Optional[str] = None
    confidence: Optional[int] = None  # 0-100 confidence in identity

    # For external actors: descriptive info
    name: Optional[str] = None
    title: Optional[str] = None
    org: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    
    # Actor characterization flags (for internal actors)
    is_vip: bool = Field(default=False, description="High-profile individual (executive, board member)")
    is_privileged: bool = Field(default=False, description="User with elevated system privileges")
    is_high_risk: bool = Field(default=False, description="User poses elevated security risk")
    is_contractor: bool = Field(default=False, description="External contractor or temporary worker")
    is_service_account: bool = Field(default=False, description="Non-human service or system account")


class Actor(ActorBase, table=True):
    """Canonical Actor entity."""

    __tablename__ = "actors"  # type: ignore
    __table_args__ = (
        # Ensure unique internal actors by (actor_type, user_id)
        UniqueConstraint("actor_type", "user_id", name="uq_actor_internal_user_id"),
        # Ensure unique external actors by (actor_type, name, org)
        UniqueConstraint("actor_type", "name", "org", name="uq_actor_external_identity"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )

    # Relationships
    snapshots: List["ActorSnapshot"] = Relationship(back_populates="actor")


class ActorSnapshot(SQLModel, table=True):
    """Versioned snapshot of an Actor at a point in time."""

    __tablename__ = "actor_snapshots"  # type: ignore
    __table_args__ = (
        UniqueConstraint("actor_id", "snapshot_hash", name="uq_actor_snapshot_hash"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    actor_id: int = Field(foreign_key="actors.id")
    snapshot_hash: str
    # Store the denormalized view used in timelines, immutable per version
    snapshot: Dict[str, Any] = Field(sa_column=Column(JSONB))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )

    # Relationship
    actor: Optional[Actor] = Relationship(back_populates="snapshots")


# ---------------------------------------------------------------------------
# Authentication models & schemas
# ---------------------------------------------------------------------------


class UserAccountBase(SQLModel):
    """Base fields shared by all user account types (human and NHI)."""
    username: str = Field(
        regex=USERNAME_REGEX.pattern,
        sa_column=Column(String(64), unique=True, index=True),
        description="Canonical username (lowercase, unique)",
    )
    role: UserRole = Field(default=UserRole.ANALYST)
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="User title (for humans) or purpose description (for NHI accounts)",
    )

    @field_validator("username", mode="before")
    @classmethod
    def _normalize_username(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if not USERNAME_REGEX.match(normalized):
            raise ValueError(
                "username must be 3-64 chars and contain lowercase letters, numbers, '.', '_', '@', or '-'"
            )
        return normalized


class UserAccount(UserAccountBase, table=True):
    __tablename__ = "user_accounts"  # type: ignore
    __table_args__ = (
        UniqueConstraint("oidc_issuer", "oidc_subject", name="uq_user_accounts_oidc_identity"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    account_type: AccountType = Field(
        default=AccountType.HUMAN,
        description="Type of account: HUMAN (email/password) or NHI (API key only)",
    )
    # Human-specific fields (required for HUMAN, null for NHI)
    email: Optional[EmailStr] = Field(
        default=None,
        sa_column=Column(String(255), unique=True, index=True, nullable=True),
        description="Unique email used for notifications/reset (required for HUMAN accounts)",
    )
    password_hash: Optional[str] = Field(
        default=None,
        max_length=256,
        sa_column=Column(String(256), nullable=True),
        description="Argon2id password hash (nullable for OIDC-only HUMAN accounts)",
    )
    oidc_subject: Optional[str] = Field(
        default=None,
        max_length=255,
        sa_column=Column(String(255), nullable=True),
        description="OIDC subject claim for linked SSO identities",
    )
    oidc_issuer: Optional[str] = Field(
        default=None,
        max_length=500,
        sa_column=Column(String(500), nullable=True),
        description="OIDC issuer for linked SSO identities",
    )
    password_updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime()),
    )
    status: UserStatus = Field(default=UserStatus.ACTIVE)
    must_change_password: bool = Field(default=False)
    failed_login_attempts: int = Field(default=0, ge=0)
    lockout_expires_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime()),
    )
    last_login_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime()),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(UTCDateTime()),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(UTCDateTime()),
    )
    created_by_admin_id: Optional[UUID] = Field(
        default=None,
        foreign_key="user_accounts.id",
        description="Admin user responsible for provisioning",
    )

    sessions: List["AuthSession"] = Relationship(back_populates="user")
    reset_requests: List["AdminResetRequest"] = Relationship(
        back_populates="target_user",
        sa_relationship_kwargs={"primaryjoin": "UserAccount.id==AdminResetRequest.target_user_id"},
    )
    issued_reset_requests: List["AdminResetRequest"] = Relationship(
        back_populates="issued_by_admin",
        sa_relationship_kwargs={"primaryjoin": "UserAccount.id==AdminResetRequest.issued_by_admin_id"},
    )
    langflow_sessions: List["LangFlowSession"] = Relationship(back_populates="user")
    api_keys: List["ApiKey"] = Relationship(back_populates="user")
    passkey_credentials: List["PasskeyCredential"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"foreign_keys": "[PasskeyCredential.user_id]"},
    )

    @model_validator(mode="after")
    def _validate_account_type_fields(self) -> "UserAccount":
        """Enforce field requirements based on account type."""
        if self.account_type == AccountType.HUMAN:
            if not self.email:
                raise ValueError("email is required for HUMAN accounts")
            if not self.password_hash and not self.oidc_subject:
                raise ValueError("password_hash or oidc_subject is required for HUMAN accounts")
            if self.oidc_subject and not self.oidc_issuer:
                raise ValueError("oidc_issuer is required when oidc_subject is set")
        elif self.account_type == AccountType.NHI:
            if self.email is not None:
                raise ValueError("email must be null for NHI accounts")
            if self.password_hash is not None:
                raise ValueError("password_hash must be null for NHI accounts")
            if self.oidc_subject is not None or self.oidc_issuer is not None:
                raise ValueError("oidc identity fields must be null for NHI accounts")
        return self


class HumanUserAccountBase(UserAccountBase):
    """Base fields for human user accounts including email."""
    email: EmailStr = Field(
        description="Unique email used for notifications/reset",
    )

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class UserAccountRead(UserAccountBase):
    """Read schema for user accounts (both human and NHI)."""
    id: UUID
    account_type: AccountType
    email: Optional[EmailStr] = None
    oidc_subject: Optional[str] = None
    oidc_issuer: Optional[str] = None
    status: UserStatus
    must_change_password: bool
    failed_login_attempts: int
    lockout_expires_at: Optional[datetime]
    last_login_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class UserAccountCreate(HumanUserAccountBase):
    """Schema for creating a human user account."""
    password: str = Field(min_length=12, description="Plain text password used during provisioning")

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        candidate = value.strip()
        if not PASSWORD_POLICY_REGEX.match(candidate):
            raise ValueError(
                "Password must be at least 12 characters and include upper, lower, number, and symbol"
            )
        return candidate


class NHIAccountCreate(UserAccountBase):
    """Schema for creating a Non-Human Identity (NHI) account."""
    initial_api_key_name: str = Field(
        min_length=1,
        max_length=100,
        description="Name for the initial API key",
    )
    initial_api_key_expires_at: datetime = Field(
        description="Expiration date for the initial API key (required)",
    )


class AuthSessionBase(SQLModel):
    user_id: UUID = Field(foreign_key="user_accounts.id")
    issued_at: datetime = Field(sa_column=Column(UTCDateTime()))
    last_seen_at: datetime = Field(sa_column=Column(UTCDateTime()))
    expires_at: datetime = Field(sa_column=Column(UTCDateTime()))
    revoked_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime()),
    )
    revoked_reason: Optional[SessionRevokedReason] = None
    ip_address: Optional[str] = Field(default=None, sa_column=Column(InetType()))
    user_agent: Optional[str] = Field(default=None, max_length=512)
    correlation_id: Optional[str] = Field(default=None, max_length=128)


class AuthSession(AuthSessionBase, table=True):
    __tablename__ = "auth_sessions"  # type: ignore

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    session_token_hash: str = Field(
        sa_column=Column(String(128), unique=True, index=True),
        description="BLAKE2b hash of the opaque session token",
    )

    user: Optional[UserAccount] = Relationship(back_populates="sessions")


class AuthSessionRead(AuthSessionBase):
    id: UUID
    revoked_reason: Optional[SessionRevokedReason] = None


class PasskeyCredentialBase(SQLModel):
    user_id: UUID = Field(foreign_key="user_accounts.id", index=True)
    name: str = Field(min_length=1, max_length=100)
    credential_id: str = Field(
        max_length=2048,
        description="Base64URL encoded WebAuthn credential ID",
    )
    credential_public_key: str = Field(
        max_length=8192,
        description="Base64URL encoded COSE public key bytes",
    )
    sign_count: int = Field(default=0, ge=0)
    transports: List[str] = Field(default_factory=list, sa_column=Column(JSONB))
    aaguid: Optional[str] = Field(default=None, max_length=64)
    is_backup_eligible: bool = Field(default=False)
    is_backed_up: bool = Field(default=False)
    last_used_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime()),
    )
    revoked_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime()),
    )
    revoked_by_admin_id: Optional[UUID] = Field(default=None, foreign_key="user_accounts.id")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(UTCDateTime()),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(UTCDateTime()),
    )


class PasskeyCredential(PasskeyCredentialBase, table=True):
    __tablename__ = "passkey_credentials"  # type: ignore
    __table_args__ = (
        UniqueConstraint("credential_id", name="uq_passkey_credentials_credential_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)

    user: Optional[UserAccount] = Relationship(
        back_populates="passkey_credentials",
        sa_relationship_kwargs={"foreign_keys": "PasskeyCredential.user_id"},
    )


class PasskeyCredentialRead(SQLModel):
    id: UUID
    user_id: UUID
    name: str
    credential_id: str
    transports: List[str]
    aaguid: Optional[str]
    is_backup_eligible: bool
    is_backed_up: bool
    last_used_at: Optional[datetime]
    revoked_at: Optional[datetime]
    created_at: datetime


class WebAuthnChallenge(SQLModel, table=True):
    __tablename__ = "webauthn_challenges"  # type: ignore

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    challenge: str = Field(max_length=512, index=True)
    flow_type: str = Field(max_length=32, index=True)
    user_id: Optional[UUID] = Field(default=None, foreign_key="user_accounts.id", index=True)
    username: Optional[str] = Field(default=None, max_length=64)
    expires_at: datetime = Field(sa_column=Column(UTCDateTime(), index=True))
    consumed_at: Optional[datetime] = Field(default=None, sa_column=Column(UTCDateTime()))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(UTCDateTime()),
    )
    challenge_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))


class OIDCAuthRequest(SQLModel, table=True):
    __tablename__ = "oidc_auth_requests"  # type: ignore

    state: str = Field(primary_key=True, max_length=255)
    nonce: str = Field(max_length=255)
    redirect_to: str = Field(max_length=2048)
    expires_at: datetime = Field(sa_column=Column(UTCDateTime(), index=True))
    consumed_at: Optional[datetime] = Field(default=None, sa_column=Column(UTCDateTime()))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(UTCDateTime()),
    )


class AdminResetRequestBase(SQLModel):
    target_user_id: UUID = Field(foreign_key="user_accounts.id")
    issued_by_admin_id: UUID = Field(foreign_key="user_accounts.id")
    temporary_secret_hash: str = Field(max_length=256)
    delivery_channel: ResetDeliveryChannel = Field(default=ResetDeliveryChannel.SECURE_EMAIL)
    delivery_reference: Optional[str] = None
    expires_at: datetime = Field(sa_column=Column(UTCDateTime(), index=True))
    consumed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime()),
    )
    invalidated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime()),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(UTCDateTime()),
    )


class AdminResetRequest(AdminResetRequestBase, table=True):
    __tablename__ = "admin_reset_requests"  # type: ignore

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)

    target_user: Optional[UserAccount] = Relationship(
        back_populates="reset_requests",
        sa_relationship_kwargs={"primaryjoin": "AdminResetRequest.target_user_id==UserAccount.id"},
    )
    issued_by_admin: Optional[UserAccount] = Relationship(
        back_populates="issued_reset_requests",
        sa_relationship_kwargs={"primaryjoin": "AdminResetRequest.issued_by_admin_id==UserAccount.id"},
    )


class AdminResetRequestRead(AdminResetRequestBase):
    id: UUID


class PasswordChangeRequest(SQLModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=12)

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, value: str) -> str:
        candidate = value.strip()
        if not PASSWORD_POLICY_REGEX.match(candidate):
            raise ValueError(
                "Password must be at least 12 characters and include upper, lower, number, and symbol"
            )
        return candidate


# ---------------------------------------------------------------------------
# API Key models & schemas
# ---------------------------------------------------------------------------


class ApiKeyBase(SQLModel):
    """Base fields for API keys."""
    name: str = Field(
        min_length=1,
        max_length=100,
        description="User-defined name for this API key",
    )
    expires_at: datetime = Field(
        sa_column=Column(UTCDateTime(), index=True),
        description="Expiration date (required for all API keys)",
    )


class ApiKey(ApiKeyBase, table=True):
    """API key for programmatic access. Keys inherit the permissions of their owning user."""
    __tablename__ = "api_keys"  # type: ignore

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(
        foreign_key="user_accounts.id",
        index=True,
        description="User account that owns this API key",
    )
    prefix: str = Field(
        max_length=12,
        index=True,
        description="First 12 characters of the key (tmi_XXXXXXXX) for identification",
    )
    key_hash: str = Field(
        sa_column=Column(String(128), unique=True, index=True),
        description="BLAKE2b hash of the full API key",
    )
    last_used_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime()),
        description="Last time this key was used for authentication",
    )
    revoked_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime()),
        description="When this key was revoked (null if active)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(UTCDateTime()),
    )

    user: Optional[UserAccount] = Relationship(back_populates="api_keys")

class ApiKeyCreate(SQLModel):
    """Schema for creating an API key."""
    name: str = Field(
        min_length=1,
        max_length=100,
        description="User-defined name for this API key",
    )
    expires_at: datetime = Field(
        description="Expiration date (required)",
    )


class ApiKeyRead(ApiKeyBase):
    """Schema for reading API key metadata (never includes the actual key)."""
    id: UUID
    user_id: UUID
    prefix: str
    last_used_at: Optional[datetime]
    revoked_at: Optional[datetime]
    created_at: datetime


class ApiKeyCreateResponse(ApiKeyRead):
    """Response when creating an API key. Includes the full key (shown only once)."""
    key: str = Field(
        description="The full API key (only shown once at creation time)",
    )


# ---------------------------------------------------------------------------
# File Upload API Models
# ---------------------------------------------------------------------------

class PresignedUploadRequest(SQLModel):
    """Request to generate presigned upload URL."""
    
    filename: str = Field(
        min_length=1,
        max_length=255,
        description="Original filename"
    )
    file_size: int = Field(
        gt=0,
        description="File size in bytes"
    )
    mime_type: Optional[str] = Field(
        default=None,
        description="Client-reported MIME type (validated server-side)"
    )
    
    @field_validator('filename')
    @classmethod
    def sanitize_filename(cls, v: str) -> str:
        """Remove path separators for security."""
        return v.replace('/', '').replace('\\', '').replace('..', '')


class PresignedUploadResponse(SQLModel):
    """Response with presigned upload URL and metadata."""
    
    item_id: str = Field(description="Timeline item ID created for this upload")
    upload_url: str = Field(description="Presigned PUT URL for direct upload to storage")
    storage_key: str = Field(description="Object storage key for this file")
    expires_at: datetime = Field(description="URL expiration timestamp")
    max_file_size: int = Field(description="Maximum allowed file size in bytes")


class AttachmentStatusUpdate(SQLModel):
    """Update attachment upload status."""
    
    status: UploadStatus = Field(description="New upload status")
    file_hash: Optional[str] = Field(
        default=None,
        description="SHA256 hash of uploaded file (for verification)"
    )


class PresignedDownloadResponse(SQLModel):
    """Response with presigned download URL."""
    
    download_url: str = Field(description="Presigned GET URL for direct download from storage")
    filename: str = Field(description="Original filename for download")
    mime_type: str = Field(description="MIME type for Content-Type header")
    file_size: int = Field(description="File size in bytes")
    expires_at: datetime = Field(description="URL expiration timestamp")


# Link Template Models
class LinkTemplateBase(SQLModel):
    """Base model for link templates."""
    
    template_id: str = Field(
        index=True,
        max_length=100,
        description="Unique identifier for this template type (e.g., 'virustotal-domain')"
    )
    name: str = Field(
        max_length=200,
        description="Human-readable name of the link template"
    )
    icon_name: str = Field(
        max_length=100,
        description="Icon identifier (e.g., 'FeatherMail', 'VirusTotalIcon')"
    )
    tooltip_template: str = Field(
        description="Tooltip text with {{variable}} placeholders for interpolation"
    )
    url_template: str = Field(
        description="URL template with {{variable}} placeholders for interpolation"
    )
    field_names: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSONB),
        description="Array of field names this template applies to"
    )
    conditions: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB),
        description="Object of field/value pairs that must match"
    )
    enabled: bool = Field(
        default=True,
        description="Whether this template is currently active"
    )
    display_order: int = Field(
        default=0,
        description="Sort order for display (lower numbers first)"
    )


class LinkTemplate(LinkTemplateBase, table=True):
    """Link template configuration stored in database."""
    
    __tablename__ = "link_templates"  # type: ignore
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(UTCDateTime)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(UTCDateTime)
    )


class LinkTemplateCreate(LinkTemplateBase):
    """Schema for creating a link template."""
    pass


class LinkTemplateUpdate(SQLModel):
    """Schema for updating a link template."""
    
    name: Optional[str] = Field(default=None, max_length=200)
    icon_name: Optional[str] = Field(default=None, max_length=100)
    tooltip_template: Optional[str] = None
    url_template: Optional[str] = None
    field_names: Optional[List[str]] = None
    conditions: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    display_order: Optional[int] = None


class LinkTemplateRead(LinkTemplateBase):
    """Schema for reading a link template."""
    
    id: int
    created_at: datetime
    updated_at: datetime


# ============================================================================
# LangFlow AI Chat Integration Models
# ============================================================================

# AppSetting Models - Generic settings storage with encryption support

class AppSettingBase(SQLModel):
    """Base model for application settings."""
    
    key: str = Field(
        max_length=200,
        regex=r"^[a-z0-9._-]+$",
        description="Setting key (lowercase, alphanumeric, dots, underscores, hyphens)"
    )
    value: Optional[str] = Field(default=None, description="Setting value (encrypted if is_secret=true)")
    value_type: SettingType = Field(default=SettingType.STRING, description="Type hint for value")
    is_secret: bool = Field(default=False, description="Whether value should be encrypted")
    description: Optional[str] = Field(default=None, description="Human-readable description")
    category: str = Field(max_length=100, description="Grouping category")


class AppSetting(AppSettingBase, table=True):
    """Application settings table."""
    
    __tablename__ = "app_settings"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )


class AppSettingCreate(AppSettingBase):
    """Schema for creating a setting."""
    pass


class AppSettingUpdate(SQLModel):
    """Schema for updating a setting."""
    
    value: Optional[str] = None
    description: Optional[str] = None
    # key, is_secret, value_type, category cannot be updated


class AppSettingRead(AppSettingBase):
    """Schema for reading a setting."""
    
    id: int
    created_at: datetime
    updated_at: datetime
    local_only: bool = False
    source: str = "default"  # "env", "database", or "default"
    # Note: Service layer masks value if is_secret=true


class EnrichmentCacheEntryBase(SQLModel):
    """Base model for durable enrichment cache entries."""

    provider_id: str = Field(max_length=100, index=True)
    cache_key: str = Field(max_length=500, index=True)
    result: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), index=True))


class EnrichmentCacheEntry(EnrichmentCacheEntryBase, table=True):
    """Durable provider cache used to reduce external enrichment calls."""

    __tablename__ = "enrichment_cache"  # type: ignore
    __table_args__ = (
        UniqueConstraint("provider_id", "cache_key", name="uq_enrichment_cache_provider_key"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )


class EnrichmentAliasBase(SQLModel):
    """Base model for alias resolution across enrichment providers."""

    provider_id: str = Field(max_length=100, index=True)
    entity_type: str = Field(max_length=100, index=True)
    canonical_value: str = Field(max_length=500, index=True)
    canonical_display: Optional[str] = Field(default=None, max_length=200)
    alias_type: str = Field(max_length=100, index=True)
    alias_value: str = Field(max_length=500, index=True)
    attributes: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))


class EnrichmentAlias(EnrichmentAliasBase, table=True):
    """Canonical alias mappings populated by providers and admin actions."""

    __tablename__ = "enrichment_aliases"  # type: ignore
    __table_args__ = (
        UniqueConstraint("provider_id", "alias_type", "alias_value", name="uq_enrichment_alias_provider_type_value"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )


class EnrichmentAliasCreate(EnrichmentAliasBase):
    """Schema for creating enrichment aliases."""


class EnrichmentAliasUpdate(SQLModel):
    """Schema for updating enrichment aliases."""

    canonical_value: Optional[str] = Field(default=None, max_length=500)
    canonical_display: Optional[str] = Field(default=None, max_length=200)
    alias_type: Optional[str] = Field(default=None, max_length=100)
    alias_value: Optional[str] = Field(default=None, max_length=500)
    attributes: Optional[Dict[str, Any]] = None


class EnrichmentAliasRead(EnrichmentAliasBase):
    """Schema for reading enrichment aliases."""

    id: int
    created_at: datetime
    updated_at: datetime


class EnrichmentProviderStatusRead(SQLModel):
    """Runtime status for a registered enrichment provider."""

    provider_id: str
    display_name: str
    settings_prefix: str
    enabled: bool
    supports_bulk_sync: bool
    item_types: List[str] = Field(default_factory=list)
    cache_entry_count: int = 0
    alias_count: int = 0
    last_activity_at: Optional[datetime] = None


# LangFlowSession Models - AI chat session tracking

class LangFlowSessionBase(SQLModel):
    """Base model for LangFlow sessions."""
    
    flow_id: str = Field(max_length=200, description="LangFlow flow identifier")
    title: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Session title (auto-generated from first message if not provided)"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
        description="Conversation context/history"
    )
    status: SessionStatus = Field(default=SessionStatus.ACTIVE, description="Session status")


class LangFlowSession(LangFlowSessionBase, table=True):
    """LangFlow session table."""
    
    __tablename__ = "langflow_sessions"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user_accounts.id", index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True))
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    
    # Relationships
    user: "UserAccount" = Relationship(back_populates="langflow_sessions")
    messages: List["LangFlowMessage"] = Relationship(
        back_populates="session",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class LangFlowSessionCreate(SQLModel):
    """Schema for creating a session. context_type determines which flow to use from server settings."""
    
    context_type: Optional[str] = Field(
        default="general",
        max_length=50,
        description="Context type (general, case, task, alert) - determines which flow to use"
    )
    title: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Session title (auto-generated from first message if not provided)"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Conversation context/history"
    )


class LangFlowSessionUpdate(SQLModel):
    """Schema for updating a session."""
    
    title: Optional[str] = Field(default=None, max_length=200, description="Session title")
    context: Optional[Dict[str, Any]] = None
    status: Optional[SessionStatus] = None


class LangFlowSessionRead(LangFlowSessionBase):
    """Schema for reading a session."""
    
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    message_count: int = 0  # Computed by service layer


# LangFlowMessage Models - Individual chat messages

class LangFlowMessageBase(SQLModel):
    """Base model for LangFlow messages."""
    
    role: MessageRole = Field(description="Message author role")
    content: str = Field(default="", description="Message text content")
    message_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
        description="Additional message context (tokens, model, etc.)"
    )


class LangFlowMessage(LangFlowMessageBase, table=True):
    """LangFlow message table."""
    
    __tablename__ = "langflow_messages"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: UUID = Field(foreign_key="langflow_sessions.id", index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True)
    )
    feedback: Optional[MessageFeedback] = Field(
        default=None,
        sa_column=Column(SAEnum(MessageFeedback), nullable=True)
    )
    
    # Relationships
    session: LangFlowSession = Relationship(back_populates="messages")


class LangFlowMessageCreate(LangFlowMessageBase):
    """Schema for creating a message."""
    
    session_id: UUID


class LangFlowMessageRead(LangFlowMessageBase):
    """Schema for reading a message."""
    
    id: UUID
    session_id: UUID
    created_at: datetime
    feedback: Optional[MessageFeedback] = None


# SOC Metrics Response Models
# ============================================================================

class MetricsTimeWindow(SQLModel):
    """A single 15-minute time window of metrics data."""
    
    time_window: datetime = Field(description="Start of the 15-minute window (UTC)")
    

class SOCMetricsWindow(MetricsTimeWindow):
    """SOC-level metrics for a single time window."""
    
    priority: Optional[str] = Field(default=None, description="Priority level filter")
    alert_source: Optional[str] = Field(default=None, description="Alert source filter")
    
    # Alert counts
    alert_count: int = Field(default=0, description="Total alerts created")
    alerts_closed: int = Field(default=0, description="Alerts closed (any disposition)")
    alerts_tp: int = Field(default=0, description="Alerts closed as true positive")
    alerts_fp: int = Field(default=0, description="Alerts closed as false positive")
    alerts_bp: int = Field(default=0, description="Alerts closed as benign positive")
    alerts_duplicate: int = Field(default=0, description="Alerts closed as duplicate")
    alerts_unresolved: int = Field(default=0, description="Alerts closed unresolved")
    alerts_escalated: int = Field(default=0, description="Alerts escalated to cases")
    alerts_triaged: int = Field(default=0, description="Alerts that received triage action")
    
    # Alert timing (MTTT)
    mttt_p50_seconds: Optional[float] = Field(default=None, description="Median time to triage (seconds)")
    mttt_mean_seconds: Optional[float] = Field(default=None, description="Mean time to triage (seconds)")
    mttt_p95_seconds: Optional[float] = Field(default=None, description="95th percentile time to triage (seconds)")
    
    # Case counts
    case_count: int = Field(default=0, description="Total cases created")
    cases_closed: int = Field(default=0, description="Cases closed")
    cases_new: int = Field(default=0, description="Cases in NEW status")
    cases_in_progress: int = Field(default=0, description="Cases in IN_PROGRESS status")
    
    # Case timing (MTTR)
    mttr_p50_seconds: Optional[float] = Field(default=None, description="Median time to resolution (seconds)")
    mttr_mean_seconds: Optional[float] = Field(default=None, description="Mean time to resolution (seconds)")
    mttr_p95_seconds: Optional[float] = Field(default=None, description="95th percentile time to resolution (seconds)")
    
    # Task counts
    task_count: int = Field(default=0, description="Total tasks created")
    tasks_completed: int = Field(default=0, description="Tasks completed")
    tasks_todo: int = Field(default=0, description="Tasks in TODO status")
    tasks_in_progress: int = Field(default=0, description="Tasks in IN_PROGRESS status")


class SOCMetricsSummary(SQLModel):
    """Aggregated SOC metrics summary across the query time range."""
    
    # Alert aggregates
    total_alerts: int = Field(default=0, description="Total alerts in period")
    total_alerts_closed: int = Field(default=0, description="Total alerts closed")
    total_alerts_tp: int = Field(default=0, description="Total true positives")
    total_alerts_fp: int = Field(default=0, description="Total false positives")
    total_alerts_bp: int = Field(default=0, description="Total benign positives")
    
    # Calculated rates
    tp_rate: Optional[float] = Field(default=None, description="True positive rate (TP / closed)")
    fp_rate: Optional[float] = Field(default=None, description="False positive rate (FP / closed)")
    bp_rate: Optional[float] = Field(default=None, description="Benign positive rate (BP / closed)")
    escalation_rate: Optional[float] = Field(default=None, description="Escalation rate (escalated / triaged)")
    
    # Overall timing
    mttt_p50_seconds: Optional[float] = Field(default=None, description="Overall median MTTT")
    mttt_mean_seconds: Optional[float] = Field(default=None, description="Overall mean MTTT")
    mttr_p50_seconds: Optional[float] = Field(default=None, description="Overall median MTTR")
    mttr_mean_seconds: Optional[float] = Field(default=None, description="Overall mean MTTR")
    
    # Case aggregates
    total_cases: int = Field(default=0, description="Total cases in period")
    total_cases_closed: int = Field(default=0, description="Total cases closed")
    open_cases: int = Field(default=0, description="Currently open cases")
    
    # Task aggregates
    total_tasks: int = Field(default=0, description="Total tasks in period")
    total_tasks_completed: int = Field(default=0, description="Total tasks completed")
    open_tasks: int = Field(default=0, description="Currently open tasks")


class SOCMetricsResponse(SQLModel):
    """Full SOC metrics response with time series and summary."""
    
    start_time: datetime = Field(description="Query period start (binned to 15-min)")
    end_time: datetime = Field(description="Query period end (binned to 15-min)")
    refreshed_at: Optional[datetime] = Field(default=None, description="Last materialized view refresh")
    
    summary: SOCMetricsSummary = Field(description="Aggregated summary for the period")
    time_series: List[SOCMetricsWindow] = Field(default_factory=list, description="Per-window breakdown")


class AnalystMetricsWindow(MetricsTimeWindow):
    """Per-analyst metrics for a single time window."""
    
    analyst: str = Field(description="Analyst username")
    
    # Alert triage
    alerts_triaged: int = Field(default=0, description="Alerts triaged by analyst")
    alerts_tp: int = Field(default=0, description="True positives")
    alerts_fp: int = Field(default=0, description="False positives")
    alerts_bp: int = Field(default=0, description="Benign positives")
    alerts_escalated: int = Field(default=0, description="Alerts escalated")
    alerts_duplicate: int = Field(default=0, description="Duplicates identified")
    
    # Timing
    mttt_p50_seconds: Optional[float] = Field(default=None, description="Analyst's median MTTT")
    mttt_mean_seconds: Optional[float] = Field(default=None, description="Analyst's mean MTTT")
    
    # Cases
    cases_assigned: int = Field(default=0, description="Cases assigned to analyst")
    cases_closed: int = Field(default=0, description="Cases closed by analyst")
    
    # Tasks
    tasks_assigned: int = Field(default=0, description="Tasks assigned to analyst")
    tasks_completed: int = Field(default=0, description="Tasks completed by analyst")


class AnalystMetricsSummary(SQLModel):
    """Aggregated metrics for a single analyst."""
    
    analyst: str = Field(description="Analyst username")
    
    # Alert aggregates
    total_alerts_triaged: int = Field(default=0, description="Total alerts triaged")
    total_alerts_tp: int = Field(default=0, description="Total true positives")
    total_alerts_fp: int = Field(default=0, description="Total false positives")
    total_alerts_bp: int = Field(default=0, description="Total benign positives")
    total_alerts_escalated: int = Field(default=0, description="Total escalations")
    
    # Rates
    tp_rate: Optional[float] = Field(default=None, description="Analyst TP rate")
    fp_rate: Optional[float] = Field(default=None, description="Analyst FP rate")
    escalation_rate: Optional[float] = Field(default=None, description="Analyst escalation rate")
    
    # Timing comparison
    mttt_p50_seconds: Optional[float] = Field(default=None, description="Analyst median MTTT")
    mttt_mean_seconds: Optional[float] = Field(default=None, description="Analyst mean MTTT")
    team_mttt_p50_seconds: Optional[float] = Field(default=None, description="Team median MTTT for comparison")
    
    # Case/task totals
    total_cases_assigned: int = Field(default=0, description="Total cases worked")
    total_cases_closed: int = Field(default=0, description="Total cases closed")
    total_tasks_completed: int = Field(default=0, description="Total tasks completed")


class AnalystMetricsResponse(SQLModel):
    """Full analyst metrics response."""
    
    start_time: datetime = Field(description="Query period start")
    end_time: datetime = Field(description="Query period end")
    refreshed_at: Optional[datetime] = Field(default=None, description="Last refresh timestamp")
    
    analysts: List[AnalystMetricsSummary] = Field(default_factory=list, description="Per-analyst summaries")
    time_series: List[AnalystMetricsWindow] = Field(default_factory=list, description="Time series by analyst")


class AlertMetricsWindow(MetricsTimeWindow):
    """Alert performance metrics for a single time window."""
    
    source: Optional[str] = Field(default=None, description="Alert source/rule")
    priority: Optional[str] = Field(default=None, description="Alert priority")
    hour_of_day: Optional[int] = Field(default=None, description="Hour of day (0-23)")
    day_of_week: Optional[int] = Field(default=None, description="Day of week (0=Sunday)")
    
    # Volume
    alert_count: int = Field(default=0, description="Total alerts")
    alerts_closed: int = Field(default=0, description="Closed alerts")
    
    # Outcomes
    alerts_tp: int = Field(default=0, description="True positives")
    alerts_fp: int = Field(default=0, description="False positives")
    alerts_bp: int = Field(default=0, description="Benign positives")
    alerts_escalated: int = Field(default=0, description="Escalated")
    alerts_duplicate: int = Field(default=0, description="Duplicates")
    
    # Rates
    fp_rate: Optional[float] = Field(default=None, description="FP rate for this source")
    escalation_rate: Optional[float] = Field(default=None, description="Escalation rate")


class AlertMetricsBySource(SQLModel):
    """Alert metrics aggregated by source."""
    
    source: Optional[str] = Field(default=None, description="Alert source/rule")
    total_alerts: int = Field(default=0, description="Total alerts from source")
    total_closed: int = Field(default=0, description="Total closed")
    total_tp: int = Field(default=0, description="Total true positives")
    total_fp: int = Field(default=0, description="Total false positives")
    total_escalated: int = Field(default=0, description="Total escalated")
    fp_rate: Optional[float] = Field(default=None, description="Overall FP rate")
    escalation_rate: Optional[float] = Field(default=None, description="Overall escalation rate")


class AlertMetricsByDimension(SQLModel):
    """Alert metrics aggregated by a generic dimension (source, title, or tag)."""
    
    dimension: str = Field(description="Dimension type: 'source', 'title', or 'tag'")
    value: Optional[str] = Field(default=None, description="Dimension value")
    total_alerts: int = Field(default=0, description="Total alerts")
    total_closed: int = Field(default=0, description="Total closed")
    total_tp: int = Field(default=0, description="Total true positives")
    total_fp: int = Field(default=0, description="Total false positives")
    total_bp: int = Field(default=0, description="Total benign positives")
    total_escalated: int = Field(default=0, description="Total escalated")
    fp_rate: Optional[float] = Field(default=None, description="Overall FP rate")
    escalation_rate: Optional[float] = Field(default=None, description="Overall escalation rate")


class AlertMetricsHourly(SQLModel):
    """Alert volume by hour of day."""
    
    hour_of_day: int = Field(description="Hour (0-23)")
    alert_count: int = Field(default=0, description="Total alerts")
    avg_alerts: float = Field(default=0, description="Average alerts per day")


class AlertMetricsResponse(SQLModel):
    """Full alert performance metrics response."""
    
    start_time: datetime = Field(description="Query period start")
    end_time: datetime = Field(description="Query period end")
    refreshed_at: Optional[datetime] = Field(default=None, description="Last refresh timestamp")
    group_by: str = Field(default="source", description="Dimension used for grouping: 'source', 'title', or 'tag'")
    
    by_source: List[AlertMetricsBySource] = Field(default_factory=list, description="Breakdown by source (deprecated, use by_dimension)")
    by_dimension: List[AlertMetricsByDimension] = Field(default_factory=list, description="Breakdown by selected dimension")
    by_hour: List[AlertMetricsHourly] = Field(default_factory=list, description="Volume by hour of day")
    time_series: List[AlertMetricsWindow] = Field(default_factory=list, description="Full time series")


# ============================================================================
# AI Accuracy Metrics Response Models
# ============================================================================

class AITriageWeeklyTrend(SQLModel):
    """Weekly trend data for AI triage accuracy."""
    
    week_start: datetime = Field(description="Start of the week (Monday)")
    total_recommendations: int = Field(default=0, description="Total recommendations made")
    accepted: int = Field(default=0, description="Recommendations accepted")
    rejected: int = Field(default=0, description="Recommendations rejected")
    acceptance_rate: Optional[float] = Field(default=None, description="Acceptance rate (0-1)")


class AITriageByCategory(SQLModel):
    """Rejection breakdown by category."""
    
    category: Optional[str] = Field(default=None, description="Rejection category (null for uncategorized)")
    count: int = Field(default=0, description="Number of rejections in this category")
    percentage: Optional[float] = Field(default=None, description="Percentage of total rejections")


class AITriageByDisposition(SQLModel):
    """Recommendation breakdown by disposition."""
    
    disposition: str = Field(description="Triage disposition")
    total: int = Field(default=0, description="Total recommendations with this disposition")
    accepted: int = Field(default=0, description="Accepted recommendations")
    rejected: int = Field(default=0, description="Rejected recommendations")
    acceptance_rate: Optional[float] = Field(default=None, description="Acceptance rate for this disposition")


class AITriageConfidenceCorrelation(SQLModel):
    """Confidence score correlation with acceptance."""
    
    confidence_bucket: str = Field(description="Confidence range (e.g., '0.8-0.9')")
    total: int = Field(default=0, description="Total recommendations in bucket")
    accepted: int = Field(default=0, description="Accepted recommendations")
    rejected: int = Field(default=0, description="Rejected recommendations")
    acceptance_rate: Optional[float] = Field(default=None, description="Acceptance rate for this confidence range")


class AITriageMetricsSummary(SQLModel):
    """Summary statistics for AI triage accuracy."""
    
    total_recommendations: int = Field(default=0, description="Total recommendations in period")
    total_accepted: int = Field(default=0, description="Total accepted")
    total_rejected: int = Field(default=0, description="Total rejected")
    total_pending: int = Field(default=0, description="Currently pending review")
    acceptance_rate: Optional[float] = Field(default=None, description="Overall acceptance rate (0-1)")
    rejection_rate: Optional[float] = Field(default=None, description="Overall rejection rate (0-1)")
    avg_confidence: Optional[float] = Field(default=None, description="Average confidence score")


class AITriageMetricsResponse(SQLModel):
    """Full AI triage accuracy metrics response."""
    
    start_time: datetime = Field(description="Query period start")
    end_time: datetime = Field(description="Query period end")
    
    summary: AITriageMetricsSummary = Field(description="Aggregated summary for the period")
    by_category: List[AITriageByCategory] = Field(default_factory=list, description="Rejection breakdown by category")
    by_disposition: List[AITriageByDisposition] = Field(default_factory=list, description="Breakdown by disposition")
    by_confidence: List[AITriageConfidenceCorrelation] = Field(default_factory=list, description="Confidence correlation")
    weekly_trend: List[AITriageWeeklyTrend] = Field(default_factory=list, description="Weekly acceptance trend")


class AIChatWeeklyTrend(SQLModel):
    """Weekly trend data for AI chat feedback."""
    
    week_start: datetime = Field(description="Start of the week (Monday)")
    total_messages: int = Field(default=0, description="Total AI messages")
    positive_feedback: int = Field(default=0, description="Positive feedback count")
    negative_feedback: int = Field(default=0, description="Negative feedback count")
    feedback_rate: Optional[float] = Field(default=None, description="Percentage of messages with feedback")
    satisfaction_rate: Optional[float] = Field(default=None, description="Positive / (Positive + Negative)")


class AIChatMetricsSummary(SQLModel):
    """Summary statistics for AI chat feedback."""
    
    total_messages: int = Field(default=0, description="Total AI assistant messages in period")
    total_with_feedback: int = Field(default=0, description="Messages with any feedback")
    positive_feedback: int = Field(default=0, description="Positive feedback count")
    negative_feedback: int = Field(default=0, description="Negative feedback count")
    feedback_rate: Optional[float] = Field(default=None, description="Percentage of messages with feedback")
    satisfaction_rate: Optional[float] = Field(default=None, description="Positive / (Positive + Negative)")


class AIChatMetricsResponse(SQLModel):
    """Full AI chat feedback metrics response."""
    
    start_time: datetime = Field(description="Query period start")
    end_time: datetime = Field(description="Query period end")
    
    summary: AIChatMetricsSummary = Field(description="Aggregated summary for the period")
    weekly_trend: List[AIChatWeeklyTrend] = Field(default_factory=list, description="Weekly feedback trend")


# ============================================================================
# AI Report Drill-Down Response Models (Admin-only)
# ============================================================================

class TriageRecommendationDetail(SQLModel):
    """Triage recommendation with linked alert summary for drill-down reports."""
    
    id: int
    alert_id: int
    alert_human_id: str = Field(description="Human-readable alert ID (e.g., ALT-0000001)")
    alert_title: str = Field(description="Alert title")
    alert_source: Optional[str] = Field(default=None, description="Alert source")
    disposition: TriageDisposition
    confidence: float
    status: RecommendationStatus
    rejection_category: Optional[RejectionCategory] = None
    rejection_reason: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime


class TriageRecommendationDrillDownResponse(SQLModel):
    """Paginated response for triage recommendation drill-down."""
    
    items: List[TriageRecommendationDetail] = Field(default_factory=list)
    total: int = Field(default=0, description="Total count matching filters")
    limit: int = Field(default=50)
    offset: int = Field(default=0)


class ChatFeedbackMessageDetail(SQLModel):
    """Chat message with feedback for drill-down reports."""
    
    id: UUID
    session_id: UUID
    session_title: Optional[str] = Field(default=None, description="Session title")
    flow_id: Optional[str] = Field(default=None, description="LangFlow flow ID")
    user_id: UUID
    username: str = Field(description="Username who received the message")
    display_name: Optional[str] = Field(default=None, description="User display name")
    content: str = Field(description="Message content (truncated preview)")
    feedback: MessageFeedback
    created_at: datetime


class ChatFeedbackDrillDownResponse(SQLModel):
    """Paginated response for chat feedback drill-down."""
    
    items: List[ChatFeedbackMessageDetail] = Field(default_factory=list)
    total: int = Field(default=0, description="Total count matching filters")
    limit: int = Field(default=50)
    offset: int = Field(default=0)

