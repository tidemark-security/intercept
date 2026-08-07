from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.enums import Priority
from app.services.collectors.models import (
    EvaluationResult,
    NormalizedFinding,
    ValidationRequest,
    ValidationResult,
)
from app.services.collectors.schedule_sync import next_collector_run_at
from app.services.collectors.security import (
    CollectorSecurityError,
    canonical_hash,
    validate_allowed_url,
)


def test_canonical_hash_is_order_independent() -> None:
    assert canonical_hash({"b": 2, "a": [1, 3]}) == canonical_hash({"a": [1, 3], "b": 2})


def test_validate_allowed_url_requires_exact_https_host() -> None:
    assert validate_allowed_url("https://api.example.com/v1/events", ["api.example.com"]) == (
        "https://api.example.com/v1/events"
    )
    with pytest.raises(CollectorSecurityError):
        validate_allowed_url("http://api.example.com/v1/events", ["api.example.com"])
    with pytest.raises(CollectorSecurityError):
        validate_allowed_url("https://api.example.com.attacker.test/v1/events", ["api.example.com"])


def test_evaluation_result_enforces_structured_outcome() -> None:
    finding = NormalizedFinding(
        finding_key="project:one",
        title="Affected project",
        priority=Priority.HIGH,
        assessment="confirmed",
    )
    assert EvaluationResult.ready([finding]).findings == [finding]
    assert EvaluationResult.skipped("NOT_ELIGIBLE").skip_code == "NOT_ELIGIBLE"
    request = ValidationRequest(validator_id="collector-validator")
    assert EvaluationResult.awaiting_validation(request).validation_request == request

    with pytest.raises(ValueError):
        EvaluationResult.ready([])


def test_validation_result_binds_revision_and_one_outcome() -> None:
    finding = NormalizedFinding(
        finding_key="project:one",
        title="Affected project",
        assessment="confirmed",
    )
    result = ValidationResult(
        event_revision=2,
        validator_id="collector-validator",
        validator_version="policy-4",
        assessment="confirmed",
        findings=[finding],
        evidence={"release": "main"},
    )
    assert result.event_revision == 2

    with pytest.raises(ValueError):
        ValidationResult(
            event_revision=2,
            validator_id="collector-validator",
            validator_version="policy-4",
            assessment="unknown",
        )


def test_next_collector_run_rolls_to_next_utc_day() -> None:
    now = datetime(2026, 8, 5, 8, 30, tzinfo=timezone.utc)
    assert next_collector_run_at("08:30", now=now) == datetime(
        2026, 8, 6, 8, 30, tzinfo=timezone.utc
    )


@pytest.mark.parametrize("value", ["", "8:30", "24:00", "12:60", "local"])
def test_next_collector_run_rejects_invalid_schedule(value: str) -> None:
    with pytest.raises(ValueError):
        next_collector_run_at(value)
