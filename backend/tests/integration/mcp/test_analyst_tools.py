"""Exercise analyst workflows through the tool names and payloads available to clients."""

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from fastmcp.exceptions import ToolError
import pytest
from sqlalchemy import text

from app.mcp import search_tools, tools, workflow_tools
from app.mcp.server import mcp
from app.core.entity_ids import ALERT_PREFIX, TASK_PREFIX, format_entity_id
from app.models.enums import AlertStatus, TaskStatus, UserRole
from app.models.models import Alert, Case, Task
from app.services import triage_recommendation_service


pytestmark = pytest.mark.asyncio


@pytest.fixture
def analyst_tools(session_maker, monkeypatch):
    for module in (tools, search_tools, workflow_tools):
        monkeypatch.setattr(module, "async_session_factory", session_maker)
    user = SimpleNamespace(username="analyst", role=UserRole.ANALYST)
    monkeypatch.setattr(tools, "get_current_mcp_principal", lambda: SimpleNamespace(user=user))
    return user


async def call(name, **arguments):
    result = await mcp.call_tool(name, arguments)
    return result.structured_content


async def test_search_and_pivot_across_multiple_items_and_legacy_shapes(analyst_tools, session_maker):
    now = datetime.now(timezone.utc)
    value = "192.0.2.7"
    async with session_maker() as db:
        await db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        for table in ("alerts", "cases", "tasks"):
            await db.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS search_vector tsvector"))
        alert = Alert(title="Alert A", timeline_items={
            "one": {"id": "one", "type": "system", "ip_address": value, "replies": {
                "reply": {"id": "reply", "type": "observable", "observable_type": "IP", "observable_value": value}}},
            "two": {"id": "two", "type": "network_traffic", "source_ip": value, "destination_ip": value},
            "near": {"id": "near", "type": "system", "ip_address": value + "0"},
        })
        historical = Case(title="Imported", created_by="analyst", created_at=now - timedelta(days=90))
        db.add_all([alert, historical])
        await db.flush()
        # Simulate a pre-migration array in storage.
        await db.execute(text("UPDATE cases SET timeline_items=CAST(:items AS jsonb) WHERE id=:id"), {
            "id": historical.id, "items": json.dumps([{"id": "legacy", "type": "observable",
                                                       "observable_type": "IP", "value": value}]),
        })
        await db.commit()

    ranked = await call("search", query=value, entity_types=["alert"])
    assert ranked["total"] == 1
    assert ranked["date_range"]["start"] and ranked["date_range"]["end"]
    queue = await call("search_queue", query=value, kind="alert", statuses=["NEW"])
    assert queue["total"] == 1 and queue["date_range"] == {"start": None, "end": None}
    assert (await call("list_work", contains=value, kind="alert"))["total_count"] == 1

    args = {"observable_type": "IP", "value": value}
    hits = await call("find_observable_occurrences", **args)
    assert {row["item_id"]: row["matched_fields"] for row in hits["items"]} == {
        "one": ["ip_address"], "two": ["destination_ip", "source_ip"], "reply": ["observable_value"],
    }
    page = await call("find_observable_occurrences", **args, all_time=True, limit=1, skip=3)
    assert page["total"] == 4 and page["items"][0]["item_id"] == "legacy"
    assert page["items"][0]["matched_fields"] == ["value"]
    empty = await call("find_observable_occurrences", **args, all_time=True, skip=4)
    assert empty["total"] == 4 and empty["items"] == []
    scoped = await call("find_observable_occurrences", **args, end_date=(now - timedelta(days=80)).isoformat())
    assert [row["item_id"] for row in scoped["items"]] == ["legacy"]
    for row in hits["items"]:
        item = await call("get_item", **{k: row[k] for k in ("item_id", "parent_entity_type", "parent_entity_id")},
                          content_format="json")
        assert json.loads(item["content"])["id"] == row["item_id"]
    with pytest.raises(ToolError, match="All time cannot"):
        await call("search", query=value, all_time=True, start_date=now.isoformat())


