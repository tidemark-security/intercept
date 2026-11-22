"""MCP-specific retries and upload ownership on the shared attachment lifecycle."""

import asyncio

import pytest
from fastmcp.exceptions import ToolError

from app.mcp import attachment_tools
from app.models.models import Case, TimelineAuthoringReceipt
from app.models.search_schemas import EntityType
from app.services.storage_service import storage_service
from tests.integration.test_attachment_lifecycle_api import FILE_BYTES, FILE_HASH, _FakeStorage


@pytest.mark.asyncio
async def test_attachment_init_and_completion_replay(
    session_maker, analyst_user_factory, monkeypatch,
):
    storage = _FakeStorage()
    storage.install(monkeypatch)
    owner = analyst_user_factory()
    other_user = analyst_user_factory()
    monkeypatch.setattr(attachment_tools, "async_session_factory", session_maker)
    current_user = owner
    monkeypatch.setattr(attachment_tools, "_require_mcp_non_auditor_user_object", lambda: current_user)
    signed_keys = []

    async def sign(key, *, expires_minutes):
        signed_keys.append(key)
        return f"https://uploads.example.test/token-{len(signed_keys)}"

    monkeypatch.setattr(storage_service, "generate_presigned_upload_url", sign)

    async with session_maker() as db:
        case = Case(title="MCP upload", created_by=owner.username)
        db.add(case)
        await db.commit()
        case_id = case.id

    client_item_id = "client-upload-1"
    request = {
        "target_kind": EntityType.CASE,
        "target_id": str(case_id),
        "item_id": client_item_id,
        "fields": {"filename": "notes.txt", "file_size": len(FILE_BYTES), "mime_type": "text/plain"},
    }
    preview = await attachment_tools.add_timeline_attachment(**request, commit=False)
    assert preview["mode"] == "dry_run"
    assert "upload_url" not in preview
    assert signed_keys == []

    started, retried = await asyncio.gather(
        attachment_tools.add_timeline_attachment(**request, commit=True),
        attachment_tools.add_timeline_attachment(**request, commit=True),
    )
    attachment_id = started["item_id"]
    assert attachment_id != client_item_id
    assert retried["item_id"] == attachment_id
    assert sorted([started["created"], retried["created"]]) == [False, True]
    assert started["upload_url"] != retried["upload_url"]
    assert len(signed_keys) == 2 and signed_keys[0] == signed_keys[1]

    async with session_maker() as db:
        receipt = await db.get(TimelineAuthoringReceipt, ("case", case_id, client_item_id))
        assert receipt.item_id == attachment_id
        assert receipt.owner_id == owner.id

    finish = {
        "target_kind": EntityType.CASE,
        "target_id": str(case_id),
        "item_id": attachment_id,
        "status": "COMPLETE",
        "file_hash": FILE_HASH,
    }
    current_user = other_user
    with pytest.raises(ToolError, match="belongs to another"):
        await attachment_tools.add_timeline_attachment(**request, commit=True)
    with pytest.raises(ToolError, match="Only upload owner"):
        await attachment_tools.finish_timeline_attachment(**finish)
    assert storage.copies == []

    current_user = owner
    completed, replayed = await asyncio.gather(
        attachment_tools.finish_timeline_attachment(**finish),
        attachment_tools.finish_timeline_attachment(**finish),
    )
    assert completed == replayed
    assert completed["upload_status"] == "COMPLETE"
    assert completed["file_hash"] == FILE_HASH
    assert len(storage.copies) == 1
    assert storage.deletes == signed_keys[:1]

    terminal = await attachment_tools.add_timeline_attachment(**request, commit=True)
    assert terminal["item_id"] == attachment_id
    assert terminal["upload_status"] == "COMPLETE"
    assert "upload_url" not in terminal

    failed = await attachment_tools.add_timeline_attachment(
        **{**request, "item_id": "client-upload-abandoned"}, commit=True,
    )
    fail = {**finish, "item_id": failed["item_id"], "status": "FAILED", "file_hash": None}
    ended = await attachment_tools.finish_timeline_attachment(**fail)
    assert ended == await attachment_tools.finish_timeline_attachment(**fail)
    assert ended["upload_status"] == "FAILED"
    assert storage.deletes == [signed_keys[0], signed_keys[-1]]
    assert len(storage.copies) == 1


@pytest.mark.asyncio
async def test_attachment_completion_replays_without_duplicate_email_companion(
    session_maker, analyst_user_factory, monkeypatch,
):
    from tests.integration.test_case_attachments_api import _stub_attachment_storage

    owner = analyst_user_factory()
    monkeypatch.setattr(attachment_tools, "async_session_factory", session_maker)
    monkeypatch.setattr(attachment_tools, "_require_mcp_non_auditor_user_object", lambda: owner)
    async with session_maker() as db:
        case = Case(title="MCP email evidence", created_by=owner.username)
        db.add(case)
        await db.commit()
        case_id = case.id

    email = (
        b"From: Evidence <evidence@example.com>\r\n"
        b"To: Security <security@example.com>\r\n"
        b"Subject: Case evidence\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Original email body.\r\n"
    )
    file_hash = _stub_attachment_storage(
        monkeypatch, case_id=case_id, attachment_bytes=email, detected_mime_type="message/rfc822",
    )
    started = await attachment_tools.add_timeline_attachment(
        target_kind=EntityType.CASE, target_id=str(case_id), item_id="message-1",
        fields={"filename": "message.eml", "file_size": len(email), "mime_type": "message/rfc822"},
        commit=True,
    )
    finish = {
        "target_kind": EntityType.CASE,
        "target_id": str(case_id),
        "item_id": started["item_id"],
        "status": "COMPLETE",
        "file_hash": file_hash,
    }
    completed, replayed = await asyncio.gather(
        attachment_tools.finish_timeline_attachment(**finish),
        attachment_tools.finish_timeline_attachment(**finish),
    )
    assert completed == replayed

    async with session_maker() as db:
        stored_case = await db.get(Case, case_id)
        assert sorted(item["type"] for item in stored_case.timeline_items.values()) == ["attachment", "email"]
