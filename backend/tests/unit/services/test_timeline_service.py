from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.entity_ids import ALERT_PREFIX, CASE_PREFIX, TASK_PREFIX
from app.models.enums import ActorType, AlertStatus, PICERLStage, Priority, TaskStatus
from app.models.models import Actor, ActorSnapshot, Alert, Case, Task
from app.services.normalization_service import (
    NormalizationValidationError,
    TimelineReferenceIndex,
    normalization_service,
)
from app.services.task_service import task_service
from app.services.timeline_service import TimelineValidationError, timeline_service


class _FakeScalarResult:
    def __init__(self, values: list[Any]) -> None:
        self.values = values

    def scalars(self) -> _FakeScalarResult:
        return self

    def all(self) -> list[Any]:
        return self.values

    def scalar_one_or_none(self) -> Any:
        return self.values[0] if self.values else None


class _FakeSession:
    def __init__(self, value: Any) -> None:
        self.value = value

    async def get(self, _model: type[Any], _entity_id: int) -> Any:
        return self.value


class _TrackingSession:
    def __init__(self, entities_by_model: dict[type[Any], list[Any]]) -> None:
        self.entities_by_model = entities_by_model
        self.queried_models: list[type[Any]] = []

    async def execute(self, query: Any) -> _FakeScalarResult:
        model = query.column_descriptions[0]["entity"]
        self.queried_models.append(model)
        return _FakeScalarResult(self.entities_by_model.get(model, []))

    async def get(self, _model: type[Any], _entity_id: int) -> Any:
        raise AssertionError("Denormalization must use the retained reference index")


@pytest.mark.asyncio
async def test_timeline_normalization_wraps_typed_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        normalization_service,
        "normalize_item",
        AsyncMock(side_effect=NormalizationValidationError("Actor 9 not found")),
    )

    with pytest.raises(TimelineValidationError, match="Actor 9 not found"):
        await timeline_service.normalize_item(
            _FakeSession(None),  # type: ignore[arg-type]
            {"type": "internal_actor", "actor_id": 9},
        )


@pytest.mark.asyncio
async def test_timeline_normalization_preserves_unexpected_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        normalization_service,
        "normalize_item",
        AsyncMock(side_effect=ValueError("normalization implementation defect")),
    )

    with pytest.raises(ValueError, match="normalization implementation defect"):
        await timeline_service.normalize_item(
            _FakeSession(None),  # type: ignore[arg-type]
            {"type": "note"},
        )