async def test_status_and_manual_escalation_use_persisted_entity_flows(analyst_tools, session_maker):
    async with session_maker() as db:
        alert = Alert(title="Suspicious sign-in")
        task = Task(title="Check logs", created_by="analyst")
        db.add_all([alert, task])
        await db.commit()
    assert (await call("set_status", kind="task", id=str(task.id), status="DONE"))["status"] == "TODO"
    for kind, entity_id, status in (("task", task.id, "DONE"), ("alert", alert.id, "IN_PROGRESS")):
        assert (await call("set_status", kind=kind, id=str(entity_id), status=status, commit=True))["status"] == status
    args = {"alert_id": str(alert.id), "case_title": "Sign-in investigation"}
    assert (await call("escalate_alert_to_case", **args))["case_id"] is None
    created = await call("escalate_alert_to_case", **args, commit=True)
    assert created["status"] == "ESCALATED" and created["case_human_id"].startswith("CAS-")
    with pytest.raises(ToolError, match="already escalated"):
        await call("escalate_alert_to_case", **args, commit=True)
    assert (await call("set_status", kind="case", id=created["case_human_id"], status="CLOSED", commit=True))["status"] == "CLOSED"
    async with session_maker() as db:
        assert (await db.get(Alert, alert.id)).status == "CLOSED_UNRESOLVED"
    with pytest.raises(ToolError, match="Invalid task status"):
        await call("set_status", kind="task", id=str(task.id), status="NEW", commit=True)


async def test_review_checks_revision_and_returns_case_or_rejection(analyst_tools, session_maker):
    async with session_maker() as db:
        alert = Alert(title="x" * 500)
        db.add(alert)
        await db.commit()
    args = {"alert_id": str(alert.id)}
    proposal = {**args, "confidence": 0.8, "commit": True, "disposition": "NEEDS_INVESTIGATION",
                "recommended_actions": [{"title": "Collect logs"}]}
    await call("record_triage_decision", **proposal)
    original = await call("get_triage_recommendation", **args)
    await call("record_triage_decision", **proposal)
    for name, extra in [("accept_triage_recommendation", {}), ("reject_triage_recommendation", {"category": "OTHER", "reason": "Duplicate"})]:
        with pytest.raises(ToolError, match="Recommendation changed"):
            await call(name, **args, **extra, expected_created_at=original["created_at"])
    current = await call("get_triage_recommendation", **args)
    with pytest.raises(ToolError, match="Reason is required"):
        await call("reject_triage_recommendation", **args, expected_created_at=current["created_at"], category="OTHER")
    rejected = await call("reject_triage_recommendation", **args, expected_created_at=current["created_at"],
                          category="MISSING_CONTEXT")
    assert rejected["status"] == "REJECTED" and rejected["reviewed_by"] == "analyst"
    await call("record_triage_decision", **proposal)
    current = await call("get_triage_recommendation", **args)
    accepted = await call("accept_triage_recommendation", **args, expected_created_at=current["created_at"])
    assert accepted["recommendation"]["status"] == "ACCEPTED"
    assert accepted["case_id"] and accepted["tasks_created"] == 1
    with pytest.raises(ToolError, match="already ACCEPTED"):
        await call("accept_triage_recommendation", **args, expected_created_at=current["created_at"])


@pytest.mark.parametrize(("name", "arguments"), [
    ("set_status", {"kind": "task", "id": "1", "status": "DONE", "commit": True}),
    ("escalate_alert_to_case", {"alert_id": "1", "commit": True}),
    ("accept_triage_recommendation", {"alert_id": "1", "expected_created_at": "2026-01-01"}),
    ("reject_triage_recommendation", {"alert_id": "1", "expected_created_at": "2026-01-01", "category": "OTHER"}),
])
async def test_auditors_cannot_commit_analyst_operations(analyst_tools, name, arguments):
    analyst_tools.role = UserRole.AUDITOR
    with pytest.raises(ToolError, match="read-only"):
        await call(name, **arguments)


async def test_context_pages_preserve_long_text_empty_fields_and_order(analyst_tools, session_maker):
    note = "Study " * 5000
    async with session_maker() as db:
        alert = Alert(title="Investigation", description="Entity context", timeline_items={
            "old": {"id": "old", "type": "note", "timestamp": "2026-11-01T08:30:00+10:00",
                    "description": "Earlier event"},
            "new": {"id": "new", "type": "note", "timestamp": "2026-11-01T00:00:00Z", "description": note},
        })
        db.add(alert)
        await db.commit()
    summary_args = {"kind": "alert", "id": str(alert.id), "max_timeline_items": 1}
    first = await call("get_summary", **summary_args)
    assert first["header"]["description"] == "Entity context" and first["header"]["assignee"] is None
    assert len(first["timeline"]["items"][0]["preview"]) == 1024
    assert first["timeline"]["items"][0]["timeline_id"] == "new"
    second = await call("get_summary", **summary_args, timeline_offset=first["timeline"]["next_offset"])
    assert second["timeline"]["items"][0]["timeline_id"] == "old" and second["timeline"]["next_offset"] is None
    item_args = {"parent_entity_type": "alert", "parent_entity_id": str(alert.id), "item_id": "new"}
    head = await call("get_item", **item_args)
    assert len(head["content"]) == 16000 and head["is_truncated"]
    rest = await call("get_item", **item_args, cursor=head["next_cursor"])
    assert head["content"] + rest["content"] == note
    tail = await call("get_item", **item_args, mode="tail")
    assert tail["is_truncated"] and tail["next_cursor"] is None and tail["full_length_chars"] == len(note)


