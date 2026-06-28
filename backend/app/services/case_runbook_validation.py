from __future__ import annotations

import re
from typing import Iterable

from app.models.enums import CaseRunbookStatus
from app.models.models import RunbookTaskDefinition


_WHITESPACE_RE = re.compile(r"\s+")


class CaseRunbookValidationError(ValueError):
    """Raised when a case runbook violates lifecycle or task rules."""


def normalize_runbook_title(title: str | None) -> str | None:
    if title is None:
        return None
    normalized = _WHITESPACE_RE.sub(" ", title.strip()).casefold()
    return normalized or None


def validate_runbook_task_titles_unique(tasks: Iterable[RunbookTaskDefinition]) -> None:
    seen: set[str] = set()
    for task in tasks:
        normalized = normalize_runbook_title(task.title)
        if not normalized:
            continue
        if normalized in seen:
            raise CaseRunbookValidationError("Runbook Task titles must be unique within a Case Runbook")
        seen.add(normalized)


def validate_case_runbook_payload(
    *,
    status: CaseRunbookStatus,
    title: str | None,
    description: str | None,
    runbook_tasks: list[RunbookTaskDefinition],
) -> None:
    """Validate lifecycle-dependent case runbook invariants."""

    normalized_title = normalize_runbook_title(title)

    if status == CaseRunbookStatus.DELETED:
        return

    if not normalized_title:
        raise CaseRunbookValidationError("Case Runbook title is required")

    validate_runbook_task_titles_unique(runbook_tasks)

    if status != CaseRunbookStatus.PUBLISHED:
        return

    if not (description or "").strip():
        raise CaseRunbookValidationError("Published Case Runbooks require a description")
    if not runbook_tasks:
        raise CaseRunbookValidationError("Published Case Runbooks require at least one Runbook Task")

    for index, task in enumerate(runbook_tasks, start=1):
        if not normalize_runbook_title(task.title):
            raise CaseRunbookValidationError(f"Runbook Task {index} requires a title")
        if task.picerl_stage is None:
            raise CaseRunbookValidationError(f"Runbook Task {index} requires a PICERL Stage")