@pytest.mark.asyncio
async def test_linked_case_timeline_items_share_consistent_synthetic_fields() -> None:
    linked_at = datetime(2026, 7, 19, 12, 30, tzinfo=timezone.utc)
    case_entity = SimpleNamespace(
        alerts=[
            SimpleNamespace(
                id=11,
                linked_at=linked_at,
                assignee="alert-owner",
                title="Linked alert",
                priority=Priority.HIGH,
                description="Alert details",
                tags=["alert-tag"],
            )
        ],
        tasks=[
            SimpleNamespace(
                id=12,
                linked_at=linked_at,
                created_by="task-author",
                title="Linked task",
                status=TaskStatus.IN_PROGRESS,
                priority=Priority.MEDIUM,
                assignee="task-owner",
                description="Task details",
                due_date=None,
                picerl_stage=PICERLStage.CONTAINMENT,
                source_runbook="Incident response",
                tags=["task-tag"],
            )
        ],
    )

    items = await timeline_service._inject_linked_entity_items(
        SimpleNamespace(),  # type: ignore[arg-type]
        case_entity,
        CASE_PREFIX,
        {},
        references=TimelineReferenceIndex(),
    )

    alert_item = items["linked-alert-11"]
    task_item = items["linked-task-12"]
    for item in (alert_item, task_item):
        assert item["created_at"] == linked_at.isoformat()
        assert item["timestamp"] == linked_at.isoformat()
        assert item["flagged"] is False
        assert item["highlighted"] is False
        assert item["replies"] == {}
        assert item["_injected"] is True

    assert alert_item["created_by"] == "alert-owner"
    assert alert_item["entity_tags"] == ["alert-tag"]
    assert task_item["created_by"] == "task-author"
    assert task_item["status"] == TaskStatus.IN_PROGRESS.value
    assert task_item["entity_tags"] == ["task-tag"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("human_prefix", "entity", "expected_created_by"),
    [
        (
            ALERT_PREFIX,
            SimpleNamespace(case_id=19, linked_at=datetime(2026, 7, 19, tzinfo=timezone.utc), assignee="analyst"),
            "analyst",
        ),
        (
            TASK_PREFIX,
            SimpleNamespace(case_id=19, linked_at=datetime(2026, 7, 19, tzinfo=timezone.utc), created_by="task-author"),
            "task-author",
        ),
    ],
)
async def test_alert_and_task_use_the_same_linked_case_item_shape(
    human_prefix: str,
    entity: SimpleNamespace,
    expected_created_by: str,
) -> None:
    linked_case = SimpleNamespace(
        id=19,
        title="Incident case",
        priority=Priority.CRITICAL,
        assignee="case-owner",
        description="Case details",
        tags=["case-tag"],
    )

    items = await timeline_service._inject_linked_entity_items(
        SimpleNamespace(),  # type: ignore[arg-type]
        entity,
        human_prefix,
        {},
        references=TimelineReferenceIndex(cases={19: linked_case}),  # type: ignore[arg-type]
    )

    assert items["linked-case-19"] == {
        "id": "linked-case-19",
        "type": "case",
        "created_at": entity.linked_at.isoformat(),
        "timestamp": entity.linked_at.isoformat(),
        "created_by": expected_created_by,
        "tags": ["linked"],
        "entity_tags": ["case-tag"],
        "flagged": False,
        "highlighted": False,
        "replies": {},
        "_injected": True,
        "case_id": 19,
        "title": "Incident case",
        "priority": Priority.CRITICAL,
        "assignee": "case-owner",
        "entity_description": "Case details",
        "description": "Linked to Case CAS-0000019",
    }


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ({"task_id": 42}, 42),
        ({"task_id": "42"}, 42),
        ({"task_human_id": "TSK-0000042"}, 42),
        ({"task_human_id": "tsk-42"}, 42),
        ({"task_id": 0, "task_human_id": "TSK-0000042"}, 42),
        ({"task_id": True}, None),
        ({"task_human_id": "ALT-0000042"}, None),
    ],
)
def test_resolve_task_id_uses_canonical_entity_parser(
    item: dict[str, Any],
    expected: int | None,
) -> None:
    assert normalization_service.resolve_task_id(item) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("item_type", "identity_field", "identity_value"),
    [
        ("alert", "alert_id", 11),
        ("case", "case_id", 12),
        ("task", "task_id", 13),
    ],
)
async def test_link_normalization_strips_fabricated_entity_fields_but_keeps_link_metadata(
    item_type: str,
    identity_field: str,
    identity_value: int,
) -> None:
    item = {
        "id": f"{item_type}-link",
        "type": item_type,
        identity_field: identity_value,
        "description": "Analyst-authored link context",
        "created_at": "2026-07-19T12:30:00+00:00",
        "created_by": "analyst",
        "tags": ["analyst-link"],
        "flagged": True,
        "title": "Fabricated title",
        "status": "FABRICATED_STATUS",
        "priority": "CRITICAL",
        "assignee": "fabricated-assignee",
        "entity_description": "Fabricated entity description",
        "source_timeline_items": {
            "fabricated": {"id": "fabricated", "type": "note"}
        },
    }

    normalized = await normalization_service.normalize_item(
        _FakeSession(None),  # type: ignore[arg-type]
        item,
    )

    assert normalized == {
        "id": f"{item_type}-link",
        "type": item_type,
        identity_field: identity_value,
        "description": "Analyst-authored link context",
        "created_at": "2026-07-19T12:30:00+00:00",
        "created_by": "analyst",
        "tags": ["analyst-link"],
        "flagged": True,
    }
    assert item["status"] == "FABRICATED_STATUS"


