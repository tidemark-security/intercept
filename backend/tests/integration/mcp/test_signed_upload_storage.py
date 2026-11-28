"""Live signed PUT and verified finalization against a disposable S3-compatible store.

Set MCP_TEST_LIVE_STORAGE=1 and configure STORAGE_* for the test store.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from uuid import uuid4

import httpx
import pytest
from fastmcp.exceptions import ToolError

from app.mcp import attachment_tools, timeline_tools
from app.mcp.principal import MCPPrincipal, _current_principal
from app.mcp.server import mcp
from app.models.models import Case
from app.services.storage_service import storage_service

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("MCP_TEST_LIVE_STORAGE") != "1", reason="requires a disposable object store"),
]


async def test_signed_case_email_upload_and_replay(session_maker, analyst_user_factory, monkeypatch):
    for module in (timeline_tools, attachment_tools):
        monkeypatch.setattr(module, "async_session_factory", session_maker)
    async with session_maker() as db:
        user = analyst_user_factory()
        other = analyst_user_factory(username="storage-reviewer", email="storage-reviewer@example.org")
        case = Case(title="Email evidence", created_by=user.username)
        db.add_all([user, other, case])
        await db.commit()
        case_id = case.id

    def bind(analyst):
        return _current_principal.set(MCPPrincipal(analyst, "test", "test-client", frozenset({"mcp:access"})))

    message = (
        b"From: Sample Sender <sender@example.org>\r\nTo: Analyst <analyst@example.org>\r\n"
        b"Date: Wed, 04 Nov 2026 12:00:00 +0000\r\nMessage-ID: <evidence@example.org>\r\n"
        b"Subject: Evidence for timeline test\r\nMIME-Version: 1.0\r\n"
        b"Content-Type: text/plain; charset=UTF-8\r\n\r\nA sample message for the case.\r\n"
    )
    args = {
        "target_kind": "case", "target_id": str(case_id), "item_id": str(uuid4()),
        "item_type": "attachment", "fields": {
            "filename": "evidence.eml", "file_size": len(message), "mime_type": "message/rfc822",
        },
    }
    owner = bind(user)
    try:
        preview = (await mcp.call_tool("add_timeline_item", args)).structured_content
        assert not preview.get("upload_url")

        # Issue one real signature with a past start time so the storage server
        # exercises expiry and renewal without waiting for its normal timeout.
        def issue_expired_url(bucket, key, expires):
            return storage_service.client.get_presigned_url(
                "PUT", bucket, key, expires=expires,
                request_date=datetime.now(timezone.utc) - expires - timedelta(minutes=10),
            )

        with monkeypatch.context() as patch:
            patch.setattr(storage_service.client, "presigned_put_object", issue_expired_url)
            expired = (await mcp.call_tool("add_timeline_item", {**args, "commit": True})).structured_content
        async with httpx.AsyncClient(trust_env=False) as client:
            assert (await client.put(expired["upload_url"], content=message)).status_code == 403

        first, retry = await asyncio.gather(*[
            mcp.call_tool("add_timeline_item", {**args, "commit": True}) for _ in range(2)
        ])
        upload = first.structured_content
        assert retry.structured_content["item_id"] == upload["item_id"] == expired["item_id"]
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.put(upload["upload_url"], content=message)
            assert response.is_success, response.status_code

        finish = {"target_kind": "case", "target_id": str(case_id), "item_id": upload["item_id"], "status": "COMPLETE"}
        foreign_token = bind(other)
        try:
            with pytest.raises(ToolError, match="owner"):
                await mcp.call_tool("finish_timeline_attachment", finish)
        finally:
            _current_principal.reset(foreign_token)
        with pytest.raises(ToolError, match="hash"):
            await mcp.call_tool("finish_timeline_attachment", {**finish, "file_hash": "a" * 64})
        for _ in range(2):
            await mcp.call_tool("finish_timeline_attachment", {**finish, "file_hash": sha256(message).hexdigest()})

        async with session_maker() as db:
            case = await db.get(Case, case_id)
            items = list(case.timeline_items.values())
            assert sorted(row["type"] for row in items) == ["attachment", "email"]
            attachment = next(item for item in items if item["type"] == "attachment")
            assert attachment["upload_status"] == "COMPLETE"
            assert attachment["file_hash"] == sha256(message).hexdigest()
            assert await storage_service.get_object_bytes(attachment["storage_key"], max_bytes=len(message)) == message
            await storage_service.delete_file(attachment["storage_key"])
    finally:
        _current_principal.reset(owner)