async def test_similar_alerts_respect_candidate_creation_window(analyst_tools, session_maker):
    now = datetime.now(timezone.utc)
    async with session_maker() as db:
        seed, old, recent = [
            Alert(title="Indicator match", source="sensor", created_at=now - timedelta(days=days))
            for days in (1, 60, 3)
        ]
        db.add_all([seed, old, recent])
        await db.commit()
    args = {"seed_kind": "alert", "seed_id": str(seed.id)}
    result = await call("find_related", **args)
    assert result["date_range"] == {"start": None, "end": None}
    assert {row["id"] for row in result["matches"]} == {old.id, recent.id}
    assert "reason" not in result and "next_tool" not in result
    historical = await call("find_related", **args, end_date=(now - timedelta(days=30)).isoformat())
    assert [row["id"] for row in historical["matches"]] == [old.id]


async def test_ioc_candidates_are_rechecked_and_follow_timeline_replacements(analyst_tools, session_maker):
    # Includes a short value with no usable trigram, mixed case, and literal SQL wildcard characters.
    async with session_maker() as db:
        case = Case(title="Occurrence edits", created_by="analyst", timeline_items={
            "one": {"id": "one", "type": "observable", "observable_type": "DOMAIN", "observable_value": "Ab"},
            "two": {"id": "two", "type": "link", "url": "https://example.org/%_Path"},
            "wrong-field": {"id": "wrong-field", "type": "note", "hostname": "Ab"},
            "enriched": {"id": "enriched", "type": "note", "enrichments": {
                "copy": {"id": "copied", "type": "system", "hostname": "Ab"}}},
        })
        db.add(case)
        await db.commit()

    async def items(kind, value):
        result = await call("find_observable_occurrences", observable_type=kind, value=value, all_time=True)
        return [row["item_id"] for row in result["items"]]

    assert await items("DOMAIN", "AB") == ["one"]
    assert await items("IP", "ab") == []
    assert await items("URL", "https://example.org/%_path") == ["two"]
    async with session_maker() as db:
        current = await db.get(Case, case.id)
        current.timeline_items = {"other": {"id": "other", "type": "system", "hostname": "Changed"}}
        await db.commit()
    assert await items("DOMAIN", "ab") == []
    assert await items("DOMAIN", "changed") == ["other"]

@pytest.mark.parametrize(("kind", "model"), [("case", Case), ("task", Task)])
async def test_find_related_unsupported_seed_points_to_ioc_pivot(analyst_tools, session_maker, kind, model):
    async with session_maker() as db:
        seed = model(title="Pivot seed", created_by="analyst")
        db.add(seed)
        await db.commit()

    result = await call("find_related", seed_kind=kind, seed_id=str(seed.id))
    assert result["seed"]["id"] == seed.id
    assert result["matches"] == []
    assert result["reason"] == "unsupported_seed_kind"
    assert result["next_tool"] == "find_observable_occurrences"


