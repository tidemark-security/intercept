from __future__ import annotations

import pytest

from app.models.enums import AlertStatus
from app.services import triage_recommendation_service


@pytest.mark.parametrize(
    (
        "disposition",
        "input_escalate",
        "input_status",
        "expected_escalate",
        "expected_status",
    ),
    [
        (
            "TRUE_POSITIVE",
            False,
            AlertStatus.CLOSED_TP.value,
            True,
            AlertStatus.ESCALATED.value,
        ),
        (
            "FALSE_POSITIVE",
            True,
            AlertStatus.ESCALATED.value,
            False,
            AlertStatus.CLOSED_FP.value,
        ),
        ("BENIGN", True, AlertStatus.ESCALATED.value, False, AlertStatus.CLOSED_BP.value),
        (
            "NEEDS_INVESTIGATION",
            False,
            AlertStatus.IN_PROGRESS.value,
            True,
            AlertStatus.ESCALATED.value,
        ),
        (
            "DUPLICATE",
            True,
            AlertStatus.ESCALATED.value,
            False,
            AlertStatus.CLOSED_DUPLICATE.value,
        ),
        (
            "UNKNOWN",
            False,
            AlertStatus.CLOSED_UNRESOLVED.value,
            True,
            AlertStatus.ESCALATED.value,
        ),
    ],
)
def test_normalize_recommendation_contract_derives_case_path_from_disposition(
    disposition: str,
    input_escalate: bool,
    input_status: str,
    expected_escalate: bool,
    expected_status: str,
) -> None:
    normalized = triage_recommendation_service.normalize_recommendation_contract(
        {
            "disposition": disposition,
            "confidence": 0.8,
            "recommended_actions": [],
            "suggested_status": input_status,
            "request_escalate_to_case": input_escalate,
        }
    )

    assert normalized["request_escalate_to_case"] is expected_escalate
    assert normalized["suggested_status"] == expected_status


def test_normalize_recommendation_contract_rejects_invalid_suggested_status() -> None:
    with pytest.raises(
        triage_recommendation_service.TriageRecommendationValidationError,
        match="Invalid suggested_status",
    ):
        triage_recommendation_service.normalize_recommendation_contract(
            {
                "disposition": "TRUE_POSITIVE",
                "confidence": 0.8,
                "recommended_actions": [],
                "suggested_status": "NOT_A_STATUS",
                "request_escalate_to_case": False,
            }
        )


def test_normalize_recommendation_contract_rejects_dismissal_work() -> None:
    with pytest.raises(
        triage_recommendation_service.TriageRecommendationValidationError,
        match="Dismissal recommendations cannot include work recommendations",
    ):
        triage_recommendation_service.normalize_recommendation_contract(
            {
                "disposition": "BENIGN",
                "confidence": 0.8,
                "recommended_actions": [{"title": "Investigate anyway"}],
                "request_escalate_to_case": True,
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("disposition", "INVALID"),
        ("suggested_priority", "INVALID"),
        ("confidence", -0.1),
        ("confidence", float("nan")),
    ],
)
def test_normalize_recommendation_contract_rejects_invalid_fields(
    field: str,
    value: object,
) -> None:
    data = {
        "disposition": "TRUE_POSITIVE",
        "confidence": 0.8,
        "recommended_actions": [],
        field: value,
    }

    with pytest.raises(
        triage_recommendation_service.TriageRecommendationValidationError,
        match=f"Invalid {field}",
    ):
        triage_recommendation_service.normalize_recommendation_contract(data)
