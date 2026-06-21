from __future__ import annotations

import re
from typing import Iterable

from app.models.enums import CaseTemplateStatus
from app.models.models import TemplateTaskDefinition


_WHITESPACE_RE = re.compile(r"\s+")


class CaseTemplateValidationError(ValueError):
    """Raised when a case template violates lifecycle or task rules."""


def normalize_template_title(title: str | None) -> str | None:
    if title is None:
        return None
    normalized = _WHITESPACE_RE.sub(" ", title.strip()).casefold()
    return normalized or None


def validate_template_task_titles_unique(tasks: Iterable[TemplateTaskDefinition]) -> None:
    seen: set[str] = set()
    for task in tasks:
        normalized = normalize_template_title(task.title)
        if not normalized:
            continue
        if normalized in seen:
            raise CaseTemplateValidationError("Template Task titles must be unique within a Case Template")
        seen.add(normalized)


def validate_case_template_payload(
    *,
    status: CaseTemplateStatus,
    title: str | None,
    description: str | None,
    template_tasks: list[TemplateTaskDefinition],
) -> None:
    """Validate lifecycle-dependent case template invariants."""

    normalized_title = normalize_template_title(title)

    if status == CaseTemplateStatus.DELETED:
        return

    if not normalized_title:
        raise CaseTemplateValidationError("Case Template title is required")

    validate_template_task_titles_unique(template_tasks)

    if status != CaseTemplateStatus.PUBLISHED:
        return

    if not (description or "").strip():
        raise CaseTemplateValidationError("Published Case Templates require a description")
    if not template_tasks:
        raise CaseTemplateValidationError("Published Case Templates require at least one Template Task")

    for index, task in enumerate(template_tasks, start=1):
        if not normalize_template_title(task.title):
            raise CaseTemplateValidationError(f"Template Task {index} requires a title")
        if task.picerl_stage is None:
            raise CaseTemplateValidationError(f"Template Task {index} requires a PICERL Stage")
