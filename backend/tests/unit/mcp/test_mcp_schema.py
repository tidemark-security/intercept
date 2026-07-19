"""Contract tests for the explicitly registered MCP tools."""

from __future__ import annotations

from typing import Any

import pytest

from app.main import mcp


_TOOL_CONTRACTS: dict[str, tuple[set[str], dict[str, Any]]] = {
    "get_summary": (
        {"kind", "id"},
        {"max_timeline_items": 25, "max_observables": 20, "since": None},
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
    "find_related": ({"seed_kind", "seed_id"}, {"max_matches": 10}),
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
    "add_timeline_item": (
        {"target_kind", "target_id", "item_id", "body"},
        {"commit": False, "created_at": None, "migration": False},
    ),
    "get_item": (
        {"parent_entity_type", "parent_entity_id", "item_id"},
        {"mode": "full", "max_chars": 4000, "cursor": None},
    ),
    "validate_mermaid": ({"diagram"}, {}),
}

_READ_ONLY_TOOLS = {
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
        if getattr(tool.annotations, "readOnlyHint", False)
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
        assert tool.output_schema == {"type": "object", "additionalProperties": True}