async def test_case_closure_preview_counts_and_bounds_open_linked_work(analyst_tools, session_maker):
    async with session_maker() as db:
        case = Case(title="Closure preview", created_by="analyst")
        db.add(case)
        await db.flush()
        db.add(Alert(title="Already closed", case_id=case.id, status=AlertStatus.CLOSED_FP))
        db.add(Task(title="Already done", case_id=case.id, created_by="analyst", status=TaskStatus.DONE))
        await db.flush()
        alerts = [Alert(title=f"Alert {i}", case_id=case.id) for i in range(21)]
        tasks = [Task(title=f"Task {i}", case_id=case.id, created_by="analyst") for i in range(22)]
        db.add_all(alerts + tasks)
        await db.commit()

    args = {"kind": "case", "id": str(case.id), "status": "CLOSED"}
    result = await call("set_status", **args)
    assert result["status"] == "NEW"
    assert result["closure_impact"] == {
        "alerts": {"count": 21, "human_ids": [format_entity_id(a.id, ALERT_PREFIX) for a in alerts[:20]]},
        "tasks": {"count": 22, "human_ids": [format_entity_id(t.id, TASK_PREFIX) for t in tasks[:20]]},
    }
    async with session_maker() as db:
        assert (await db.get(Alert, alerts[0].id)).status == AlertStatus.NEW
        assert (await db.get(Task, tasks[0].id)).status == TaskStatus.TODO
    await call("set_status", **args, commit=True)
    assert (await call("set_status", **args))["closure_impact"] == {
        "alerts": {"count": 0, "human_ids": []},
        "tasks": {"count": 0, "human_ids": []},
    }


@pytest.mark.parametrize(("apply_status", "linked", "disposition", "expected_status", "case_action"), [
    (True, False, "FALSE_POSITIVE", "CLOSED_FP", "none"),
    (False, False, "FALSE_POSITIVE", "ESCALATED", "create"),
    (False, True, "FALSE_POSITIVE", "ESCALATED", "reuse"),
    (True, True, "NEEDS_INVESTIGATION", "ESCALATED", "reuse"),
])
async def test_acceptance_preview_matches_commit(
    analyst_tools, session_maker, apply_status, linked, disposition, expected_status, case_action,
):
    async with session_maker() as db:
        case_id = None
        if linked:
            case = Case(title="Investigation", created_by="analyst")
            db.add(case)
            await db.flush()
            case_id = case.id
        alert = Alert(title="Review preview", case_id=case_id)
        db.add(alert)
        await db.commit()

    args = {"alert_id": str(alert.id)}
    await call("record_triage_decision", **args, confidence=0.8, commit=True, disposition=disposition)
    if disposition == "FALSE_POSITIVE":
        # Older dismissal recommendations could persist contradictory escalation settings.
        async with session_maker() as db:
            recommendation = await triage_recommendation_service.get_by_alert_id(db, alert.id)
            recommendation.request_escalate_to_case = True
            recommendation.suggested_status = AlertStatus.ESCALATED
            await db.commit()
    preview = await call("get_triage_recommendation", **args)
    outcomes = preview["acceptance_outcomes"]
    assert set(outcomes) == {"apply_status", "skip_status"}
    decision = outcomes["apply_status" if apply_status else "skip_status"]
    assert decision["alert_status"] == expected_status
    assert decision["case_action"] == case_action
    accepted = await call(
        "accept_triage_recommendation", **args, expected_created_at=preview["created_at"], apply_status=apply_status,
    )
    async with session_maker() as db:
        assert (await db.get(Alert, alert.id)).status == expected_status
    if case_action == "none":
        assert accepted["case_id"] is None
    elif case_action == "reuse":
        assert accepted["case_id"] == case_id
        assert accepted["case_human_id"] == decision["case_human_id"]
    else:
        assert accepted["case_id"] is not None


async def test_summary_enrichment_flag_only_removes_provider_payloads(analyst_tools, session_maker):
    async with session_maker() as db:
        alert = Alert(title="Enriched traffic", timeline_items={
            "new": {"id": "new", "type": "observable", "timestamp": "2026-11-01T00:00:00Z",
                    "observable_type": "IP", "observable_value": "192.0.2.7",
                    "enrichment_status": "complete", "enrichments": {"example": {"value": "data"}}},
            "old": {"id": "old", "type": "note", "timestamp": "2026-10-31T00:00:00Z", "body": "Earlier note"},
        })
        db.add(alert)
        await db.commit()

    args = {"kind": "alert", "id": str(alert.id), "max_timeline_items": 1}
    for offset in (0, 1):
        default = await call("get_summary", **args, timeline_offset=offset)
        explicit = await call("get_summary", **args, timeline_offset=offset, include_enrichments=True)
        without = await call("get_summary", **args, timeline_offset=offset, include_enrichments=False)
        assert default == explicit
        item = default["timeline"]["items"][0]
        if offset == 0:
            assert item["enrichment_status"] == "complete"
            assert item["enrichments"] == {"example": {"value": "data"}}
            assert default["timeline"]["next_offset"] == 1
        del item["enrichments"]
        assert without == default
