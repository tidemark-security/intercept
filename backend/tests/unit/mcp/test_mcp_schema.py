"""Contract tests for the explicitly registered MCP tools."""

from __future__ import annotations

from typing import Any

import pytest

from app.main import mcp


_TOOL_CONTRACTS: dict[str, tuple[set[str], dict[str, Any]]] = {
    "get_summary": (
        {"kind", "id"},
        {"max_timeline_items": 25, "max_observables": 20, "since": None, "preview_chars": 1024, "timeline_offset": 0, "compact": False, "include_enrichments": True},
    ),
    "list_work": (
        {"kind"},
        {
            "statuses": None,
            "priorities": None,
            "assignees": None,
            "contains": None,
            "time_range_start": None,
            "time_range_end": None,
            "limit": 50,
            "cursor": None,
        },
    ),
    "search": ({"query"}, {"entity_types": None, "tags": None, "start_date": None, "end_date": None,
                           "all_time": False, "skip": 0, "limit": 20}),
    "search_queue": ({"kind", "query"}, {"statuses": None, "assignees": None, "include_tags": None,
                    "exclude_tags": None, "start_date": None, "end_date": None, "sort_by": "created_at",
                    "sort_order": "desc", "skip": 0, "limit": 50}),
    "find_observable_occurrences": ({"observable_type", "value"}, {"entity_types": None, "start_date": None,
                                "end_date": None, "all_time": False, "skip": 0, "limit": 20}),
    "get_triage_recommendation": ({"alert_id"}, {}),
    "accept_triage_recommendation": ({"alert_id", "expected_created_at"}, {"apply_status": True,
            "apply_priority": True, "apply_assignee": True, "apply_tags": True, "case_runbook_id": None,
            "skip_case_runbook": False}),
    "reject_triage_recommendation": ({"alert_id", "expected_created_at", "category"}, {"reason": None}),
    "escalate_alert_to_case": ({"alert_id"}, {"case_title": None, "case_description": None,
                                             "triage_notes": None, "commit": False}),
    "set_status": ({"kind", "id", "status"}, {"commit": False}),
    "find_related": ({"seed_kind", "seed_id"}, {"max_matches": 10, "start_date": None, "end_date": None}),
    "search_case_runbooks": (set(), {"query": None, "limit": 10}),
    "get_case_runbook": ({"id"}, {}),
    "record_triage_decision": (
        {"alert_id", "disposition", "confidence"},
        {
            "reasoning_bullets": None,
            "recommended_actions": None,
            "recommended_case_runbook_id": None,
            "suggested_status": None,
            "suggested_priority": None,
            "suggested_assignee": None,
            "suggested_tags_add": None,
            "suggested_tags_remove": None,
            "request_escalate_to_case": False,
            "commit": False,
        },
    ),
    "describe_timeline_item": ({"target_kind"}, {"item_type": None}),
    "finish_timeline_attachment": ({"target_kind", "target_id", "item_id", "status"}, {"file_hash": None}),
    "add_timeline_item": (
        {"target_kind", "target_id", "item_id"},
        {"body": None, "commit": False, "created_at": None, "migration": False, "item_type": "note", "fields": None},
    ),
    "get_item": (
        {"parent_entity_type", "parent_entity_id", "item_id"},
        {"mode": "full", "max_chars": 16000, "cursor": None, "content_format": "text"},
    ),
    "validate_mermaid": ({"diagram"}, {}),
}

_READ_ONLY_TOOLS = {
    "describe_timeline_item",
    "search", "search_queue", "get_triage_recommendation", "find_observable_occurrences",
    "get_summary",
    "list_work",
    "find_related",
    "search_case_runbooks",
    "get_case_runbook",
    "get_item",
    "validate_mermaid",
}


@pytest.mark.asyncio
async def test_registered_tools_match_public_mcp_contract() -> None:
    tools = await mcp.list_tools()

    assert {tool.name for tool in tools} == set(_TOOL_CONTRACTS)
    assert {
        tool.name
        for tool in tools
        if tool.annotations and tool.annotations.read_only_hint
    } == _READ_ONLY_TOOLS


@pytest.mark.asyncio
async def test_registered_tool_input_schemas_match_function_contracts() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    for name, (required_fields, defaults) in _TOOL_CONTRACTS.items():
        schema = tools[name].parameters
        properties = schema["properties"]

        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert set(schema.get("required", [])) == required_fields
        assert set(properties) == required_fields | defaults.keys()
        assert {
            field_name: field_schema["default"]
            for field_name, field_schema in properties.items()
            if "default" in field_schema
        } == defaults


@pytest.mark.asyncio
async def test_registered_tools_publish_descriptions_and_object_outputs() -> None:
    tools = await mcp.list_tools()

    for tool in tools:
        assert tool.description and tool.description.strip()
        assert all(
            property_schema.get("description", "").strip()
            for property_schema in tool.parameters["properties"].values()
        )
        if tool.name in {"search", "get_triage_recommendation", "reject_triage_recommendation"}:
            assert tool.output_schema["type"] == "object"
            assert tool.output_schema["properties"]
        else:
            assert tool.output_schema == {"type": "object", "additionalProperties": True}