@pytest.mark.asyncio
async def test_task_reference_normalization_and_denormalization_share_one_seam() -> None:
    task = Task(
        id=42,
        title="Contain affected host",
        description="Canonical task description",
        status=TaskStatus.IN_PROGRESS,
        priority=Priority.HIGH,
        assignee="responder",
        due_date=datetime(2026, 7, 20, 8, 30, tzinfo=timezone.utc),
        picerl_stage=PICERLStage.CONTAINMENT,
        source_runbook=7,
        created_at=datetime(2026, 7, 19, 12, 30, tzinfo=timezone.utc),
        created_by="runbook-author",
        timeline_items={},
    )
    session = _TrackingSession({})
    item = {
        "id": "task-link-42",
        "type": "task",
        "task_human_id": "tsk-0000042",
        "description": "Linked during incident review",
        "title": "Stale snapshot title",
        "status": TaskStatus.TODO.value,
    }

    normalized = await normalization_service.normalize_item(
        session,  # type: ignore[arg-type]
        item,
    )
    assert normalized == {
        "id": "task-link-42",
        "type": "task",
        "task_id": 42,
        "description": "Linked during incident review",
    }

    denormalized = await normalization_service.denormalize_item(
        session,  # type: ignore[arg-type]
        normalized,
        references=TimelineReferenceIndex(tasks={42: task}),
    )

    assert denormalized["task_human_id"] == "TSK-0000042"
    assert denormalized["description"] == "Linked during incident review"
    assert denormalized["title"] == "Contain affected host"
    assert denormalized["entity_description"] == "Canonical task description"
    assert denormalized["status"] == TaskStatus.IN_PROGRESS.value
    assert denormalized["priority"] == Priority.HIGH.value
    assert denormalized["due_date"] == "2026-07-20T08:30:00+00:00"
    assert denormalized["picerl_stage"] == PICERLStage.CONTAINMENT.value
    assert denormalized["source_runbook"] == 7
    assert denormalized["created_by"] == "runbook-author"


def test_build_note_item_preserves_metadata_and_defers_id_generation() -> None:
    occurred_at = datetime(2026, 7, 19, 12, 30, tzinfo=timezone.utc)
    tags = ["status-change"]

    note = timeline_service.build_note_item(
        description="Alert status changed to Closed",
        created_by="analyst",
        created_at=occurred_at,
        timestamp=occurred_at,
        tags=tags,
    )
    tags.append("mutated-later")

    assert note == {
        "type": "note",
        "description": "Alert status changed to Closed",
        "created_at": occurred_at,
        "timestamp": occurred_at,
        "created_by": "analyst",
        "tags": ["status-change"],
        "flagged": False,
        "highlighted": False,
        "replies": [],
    }
    assert "id" not in note


def test_built_note_uses_existing_insertion_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(timeline_service, "generate_item_id", lambda: "generated-note-id")
    case = Case(title="Builder test", created_by="analyst", timeline_items={})
    note = timeline_service.build_note_item(
        description="Closure summary",
        created_by="analyst",
        timestamp="2026-07-19T12:30:00+00:00",
        tags=["case-closure"],
    )

    assert "created_at" not in note
    timeline_service.add_timeline_item(case, note, created_by="analyst")

    stored = case.timeline_items["generated-note-id"]
    assert stored["id"] == "generated-note-id"
    assert stored["created_by"] == "analyst"
    assert stored["timestamp"] == "2026-07-19T12:30:00+00:00"
    assert stored["tags"] == ["case-closure"]
    assert stored["flagged"] is False
    assert stored["highlighted"] is False
    assert stored["replies"] == {}
    assert isinstance(stored["created_at"], str)


def test_datetime_serialization_reaches_all_json_nesting_shapes() -> None:
    occurred_at = datetime(2026, 7, 19, 12, 30, tzinfo=timezone.utc)
    payload = {
        "direct": occurred_at,
        "mapping": {"occurred_at": occurred_at},
        "values": [occurred_at, {"occurred_at": occurred_at}, [occurred_at]],
    }

    timeline_service._serialize_datetime_fields(payload)

    expected = occurred_at.isoformat()
    assert payload == {
        "direct": expected,
        "mapping": {"occurred_at": expected},
        "values": [expected, {"occurred_at": expected}, [expected]],
    }


