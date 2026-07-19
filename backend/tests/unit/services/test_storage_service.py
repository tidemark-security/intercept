from __future__ import annotations

import base64
import hashlib
from datetime import timedelta
from typing import Any

import pytest
from minio.credentials import ChainedProvider

from app.core.storage_config import StorageConfig
from app.models.models import PresignedUploadRequest
from app.services.storage_service import (
    MIME_SNIFF_BYTES,
    StorageService,
    _copy_object_with_sha256_checksum,
    storage_service,
)


def test_copy_checksum_adapter_isolates_minio_private_request() -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    class FakeClient:
        def _execute(self, *args: Any, **kwargs: Any) -> None:
            calls.append((args, kwargs))

    _copy_object_with_sha256_checksum(
        FakeClient(),  # type: ignore[arg-type]
        "attachments",
        "staging/source",
        "tasks/1/destination",
    )

    assert calls == [
        (
            ("PUT", "attachments"),
            {
                "object_name": "tasks/1/destination",
                "headers": {
                    "x-amz-copy-source": "/attachments/staging/source",
                    "x-amz-checksum-algorithm": "SHA256",
                },
            },
        )
    ]


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


def test_storage_config_normalizes_blank_credentials_to_none() -> None:
    config = StorageConfig(
        _env_file=None,
        STORAGE_ACCESS_KEY=" ",
        STORAGE_SECRET_KEY="",
    )

    assert config.storage_access_key is None
    assert config.storage_secret_key is None


def test_storage_service_uses_static_credentials_when_keys_are_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeMinio:
        def __init__(self, endpoint: str, **kwargs: Any) -> None:
            calls.append({"endpoint": endpoint, **kwargs})

    monkeypatch.setattr("app.services.storage_service.Minio", FakeMinio)

    StorageService(
        StorageConfig(
            _env_file=None,
            STORAGE_ENDPOINT="localhost:9000",
            STORAGE_ACCESS_KEY="minioadmin",
            STORAGE_SECRET_KEY="miniosecret",
            STORAGE_BUCKET="test-bucket",
            STORAGE_USE_SSL=False,
            STORAGE_REGION="us-east-1",
        )
    )

    assert calls == [
        {
            "endpoint": "localhost:9000",
            "secure": False,
            "region": "us-east-1",
            "access_key": "minioadmin",
            "secret_key": "miniosecret",
        }
    ]


def test_storage_service_uses_aws_provider_when_keys_are_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeMinio:
        def __init__(self, endpoint: str, **kwargs: Any) -> None:
            calls.append({"endpoint": endpoint, **kwargs})

    monkeypatch.setattr("app.services.storage_service.Minio", FakeMinio)

    StorageService(
        StorageConfig(
            _env_file=None,
            STORAGE_ENDPOINT="s3.ap-southeast-2.amazonaws.com",
            STORAGE_ACCESS_KEY="",
            STORAGE_SECRET_KEY=" ",
            STORAGE_BUCKET="test-bucket",
            STORAGE_USE_SSL=True,
            STORAGE_REGION="ap-southeast-2",
        )
    )

    credentials = calls[0]["credentials"]
    provider_names = [type(provider).__name__ for provider in credentials._providers]

    assert calls[0]["endpoint"] == "s3.ap-southeast-2.amazonaws.com"
    assert calls[0]["secure"] is True
    assert calls[0]["region"] == "ap-southeast-2"
    assert "access_key" not in calls[0]
    assert "secret_key" not in calls[0]
    assert isinstance(credentials, ChainedProvider)
    assert provider_names == ["EnvAWSProvider", "AWSConfigProvider", "IamAwsProvider"]


@pytest.mark.parametrize(
    ("access_key", "secret_key"),
    [
        ("minioadmin", ""),
        ("", "miniosecret"),
    ],
)
def test_storage_service_rejects_partial_static_credentials(
    access_key: str,
    secret_key: str,
) -> None:
    config = StorageConfig(
        _env_file=None,
        STORAGE_ACCESS_KEY=access_key,
        STORAGE_SECRET_KEY=secret_key,
    )

    with pytest.raises(ValueError, match="STORAGE_ACCESS_KEY and STORAGE_SECRET_KEY"):
        StorageService(config)


@pytest.mark.asyncio
async def test_storage_service_uses_injected_limits_and_default_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expiries: dict[str, timedelta] = {}

    class FakeClient:
        def presigned_put_object(
            self,
            _bucket_name: str,
            _storage_key: str,
            *,
            expires: timedelta,
        ) -> str:
            expiries["upload"] = expires
            return "https://storage.test/upload"

        def presigned_get_object(
            self,
            _bucket_name: str,
            _storage_key: str,
            *,
            expires: timedelta,
            response_headers: Any,
        ) -> str:
            expiries["download"] = expires
            return "https://storage.test/download"

    fake_client = FakeClient()
    monkeypatch.setattr(
        StorageService,
        "_build_client",
        classmethod(lambda _cls, _config: fake_client),
    )
    service = StorageService(
        StorageConfig(
            _env_file=None,
            STORAGE_AUTO_CREATE_BUCKET=False,
            upload_timeout_minutes=7,
            download_timeout_minutes=11,
        )
    )

    await service.generate_presigned_upload_url("upload-key")
    await service.generate_presigned_download_url("download-key")

    assert expiries == {
        "upload": timedelta(minutes=7),
        "download": timedelta(minutes=11),
    }


@pytest.mark.asyncio
async def test_ensure_bucket_exists_skips_bucket_calls_when_auto_create_disabled() -> None:
    class FakeClient:
        def bucket_exists(self, _bucket_name: str) -> bool:
            raise AssertionError("bucket_exists must not be called when auto-create is disabled")

        def make_bucket(self, _bucket_name: str) -> None:
            raise AssertionError("make_bucket must not be called when auto-create is disabled")

    service = StorageService.__new__(StorageService)
    service.client = FakeClient()
    service.bucket_name = "test-bucket"
    service._auto_create_bucket = False
    service._bucket_checked = False

    await service.ensure_bucket_exists()

    assert service._bucket_checked is True


@pytest.mark.asyncio
async def test_put_object_bytes_owns_bucket_setup_and_stream_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeClient:
        def put_object(
            self,
            bucket_name: str,
            storage_key: str,
            stream: Any,
            length: int,
            *,
            content_type: str,
        ) -> None:
            calls.append(
                {
                    "bucket_name": bucket_name,
                    "storage_key": storage_key,
                    "data": stream.read(),
                    "length": length,
                    "content_type": content_type,
                }
            )

    service = StorageService.__new__(StorageService)
    service.client = FakeClient()
    service.bucket_name = "test-bucket"
    bucket_ready = False

    async def ensure_bucket_exists() -> None:
        nonlocal bucket_ready
        bucket_ready = True

    monkeypatch.setattr(service, "ensure_bucket_exists", ensure_bucket_exists)

    await service.put_object_bytes(
        "maxmind/GeoLite2-ASN.mmdb",
        b"database bytes",
        content_type="application/octet-stream",
    )

    assert bucket_ready is True
    assert calls == [
        {
            "bucket_name": "test-bucket",
            "storage_key": "maxmind/GeoLite2-ASN.mmdb",
            "data": b"database bytes",
            "length": 14,
            "content_type": "application/octet-stream",
        }
    ]


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
