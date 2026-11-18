import asyncio
import hashlib
import json
import shutil
import tarfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import AsyncMock

import httpx
import pytest
from minio.error import S3Error

from app.services.maxmind_service import (
    MaxMindArchiveError,
    MaxMindCacheSyncError,
    MaxMindConfigurationError,
    MaxMindObjectNotFoundError,
    MaxMindReaderError,
    MaxMindUpdateError,
    maxmind_service,
)
from app.services.storage_service import storage_service


class StubSettings:
    def __init__(self, values: dict[str, object]):
        self._values = values

    async def get(self, key: str, default: object = None) -> object:
        return self._values.get(key, default)


async def _run_in_place(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return function(*args, **kwargs)


def _prepare_local_mmdbs(source_dir: Path, target_dir: Path, file_names: list[str]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for file_name in file_names:
        edition_id = file_name.replace("-Test.mmdb", "")
        shutil.copy2(source_dir / file_name, target_dir / f"{edition_id}.mmdb")


@pytest.mark.asyncio
async def test_parse_geoip_conf_extracts_credentials_and_editions() -> None:
    parsed = maxmind_service.parse_geoip_conf(
        """
        # Example GeoIP.conf
        AccountID 1234567
        LicenseKey REDACTED_TEST_LICENSE_KEY_placeholder00
        EditionIDs GeoLite2-ASN GeoLite2-City GeoLite2-Country
        """
    )

    assert parsed["account_id"] == "1234567"
    assert parsed["license_key"] == "REDACTED_TEST_LICENSE_KEY_placeholder00"
    assert parsed["edition_ids"] == ["GeoLite2-ASN", "GeoLite2-City", "GeoLite2-Country"]


@pytest.mark.asyncio
async def test_enqueue_update_after_commit_does_not_report_saved_settings_as_failed(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    enqueue_update = AsyncMock(side_effect=RuntimeError("queue unavailable"))
    monkeypatch.setattr(maxmind_service, "enqueue_update", enqueue_update)
    db = SimpleNamespace(rollback=AsyncMock())

    task_id = await maxmind_service.enqueue_update_after_commit(
        db=db,  # type: ignore[arg-type]
        reschedule=True,
    )

    assert task_id is None
    enqueue_update.assert_awaited_once_with(db, reschedule=True)
    db.rollback.assert_awaited_once_with()
    assert "settings were saved" in caplog.text


@pytest.mark.asyncio
async def test_storage_reads_use_storage_service_interface(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def ensure_bucket_exists() -> None:
        calls.append("ensure")

    async def get_object_bytes(key: str, *, max_bytes: int | None = None) -> bytes:
        assert max_bytes is None
        calls.append(key)
        return b"database"

    monkeypatch.setattr(storage_service, "ensure_bucket_exists", ensure_bucket_exists)
    monkeypatch.setattr(storage_service, "get_object_bytes", get_object_bytes)

    assert await maxmind_service._get_object_bytes("maxmind/database.mmdb") == b"database"
    assert calls == ["ensure", "maxmind/database.mmdb"]


@pytest.mark.asyncio
async def test_download_offloads_archive_validation_and_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_bytes = b"maxmind database"
    archive_buffer = BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w:gz") as archive:
        member = tarfile.TarInfo("GeoLite2-ASN/database.mmdb")
        member.size = len(database_bytes)
        archive.addfile(member, BytesIO(database_bytes))
    archive_bytes = archive_buffer.getvalue()
    archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()

    class FakeResponse:
        def __init__(
            self,
            *,
            content: bytes = b"",
            text: str = "",
        ) -> None:
            self.status_code = 200
            self.content = content
            self.text = text
            self.headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, url: str, **_kwargs: object) -> FakeResponse:
            if url.endswith(".sha256"):
                return FakeResponse(text=archive_sha256)
            return FakeResponse(content=archive_bytes)

    async def fake_get_settings(
        _db: object,
        *,
        strict_editions: bool = True,
    ) -> tuple[StubSettings, dict[str, object]]:
        assert strict_editions is True
        return StubSettings({}), {
            "account_id": "1234567",
            "license_key": "license",
            "edition_ids": ["GeoLite2-ASN"],
            "storage_prefix": "maxmind/",
        }

    async def fake_load_metadata(_prefix: str, _edition_id: str) -> dict[str, object]:
        return {}

    saved_metadata: dict[str, object] = {}

    async def fake_save_metadata(
        _prefix: str,
        _edition_id: str,
        metadata: dict[str, Any],
    ) -> None:
        saved_metadata.update(metadata)

    stored_objects: list[tuple[str, bytes, str]] = []

    async def fake_put_object_bytes(
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> None:
        stored_objects.append((key, data, content_type))

    offloaded_operations: list[str] = []

    async def run_in_place(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        offloaded_operations.append(getattr(function, "__name__", repr(function)))
        return function(*args, **kwargs)

    monkeypatch.setattr(maxmind_service, "_get_settings", fake_get_settings)
    monkeypatch.setattr(maxmind_service, "_load_metadata", fake_load_metadata)
    monkeypatch.setattr(maxmind_service, "_save_metadata", fake_save_metadata)
    monkeypatch.setattr(storage_service, "put_object_bytes", fake_put_object_bytes)
    monkeypatch.setattr("app.services.maxmind_service.httpx.AsyncClient", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(asyncio, "to_thread", run_in_place)

    result = await maxmind_service.download_databases(db=None)  # type: ignore[arg-type]

    assert offloaded_operations == ["_prepare_database_archive"]
    assert stored_objects == [
        ("maxmind/GeoLite2-ASN.mmdb", database_bytes, "application/octet-stream")
    ]
    assert saved_metadata["archive_sha256"] == archive_sha256
    assert saved_metadata["content_sha256"] == hashlib.sha256(database_bytes).hexdigest()
    assert result["GeoLite2-ASN"]["status"] == "updated"


@pytest.mark.parametrize(
    ("configured_editions", "expected_editions"),
    [
        (
            [" GeoLite2-ASN ", "", "GeoLite2-City", "GeoLite2-ASN"],
            ["GeoLite2-ASN", "GeoLite2-City"],
        ),
        ('["GeoLite2-ASN", "GeoLite2-City"]', ["GeoLite2-ASN", "GeoLite2-City"]),
        ("GeoLite2-ASN, GeoLite2-City", ["GeoLite2-ASN", "GeoLite2-City"]),
    ],
)
@pytest.mark.asyncio
async def test_sync_local_cache_normalizes_supported_edition_setting_formats(
    configured_editions: object,
    expected_editions: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = StubSettings(
        {
            "enrichment.maxmind.edition_ids": configured_editions,
            "enrichment.maxmind.local_cache_dir": str(tmp_path / "maxmind"),
        }
    )
    loaded_editions: list[str] = []

    async def fake_sync_local_cache_edition(
        *,
        prefix: str,
        local_cache_dir: Path,
        edition_id: str,
    ) -> bool:
        assert prefix == "maxmind/"
        assert local_cache_dir == tmp_path / "maxmind"
        loaded_editions.append(edition_id)
        return False

    monkeypatch.setattr(
        maxmind_service,
        "_sync_local_cache_edition",
        fake_sync_local_cache_edition,
    )
    monkeypatch.setattr(asyncio, "to_thread", _run_in_place)

    assert await maxmind_service.sync_local_cache(settings=settings) == []  # type: ignore[arg-type]
    assert loaded_editions == expected_editions


@pytest.mark.asyncio
async def test_sync_local_cache_atomically_replaces_files_via_offloaded_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_cache_dir = tmp_path / "maxmind"
    local_cache_dir.mkdir()
    db_path = local_cache_dir / "GeoLite2-ASN.mmdb"
    meta_path = local_cache_dir / "GeoLite2-ASN.json"
    db_path.write_bytes(b"old database")
    meta_path.write_text('{"version": "old"}', encoding="utf-8")
    database_bytes = b"new database"
    metadata = {
        "content_sha256": maxmind_service._sha256_bytes(database_bytes),
        "version": "new",
    }
    settings = StubSettings(
        {
            "enrichment.maxmind.edition_ids": ["GeoLite2-ASN"],
            "enrichment.maxmind.local_cache_dir": str(local_cache_dir),
        }
    )

    async def fake_load_metadata(_prefix: str, _edition_id: str) -> dict[str, object]:
        return metadata

    async def fake_get_object_bytes(_key: str) -> bytes:
        return database_bytes

    offloaded_operations: list[str] = []
    replaced_paths: list[Path] = []
    original_replace = Path.replace

    def track_replace(source: Path, target: Path) -> Path:
        replaced_paths.append(target)
        return original_replace(source, target)

    async def run_in_place(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        offloaded_operations.append(getattr(function, "__name__", repr(function)))
        return function(*args, **kwargs)

    monkeypatch.setattr(maxmind_service, "_load_metadata", fake_load_metadata)
    monkeypatch.setattr(maxmind_service, "_get_object_bytes", fake_get_object_bytes)
    monkeypatch.setattr(Path, "replace", track_replace)
    monkeypatch.setattr(asyncio, "to_thread", run_in_place)

    assert await maxmind_service.sync_local_cache(settings=settings) == ["GeoLite2-ASN"]  # type: ignore[arg-type]
    assert db_path.read_bytes() == database_bytes
    assert json.loads(meta_path.read_text(encoding="utf-8")) == metadata
    assert "_write_local_cache_entry" in offloaded_operations
    assert replaced_paths == [meta_path, db_path]
    assert not list(local_cache_dir.glob(".*.tmp"))


@pytest.mark.asyncio
async def test_sync_local_cache_preserves_database_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_cache_dir = tmp_path / "maxmind"
    local_cache_dir.mkdir()
    db_path = local_cache_dir / "GeoLite2-ASN.mmdb"
    meta_path = local_cache_dir / "GeoLite2-ASN.json"
    original_database = b"complete database"
    db_path.write_bytes(original_database)
    meta_path.write_text("{}", encoding="utf-8")
    database_bytes = b"replacement database"
    metadata = {"content_sha256": maxmind_service._sha256_bytes(database_bytes)}
    settings = StubSettings(
        {
            "enrichment.maxmind.edition_ids": ["GeoLite2-ASN"],
            "enrichment.maxmind.local_cache_dir": str(local_cache_dir),
        }
    )

    async def fake_load_metadata(_prefix: str, _edition_id: str) -> dict[str, object]:
        return metadata

    async def fake_get_object_bytes(_key: str) -> bytes:
        return database_bytes

    original_replace = Path.replace

    def fail_database_replace(source: Path, target: Path) -> Path:
        if target == db_path:
            raise OSError("simulated atomic replace failure")
        return original_replace(source, target)

    monkeypatch.setattr(maxmind_service, "_load_metadata", fake_load_metadata)
    monkeypatch.setattr(maxmind_service, "_get_object_bytes", fake_get_object_bytes)
    monkeypatch.setattr(Path, "replace", fail_database_replace)
    monkeypatch.setattr(asyncio, "to_thread", _run_in_place)

    with pytest.raises(MaxMindCacheSyncError) as exc_info:
        await maxmind_service.sync_local_cache(settings=settings)  # type: ignore[arg-type]

    assert exc_info.value.failures == {"GeoLite2-ASN": "filesystem"}
    assert db_path.read_bytes() == original_database
    assert not list(local_cache_dir.glob(".*.tmp"))


@pytest.mark.asyncio
async def test_lookup_ip_reads_real_mmdb_data(
    maxmind_test_data_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await maxmind_service.close_readers()
    local_cache_dir = tmp_path / "maxmind"
    _prepare_local_mmdbs(
        maxmind_test_data_dir,
        local_cache_dir,
        ["GeoLite2-ASN-Test.mmdb", "GeoLite2-City-Test.mmdb", "GeoLite2-Country-Test.mmdb"],
    )
    settings = StubSettings(
        {
            "enrichment.maxmind.edition_ids": ["GeoLite2-ASN", "GeoLite2-City", "GeoLite2-Country"],
            "enrichment.maxmind.local_cache_dir": str(local_cache_dir),
            "enrichment.maxmind.storage_prefix": "maxmind/",
        }
    )

    offloaded_operations: list[str] = []

    async def run_in_place(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        offloaded_operations.append(getattr(function, "__name__", repr(function)))
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", run_in_place)

    await maxmind_service.ensure_readers_loaded(settings=settings)  # type: ignore[arg-type]

    city_result = await maxmind_service.lookup_ip("81.2.69.160")
    assert city_result["databases"]["GeoLite2-City"]["country"]["iso_code"] == "GB"
    assert city_result["databases"]["GeoLite2-City"]["country"]["name"] == "United Kingdom"
    assert city_result["databases"]["GeoLite2-Country"]["country"]["iso_code"] == "GB"

    asn_result = await maxmind_service.lookup_ip("1.128.0.0")
    assert asn_result["databases"]["GeoLite2-ASN"]["autonomous_system_number"] == 1221
    assert asn_result["databases"]["GeoLite2-ASN"]["autonomous_system_organization"] == "Telstra Pty Ltd"

    await maxmind_service.close_readers()
    assert "_missing_local_databases" in offloaded_operations
    assert "_reconcile_readers" in offloaded_operations
    assert "_lookup_ip_in_readers" in offloaded_operations
    assert "_close_reader_states" in offloaded_operations


@pytest.mark.asyncio
async def test_get_database_status_handles_unavailable_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    await maxmind_service.close_readers()

    settings = StubSettings(
        {
            "enrichment.maxmind.edition_ids": ["GeoLite2-ASN", "GeoLite2-City"],
            "enrichment.maxmind.local_cache_dir": str(tmp_path / "maxmind"),
            "enrichment.maxmind.storage_prefix": "maxmind/",
            "enrichment.maxmind.account_id": "1234567",
            "enrichment.maxmind.license_key": "test-license",
            "enrichment.maxmind.ttl_seconds": 604800,
            "enrichment.maxmind.update_frequency_hours": 24,
        }
    )

    async def fake_get_settings(
        _db: object,
        *,
        strict_editions: bool = True,
    ) -> tuple[StubSettings, dict[str, object]]:
        return settings, {
            "account_id": "1234567",
            "license_key": "test-license",
            "edition_ids": ["GeoLite2-ASN", "GeoLite2-City"],
            "storage_prefix": "maxmind/",
            "local_cache_dir": str(tmp_path / "maxmind"),
        }

    async def fake_ensure_bucket() -> None:
        raise ConnectionError("storage unavailable")

    monkeypatch.setattr(maxmind_service, "_get_settings", fake_get_settings)
    monkeypatch.setattr(storage_service, "ensure_bucket_exists", fake_ensure_bucket)
    monkeypatch.setattr(asyncio, "to_thread", _run_in_place)

    statuses = await maxmind_service.get_database_status(db=None)  # type: ignore[arg-type]

    assert [status["edition_id"] for status in statuses] == ["GeoLite2-ASN", "GeoLite2-City"]
    assert all(status["available_in_storage"] is False for status in statuses)
    assert all(status["loaded"] is False for status in statuses)
    assert all(status["local_path"] is None for status in statuses)

    await maxmind_service.close_readers()


@pytest.mark.asyncio
async def test_download_reports_expected_failures_by_raising_after_all_editions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted_editions: list[str] = []

    async def fake_get_settings(
        _db: object,
        *,
        strict_editions: bool = True,
    ) -> tuple[StubSettings, dict[str, object]]:
        assert strict_editions is True
        return StubSettings({}), {
            "account_id": "1234567",
            "license_key": "license",
            "edition_ids": ["GeoLite2-ASN", "GeoLite2-City"],
            "storage_prefix": "maxmind/",
        }

    async def fake_load_metadata(_prefix: str, edition_id: str) -> dict[str, object]:
        attempted_editions.append(edition_id)
        return {}

    class UnavailableClient:
        async def __aenter__(self) -> "UnavailableClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, url: str, **_kwargs: object) -> object:
            raise httpx.ConnectError("download unavailable", request=httpx.Request("GET", url))

    monkeypatch.setattr(maxmind_service, "_get_settings", fake_get_settings)
    monkeypatch.setattr(maxmind_service, "_load_metadata", fake_load_metadata)
    monkeypatch.setattr(
        "app.services.maxmind_service.httpx.AsyncClient",
        lambda **_kwargs: UnavailableClient(),
    )

    with pytest.raises(
        MaxMindUpdateError,
        match="2 MaxMind database updates failed",
    ) as exc_info:
        await maxmind_service.download_databases(db=None)  # type: ignore[arg-type]

    assert attempted_editions == ["GeoLite2-ASN", "GeoLite2-City"]
    assert exc_info.value.failures == {
        "GeoLite2-ASN": "http",
        "GeoLite2-City": "http",
    }
    assert all(
        result == {"status": "error", "error": "http"}
        for result in exc_info.value.results.values()
    )
    assert "download unavailable" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_download_rejection_is_a_safe_nonretryable_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_settings(
        _db: object,
        *,
        strict_editions: bool = True,
    ) -> tuple[StubSettings, dict[str, object]]:
        assert strict_editions is True
        return StubSettings({}), {
            "account_id": "1234567",
            "license_key": "secret-license",
            "edition_ids": ["GeoLite2-ASN"],
            "storage_prefix": "maxmind/",
        }

    async def fake_load_metadata(_prefix: str, _edition_id: str) -> dict[str, object]:
        return {}

    class RejectedClient:
        async def __aenter__(self) -> "RejectedClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, url: str, **_kwargs: object) -> httpx.Response:
            return httpx.Response(
                401,
                text="license secret-license was rejected",
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(maxmind_service, "_get_settings", fake_get_settings)
    monkeypatch.setattr(maxmind_service, "_load_metadata", fake_load_metadata)
    monkeypatch.setattr(
        "app.services.maxmind_service.httpx.AsyncClient",
        lambda **_kwargs: RejectedClient(),
    )

    with pytest.raises(
        MaxMindConfigurationError,
        match="MaxMind rejected the download request for GeoLite2-ASN",
    ) as exc_info:
        await maxmind_service.download_databases(db=None)  # type: ignore[arg-type]

    assert "secret-license" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_sync_local_cache_raises_when_configured_database_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = StubSettings(
        {
            "enrichment.maxmind.edition_ids": ["GeoLite2-ASN"],
            "enrichment.maxmind.local_cache_dir": str(tmp_path / "maxmind"),
        }
    )

    async def fake_load_metadata(_prefix: str, _edition_id: str) -> dict[str, object]:
        return {}

    async def fake_get_object_bytes(_key: str) -> None:
        return None

    monkeypatch.setattr(maxmind_service, "_load_metadata", fake_load_metadata)
    monkeypatch.setattr(maxmind_service, "_get_object_bytes", fake_get_object_bytes)
    monkeypatch.setattr(asyncio, "to_thread", _run_in_place)

    with pytest.raises(MaxMindCacheSyncError, match="GeoLite2-ASN") as exc_info:
        await maxmind_service.sync_local_cache(settings=settings)  # type: ignore[arg-type]

    assert exc_info.value.failures == {"GeoLite2-ASN": "missing"}


@pytest.mark.asyncio
async def test_lookup_does_not_disguise_unexpected_reader_failures_as_no_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenReader:
        def asn(self, _ip: str) -> object:
            raise AssertionError("programming defect")

        def close(self) -> None:
            return None

    original_readers = maxmind_service._readers
    maxmind_service._readers = {
        "GeoLite2-ASN": SimpleNamespace(
            reader=BrokenReader(),
            path="GeoLite2-ASN.mmdb",
            mtime_ns=1,
        )
    }
    monkeypatch.setattr(asyncio, "to_thread", _run_in_place)
    try:
        with pytest.raises(AssertionError, match="programming defect"):
            await maxmind_service.lookup_ip("1.1.1.1")
    finally:
        maxmind_service._readers = original_readers


@pytest.mark.asyncio
async def test_database_status_does_not_disguise_programming_errors_as_storage_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = StubSettings({})

    async def fake_get_settings(
        _db: object,
        *,
        strict_editions: bool = True,
    ) -> tuple[StubSettings, dict[str, object]]:
        assert strict_editions is False
        return settings, {
            "account_id": "1234567",
            "license_key": "license",
            "edition_ids": ["GeoLite2-ASN"],
            "storage_prefix": "maxmind/",
            "local_cache_dir": "/tmp/tmi-maxmind",
        }

    async def fail_with_programming_error() -> None:
        raise AssertionError("programming defect")

    monkeypatch.setattr(maxmind_service, "_get_settings", fake_get_settings)
    monkeypatch.setattr(storage_service, "ensure_bucket_exists", fail_with_programming_error)
    monkeypatch.setattr(asyncio, "to_thread", _run_in_place)

    with pytest.raises(AssertionError, match="programming defect"):
        await maxmind_service.get_database_status(db=None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_storage_adapter_only_translates_explicit_missing_object_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ensure_bucket_exists() -> None:
        return None

    async def missing_object(_key: str, *, max_bytes: int | None = None) -> bytes:
        assert max_bytes is None
        raise S3Error(
            None,  # type: ignore[arg-type]
            "NoSuchKey",
            "missing",
            "maxmind/GeoLite2-ASN.mmdb",
            "request-id",
            "host-id",
            "intercept",
            "maxmind/GeoLite2-ASN.mmdb",
        )

    monkeypatch.setattr(storage_service, "ensure_bucket_exists", ensure_bucket_exists)
    monkeypatch.setattr(storage_service, "get_object_bytes", missing_object)

    with pytest.raises(MaxMindObjectNotFoundError, match="GeoLite2-ASN.mmdb"):
        await maxmind_service._get_object_bytes("maxmind/GeoLite2-ASN.mmdb")


def test_invalid_download_archive_raises_typed_archive_error() -> None:
    archive_bytes = b"not a gzip archive"

    with pytest.raises(MaxMindArchiveError, match="archive.*invalid"):
        maxmind_service._prepare_database_archive(
            archive_bytes,
            "GeoLite2-ASN",
            hashlib.sha256(archive_bytes).hexdigest(),
        )


def test_invalid_local_database_raises_typed_reader_error(tmp_path: Path) -> None:
    local_cache_dir = tmp_path / "maxmind"
    local_cache_dir.mkdir()
    (local_cache_dir / "GeoLite2-ASN.mmdb").write_bytes(b"not an mmdb")

    with pytest.raises(MaxMindReaderError, match="GeoLite2-ASN"):
        maxmind_service._reconcile_readers(
            str(local_cache_dir),
            {"GeoLite2-ASN"},
        )


def test_reader_cleanup_attempts_every_reader_after_one_close_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    closed: list[str] = []

    class BrokenReader:
        def close(self) -> None:
            closed.append("broken")
            raise RuntimeError("close failed")

    class HealthyReader:
        def close(self) -> None:
            closed.append("healthy")

    maxmind_service._close_reader_states(  # type: ignore[arg-type]
        [
            (
                "GeoLite2-ASN",
                SimpleNamespace(reader=BrokenReader(), path="asn", mtime_ns=1),
            ),
            (
                "GeoLite2-City",
                SimpleNamespace(reader=HealthyReader(), path="city", mtime_ns=1),
            ),
        ]
    )

    assert closed == ["broken", "healthy"]
    assert "Failed to close MaxMind reader for GeoLite2-ASN" in caplog.text


@pytest.mark.asyncio
async def test_conditional_download_refetches_when_stored_content_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_bytes = b"maxmind database"
    archive_buffer = BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w:gz") as archive:
        member = tarfile.TarInfo("GeoLite2-ASN/database.mmdb")
        member.size = len(database_bytes)
        archive.addfile(member, BytesIO(database_bytes))
    archive_bytes = archive_buffer.getvalue()
    archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()

    class FakeResponse:
        def __init__(
            self,
            *,
            status_code: int,
            content: bytes = b"",
            text: str = "",
        ) -> None:
            self.status_code = status_code
            self.content = content
            self.text = text
            self.headers = {"last-modified": "Sun, 19 Jul 2026 00:00:00 GMT"}

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self) -> None:
            self.download_headers: list[dict[str, str]] = []

        async def get(self, url: str, **kwargs: object) -> FakeResponse:
            if url.endswith(".sha256"):
                return FakeResponse(status_code=200, text=archive_sha256)
            headers = dict(kwargs.get("headers") or {})  # type: ignore[arg-type]
            self.download_headers.append(headers)
            if len(self.download_headers) == 1:
                return FakeResponse(status_code=304)
            return FakeResponse(status_code=200, content=archive_bytes)

    async def fake_load_metadata(
        _prefix: str,
        _edition_id: str,
    ) -> dict[str, object]:
        return {
            "source_last_modified": "Sat, 18 Jul 2026 00:00:00 GMT",
            "content_sha256": "a" * 64,
        }

    async def missing_stored_database(_key: str) -> bytes:
        raise MaxMindObjectNotFoundError("missing")

    stored_objects: list[tuple[str, bytes]] = []

    async def fake_put_object_bytes(
        key: str,
        data: bytes,
        *,
        content_type: str,
    ) -> None:
        assert content_type == "application/octet-stream"
        stored_objects.append((key, data))

    async def fake_save_metadata(
        _prefix: str,
        _edition_id: str,
        _metadata: dict[str, Any],
    ) -> None:
        return None

    client = FakeClient()
    monkeypatch.setattr(maxmind_service, "_load_metadata", fake_load_metadata)
    monkeypatch.setattr(maxmind_service, "_get_object_bytes", missing_stored_database)
    monkeypatch.setattr(maxmind_service, "_put_object_bytes", fake_put_object_bytes)
    monkeypatch.setattr(maxmind_service, "_save_metadata", fake_save_metadata)
    monkeypatch.setattr(asyncio, "to_thread", _run_in_place)

    result = await maxmind_service._download_database(
        client=client,  # type: ignore[arg-type]
        auth=("account", "license"),
        prefix="maxmind/",
        edition_id="GeoLite2-ASN",
    )

    assert result["status"] == "updated"
    assert client.download_headers == [
        {"If-Modified-Since": "Sat, 18 Jul 2026 00:00:00 GMT"},
        {},
    ]
    assert stored_objects == [("maxmind/GeoLite2-ASN.mmdb", database_bytes)]
