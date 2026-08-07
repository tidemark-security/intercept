"""Provider-facing contracts and API schemas for alert collectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.models.enums import Priority


class CollectorErrorCode(str, Enum):
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INVALID_PROVIDER_RESPONSE = "INVALID_PROVIDER_RESPONSE"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    NORMALIZATION_FAILED = "NORMALIZATION_FAILED"
    VALIDATION_REQUIRED = "VALIDATION_REQUIRED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    STALE_REVISION = "STALE_REVISION"
    ALERT_INGESTION_FAILED = "ALERT_INGESTION_FAILED"
    CONFIGURATION_INVALID = "CONFIGURATION_INVALID"


class CollectorRunTrigger(str, Enum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    WEBHOOK = "webhook"
    BACKFILL = "backfill"


class CollectorRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class CollectorEventStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    PROCESSING = "PROCESSING"
    AWAITING_VALIDATION = "AWAITING_VALIDATION"
    READY = "READY"
    IMPORTED = "IMPORTED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class CollectorFindingStatus(str, Enum):
    PENDING = "pending"
    IMPORTED = "imported"
    SKIPPED = "skipped"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class EvaluationOutcome(str, Enum):
    READY = "ready"
    SKIPPED = "skipped"
    AWAITING_VALIDATION = "awaiting_validation"


class TriagePolicy(str, Enum):
    STANDARD = "standard"
    SKIP = "skip"


class TriageEnqueueStatus(str, Enum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    ENQUEUED = "enqueued"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(slots=True)
class ExternalEvent:
    external_id: str
    raw_payload: dict[str, Any]
    external_created_at: datetime | None = None
    external_updated_at: datetime | None = None


@dataclass(slots=True)
class CollectionPage:
    events: list[ExternalEvent] = field(default_factory=list)
    next_checkpoint: dict[str, Any] | None = None
    has_more: bool = False


class NormalizedEvent(BaseModel):
    """Versioned, durable provider event used for repeatable evaluation."""

    schema_version: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=100_000)
    source_url: HttpUrl | None = None
    provider_created_at: datetime | None = None
    provider_updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedFinding(BaseModel):
    """Stable alert projection for one affected target of an event."""

    finding_key: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=100_000)
    priority: Priority | None = None
    tags: list[str] = Field(default_factory=list, max_length=100)
    assessment: str = Field(min_length=1, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_url: HttpUrl | None = None
    triage_policy: TriagePolicy = TriagePolicy.STANDARD
    validation_payload: dict[str, Any] = Field(default_factory=dict)
    validation_report_ref: str | None = Field(default=None, max_length=1000)
    validator_version: str | None = Field(default=None, max_length=200)


class ValidationRequest(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    validator_id: str = Field(min_length=1, max_length=200)
    workflow_id: str | None = Field(default=None, max_length=500)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    event_revision: int = Field(ge=1)
    validator_id: str = Field(min_length=1, max_length=200)
    validator_version: str = Field(min_length=1, max_length=200)
    assessment: str = Field(min_length=1, max_length=200)
    findings: list[NormalizedFinding] = Field(default_factory=list, max_length=100)
    evidence: dict[str, Any] = Field(default_factory=dict)
    validation_report_ref: str | None = Field(default=None, max_length=1000)
    skipped: bool = False
    skip_code: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_outcome(self) -> "ValidationResult":
        if self.skipped == bool(self.findings):
            raise ValueError("Validation must either be skipped or contain findings")
        if self.skipped and not self.skip_code:
            raise ValueError("skip_code is required for a skipped validation")
        if self.findings and not self.evidence:
            raise ValueError("evidence is required when validation produces findings")
        return self


@dataclass(slots=True)
class EvaluationResult:
    outcome: EvaluationOutcome
    findings: list[NormalizedFinding] = field(default_factory=list)
    skip_code: str | None = None
    validation_request: ValidationRequest | None = None

    def __post_init__(self) -> None:
        if self.outcome is EvaluationOutcome.READY and not self.findings:
            raise ValueError("Ready evaluations must contain at least one finding")
        if self.outcome is EvaluationOutcome.SKIPPED and not self.skip_code:
            raise ValueError("Skipped evaluations require a skip_code")
        if self.outcome is EvaluationOutcome.AWAITING_VALIDATION and self.validation_request is None:
            raise ValueError("Deferred evaluations require a validation_request")

    @classmethod
    def ready(cls, findings: Sequence[NormalizedFinding]) -> "EvaluationResult":
        return cls(EvaluationOutcome.READY, findings=list(findings))

    @classmethod
    def skipped(cls, skip_code: str) -> "EvaluationResult":
        return cls(EvaluationOutcome.SKIPPED, skip_code=skip_code)

    @classmethod
    def awaiting_validation(cls, request: ValidationRequest) -> "EvaluationResult":
        return cls(EvaluationOutcome.AWAITING_VALIDATION, validation_request=request)


@dataclass(frozen=True, slots=True)
class CollectorContext:
    provider_id: str
    stream_key: str
    config: Mapping[str, Any]
    run_id: int | None = None
    event_id: int | None = None
    event_revision: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "config", MappingProxyType(dict(self.config)))


class CollectorRunRequest(BaseModel):
    stream_key: str = Field(default="default", min_length=1, max_length=255)
    mode: str = Field(default="incremental", pattern="^(incremental|backfill)$")
    dry_run: bool = False
    since: datetime | None = None
    max_pages: int | None = Field(default=None, ge=1, le=1000)


class CollectorRunEnqueueResponse(BaseModel):
    enqueued: bool
    task_id: str | None = None
    run_id: int | None = None
    dry_run: bool = False
    counts: dict[str, int] | None = None


class CollectorProviderStatus(BaseModel):
    provider_id: str
    display_name: str
    enabled: bool
    schedule_enabled: bool
    schedule_time_utc: str | None = None
    streams: list[str] = Field(default_factory=list)
    checkpoint_age_seconds: float | None = None
    pending_events: dict[str, int] = Field(default_factory=dict)


class CollectorConnectionTestResponse(BaseModel):
    provider_id: str
    ok: bool
    event_count: int = 0
    has_more: bool = False
    error_code: CollectorErrorCode | None = None
    error_summary: str | None = None
