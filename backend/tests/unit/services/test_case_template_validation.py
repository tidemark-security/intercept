from __future__ import annotations

import pytest

from app.models.enums import CaseTemplateStatus, PICERLStage
from app.models.models import TemplateTaskDefinition
from app.services.case_template_validation import (
    CaseTemplateValidationError,
    normalize_template_title,
    validate_case_template_payload,
)


def test_normalize_template_title_collapses_case_and_whitespace() -> None:
    assert normalize_template_title("  DLP   Exfiltration  ") == "dlp exfiltration"


def test_draft_templates_can_be_incomplete() -> None:
    validate_case_template_payload(
        status=CaseTemplateStatus.DRAFT,
        title="DLP response",
        description=None,
        template_tasks=[],
    )


def test_published_templates_require_description_and_tasks() -> None:
    with pytest.raises(CaseTemplateValidationError, match="description"):
        validate_case_template_payload(
            status=CaseTemplateStatus.PUBLISHED,
            title="DLP response",
            description="",
            template_tasks=[],
        )

    with pytest.raises(CaseTemplateValidationError, match="at least one"):
        validate_case_template_payload(
            status=CaseTemplateStatus.PUBLISHED,
            title="DLP response",
            description="Investigate DLP alert",
            template_tasks=[],
        )


def test_template_task_titles_are_unique_after_normalization() -> None:
    with pytest.raises(CaseTemplateValidationError, match="unique"):
        validate_case_template_payload(
            status=CaseTemplateStatus.PUBLISHED,
            title="DLP response",
            description="Investigate DLP alert",
            template_tasks=[
                TemplateTaskDefinition(title="Collect Evidence", picerl_stage=PICERLStage.IDENTIFICATION),
                TemplateTaskDefinition(title=" collect   evidence ", picerl_stage=PICERLStage.CONTAINMENT),
            ],
        )


def test_deleted_tombstones_allow_null_title_and_redacted_content() -> None:
    validate_case_template_payload(
        status=CaseTemplateStatus.DELETED,
        title=None,
        description=None,
        template_tasks=[],
    )
