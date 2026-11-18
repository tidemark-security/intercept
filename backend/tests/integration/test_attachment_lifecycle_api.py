"""End-to-end attachment lifecycle across alerts, cases and tasks.

See docs/attachment-lifecycle.md. Each stage asserts the stored timeline item
(not the API response, which hides storage keys) so a regression that orphans
the file in object storage fails here even when the API still returns 200.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.models import Alert, Case, Task
from app.services.storage_service import ObjectMetadata, storage_service
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD

FILE_BYTES = b"attachment lifecycle regression\n"
FILE_HASH = hashlib.sha256(FILE_BYTES).hexdigest()

STORAGE_FIELDS = (
    "file_name",
    "mime_type",
    "file_size",
    "storage_key",
    "upload_storage_key",
    "file_hash",
    "uploaded_by",
    "uploaded_by_user_id",
    "upload_status",
)

ENTITIES: dict[str, dict[str, Any]] = {
    "alert": {
        "model": Alert,
        "create": {
            "title": "Attachment lifecycle alert",
            "description": "Alert used for attachment lifecycle tests",
            "priority": "MEDIUM",
            "source": "IntegrationTest",
        },
    },
    "case": {
        "model": Case,
        "create": {
            "title": "Attachment lifecycle case",
            "description": "Case used for attachment lifecycle tests",
        },
    },
    "task": {
        "model": Task,
        "create": {
            "title": "Attachment lifecycle task",
            "description": "Task used for attachment lifecycle tests",
        },
    },
}


def _timeline_values(items: Any) -> list[dict[str, Any]]:
    if isinstance(items, dict):
        return [item for item in items.values() if isinstance(item, dict)]
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


class _FakeStorage:
    """Records storage calls so tests can assert which object each stage touched."""

    def __init__(self) -> None:
        self.copies: list[tuple[str, str]] = []
        self.deletes: list[str] = []
        self.downloads: list[str] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
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

        async def generate_presigned_upload_url(_storage_key: str, *, expires_minutes: int) -> str:
            return "https://uploads.example.test/presigned"

        async def verify_file_exists(_storage_key: str) -> bool:
            return True

        async def get_object_metadata(_storage_key: str, *, require_checksum: bool = False) -> ObjectMetadata:
            return ObjectMetadata(
                size=len(FILE_BYTES),
                content_type="text/plain",
                sha256=FILE_HASH if require_checksum else None,
            )

        async def copy_object(source_key: str, destination_key: str) -> None:
            self.copies.append((source_key, destination_key))

        async def detect_mime_type(_storage_key: str) -> str:
            return "text/plain"

        async def delete_file(storage_key: str) -> None:
            self.deletes.append(storage_key)

        async def generate_presigned_download_url(storage_key: str, **_kwargs: Any) -> str:
            self.downloads.append(storage_key)
            return "https://downloads.example.test/presigned"

        monkeypatch.setattr(storage_service, "generate_presigned_upload_url", generate_presigned_upload_url)
        monkeypatch.setattr(storage_service, "verify_file_exists", verify_file_exists)
        monkeypatch.setattr(storage_service, "get_object_metadata", get_object_metadata)
        monkeypatch.setattr(storage_service, "copy_object", copy_object)
        monkeypatch.setattr(storage_service, "detect_mime_type", detect_mime_type)
        monkeypatch.setattr(storage_service, "delete_file", delete_file)
        monkeypatch.setattr(storage_service, "generate_presigned_download_url", generate_presigned_download_url)


class _AttachmentClient:
    def __init__(self, client: AsyncClient, session_maker: Any, entity_type: str, entity_id: int, cookie: str) -> None:
        self.client = client
        self.session_maker = session_maker
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.cookies = {"intercept_session": cookie}
        self.base = f"/api/v1/{entity_type}s/{entity_id}"

    async def stored_item(self, item_id: str) -> dict[str, Any] | None:
        async with self.session_maker() as session:
            entity = await session.get(ENTITIES[self.entity_type]["model"], self.entity_id)
            assert entity is not None
            return next(
                (item for item in _timeline_values(entity.timeline_items) if item["id"] == item_id),
                None,
            )

    async def edit_metadata(self, item_id: str, **changes: Any) -> Any:
        """Mirror the frontend edit: resend the cached item minus created_at/replies."""
        entity_response = await self.client.get(self.base, cookies=self.cookies)
        assert entity_response.status_code == 200, entity_response.text
        cached = next(
            item for item in _timeline_values(entity_response.json()["timeline_items"]) if item["id"] == item_id
        )
        payload = {key: value for key, value in cached.items() if key not in {"created_at", "replies"}}
        payload.update(changes)
        return await self.client.put(f"{self.base}/timeline/{item_id}", json=payload, cookies=self.cookies)

    async def set_status(self, item_id: str, status: str) -> Any:
        return await self.client.patch(
            f"{self.base}/timeline/items/{item_id}/status",
            json={"status": status},
            cookies=self.cookies,
        )

    async def download_url(self, item_id: str) -> Any:
        return await self.client.get(f"{self.base}/timeline/items/{item_id}/download-url", cookies=self.cookies)


async def _setup(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    entity_type: str,
) -> _AttachmentClient:
    user = analyst_user_factory()
    async with session_maker() as session:
        session.add(user)
        await session.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login.status_code == 200
    cookie = login.cookies.get("intercept_session")
    assert cookie is not None

    created = await client.post(
        f"/api/v1/{entity_type}s",
        json=ENTITIES[entity_type]["create"],
        cookies={"intercept_session": cookie},
    )
    assert created.status_code == 200, created.text
    return _AttachmentClient(client, session_maker, entity_type, created.json()["id"], cookie)


async def _start_upload(attachments: _AttachmentClient) -> str:
    response = await attachments.client.post(
        f"{attachments.base}/timeline/attachments/upload-url",
        json={
            "filename": "notes.txt",
            "file_size": len(FILE_BYTES),
            "mime_type": "text/plain",
            "description": "Uploaded description",
            "timestamp": "2026-10-20T09:00:00Z",
            "tags": ["uploaded"],
        },
        cookies=attachments.cookies,
    )
    assert response.status_code == 200, response.text
    return response.json()["item_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("entity_type", list(ENTITIES))
async def test_attachment_lifecycle_keeps_stored_file_through_metadata_edits(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
    entity_type: str,
) -> None:
    storage = _FakeStorage()
    storage.install(monkeypatch)
    attachments = await _setup(client, session_maker, analyst_user_factory, entity_type)
    entity_id = attachments.entity_id

    # 1. Upload URL: item is created UPLOADING with a final key and a staging key,
    #    and keeps the metadata supplied with the upload.
    item_id = await _start_upload(attachments)
    uploading = await attachments.stored_item(item_id)
    assert uploading is not None
    assert uploading["upload_status"] == "UPLOADING"
    assert uploading["storage_key"] == f"{entity_type}s/{entity_id}/attachments/{item_id}/notes.txt"
    assert uploading["upload_storage_key"] == f"_uploads/{entity_type}s/{entity_id}/attachments/{item_id}/upload"
    assert uploading["description"] == "Uploaded description"
    assert uploading["tags"] == ["uploaded"]
    assert uploading["timestamp"].startswith("2026-10-20T09:00:00")

    # 2. Downloads are refused until the upload is finalized.
    assert (await attachments.download_url(item_id)).status_code == 400

    # 3. A metadata edit mid-upload must not drop the keys finalization depends on.
    mid_edit = await attachments.edit_metadata(item_id, description="Edited mid-upload")
    assert mid_edit.status_code == 200, mid_edit.text
    after_mid_edit = await attachments.stored_item(item_id)
    assert after_mid_edit is not None
    assert after_mid_edit["description"] == "Edited mid-upload"
    for field in STORAGE_FIELDS:
        assert after_mid_edit.get(field) == uploading.get(field), field

    # 4. Finalization copies staging -> final, records the server hash and
    #    clears the staging key.
    complete = await attachments.set_status(item_id, "COMPLETE")
    assert complete.status_code == 200, complete.text
    finalized = await attachments.stored_item(item_id)
    assert finalized is not None
    assert finalized["upload_status"] == "COMPLETE"
    assert finalized["file_hash"] == FILE_HASH
    assert finalized.get("upload_storage_key") is None
    assert finalized["storage_key"] == uploading["storage_key"]
    assert storage.copies == [(uploading["upload_storage_key"], uploading["storage_key"])]
    assert storage.deletes == [uploading["upload_storage_key"]]

    # 5. A metadata edit after finalization updates metadata only, even when the
    #    client tries to rewrite file fields.
    edit = await attachments.edit_metadata(
        item_id,
        description="Edited description",
        tags=["uploaded", "edited"],
        timestamp="2026-10-26T11:51:00",
        file_name="renamed.exe",
        mime_type="application/x-msdownload",
        file_size=1,
        storage_key=None,
        upload_status="UPLOADING",
    )
    assert edit.status_code == 200, edit.text
    edited = await attachments.stored_item(item_id)
    assert edited is not None
    assert edited["description"] == "Edited description"
    assert edited["tags"] == ["uploaded", "edited"]
    assert edited["timestamp"].startswith("2026-10-26T11:51:00")
    assert edited["created_at"] == finalized["created_at"]
    for field in STORAGE_FIELDS:
        assert edited.get(field) == finalized.get(field), field

    # 6. Finalized uploads cannot transition again.
    assert (await attachments.set_status(item_id, "FAILED")).status_code == 400
    assert (await attachments.stored_item(item_id)) == edited

    # 7. Download resolves to the finalized object.
    download = await attachments.download_url(item_id)
    assert download.status_code == 200, download.text
    assert storage.downloads == [finalized["storage_key"]]

    # 8. Deleting the timeline item removes the finalized object.
    deleted = await client.delete(f"{attachments.base}/timeline/{item_id}", cookies=attachments.cookies)
    assert deleted.status_code == 200, deleted.text
    assert await attachments.stored_item(item_id) is None
    assert storage.deletes[-1] == finalized["storage_key"]


@pytest.mark.asyncio
async def test_failed_upload_keeps_keys_and_blocks_download(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    storage.install(monkeypatch)
    attachments = await _setup(client, session_maker, analyst_user_factory, "case")
    item_id = await _start_upload(attachments)
    uploading = await attachments.stored_item(item_id)
    assert uploading is not None

    failed = await attachments.set_status(item_id, "FAILED")
    assert failed.status_code == 200, failed.text

    stored = await attachments.stored_item(item_id)
    assert stored is not None
    assert stored["upload_status"] == "FAILED"
    assert stored["storage_key"] == uploading["storage_key"]
    assert stored["upload_storage_key"] == uploading["upload_storage_key"]
    assert storage.copies == []
    assert (await attachments.download_url(item_id)).status_code == 400
    assert (await attachments.set_status(item_id, "COMPLETE")).status_code == 400