@pytest.mark.asyncio
async def test_load_referenced_entities_retains_nested_entities_and_snapshots() -> None:
    actor = SimpleNamespace(id=1)
    alert = SimpleNamespace(id=2)
    case = SimpleNamespace(id=3)
    task = SimpleNamespace(id=4)
    snapshot = SimpleNamespace(actor_id=1, snapshot_hash="snapshot-1", snapshot={"name": "Alice"})
    session = _TrackingSession(
        {
            Actor: [actor],
            ActorSnapshot: [snapshot],
            Alert: [alert],
            Case: [case],
            Task: [task],
        }
    )
    timeline_items = {
        "actor": {
            "type": "internal_actor",
            "actor_id": 1,
            "snapshot_hash": "snapshot-1",
            "replies": {
                "alert": {"type": "alert", "alert_id": 2},
                "case": {"type": "case", "case_id": 3},
                "task": {"type": "task", "task_id": 4},
            },
        }
    }

    references = await timeline_service.load_referenced_entities(
        session,  # type: ignore[arg-type]
        timeline_items,
    )

    assert references.actors == {1: actor}
    assert references.actor_snapshots == {(1, "snapshot-1"): snapshot}
    assert references.alerts == {2: alert}
    assert references.cases == {3: case}
    assert references.tasks == {4: task}
    assert session.queried_models == [Actor, Alert, Case, Task, ActorSnapshot]


@pytest.mark.asyncio
async def test_denormalize_linked_entities_uses_batched_reference_index() -> None:
    source_actor_1 = {
        "id": "actor-1",
        "type": "internal_actor",
        "actor_id": 11,
        "replies": {},
    }
    source_actor_2 = {
        "id": "actor-2",
        "type": "internal_actor",
        "actor_id": 12,
        "replies": {},
    }
    alerts = [
        SimpleNamespace(
            id=21,
            title="First linked alert",
            description="First alert details",
            status=AlertStatus.NEW,
            priority=Priority.HIGH,
            assignee="analyst",
            timeline_items={"actor-1": source_actor_1},
        ),
        SimpleNamespace(
            id=22,
            title="Second linked alert",
            description="Second alert details",
            status=AlertStatus.ESCALATED,
            priority=Priority.CRITICAL,
            assignee=None,
            timeline_items={},
        ),
    ]
    tasks = [
        SimpleNamespace(
            id=31,
            title="First linked task",
            description="First task details",
            status=TaskStatus.TODO,
            priority=Priority.MEDIUM,
            assignee="analyst",
            due_date=None,
            picerl_stage=None,
            source_runbook=None,
            created_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
            created_by="analyst",
            timeline_items={"actor-2": source_actor_2},
        ),
        SimpleNamespace(
            id=32,
            title="Second linked task",
            description="Second task details",
            status=TaskStatus.IN_PROGRESS,
            priority=Priority.HIGH,
            assignee=None,
            due_date=None,
            picerl_stage=None,
            source_runbook=None,
            created_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
            created_by="analyst",
            timeline_items={},
        ),
    ]
    actors = [
        SimpleNamespace(
            id=11,
            actor_type=ActorType.INTERNAL,
            user_id="alice@example.com",
            name="Alice",
            title=None,
            org=None,
            contact_phone=None,
            contact_email="alice@example.com",
        ),
        SimpleNamespace(
            id=12,
            actor_type=ActorType.INTERNAL,
            user_id="bob@example.com",
            name="Bob",
            title=None,
            org=None,
            contact_phone=None,
            contact_email="bob@example.com",
        ),
    ]
    session = _TrackingSession({Alert: alerts, Task: tasks, Actor: actors})
    owner = SimpleNamespace(
        timeline_items={
            "alert-21": {
                "id": "alert-21",
                "type": "alert",
                "alert_id": 21,
                "description": "Analyst link note",
                "replies": {},
            },
            "alert-22": {"id": "alert-22", "type": "alert", "alert_id": 22, "replies": {}},
            "task-31": {
                "id": "task-31",
                "type": "task",
                "task_id": 31,
                "description": "Investigate this relationship",
                "replies": {},
            },
            "task-32": {"id": "task-32", "type": "task", "task_id": 32, "replies": {}},
        }
    )

    result = await timeline_service.denormalize_entity_timeline(
        session,  # type: ignore[arg-type]
        owner,
        human_prefix="TEST",
        include_linked_timelines=True,
        detach=False,
    )

    assert session.queried_models.count(Alert) == 1
    assert session.queried_models.count(Task) == 1
    assert session.queried_models.count(Actor) == 1
    assert result.timeline_items["alert-21"]["description"] == "Analyst link note"
    assert result.timeline_items["alert-21"]["entity_description"] == "First alert details"
    assert result.timeline_items["task-31"]["description"] == "Investigate this relationship"
    assert result.timeline_items["task-31"]["entity_description"] == "First task details"
    assert result.timeline_items["alert-21"]["source_timeline_items"]["actor-1"]["name"] == "Alice"
    assert result.timeline_items["task-31"]["source_timeline_items"]["actor-2"]["name"] == "Bob"


