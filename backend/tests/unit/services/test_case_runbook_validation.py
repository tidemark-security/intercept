from __future__ import annotations

import pytest

from app.models.enums import CaseRunbookStatus, PICERLStage
from app.models.models import RunbookTaskDefinition
from app.services.case_runbook_validation import (
    CaseRunbookValidationError,
    normalize_runbook_title,
    validate_case_runbook_payload,
)


def test_normalize_runbook_title_collapses_case_and_whitespace() -> None:
    assert normalize_runbook_title("  DLP   Exfiltration  ") == "dlp exfiltration"


def test_draft_runbooks_can_be_incomplete() -> None:
    validate_case_runbook_payload(
        status=CaseRunbookStatus.DRAFT,
        title="DLP response",
        description=None,
        runbook_tasks=[],
    )


def test_published_runbooks_require_description_and_tasks() -> None:
    with pytest.raises(CaseRunbookValidationError, match="description"):
        validate_case_runbook_payload(
            status=CaseRunbookStatus.PUBLISHED,
            title="DLP response",
            description="",
            runbook_tasks=[],
        )

    with pytest.raises(CaseRunbookValidationError, match="at least one"):
        validate_case_runbook_payload(
            status=CaseRunbookStatus.PUBLISHED,
            title="DLP response",
            description="Investigate DLP alert",
            runbook_tasks=[],
        )


def test_runbook_task_titles_are_unique_after_normalization() -> None:
    with pytest.raises(CaseRunbookValidationError, match="unique"):
        validate_case_runbook_payload(
            status=CaseRunbookStatus.PUBLISHED,
            title="DLP response",
            description="Investigate DLP alert",
            runbook_tasks=[
                RunbookTaskDefinition(title="Collect Evidence", picerl_stage=PICERLStage.IDENTIFICATION),
                RunbookTaskDefinition(title=" collect   evidence ", picerl_stage=PICERLStage.CONTAINMENT),
            ],
        )


def test_deleted_tombstones_allow_null_title_and_redacted_content() -> None:
    validate_case_runbook_payload(
        status=CaseRunbookStatus.DELETED,
        title=None,
        description=None,
        runbook_tasks=[],
    )
