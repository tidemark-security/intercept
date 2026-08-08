from datetime import datetime, timezone

from app.models.enums import AlertStatus, CaseRunbookStatus, CaseStatus, PICERLStage, TaskStatus
from app.models.models import AlertRead, CaseRead, CaseRunbookRead, TaskRead
from app.services.tag_filter_utils import (
    merge_persisted_tags,
    normalize_persisted_tags,
    persisted_tag_delta,
)


def test_normalize_persisted_tags_drops_invalid_values_and_deduplicates_case_insensitively() -> None:
    assert normalize_persisted_tags(
        [" Review ", "review", "", "  ", "Null", "null", None, 42, "Escalated"]
    ) == ["Review", "Escalated"]


def test_merge_persisted_tags_normalizes_existing_and_incoming_tags() -> None:
    assert merge_persisted_tags([" Existing ", "null"], ["existing", " New "]) == [
        "Existing",
        "New",
    ]


def test_persisted_tag_delta_is_case_insensitive() -> None:
    assert persisted_tag_delta(
        ["Existing", "removed"],
        ["existing", "added"],
    ) == (["added"], ["removed"])


def test_read_models_normalize_legacy_persisted_tags() -> None:
    now = datetime.now(timezone.utc)
    dirty_tags = ["Null", "Null", "codex-test", "Codex-Test", " review ", "", None, 42]

    alert = AlertRead.model_validate(
        {
            "id": 1,
            "title": "Alert",
            "description": None,
            "priority": None,
            "source": "seed",
            "status": AlertStatus.NEW,
            "created_at": now,
            "updated_at": now,
            "timeline_items": {},
            "tags": dirty_tags,
        }
    )
    assert alert.tags == ["codex-test", "review"]

    case = CaseRead.model_validate(
        {
            "id": 2,
            "title": "Case",
            "description": None,
            "priority": "MEDIUM",
            "status": CaseStatus.NEW,
            "created_by": "seed-user",
            "created_at": now,
            "updated_at": now,
            "timeline_items": {},
            "tags": dirty_tags,
        }
    )
    assert case.tags == ["codex-test", "review"]

    task = TaskRead.model_validate(
        {
            "id": 3,
            "title": "Task",
            "description": None,
            "priority": "MEDIUM",
            "status": TaskStatus.TODO,
            "created_by": "seed-user",
            "created_at": now,
            "updated_at": now,
            "timeline_items": {},
            "tags": dirty_tags,
        }
    )
    assert task.tags == ["codex-test", "review"]


def test_case_runbook_read_normalizes_case_and_task_tags() -> None:
    now = datetime.now(timezone.utc)

    runbook = CaseRunbookRead.model_validate(
        {
            "id": 4,
            "title": "Runbook",
            "description": None,
            "status": CaseRunbookStatus.DRAFT,
            "case_tags": [" Null ", "ir", "IR", "review"],
            "runbook_tasks": [
                {
                    "title": "Collect evidence",
                    "description": None,
                    "picerl_stage": PICERLStage.IDENTIFICATION,
                    "relative_due_seconds": None,
                    "priority": None,
                    "tags": ["Null", "evidence", "Evidence", " review "],
                }
            ],
            "title_normalized": "runbook",
            "created_at": now,
            "updated_at": now,
            "created_by": "seed-user",
            "updated_by": "seed-user",
        }
    )

    assert runbook.case_tags == ["ir", "review"]
    assert runbook.runbook_tasks[0].tags == ["evidence", "review"]