@pytest.mark.asyncio
async def test_attachment_removal_defers_storage_cleanup() -> None:
    entity = Case(
        title="Attachment cleanup",
        created_by="analyst",
        timeline_items={
            "attachment-1": {
                "id": "attachment-1",
                "type": "attachment",
                "storage_key": "cases/1/attachments/attachment-1/evidence.txt",
            }
        }
    )

    cleanup = await timeline_service.remove_timeline_item_with_cleanup(
        SimpleNamespace(),  # type: ignore[arg-type]
        entity,
        "attachment-1",
        "analyst",
    )

    assert cleanup is not None
    assert cleanup.storage_key == "cases/1/attachments/attachment-1/evidence.txt"
    assert "attachment-1" not in entity.timeline_items


@pytest.mark.asyncio
async def test_task_cleanup_miss_preserves_timeline_item(monkeypatch: pytest.MonkeyPatch) -> None:
    delete_task = AsyncMock(return_value=False)
    monkeypatch.setattr(task_service, "delete_task_in_transaction", delete_task)
    entity = SimpleNamespace(
        timeline_items={
            "task-1": {
                "id": "task-1",
                "type": "task",
                "task_id": 42,
            }
        }
    )

    with pytest.raises(ValueError, match="Task 42 not found"):
        await timeline_service.remove_timeline_item_with_cleanup(
            SimpleNamespace(),  # type: ignore[arg-type]
            entity,
            "task-1",
            "analyst",
        )

    assert "task-1" in entity.timeline_items


def test_remove_timeline_item_tolerates_malformed_legacy_containers() -> None:
    malformed_entity = SimpleNamespace(timeline_items=42)

    assert timeline_service.remove_timeline_item(malformed_entity, "missing") is False
    assert malformed_entity.timeline_items == {}

    nested_items: list[Any] = [
        "malformed-entry",
        {
            "id": "parent",
            "replies": {
                "target": {"id": "target", "type": "note"},
                "malformed-reply": None,
            },
        },
    ]

    assert timeline_service._remove_item_recursive(nested_items, "target") is True
    assert nested_items[0] == "malformed-entry"
    assert nested_items[1]["replies"] == {"malformed-reply": None}


@pytest.mark.asyncio
async def test_embed_alert_timeline_items_populates_source_items() -> None:
    linked_alert = SimpleNamespace(
        id=68,
        title="Critical Zero-Day Vulnerability Exploitation Attempt",
        description="Underlying alert markdown",
        status=AlertStatus.ESCALATED,
        priority=Priority.CRITICAL,
        assignee="admin",
        timeline_items={
            "source-note-1": {
                "id": "source-note-1",
                "type": "note",
                "created_by": "admin",
                "created_at": "2026-06-08T11:14:31Z",
                "timestamp": "2026-06-08T11:14:31Z",
                "description": "Alert child timeline item",
                "replies": {},
            }
        },
    )

    item = {
        "id": "linked-alert-68",
        "type": "alert",
        "alert_id": 68,
        "description": "Linked during incident review",
    }
    references = TimelineReferenceIndex(alerts={68: linked_alert})  # type: ignore[arg-type]

    result = await timeline_service._embed_alert_timeline_items(
        _FakeSession(linked_alert),  # type: ignore[arg-type]
        item,
        references=references,
    )

    assert result["title"] == linked_alert.title
    assert result["description"] == "Linked during incident review"
    assert result["entity_description"] == linked_alert.description
    assert result["status"] == AlertStatus.ESCALATED.value
    assert result["priority"] == Priority.CRITICAL.value
    assert result["assignee"] == "admin"
    assert result["source_timeline_items"] == linked_alert.timeline_items


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "item"),
    [
        ("_embed_alert_timeline_items", {"type": "alert", "alert_id": 68}),
        ("_embed_case_timeline_items", {"type": "case", "case_id": 19}),
    ],
)
async def test_linked_timeline_embedding_surfaces_unexpected_lookup_failures(
    method_name: str,
    item: dict[str, Any],
) -> None:
    session = SimpleNamespace(get=AsyncMock(side_effect=RuntimeError("lookup failed")))
    embed = getattr(timeline_service, method_name)

    with pytest.raises(RuntimeError, match="lookup failed"):
        await embed(session, item)
