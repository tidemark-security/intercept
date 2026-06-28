from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient

from app.services.storage_service import ObjectMetadata, storage_service
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


def _timeline_values(items: Any) -> list[dict[str, Any]]:
    if isinstance(items, dict):
        return [item for item in items.values() if isinstance(item, dict)]
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


async def _login_and_get_session_cookie(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> str:
    user = analyst_user_factory()

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200

    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    return session_cookie


async def _create_case(client: AsyncClient, session_cookie: str) -> int:
    response = await client.post(
        "/api/v1/cases",
        json={
            "title": "Email evidence case",
            "description": "Case used for email attachment tests",
        },
        cookies={"intercept_session": session_cookie},
    )
    assert response.status_code == 200
    return response.json()["id"]


def _stub_attachment_storage(
    monkeypatch: pytest.MonkeyPatch,
    *,
    case_id: int,
    attachment_bytes: bytes,
    detected_mime_type: str,
) -> str:
    expected_hash = hashlib.sha256(attachment_bytes).hexdigest()

    monkeypatch.setattr(
        storage_service,
        "generate_storage_key",
        lambda parent_id, item_id, filename, parent_type="alerts": (
            f"{parent_type}/{parent_id}/attachments/{item_id}/{filename}"
        ),
    )
    monkeypatch.setattr(
        storage_service,
        "generate_upload_storage_key",
        lambda parent_id, item_id, parent_type="alerts": (
            f"_uploads/{parent_type}/{parent_id}/attachments/{item_id}/upload"
        ),
    )

    async def fake_generate_presigned_upload_url(_storage_key: str, *, expires_minutes: int) -> str:
        assert expires_minutes > 0
        return "https://uploads.example.test/presigned"

    async def fake_verify_file_exists(storage_key: str) -> bool:
        return storage_key.startswith((f"_uploads/cases/{case_id}/", f"cases/{case_id}/"))

    async def fake_get_object_metadata(
        storage_key: str,
        *,
        require_checksum: bool = False,
    ) -> ObjectMetadata:
        assert storage_key.startswith((f"_uploads/cases/{case_id}/", f"cases/{case_id}/"))
        return ObjectMetadata(
            size=len(attachment_bytes),
            content_type=detected_mime_type,
            sha256=expected_hash if require_checksum else None,
        )

    async def fake_copy_object(_source_key: str, _destination_key: str) -> None:
        return None

    async def fake_detect_mime_type(_storage_key: str) -> str:
        return detected_mime_type

    async def fake_get_object_bytes(
        storage_key: str,
        *,
        max_bytes: int | None = None,
    ) -> bytes:
        assert storage_key.startswith(f"cases/{case_id}/")
        assert max_bytes == len(attachment_bytes)
        return attachment_bytes

    async def fake_delete_file(_storage_key: str) -> None:
        return None

    monkeypatch.setattr(
        storage_service,
        "generate_presigned_upload_url",
        fake_generate_presigned_upload_url,
    )
    monkeypatch.setattr(storage_service, "verify_file_exists", fake_verify_file_exists)
    monkeypatch.setattr(storage_service, "get_object_metadata", fake_get_object_metadata)
    monkeypatch.setattr(storage_service, "copy_object", fake_copy_object)
    monkeypatch.setattr(storage_service, "detect_mime_type", fake_detect_mime_type)
    monkeypatch.setattr(storage_service, "get_object_bytes", fake_get_object_bytes)
    monkeypatch.setattr(storage_service, "delete_file", fake_delete_file)

    return expected_hash


@pytest.mark.asyncio
async def test_complete_case_eml_attachment_creates_email_timeline_item(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie = await _login_and_get_session_cookie(
        client,
        session_maker,
        analyst_user_factory,
    )
    case_id = await _create_case(client, session_cookie)
    email_bytes = (
        b"From: Attacker <attacker@evil.example>\r\n"
        b"To: Victim <victim@corp.example>\r\n"
        b"Subject: Urgent reset\r\n"
        b"Message-ID: <abc123@evil.example>\r\n"
        b"Date: Fri, 20 Jun 2026 10:15:00 +0000\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Click the link immediately.\r\n"
    )
    expected_hash = _stub_attachment_storage(
        monkeypatch,
        case_id=case_id,
        attachment_bytes=email_bytes,
        detected_mime_type="message/rfc822",
    )

    upload_response = await client.post(
        f"/api/v1/cases/{case_id}/timeline/attachments/upload-url",
        json={
            "filename": "message.eml",
            "file_size": len(email_bytes),
            "mime_type": "message/rfc822",
        },
        cookies={"intercept_session": session_cookie},
    )
    assert upload_response.status_code == 200, upload_response.text
    item_id = upload_response.json()["item_id"]

    status_response = await client.patch(
        f"/api/v1/cases/{case_id}/timeline/items/{item_id}/status",
        json={"status": "COMPLETE"},
        cookies={"intercept_session": session_cookie},
    )

    assert status_response.status_code == 200, status_response.text
    items = _timeline_values(status_response.json()["timeline_items"])
    attachment = next(item for item in items if item["id"] == item_id)
    email_item = next(item for item in items if item["type"] == "email")

    assert attachment["type"] == "attachment"
    assert attachment["upload_status"] == "COMPLETE"
    assert attachment["file_hash"] == expected_hash
    assert email_item["sender"] == "Attacker <attacker@evil.example>"
    assert email_item["recipient"] == "Victim <victim@corp.example>"
    assert email_item["subject"] == "Urgent reset"
    assert email_item["message_id"] == "<abc123@evil.example>"
    assert email_item["description"] == "Click the link immediately."


@pytest.mark.asyncio
async def test_complete_case_msg_attachment_creates_email_timeline_item(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie = await _login_and_get_session_cookie(
        client,
        session_maker,
        analyst_user_factory,
    )
    case_id = await _create_case(client, session_cookie)
    msg_bytes = b"msg bytes"
    expected_hash = _stub_attachment_storage(
        monkeypatch,
        case_id=case_id,
        attachment_bytes=msg_bytes,
        detected_mime_type="application/vnd.ms-outlook",
    )

    class FakeMessage:
        def __init__(self, path: str) -> None:
            assert Path(path).read_bytes() == msg_bytes
            self.sender = "Attacker <attacker@evil.example>"
            self.to = "Victim <victim@corp.example>"
            self.cc = "SOC <soc@corp.example>"
            self.subject = "Urgent reset\x00"
            self.messageId = "<abc123@evil.example>"
            self.date = datetime(2026, 6, 20, 10, 15, tzinfo=timezone.utc)
            self.body = None
            self.htmlBody = b"<p>Click the link immediately.</p>\x00"

        def close(self) -> None:
            return None

    monkeypatch.setitem(sys.modules, "extract_msg", SimpleNamespace(Message=FakeMessage))

    upload_response = await client.post(
        f"/api/v1/cases/{case_id}/timeline/attachments/upload-url",
        json={
            "filename": "message.msg",
            "file_size": len(msg_bytes),
            "mime_type": "application/vnd.ms-outlook",
        },
        cookies={"intercept_session": session_cookie},
    )
    assert upload_response.status_code == 200, upload_response.text
    item_id = upload_response.json()["item_id"]

    status_response = await client.patch(
        f"/api/v1/cases/{case_id}/timeline/items/{item_id}/status",
        json={"status": "COMPLETE"},
        cookies={"intercept_session": session_cookie},
    )

    assert status_response.status_code == 200, status_response.text
    items = _timeline_values(status_response.json()["timeline_items"])
    attachment = next(item for item in items if item["id"] == item_id)
    email_item = next(item for item in items if item["type"] == "email")

    assert attachment["type"] == "attachment"
    assert attachment["upload_status"] == "COMPLETE"
    assert attachment["file_hash"] == expected_hash
    assert email_item["sender"] == "Attacker <attacker@evil.example>"
    assert email_item["recipient"] == "Victim <victim@corp.example>, SOC <soc@corp.example>"
    assert email_item["subject"] == "Urgent reset"
    assert email_item["message_id"] == "<abc123@evil.example>"
    assert email_item["description"] == "Click the link immediately."
