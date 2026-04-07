from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.services.storage_service import storage_service
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
        lambda parent_id, item_id, filename, parent_type="alerts": f"{parent_type}/{parent_id}/{item_id}/{filename}",
    )

    async def fake_generate_presigned_upload_url(storage_key: str, *, expires_minutes: int) -> str:
        assert storage_key.startswith(f"tasks/{task_id}/")
        assert expires_minutes > 0
        return "https://uploads.example.test/presigned"

    monkeypatch.setattr(storage_service, "generate_presigned_upload_url", fake_generate_presigned_upload_url)

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
    body = response.json()
    assert body["upload_url"] == "https://uploads.example.test/presigned"
    assert body["storage_key"].startswith(f"tasks/{task_id}/")

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
    assert attachment["storage_key"] == body["storage_key"]
    assert attachment["uploaded_by"] == username


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
        lambda parent_id, item_id, filename, parent_type="alerts": f"{parent_type}/{parent_id}/{item_id}/{filename}",
    )

    async def fake_generate_presigned_upload_url(_storage_key: str, *, expires_minutes: int) -> str:
        assert expires_minutes > 0
        return "https://uploads.example.test/presigned"

    async def fake_verify_file_exists(storage_key: str) -> bool:
        return storage_key.startswith(f"tasks/{task_id}/")

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
        json={
            "status": "COMPLETE",
            "file_hash": "abc123",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert status_response.status_code == 200
    task_body = status_response.json()
    attachment = next(item for item in _timeline_values(task_body["timeline_items"]) if item["id"] == item_id)
    assert attachment["upload_status"] == "COMPLETE"
    assert attachment["file_hash"] == "abc123"


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
        lambda parent_id, item_id, filename, parent_type="alerts": f"{parent_type}/{parent_id}/{item_id}/{filename}",
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