"""Verify typed MCP discovery, validation, placement, and task retry behavior."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

from fastmcp.exceptions import ToolError
import pytest
from sqlmodel import select

from app.mcp import timeline_tools, tools
from app.mcp.server import mcp
from app.models.enums import AccountType, UserRole
from app.models.models import Actor, Alert, Case, ProcessTreeNode, Task


pytestmark = pytest.mark.asyncio


@pytest.fixture
def analyst(session_maker, monkeypatch):
    monkeypatch.setattr(timeline_tools, "async_session_factory", session_maker)
    monkeypatch.setattr(tools, "async_session_factory", session_maker)
    user = SimpleNamespace(id=uuid4(), username="analyst", role=UserRole.ANALYST)
    monkeypatch.setattr(tools, "get_current_mcp_principal", lambda: SimpleNamespace(user=user))
    return user


async def call(name, **arguments):
    result = await mcp.call_tool(name, arguments)
    return result.structured_content


async def test_describe_exposes_target_specific_types_and_disallows_server_fields():
    for kind, count in {"case": 18, "alert": 15, "task": 15}.items():
        discovery = await call("describe_timeline_item", target_kind=kind)
        types = {entry["item_type"] for entry in discovery["item_types"]}
        assert len(types) == count
        assert "deleted" not in types
        assert "process_tree" in types
        assert ("task" in types) == (kind == "case")

    description = await call("describe_timeline_item", target_kind="case", item_type="observable")
    fields = description["fields"]
    assert fields["required"] == ["observable_type", "observable_value"]
    assert "IP" in fields["$defs"]["ObservableType"]["enum"]
    assert "created_by" not in fields["properties"]
    assert "replies" not in fields["properties"]

    description = await call("describe_timeline_item", target_kind="case", item_type="process_tree")
    fields = description["fields"]
    assert fields["required"] == ["processes"]
    assert fields["properties"]["processes"]["items"]["$ref"] == "#/$defs/ProcessTreeNode"
    assert set(fields["$defs"]["ProcessTreeNode"]["required"]) == {"id", "process_name", "process_id"}


async def test_preview_is_read_only_and_replies_require_stored_parent(analyst, session_maker):
    async with session_maker() as db:
        case = Case(title="Typed timeline", created_by="analyst")
        db.add(case)
        await db.flush()
        case_id = case.id
        await db.commit()

    args = {"target_kind": "case", "target_id": str(case_id)}
    actor = {
        **args, "item_id": "actor", "item_type": "internal_actor",
        "fields": {"user_id": "authoring@example.com"},
    }
    preview = await call("add_timeline_item", **actor)
    assert preview["mode"] == "dry_run"
    assert preview["side_effects"]
    async with session_maker() as db:
        assert (await db.execute(select(Actor))).scalars().all() == []
        assert (await db.get(Case, case_id)).timeline_items == {}

    reply = {
        **args, "item_id": "reply", "body": "I reviewed this event",
        "fields": {"parent_id": "actor"}, "commit": True,
    }
    with pytest.raises(ToolError, match="Parent timeline item"):
        await call("add_timeline_item", **reply)
    committed = await call("add_timeline_item", **actor, commit=True)
    assert committed["item_id"] == "actor"
    assert (await call("add_timeline_item", **reply))["mode"] == "committed"
    content = await call(
        "get_item", parent_entity_type="case", parent_entity_id=str(case_id), item_id="reply",
    )
    assert content["content"] == "I reviewed this event"
    async with session_maker() as db:
        saved = await db.get(Case, case_id)
        assert saved.timeline_items["actor"]["actor_id"]
        assert saved.timeline_items["actor"]["replies"]["reply"]["created_by"] == "analyst"


async def test_case_task_retry_returns_one_canonical_link_and_blocks_note_collision(analyst, session_maker):
    async with session_maker() as db:
        case = Case(title="Task parent", created_by="analyst")
        db.add(case)
        await db.flush()
        case_id = case.id
        await db.commit()

    args = {"target_kind": "case", "target_id": str(case_id), "item_id": "same-client-key"}
    task = {**args, "item_type": "task", "fields": {"title": "Review evidence"}}
    results = await asyncio.gather(
        call("add_timeline_item", **task, commit=True),
        call("add_timeline_item", **task, commit=True),
    )
    assert {result["mode"] for result in results} == {"committed", "already_exists"}
    assert len({result["item_id"] for result in results}) == 1
    assert results[0]["item_id"] == f"linked-task-{results[0]['task_id']}"
    assert results[0]["task_human_id"].startswith("TSK-")
    item = await call(
        "get_item", parent_entity_type="case", parent_entity_id=str(case_id),
        item_id=results[0]["item_id"], content_format="json",
    )
    assert "Review evidence" in item["content"]
    assert (await call("add_timeline_item", **task))["mode"] == "already_exists"
    with pytest.raises(ToolError, match="another timeline"):
        await call("add_timeline_item", **args, body="Collision with task receipt")
    async with session_maker() as db:
        saved_tasks = (await db.execute(select(Task).where(Task.case_id == case_id))).scalars().all()
        assert len(saved_tasks) == 1
        assert saved_tasks[0].id == results[0]["task_id"]


@pytest.mark.parametrize(
    "item_type",
    sorted(timeline_tools._TYPES["case"].keys() - {"attachment", "task"}),
)
async def test_ordinary_types_preview_commit_and_read_back(analyst, session_maker, item_type):
    async with session_maker() as db:
        target = Case(title="Destination", created_by="analyst")
        related_case = Case(title="Related case", created_by="analyst")
        related_alert = Alert(title="Related alert")
        db.add_all([target, related_case, related_alert])
        await db.flush()
        target_id = str(target.id)
        referenced_ids = {"alert": related_alert.id, "case": related_case.id}
        await db.commit()

    description = await call("describe_timeline_item", target_kind="case", item_type=item_type)
    fields = description["example"].copy()
    if item_type in referenced_ids:
        fields[f"{item_type}_id"] = referenced_ids[item_type]
    args = {
        "target_kind": "case", "target_id": target_id, "item_id": "typed-item",
        "item_type": item_type, "fields": fields,
    }
    preview = await call("add_timeline_item", **args)
    assert preview["mode"] == "dry_run"
    expected_fields = fields
    if item_type == "process_tree":
        expected_fields = {
            **fields,
            "processes": [ProcessTreeNode.model_validate(node).model_dump(mode="json") for node in fields["processes"]],
        }
    assert preview["fields"] == expected_fields
    committed = await call("add_timeline_item", **args, commit=True)
    assert committed["mode"] == "committed"
    persisted = await call(
        "get_item", parent_entity_type="case", parent_entity_id=target_id,
        item_id=committed["item_id"], content_format="json",
    )
    saved = json.loads(persisted["content"])
    assert saved["id"] == "typed-item"
    assert saved["type"] == item_type
    assert saved["created_by"] == "analyst"
    if item_type == "process_tree":
        assert saved["hostname"] == fields["hostname"]
        assert [(node["id"], node["parent_id"]) for node in saved["processes"]] == [
            ("desktop", None), ("report", "desktop"),
        ]


@pytest.mark.parametrize("kind", ["alert", "task"])
async def test_alert_and_task_preview_matrix_and_legacy_defaults(analyst, session_maker, kind):
    async with session_maker() as db:
        entity = Alert(title="Alert") if kind == "alert" else Task(title="Task", created_by="analyst")
        db.add(entity)
        await db.flush()
        entity_id = str(entity.id)
        await db.commit()

    args = {"target_kind": kind, "target_id": entity_id, "item_id": "client-preview"}
    assert (await call("add_timeline_item", **args, body="Legacy note"))["mode"] == "dry_run"
    for item_type in timeline_tools._TYPES[kind]:
        if item_type in {"case", "attachment"}:
            continue
        description = await call("describe_timeline_item", target_kind=kind, item_type=item_type)
        result = await call("add_timeline_item", **args, item_type=item_type, fields=description["example"])
        assert result["mode"] == "dry_run"
    for item_type in ("task", "alert", "forensic_artifact"):
        with pytest.raises(ToolError, match="cannot be added"):
            await call("add_timeline_item", **args, item_type=item_type)


async def test_typed_migration_override_requires_authorized_nhi_and_timezone(analyst, session_maker):
    async with session_maker() as db:
        case = Case(title="Import history", created_by="analyst")
        db.add(case)
        await db.flush()
        entity_id = str(case.id)
        await db.commit()

    analyst.account_type = AccountType.HUMAN
    analyst.override_timestamps = False
    args = {
        "target_kind": "case", "target_id": entity_id, "item_id": "old-host",
        "item_type": "system", "fields": {"hostname": "example.test"},
        "commit": True, "migration": True,
    }
    with pytest.raises(ToolError, match="require an NHI"):
        await call("add_timeline_item", **args, created_at="2024-01-02T03:04:05+10:00")
    analyst.account_type = AccountType.NHI
    analyst.override_timestamps = True
    with pytest.raises(ToolError, match="timezone"):
        await call("add_timeline_item", **args, created_at="2024-01-02T03:04:05")
    response = await call("add_timeline_item", **args, created_at="2024-01-02T03:04:05+10:00")
    assert response["mode"] == "committed"
    async with session_maker() as db:
        saved = (await db.get(Case, int(entity_id))).timeline_items["old-host"]
        assert saved["created_at"] == "2024-01-01T17:04:05+00:00"
        assert saved["timestamp"] != saved["created_at"]
