from datetime import datetime, timezone

import pytest

from app.models.enums import AlertStatus, Priority
from app.models.models import Alert
from app.services import mcp_service
from app.services.mcp_errors import McpValidationError


def test_summarize_timeline_owns_filter_order_and_preview_mapping() -> None:
    section, filtered_items = mcp_service._summarize_timeline(
        [
            {
                "id": "old",
                "type": "note",
                "timestamp": "2026-06-01T00:00:00Z",
                "description": "old note",
            },
            {
                "id": "linked",
                "type": "task",
                "task_id": 12,
                "timestamp": "2026-06-03T00:00:00Z",
                "description": "linked task",
            },
            {
                "id": "malformed",
                "type": "note",
                "timestamp": "not-a-date",
            },
        ],
        since=datetime(2026, 6, 2, tzinfo=timezone.utc),
        limit=1,
        default_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert [item["id"] for item in filtered_items] == ["linked"]
    assert section.total_count == 1
    assert section.omitted_count == 0
    assert section.bounded_by == "since"
    assert section.items[0].timeline_id == "linked"
    assert section.items[0].entity_id == "TSK-0000012"


def test_timeline_preview_tolerates_malformed_legacy_scalar_fields() -> None:
    section, _ = mcp_service._summarize_timeline(
        [
            {
                "id": "legacy",
                "type": 7,
                "timestamp": 123,
                "created_by": 42,
                "body": {"legacy": "content"},
            },
            {
                "id": "current",
                "type": "task",
                "task_id": True,
                "timestamp": "2026-06-03T00:00:00Z",
                "description": "current item",
            },
        ],
        since=None,
        limit=2,
        default_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert [item.timeline_id for item in section.items] == ["current", "legacy"]
    assert section.items[0].entity_id is None
    assert section.items[1].type == "note"
    assert section.items[1].author == "42"
    assert section.items[1].preview == "{'legacy': 'content'}"


def test_suggested_triage_patches_returns_patches_and_persisted_tags() -> None:
    alert = Alert(
        title="Suspicious activity",
        created_by="analyst",
        status=AlertStatus.NEW,
        priority=Priority.HIGH,
        assignee="analyst",
        tags=["existing"],
    )

    patches, tags_to_add, tags_to_remove = mcp_service._suggested_triage_patches(
        alert,
        {
            "suggested_status": AlertStatus.ESCALATED.value,
            "suggested_priority": Priority.CRITICAL.value,
            "suggested_assignee": "responder",
            "suggested_tags_add": [" new ", "existing", "NEW"],
            "suggested_tags_remove": ["existing", "missing"],
        },
    )

    assert tags_to_add == ["new", "existing"]
    assert tags_to_remove == ["existing", "missing"]
    assert [patch.model_dump() for patch in patches] == [
        {
            "field": "status",
            "current_value": "NEW",
            "new_value": "ESCALATED",
        },
        {
            "field": "priority",
            "current_value": "HIGH",
            "new_value": "CRITICAL",
        },
        {
            "field": "assignee",
            "current_value": "analyst",
            "new_value": "responder",
        },
        {"field": "tags", "current_value": None, "new_value": "add:new"},
        {
            "field": "tags",
            "current_value": "existing",
            "new_value": "remove:existing",
        },
    ]


def test_suggested_triage_patches_reports_only_effective_tag_changes() -> None:
    alert = Alert(
        title="Suspicious activity",
        status=AlertStatus.NEW,
        tags=["Existing"],
    )

    patches, _, _ = mcp_service._suggested_triage_patches(
        alert,
        {
            "suggested_status": AlertStatus.NEW.value,
            "suggested_priority": None,
            "suggested_assignee": None,
            "suggested_tags_add": ["existing", "transient"],
            "suggested_tags_remove": ["transient", "missing"],
        },
    )

    assert patches == []


def test_normalize_work_statuses_expands_alert_closed_without_mutating_input() -> None:
    requested = ["NEW", "CLOSED"]

    statuses = mcp_service._normalize_work_statuses("alert", requested)

    assert requested == ["NEW", "CLOSED"]
    assert statuses == [
        AlertStatus.NEW,
        AlertStatus.CLOSED_TP,
        AlertStatus.CLOSED_BP,
        AlertStatus.CLOSED_FP,
        AlertStatus.CLOSED_UNRESOLVED,
        AlertStatus.CLOSED_DUPLICATE,
    ]


def test_normalize_work_statuses_reports_invalid_value() -> None:
    with pytest.raises(McpValidationError, match="Invalid status value"):
        mcp_service._normalize_work_statuses("alert", ["NOT_A_STATUS"])


def test_work_item_id_parser_does_not_mask_unexpected_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_parser(_raw: str, _kind: str) -> tuple[int, str]:
        raise RuntimeError("parser defect")

    monkeypatch.setattr(mcp_service, "parse_entity_id", fail_parser)

    with pytest.raises(RuntimeError, match="parser defect"):
        mcp_service._parse_work_item_id("1", "case")


@pytest.mark.parametrize(
    ("value", "minimum", "maximum", "expected"),
    [
        (-1, 1, 50, 1),
        (25, 1, 50, 25),
        (100, 1, 50, 50),
    ],
)
def test_clamp_int_enforces_documented_tool_bounds(
    value: int,
    minimum: int,
    maximum: int,
    expected: int,
) -> None:
    assert mcp_service._clamp_int(
        value,
        minimum=minimum,
        maximum=maximum,
    ) == expected


@pytest.mark.parametrize(
    ("mode", "offset", "expected_page", "expected_offset"),
    [
        ("full", 3, "defg", 7),
        ("head", 3, "abcd", 4),
        ("tail", 3, "ghij", 10),
    ],
)
def test_slice_timeline_content_owns_all_retrieval_modes(
    mode: str,
    offset: int,
    expected_page: str,
    expected_offset: int,
) -> None:
    assert mcp_service._slice_timeline_content(
        "abcdefghij",
        mode=mode,
        max_chars=4,
        offset=offset,
    ) == (expected_page, expected_offset)


def test_cursor_offset_treats_invalid_or_negative_cursors_as_first_page() -> None:
    assert mcp_service._cursor_offset("not-base64") == 0
    assert mcp_service._cursor_offset(
        mcp_service._encode_cursor({"offset": -1})
    ) == 0
    assert mcp_service._cursor_offset(
        mcp_service._encode_cursor({"offset": True})
    ) == 0
    assert mcp_service._cursor_offset(
        mcp_service._encode_cursor({"offset": 42})
    ) == 42
