from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.models.enums import AlertStatus, Priority
from app.services.timeline_service import timeline_service


class _FakeScalarResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


class _FakeSession:
    def __init__(self, value: Any) -> None:
        self.value = value

    async def execute(self, _query: Any) -> _FakeScalarResult:
        return _FakeScalarResult(self.value)


@pytest.mark.asyncio
async def test_embed_alert_timeline_items_populates_source_items(monkeypatch: pytest.MonkeyPatch) -> None:
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

    async def fake_denormalize(_db: Any, item: dict[str, Any], include_linked_timelines: bool = False) -> dict[str, Any]:
        assert include_linked_timelines is False
        return item

    monkeypatch.setattr(timeline_service, "_denormalize_item_recursive", fake_denormalize)

    item = {"id": "linked-alert-68", "type": "alert", "alert_id": 68}

    result = await timeline_service._embed_alert_timeline_items(_FakeSession(linked_alert), item)

    assert result["title"] == linked_alert.title
    assert result["entity_description"] == linked_alert.description
    assert result["status"] == AlertStatus.ESCALATED.value
    assert result["priority"] == Priority.CRITICAL.value
    assert result["assignee"] == "admin"
    assert result["source_timeline_items"] == linked_alert.timeline_items
