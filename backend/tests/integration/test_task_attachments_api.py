from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.services.attachment_settings_service import AttachmentLimits
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
) -> tuple[str, str]:
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
    return session_cookie, user.username


async def _create_task(client: AsyncClient, session_cookie: str) -> int:
    response = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Attachment test task",
            "description": "Task used for attachment API tests",
        },
        cookies={"intercept_session": session_cookie},
    )
    assert response.status_code == 200
    return response.json()["id"]


def _patch_task_attachment_keys(monkeypatch: pytest.MonkeyPatch, task_id: int) -> None:
    monkeypatch.setattr(
        storage_service,
        "generate_storage_key",
        lambda parent_id, item_id, filename, parent_type="alerts": f"{parent_type}/{parent_id}/attachments/{item_id}/{filename}",
    )
    monkeypatch.setattr(
        storage_service,
        "generate_upload_storage_key",
        lambda parent_id, item_id, parent_type="alerts": f"_uploads/{parent_type}/{parent_id}/attachments/{item_id}/upload",
    )


async def _create_uploading_attachment(
    client: AsyncClient,
    task_id: int,
    session_cookie: str,
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/tasks/{task_id}/timeline/attachments/upload-url",
        json={
            "filename": "report.txt",
            "file_size": 128,
            "mime_type": "text/plain",
        },
        cookies={"intercept_session": session_cookie},
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_generate_task_attachment_upload_url_creates_uploading_timeline_item(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie, username = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)

    monkeypatch.setattr(
        storage_service,
        "generate_storage_key",
        lambda parent_id, item_id, filename, parent_type="alerts": f"{parent_type}/{parent_id}/attachments/{item_id}/{filename}",
    )
    monkeypatch.setattr(
        storage_service,
        "generate_upload_storage_key",
        lambda parent_id, item_id, parent_type="alerts": f"_uploads/{parent_type}/{parent_id}/attachments/{item_id}/upload",
    )

    async def fake_generate_presigned_upload_url(storage_key: str, *, expires_minutes: int) -> str:
        assert storage_key.startswith(f"_uploads/tasks/{task_id}/")
        assert expires_minutes > 0
        return "https://uploads.example.test/presigned"

    monkeypatch.setattr(storage_service, "generate_presigned_upload_url", fake_generate_presigned_upload_url)

    response = await client.post(
        f"/api/v1/tasks/{task_id}/timeline/attachments/upload-url",
        json={
            "filename": "report.txt",
            "file_size": 128,
            "mime_type": "text/plain",
            "description": "Collected from the affected endpoint",
            "timestamp": "2026-07-12T14:30:00Z",
            "tags": ["evidence", "endpoint"],
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["upload_url"] == "https://uploads.example.test/presigned"
    assert body["storage_key"].startswith(f"_uploads/tasks/{task_id}/")

    task_response = await client.get(
        f"/api/v1/tasks/{task_id}",
        cookies={"intercept_session": session_cookie},
    )

    assert task_response.status_code == 200
    task_body = task_response.json()
    attachment = next(item for item in _timeline_values(task_body["timeline_items"]) if item["id"] == body["item_id"])
    assert attachment["type"] == "attachment"
    assert attachment["upload_status"] == "UPLOADING"
    assert attachment["file_name"] == "report.txt"
    assert attachment["storage_key"].startswith(f"tasks/{task_id}/")
    assert attachment["upload_storage_key"] == body["storage_key"]
    assert attachment["uploaded_by"] == username
    assert attachment["description"] == "Collected from the affected endpoint"
    assert datetime.fromisoformat(attachment["timestamp"].replace("Z", "+00:00")) == datetime(
        2026, 7, 12, 14, 30, tzinfo=timezone.utc
    )
    assert attachment["tags"] == ["evidence", "endpoint"]


@pytest.mark.asyncio
async def test_presigned_url_failure_does_not_create_orphan_attachment(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie, _username = await _login_and_get_session_cookie(
        client,
        session_maker,
        analyst_user_factory,
    )
    task_id = await _create_task(client, session_cookie)
    _patch_task_attachment_keys(monkeypatch, task_id)

    async def fail_generate_presigned_upload_url(
        _storage_key: str,
        *,
        expires_minutes: int,
    ) -> str:
        assert expires_minutes > 0
        raise RuntimeError("sensitive storage failure")

    monkeypatch.setattr(
        storage_service,
        "generate_presigned_upload_url",
        fail_generate_presigned_upload_url,
    )

    response = await client.post(
        f"/api/v1/tasks/{task_id}/timeline/attachments/upload-url",
        json={
            "filename": "report.txt",
            "file_size": 128,
            "mime_type": "text/plain",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to generate upload URL"

    task_response = await client.get(
        f"/api/v1/tasks/{task_id}",
        cookies={"intercept_session": session_cookie},
    )
    assert task_response.status_code == 200
    assert not any(
        item.get("type") == "attachment"
        for item in _timeline_values(task_response.json()["timeline_items"])
    )


@pytest.mark.asyncio
async def test_complete_task_attachment_upload_updates_status_and_hash(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie, _username = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)

    monkeypatch.setattr(
        storage_service,
        "generate_storage_key",
        lambda parent_id, item_id, filename, parent_type="alerts": f"{parent_type}/{parent_id}/attachments/{item_id}/{filename}",
    )
    monkeypatch.setattr(
        storage_service,
        "generate_upload_storage_key",
        lambda parent_id, item_id, parent_type="alerts": f"_uploads/{parent_type}/{parent_id}/attachments/{item_id}/upload",
    )

    async def fake_generate_presigned_upload_url(_storage_key: str, *, expires_minutes: int) -> str:
        assert expires_minutes > 0
        return "https://uploads.example.test/presigned"

    async def fake_verify_file_exists(storage_key: str) -> bool:
        return storage_key.startswith((f"_uploads/tasks/{task_id}/", f"tasks/{task_id}/"))

    expected_hash = hashlib.sha256(b"attachment bytes").hexdigest()
    copied: list[tuple[str, str]] = []

    async def fake_get_object_metadata(storage_key: str, *, require_checksum: bool = False) -> ObjectMetadata:
        assert storage_key.startswith((f"_uploads/tasks/{task_id}/", f"tasks/{task_id}/"))
        return ObjectMetadata(
            size=128,
            content_type="text/plain",
            sha256=expected_hash if require_checksum else None,
        )

    async def fake_copy_object(source_key: str, destination_key: str) -> None:
        copied.append((source_key, destination_key))

    async def fake_get_object_bytes(*_args: Any, **_kwargs: Any) -> bytes:
        raise AssertionError("completion must not fetch the full object to hash it")

    async def fake_detect_mime_type(_storage_key: str) -> str:
        return "text/plain"

    async def fake_delete_file(_storage_key: str) -> None:
        return None

    monkeypatch.setattr(storage_service, "generate_presigned_upload_url", fake_generate_presigned_upload_url)
    monkeypatch.setattr(storage_service, "verify_file_exists", fake_verify_file_exists)
    monkeypatch.setattr(storage_service, "get_object_metadata", fake_get_object_metadata)
    monkeypatch.setattr(storage_service, "copy_object", fake_copy_object)
    monkeypatch.setattr(storage_service, "get_object_bytes", fake_get_object_bytes)
    monkeypatch.setattr(storage_service, "detect_mime_type", fake_detect_mime_type)
    monkeypatch.setattr(storage_service, "delete_file", fake_delete_file)

    upload_response = await client.post(
        f"/api/v1/tasks/{task_id}/timeline/attachments/upload-url",
        json={
            "filename": "report.txt",
            "file_size": 128,
            "mime_type": "text/plain",
        },
        cookies={"intercept_session": session_cookie},
    )
    assert upload_response.status_code == 200
    item_id = upload_response.json()["item_id"]

    status_response = await client.patch(
        f"/api/v1/tasks/{task_id}/timeline/items/{item_id}/status",
        json={
            "status": "COMPLETE",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert status_response.status_code == 200
    task_body = status_response.json()
    attachment = next(item for item in _timeline_values(task_body["timeline_items"]) if item["id"] == item_id)
    assert attachment["upload_status"] == "COMPLETE"
    assert attachment["file_hash"] == expected_hash
    assert attachment.get("upload_storage_key") is None
    assert copied == [(upload_response.json()["storage_key"], attachment["storage_key"])]

    original_storage_metadata = {
        key: attachment.get(key)
        for key in (
            "file_name",
            "mime_type",
            "file_size",
            "storage_key",
            "file_hash",
            "uploaded_by",
            "uploaded_by_user_id",
            "upload_status",
        )
    }
    edit_response = await client.put(
        f"/api/v1/tasks/{task_id}/timeline/{item_id}",
        json={
            "id": item_id,
            "type": "attachment",
            "description": "Updated analyst context",
            "timestamp": "2026-07-13T09:45:00Z",
            "tags": ["evidence", "reviewed"],
            # Server-owned fields must be ignored rather than overwritten.
            "storage_key": "tasks/999/attachments/attacker-controlled/file.txt",
            "upload_status": "FAILED",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert edit_response.status_code == 200, edit_response.text
    edited_attachment = next(
        item
        for item in _timeline_values(edit_response.json()["timeline_items"])
        if item["id"] == item_id
    )
    assert edited_attachment["description"] == "Updated analyst context"
    assert datetime.fromisoformat(edited_attachment["timestamp"].replace("Z", "+00:00")) == datetime(
        2026, 7, 13, 9, 45, tzinfo=timezone.utc
    )
    assert edited_attachment["tags"] == ["evidence", "reviewed"]
    assert {
        key: edited_attachment.get(key)
        for key in original_storage_metadata
    } == original_storage_metadata

    async def fake_generate_presigned_download_url(
        storage_key: str,
        *,
        expires_minutes: int,
        filename: str | None = None,
        as_attachment: bool = False,
    ) -> str:
        assert storage_key == edited_attachment["storage_key"]
        assert storage_key != upload_response.json()["storage_key"]
        assert expires_minutes > 0
        assert filename == "report.txt"
        assert as_attachment is False
        return "https://downloads.example.test/presigned"

    monkeypatch.setattr(storage_service, "generate_presigned_download_url", fake_generate_presigned_download_url)

    download_response = await client.get(
        f"/api/v1/tasks/{task_id}/timeline/items/{item_id}/download-url",
        cookies={"intercept_session": session_cookie},
    )

    assert download_response.status_code == 200
    assert download_response.json()["download_url"] == "https://downloads.example.test/presigned"


@pytest.mark.asyncio
async def test_failed_attachment_commit_keeps_staged_object_and_uploading_status(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie, _username = await _login_and_get_session_cookie(
        client,
        session_maker,
        analyst_user_factory,
    )
    task_id = await _create_task(client, session_cookie)
    _patch_task_attachment_keys(monkeypatch, task_id)
    expected_hash = hashlib.sha256(b"attachment bytes").hexdigest()
    deleted: list[str] = []

    async def fake_generate_presigned_upload_url(
        _storage_key: str,
        *,
        expires_minutes: int,
    ) -> str:
        assert expires_minutes > 0
        return "https://uploads.example.test/presigned"

    async def fake_verify_file_exists(_storage_key: str) -> bool:
        return True

    async def fake_get_object_metadata(
        _storage_key: str,
        *,
        require_checksum: bool = False,
    ) -> ObjectMetadata:
        return ObjectMetadata(
            size=128,
            content_type="text/plain",
            sha256=expected_hash if require_checksum else None,
        )

    async def fake_copy_object(_source_key: str, _destination_key: str) -> None:
        return None

    async def fake_detect_mime_type(_storage_key: str) -> str:
        return "text/plain"

    async def fake_delete_file(storage_key: str) -> None:
        deleted.append(storage_key)

    monkeypatch.setattr(
        storage_service,
        "generate_presigned_upload_url",
        fake_generate_presigned_upload_url,
    )
    monkeypatch.setattr(storage_service, "verify_file_exists", fake_verify_file_exists)
    monkeypatch.setattr(storage_service, "get_object_metadata", fake_get_object_metadata)
    monkeypatch.setattr(storage_service, "copy_object", fake_copy_object)
    monkeypatch.setattr(storage_service, "detect_mime_type", fake_detect_mime_type)
    monkeypatch.setattr(storage_service, "delete_file", fake_delete_file)

    upload_body = await _create_uploading_attachment(client, task_id, session_cookie)
    staged_storage_key = upload_body["storage_key"]
    monkeypatch.setattr(
        "app.services.timeline_add_service.emit_event",
        AsyncMock(side_effect=RuntimeError("sensitive event-store failure")),
    )

    status_response = await client.patch(
        f"/api/v1/tasks/{task_id}/timeline/items/{upload_body['item_id']}/status",
        json={"status": "COMPLETE"},
        cookies={"intercept_session": session_cookie},
    )

    assert status_response.status_code == 500
    assert status_response.json()["detail"] == "Failed to update attachment status"
    assert staged_storage_key not in deleted

    task_response = await client.get(
        f"/api/v1/tasks/{task_id}",
        cookies={"intercept_session": session_cookie},
    )
    assert task_response.status_code == 200
    attachment = next(
        item
        for item in _timeline_values(task_response.json()["timeline_items"])
        if item["id"] == upload_body["item_id"]
    )
    assert attachment["upload_status"] == "UPLOADING"
    assert attachment["upload_storage_key"] == staged_storage_key


@pytest.mark.asyncio
async def test_other_analyst_can_download_completed_task_attachment(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploader_cookie, uploader_username = await _login_and_get_session_cookie(
        client, session_maker, analyst_user_factory
    )
    downloader_cookie, downloader_username = await _login_and_get_session_cookie(
        client, session_maker, analyst_user_factory
    )
    assert downloader_username != uploader_username
    task_id = await _create_task(client, uploader_cookie)
    _patch_task_attachment_keys(monkeypatch, task_id)

    async def fake_generate_presigned_upload_url(_storage_key: str, *, expires_minutes: int) -> str:
        assert expires_minutes > 0
        return "https://uploads.example.test/presigned"

    async def fake_verify_file_exists(storage_key: str) -> bool:
        return storage_key.startswith((f"_uploads/tasks/{task_id}/", f"tasks/{task_id}/"))

    expected_hash = hashlib.sha256(b"attachment bytes").hexdigest()

    async def fake_get_object_metadata(storage_key: str, *, require_checksum: bool = False) -> ObjectMetadata:
        assert storage_key.startswith((f"_uploads/tasks/{task_id}/", f"tasks/{task_id}/"))
        return ObjectMetadata(
            size=128,
            content_type="text/plain",
            sha256=expected_hash if require_checksum else None,
        )

    async def fake_copy_object(_source_key: str, _destination_key: str) -> None:
        return None

    async def fake_detect_mime_type(_storage_key: str) -> str:
        return "text/plain"

    async def fake_delete_file(_storage_key: str) -> None:
        return None

    monkeypatch.setattr(storage_service, "generate_presigned_upload_url", fake_generate_presigned_upload_url)
    monkeypatch.setattr(storage_service, "verify_file_exists", fake_verify_file_exists)
    monkeypatch.setattr(storage_service, "get_object_metadata", fake_get_object_metadata)
    monkeypatch.setattr(storage_service, "copy_object", fake_copy_object)
    monkeypatch.setattr(storage_service, "detect_mime_type", fake_detect_mime_type)
    monkeypatch.setattr(storage_service, "delete_file", fake_delete_file)

    upload_response = await _create_uploading_attachment(client, task_id, uploader_cookie)
    item_id = upload_response["item_id"]

    status_response = await client.patch(
        f"/api/v1/tasks/{task_id}/timeline/items/{item_id}/status",
        json={"status": "COMPLETE"},
        cookies={"intercept_session": uploader_cookie},
    )
    assert status_response.status_code == 200
    attachment = next(
        item
        for item in _timeline_values(status_response.json()["timeline_items"])
        if item["id"] == item_id
    )
    assert attachment["uploaded_by"] == uploader_username

    async def fake_generate_presigned_download_url(
        storage_key: str,
        *,
        expires_minutes: int,
        filename: str | None = None,
        as_attachment: bool = False,
    ) -> str:
        assert storage_key == attachment["storage_key"]
        assert expires_minutes > 0
        assert filename == "report.txt"
        assert as_attachment is True
        return "https://downloads.example.test/other-analyst"

    monkeypatch.setattr(storage_service, "generate_presigned_download_url", fake_generate_presigned_download_url)

    download_response = await client.get(
        f"/api/v1/tasks/{task_id}/timeline/items/{item_id}/download-url",
        params={"download": True},
        cookies={"intercept_session": downloader_cookie},
    )

    assert download_response.status_code == 200
    assert download_response.json()["download_url"] == "https://downloads.example.test/other-analyst"


@pytest.mark.asyncio
async def test_complete_task_attachment_upload_rejects_staged_size_mismatch_before_copy(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie, _username = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    _patch_task_attachment_keys(monkeypatch, task_id)

    async def fake_generate_presigned_upload_url(_storage_key: str, *, expires_minutes: int) -> str:
        assert expires_minutes > 0
        return "https://uploads.example.test/presigned"

    async def fake_verify_file_exists(_storage_key: str) -> bool:
        return True

    async def fake_get_object_metadata(_storage_key: str, *, require_checksum: bool = False) -> ObjectMetadata:
        assert require_checksum is False
        return ObjectMetadata(size=129, content_type="text/plain", sha256=None)

    async def fake_copy_object(_source_key: str, _destination_key: str) -> None:
        raise AssertionError("size mismatch must be rejected before copy")

    async def fake_detect_mime_type(_storage_key: str) -> str:
        raise AssertionError("size mismatch must be rejected before MIME detection")

    monkeypatch.setattr(storage_service, "generate_presigned_upload_url", fake_generate_presigned_upload_url)
    monkeypatch.setattr(storage_service, "verify_file_exists", fake_verify_file_exists)
    monkeypatch.setattr(storage_service, "get_object_metadata", fake_get_object_metadata)
    monkeypatch.setattr(storage_service, "copy_object", fake_copy_object)
    monkeypatch.setattr(storage_service, "detect_mime_type", fake_detect_mime_type)

    upload_body = await _create_uploading_attachment(client, task_id, session_cookie)

    status_response = await client.patch(
        f"/api/v1/tasks/{task_id}/timeline/items/{upload_body['item_id']}/status",
        json={"status": "COMPLETE"},
        cookies={"intercept_session": session_cookie},
    )

    assert status_response.status_code == 409
    assert status_response.json()["detail"] == "Uploaded file size does not match the expected size"


@pytest.mark.asyncio
async def test_complete_task_attachment_upload_rejects_oversized_staged_object_before_copy(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie, _username = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    _patch_task_attachment_keys(monkeypatch, task_id)

    async def fake_get_attachment_limits(_db: Any) -> AttachmentLimits:
        return AttachmentLimits(
            max_upload_size_mb=1,
            max_image_preview_size_mb=5,
            max_text_preview_size_mb=1,
            allowed_file_types=("text/plain",),
            denied_file_types=(),
        )

    async def fake_generate_presigned_upload_url(_storage_key: str, *, expires_minutes: int) -> str:
        assert expires_minutes > 0
        return "https://uploads.example.test/presigned"

    async def fake_verify_file_exists(_storage_key: str) -> bool:
        return True

    async def fake_get_object_metadata(_storage_key: str, *, require_checksum: bool = False) -> ObjectMetadata:
        assert require_checksum is False
        return ObjectMetadata(size=2 * 1024 * 1024, content_type="text/plain", sha256=None)

    async def fake_copy_object(_source_key: str, _destination_key: str) -> None:
        raise AssertionError("oversized staged object must be rejected before copy")

    async def fake_detect_mime_type(_storage_key: str) -> str:
        raise AssertionError("oversized staged object must be rejected before MIME detection")

    monkeypatch.setattr(
        "app.services.attachment_settings_service.get_attachment_limits",
        fake_get_attachment_limits,
    )
    monkeypatch.setattr(storage_service, "generate_presigned_upload_url", fake_generate_presigned_upload_url)
    monkeypatch.setattr(storage_service, "verify_file_exists", fake_verify_file_exists)
    monkeypatch.setattr(storage_service, "get_object_metadata", fake_get_object_metadata)
    monkeypatch.setattr(storage_service, "copy_object", fake_copy_object)
    monkeypatch.setattr(storage_service, "detect_mime_type", fake_detect_mime_type)

    upload_body = await _create_uploading_attachment(client, task_id, session_cookie)

    status_response = await client.patch(
        f"/api/v1/tasks/{task_id}/timeline/items/{upload_body['item_id']}/status",
        json={"status": "COMPLETE"},
        cookies={"intercept_session": session_cookie},
    )

    assert status_response.status_code == 413
    assert status_response.json()["detail"] == "Uploaded file size 2097152 exceeds limit 1MB"


@pytest.mark.asyncio
async def test_complete_task_attachment_upload_rejects_missing_final_checksum_and_cleans_up(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie, _username = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    _patch_task_attachment_keys(monkeypatch, task_id)
    deleted: list[str] = []

    async def fake_generate_presigned_upload_url(_storage_key: str, *, expires_minutes: int) -> str:
        assert expires_minutes > 0
        return "https://uploads.example.test/presigned"

    async def fake_verify_file_exists(_storage_key: str) -> bool:
        return True

    async def fake_get_object_metadata(storage_key: str, *, require_checksum: bool = False) -> ObjectMetadata:
        return ObjectMetadata(
            size=128,
            content_type="text/plain",
            sha256=None if require_checksum else None,
        )

    async def fake_copy_object(_source_key: str, _destination_key: str) -> None:
        return None

    async def fake_detect_mime_type(_storage_key: str) -> str:
        raise AssertionError("missing checksum must be rejected before MIME detection")

    async def fake_delete_file(storage_key: str) -> None:
        deleted.append(storage_key)

    monkeypatch.setattr(storage_service, "generate_presigned_upload_url", fake_generate_presigned_upload_url)
    monkeypatch.setattr(storage_service, "verify_file_exists", fake_verify_file_exists)
    monkeypatch.setattr(storage_service, "get_object_metadata", fake_get_object_metadata)
    monkeypatch.setattr(storage_service, "copy_object", fake_copy_object)
    monkeypatch.setattr(storage_service, "detect_mime_type", fake_detect_mime_type)
    monkeypatch.setattr(storage_service, "delete_file", fake_delete_file)

    upload_body = await _create_uploading_attachment(client, task_id, session_cookie)

    status_response = await client.patch(
        f"/api/v1/tasks/{task_id}/timeline/items/{upload_body['item_id']}/status",
        json={"status": "COMPLETE"},
        cookies={"intercept_session": session_cookie},
    )

    assert status_response.status_code == 409
    assert status_response.json()["detail"] == "Storage did not return a SHA256 checksum for the finalized file"
    assert deleted == [f"tasks/{task_id}/attachments/{upload_body['item_id']}/report.txt"]


@pytest.mark.asyncio
async def test_complete_task_attachment_upload_rejects_mime_mismatch_and_cleans_up(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie, _username = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)
    _patch_task_attachment_keys(monkeypatch, task_id)
    expected_hash = hashlib.sha256(b"attachment bytes").hexdigest()
    deleted: list[str] = []

    async def fake_generate_presigned_upload_url(_storage_key: str, *, expires_minutes: int) -> str:
        assert expires_minutes > 0
        return "https://uploads.example.test/presigned"

    async def fake_verify_file_exists(_storage_key: str) -> bool:
        return True

    async def fake_get_object_metadata(_storage_key: str, *, require_checksum: bool = False) -> ObjectMetadata:
        return ObjectMetadata(
            size=128,
            content_type="text/plain",
            sha256=expected_hash if require_checksum else None,
        )

    async def fake_copy_object(_source_key: str, _destination_key: str) -> None:
        return None

    async def fake_detect_mime_type(_storage_key: str) -> str:
        return "application/pdf"

    async def fake_delete_file(storage_key: str) -> None:
        deleted.append(storage_key)

    monkeypatch.setattr(storage_service, "generate_presigned_upload_url", fake_generate_presigned_upload_url)
    monkeypatch.setattr(storage_service, "verify_file_exists", fake_verify_file_exists)
    monkeypatch.setattr(storage_service, "get_object_metadata", fake_get_object_metadata)
    monkeypatch.setattr(storage_service, "copy_object", fake_copy_object)
    monkeypatch.setattr(storage_service, "detect_mime_type", fake_detect_mime_type)
    monkeypatch.setattr(storage_service, "delete_file", fake_delete_file)

    upload_body = await _create_uploading_attachment(client, task_id, session_cookie)

    status_response = await client.patch(
        f"/api/v1/tasks/{task_id}/timeline/items/{upload_body['item_id']}/status",
        json={"status": "COMPLETE"},
        cookies={"intercept_session": session_cookie},
    )

    assert status_response.status_code == 415
    assert status_response.json()["detail"] == "Uploaded file content type does not match the declared MIME type"
    assert deleted == [f"tasks/{task_id}/attachments/{upload_body['item_id']}/report.txt"]


@pytest.mark.asyncio
async def test_complete_task_attachment_upload_rejects_missing_storage_file(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie, _username = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    task_id = await _create_task(client, session_cookie)

    monkeypatch.setattr(
        storage_service,
        "generate_storage_key",
        lambda parent_id, item_id, filename, parent_type="alerts": f"{parent_type}/{parent_id}/attachments/{item_id}/{filename}",
    )
    monkeypatch.setattr(
        storage_service,
        "generate_upload_storage_key",
        lambda parent_id, item_id, parent_type="alerts": f"_uploads/{parent_type}/{parent_id}/attachments/{item_id}/upload",
    )

    async def fake_generate_presigned_upload_url(_storage_key: str, *, expires_minutes: int) -> str:
        assert expires_minutes > 0
        return "https://uploads.example.test/presigned"

    async def fake_verify_file_exists(_storage_key: str) -> bool:
        return False

    monkeypatch.setattr(storage_service, "generate_presigned_upload_url", fake_generate_presigned_upload_url)
    monkeypatch.setattr(storage_service, "verify_file_exists", fake_verify_file_exists)

    upload_response = await client.post(
        f"/api/v1/tasks/{task_id}/timeline/attachments/upload-url",
        json={
            "filename": "report.txt",
            "file_size": 128,
            "mime_type": "text/plain",
        },
        cookies={"intercept_session": session_cookie},
    )
    assert upload_response.status_code == 200
    item_id = upload_response.json()["item_id"]

    status_response = await client.patch(
        f"/api/v1/tasks/{task_id}/timeline/items/{item_id}/status",
        json={"status": "COMPLETE"},
        cookies={"intercept_session": session_cookie},
    )

    assert status_response.status_code == 409
    assert status_response.json()["detail"] == "File not found in storage"
