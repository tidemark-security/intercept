from __future__ import annotations

import base64
import hashlib
from typing import Any

import pytest

from app.models.models import PresignedUploadRequest
from app.services.storage_service import MIME_SNIFF_BYTES, StorageService, storage_service


def test_checksum_sha256_hex_accepts_base64_checksum() -> None:
    digest = hashlib.sha256(b"attachment bytes").digest()

    assert StorageService._checksum_sha256_hex(
        {"x-amz-checksum-sha256": base64.b64encode(digest).decode("ascii")}
    ) == digest.hex()


def test_checksum_sha256_hex_accepts_hex_checksum() -> None:
    expected = hashlib.sha256(b"attachment bytes").hexdigest()

    assert StorageService._checksum_sha256_hex({"x-amz-checksum-sha256": expected.upper()}) == expected


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"x-amz-checksum-sha256": "not-base64"},
        {"x-amz-checksum-sha256": base64.b64encode(b"too-short").decode("ascii")},
    ],
)
def test_checksum_sha256_hex_rejects_invalid_checksum(headers: dict[str, str]) -> None:
    assert StorageService._checksum_sha256_hex(headers) is None


ALLOWED_TYPES = (
    "message/rfc822",
    "application/vnd.ms-outlook",
    "application/zip",
    "application/x-7z-compressed",
    "text/html",
)
DENIED_TYPES = ("text/html", "application/x-7z-compressed")


@pytest.mark.parametrize(
    "mime_type",
    [
        "message/rfc822",
        "application/vnd.ms-outlook",
        "application/zip",
        "application/x-zip-compressed",
        "APPLICATION/X-ZIP-COMPRESSED",
    ],
)
def test_validate_file_type_allows_email_and_zip_aliases(mime_type: str) -> None:
    assert storage_service.validate_file_type(mime_type, ALLOWED_TYPES, DENIED_TYPES)


@pytest.mark.parametrize(
    "mime_type",
    [
        "text/html",  # denied even though allowed — deny wins
        "application/x-compressed",  # alias of denied application/x-7z-compressed
        "application/pdf",  # not in the allowed list
        "",
        None,
    ],
)
def test_validate_file_type_rejects_denied_and_unlisted_types(mime_type: str | None) -> None:
    assert not storage_service.validate_file_type(mime_type, ALLOWED_TYPES, DENIED_TYPES)


def test_normalize_mime_type_resolves_windows_zip_aliases() -> None:
    assert StorageService.normalize_mime_type("application/x-zip-compressed") == "application/zip"
    assert StorageService.normalize_mime_type("application/x-compressed") == "application/x-7z-compressed"
    assert StorageService.normalize_mime_type(" Message/RFC822 ") == "message/rfc822"
    assert StorageService.normalize_mime_type(None) == ""


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        (
            "Build an app in a fraction of the time. Here's where to start..eml",
            "Build an app in a fraction of the time. Here's where to start..eml",
        ),
        ("../../etc/passwd", "etcpasswd"),
        ("reports\\..\\evidence.msg", "reportsevidence.msg"),
        ('"\r\n\x00', "attachment"),
    ],
)
def test_sanitize_filename_preserves_extensions_without_path_components(
    filename: str,
    expected: str,
) -> None:
    assert StorageService.sanitize_filename(filename) == expected
    request = PresignedUploadRequest(
        filename=filename,
        file_size=1,
        mime_type="application/octet-stream",
    )
    assert request.filename == expected


@pytest.mark.asyncio
async def test_detect_mime_type_reads_bounded_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_object_bytes(storage_key: str, *, max_bytes: int | None = None) -> bytes:
        assert storage_key == "tasks/1/attachments/item/file.txt"
        assert max_bytes == MIME_SNIFF_BYTES
        return b"sample"

    async def fake_detect_mime_type_from_bytes(data: bytes) -> str:
        assert data == b"sample"
        return "text/plain"

    monkeypatch.setattr(storage_service, "get_object_bytes", fake_get_object_bytes)
    monkeypatch.setattr(storage_service, "detect_mime_type_from_bytes", fake_detect_mime_type_from_bytes)

    assert await storage_service.detect_mime_type("tasks/1/attachments/item/file.txt") == "text/plain"


@pytest.mark.asyncio
async def test_get_object_bytes_passes_length_to_minio() -> None:
    calls: list[dict[str, Any]] = []

    class FakeResponse:
        def read(self) -> bytes:
            return b"abc"

        def close(self) -> None:
            return None

        def release_conn(self) -> None:
            return None

    class FakeClient:
        def get_object(self, bucket_name: str, storage_key: str, **kwargs: Any) -> FakeResponse:
            calls.append(
                {
                    "bucket_name": bucket_name,
                    "storage_key": storage_key,
                    **kwargs,
                }
            )
            return FakeResponse()

    service = StorageService.__new__(StorageService)
    service.client = FakeClient()
    service.bucket_name = "test-bucket"

    assert await service.get_object_bytes("object-key", max_bytes=123) == b"abc"
    assert calls == [
        {
            "bucket_name": "test-bucket",
            "storage_key": "object-key",
            "offset": 0,
            "length": 123,
        }
    ]


@pytest.mark.asyncio
async def test_get_object_bytes_zero_limit_does_not_issue_unbounded_get() -> None:
    class FakeClient:
        def get_object(self, *_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("zero max_bytes must not become an unbounded get")

    service = StorageService.__new__(StorageService)
    service.client = FakeClient()
    service.bucket_name = "test-bucket"

    assert await service.get_object_bytes("object-key", max_bytes=0) == b""
