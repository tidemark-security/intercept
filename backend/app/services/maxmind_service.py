from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import math
import tarfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import geoip2.database
import httpx
from geoip2.errors import AddressNotFoundError
from maxminddb.errors import InvalidDatabaseError
from minio.error import MinioException, S3Error
from sqlalchemy.ext.asyncio import AsyncSession
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from app.services.committed_response import reset_post_commit_session
from app.services.date_filter_utils import parse_optional_utc_datetime
from app.services.settings_service import SettingsService
from app.services.storage_service import ObjectMetadata, storage_service

logger = logging.getLogger(__name__)

MAXMIND_DOWNLOAD_URL = "https://download.maxmind.com/geoip/databases/{edition_id}/download?suffix=tar.gz"
MAXMIND_SHA256_URL = "https://download.maxmind.com/geoip/databases/{edition_id}/download?suffix=tar.gz.sha256"
SUPPORTED_EDITIONS: dict[str, str] = {
    "GeoLite2-ASN": "asn",
    "GeoLite2-City": "city",
    "GeoLite2-Country": "country",
    "GeoIP2-Anonymous-IP": "anonymous_ip",
    "GeoIP2-Connection-Type": "connection_type",
    "GeoIP2-Domain": "domain",
    "GeoIP2-Enterprise": "enterprise",
    "GeoIP2-ISP": "isp",
    "GeoIP2-City": "city",
    "GeoIP2-Country": "country",
}
_STORAGE_OBJECT_NOT_FOUND_CODES = frozenset({"NoSuchKey", "NoSuchObject"})


class MaxMindConfigurationError(ValueError):
    """Raised when MaxMind settings are absent or invalid."""


class MaxMindStorageError(RuntimeError):
    """Raised when MaxMind data cannot be read from or written to object storage."""


class MaxMindObjectNotFoundError(MaxMindStorageError):
    """Raised when a specific MaxMind object is not present in storage."""


class MaxMindArchiveError(RuntimeError):
    """Raised when a downloaded archive or checksum is invalid."""


class MaxMindReaderError(RuntimeError):
    """Raised when a local MaxMind database cannot be opened or queried."""


class MaxMindUpdateError(RuntimeError):
    """Raised after all configured downloads are attempted and any one fails."""

    def __init__(
        self,
        failures: dict[str, str],
        results: dict[str, Any],
    ) -> None:
        self.failures = dict(failures)
        self.results = dict(results)
        editions = ", ".join(sorted(failures))
        super().__init__(
            f"{len(failures)} MaxMind database updates failed: {editions}"
        )


class MaxMindCacheSyncError(RuntimeError):
    """Raised after all configured cache entries are attempted and any one fails."""

    def __init__(self, failures: dict[str, str]) -> None:
        self.failures = dict(failures)
        editions = ", ".join(sorted(failures))
        super().__init__(
            f"MaxMind local cache sync failed for {editions}"
        )


@dataclass(slots=True)
class _ReaderState:
    reader: geoip2.database.Reader
    path: str
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class _PreparedDatabase:
    archive_sha256: str
    content: bytes
    content_sha256: str
    extracted_name: str


class MaxMindService:
    def __init__(self) -> None:
        self._reader_lock = asyncio.Lock()
        self._readers: dict[str, _ReaderState] = {}

    def parse_geoip_conf(self, text: str) -> dict[str, Any]:
        account_id = ""
        license_key = ""
        edition_ids: list[str] = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            key, raw_value = parts[0], parts[1].strip()
            value = raw_value.strip().strip('"').strip("'")

            if key == "AccountID":
                account_id = value
            elif key == "LicenseKey":
                license_key = value
            elif key == "EditionIDs":
                edition_ids = [item.strip() for item in value.split() if item.strip()]

        if not account_id:
            raise MaxMindConfigurationError("GeoIP.conf is missing AccountID")
        if not license_key:
            raise MaxMindConfigurationError("GeoIP.conf is missing LicenseKey")
        if not edition_ids:
            raise MaxMindConfigurationError("GeoIP.conf is missing EditionIDs")
        unsupported = [edition for edition in edition_ids if edition not in SUPPORTED_EDITIONS]
        if unsupported:
            raise MaxMindConfigurationError(
                f"Unsupported MaxMind edition IDs: {', '.join(unsupported)}"
            )

        return {
            "account_id": account_id,
            "license_key": license_key,
            "edition_ids": edition_ids,
        }

    def serialize_edition_ids(self, edition_ids: Iterable[str]) -> str:
        return json.dumps(list(edition_ids))

    @staticmethod
    def _normalize_edition_ids(edition_ids: Any) -> list[str]:
        if isinstance(edition_ids, str):
            try:
                edition_ids = json.loads(edition_ids)
            except json.JSONDecodeError:
                edition_ids = edition_ids.split(",")

        if edition_ids is None:
            return []
        if not isinstance(edition_ids, (list, tuple)):
            raise MaxMindConfigurationError(
                "MaxMind edition IDs must be configured as a list"
            )

        normalized: list[str] = []
        seen: set[str] = set()
        for item in edition_ids:
            edition_id = str(item).strip()
            if not edition_id or edition_id in seen:
                continue
            seen.add(edition_id)
            normalized.append(edition_id)
        return normalized

    @classmethod
    def _validated_edition_ids(
        cls,
        edition_ids: Any,
        *,
        strict: bool = True,
        require_any: bool = False,
    ) -> list[str]:
        normalized = cls._normalize_edition_ids(edition_ids)
        unsupported = [
            edition_id
            for edition_id in normalized
            if edition_id not in SUPPORTED_EDITIONS
        ]
        if unsupported:
            if strict:
                raise MaxMindConfigurationError(
                    f"Unsupported MaxMind edition IDs: {', '.join(unsupported)}"
                )
            logger.warning(
                "Ignoring unsupported MaxMind edition IDs: %s",
                ", ".join(unsupported),
            )

        supported = [
            edition_id
            for edition_id in normalized
            if edition_id in SUPPORTED_EDITIONS
        ]
        if require_any and not supported:
            raise MaxMindConfigurationError(
                "At least one MaxMind edition must be configured"
            )
        return supported

    async def _get_settings(
        self,
        db: AsyncSession,
        *,
        strict_editions: bool = True,
    ) -> tuple[SettingsService, dict[str, Any]]:
        settings = SettingsService(db)  # type: ignore[arg-type]
        edition_ids = self._validated_edition_ids(
            await settings.get(
                "enrichment.maxmind.edition_ids",
                ["GeoLite2-ASN", "GeoLite2-City", "GeoLite2-Country"],
            ),
            strict=strict_editions,
        )

        return settings, {
            "account_id": str(await settings.get("enrichment.maxmind.account_id", "") or ""),
            "license_key": str(await settings.get("enrichment.maxmind.license_key", "") or ""),
            "edition_ids": edition_ids,
            "storage_prefix": str(await settings.get("enrichment.maxmind.storage_prefix", "maxmind/") or "maxmind/"),
            "local_cache_dir": str(
                await settings.get(
                    "enrichment.maxmind.local_cache_dir",
                    "/tmp/tmi-maxmind",
                )
                or "/tmp/tmi-maxmind"
            ),
        }

    @staticmethod
    def _storage_key(prefix: str, edition_id: str) -> str:
        return f"{prefix.rstrip('/')}/{edition_id}.mmdb"

    @staticmethod
    def _metadata_key(prefix: str, edition_id: str) -> str:
        return f"{prefix.rstrip('/')}/{edition_id}.json"

    @staticmethod
    def _local_db_path(local_cache_dir: str, edition_id: str) -> Path:
        return Path(local_cache_dir) / f"{edition_id}.mmdb"

    @staticmethod
    def _local_meta_path(local_cache_dir: str, edition_id: str) -> Path:
        return Path(local_cache_dir) / f"{edition_id}.json"

    @staticmethod
    def _translate_storage_error(
        exc: MinioException | Urllib3HTTPError | OSError,
        key: str,
    ) -> MaxMindStorageError:
        if isinstance(exc, S3Error) and exc.code in _STORAGE_OBJECT_NOT_FOUND_CODES:
            return MaxMindObjectNotFoundError(
                f"MaxMind storage object is missing: {key}"
            )
        return MaxMindStorageError("MaxMind object storage is unavailable")

    async def _ensure_storage_available(self) -> None:
        try:
            await storage_service.ensure_bucket_exists()
        except (MinioException, Urllib3HTTPError, OSError) as exc:
            raise self._translate_storage_error(exc, "") from exc

    async def _get_object_bytes(self, key: str) -> bytes:
        await self._ensure_storage_available()
        try:
            return await storage_service.get_object_bytes(key)
        except (MinioException, Urllib3HTTPError, OSError) as exc:
            raise self._translate_storage_error(exc, key) from exc

    async def _get_object_metadata(self, key: str) -> ObjectMetadata:
        await self._ensure_storage_available()
        try:
            return await storage_service.get_object_metadata(key)
        except (MinioException, Urllib3HTTPError, OSError) as exc:
            raise self._translate_storage_error(exc, key) from exc

    async def _put_object_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
    ) -> None:
        try:
            await storage_service.put_object_bytes(
                key,
                data,
                content_type=content_type,
            )
        except (MinioException, Urllib3HTTPError, OSError) as exc:
            raise self._translate_storage_error(exc, key) from exc

    async def _load_metadata(self, prefix: str, edition_id: str) -> dict[str, Any]:
        try:
            metadata_bytes = await self._get_object_bytes(
                self._metadata_key(prefix, edition_id)
            )
        except MaxMindObjectNotFoundError:
            return {}
        if not metadata_bytes:
            return {}
        try:
            metadata = json.loads(metadata_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Invalid MaxMind metadata JSON for %s", edition_id)
            return {}
        if not isinstance(metadata, dict):
            logger.warning("Invalid MaxMind metadata document for %s", edition_id)
            return {}
        return metadata

    async def _save_metadata(self, prefix: str, edition_id: str, metadata: dict[str, Any]) -> None:
        payload = json.dumps(metadata, sort_keys=True).encode("utf-8")
        await self._put_object_bytes(
            self._metadata_key(prefix, edition_id),
            payload,
            content_type="application/json",
        )

    @staticmethod
    def _sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _sha256_path(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _cache_entry_is_current(
        cls,
        db_path: Path,
        meta_path: Path,
        desired_hash: str,
    ) -> bool:
        current_hash = cls._sha256_path(db_path) if db_path.exists() else None
        return current_hash == desired_hash and meta_path.exists()

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(data)
            temporary_path.replace(path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @classmethod
    def _write_local_cache_entry(
        cls,
        db_path: Path,
        database_bytes: bytes,
        meta_path: Path,
        metadata: dict[str, Any],
    ) -> None:
        cls._atomic_write(meta_path, json.dumps(metadata, sort_keys=True).encode("utf-8"))
        cls._atomic_write(db_path, database_bytes)

    @staticmethod
    def _extract_mmdb_from_tar(archive_bytes: bytes, edition_id: str) -> tuple[bytes, str]:
        try:
            with tarfile.open(fileobj=BytesIO(archive_bytes), mode="r:gz") as archive:
                for member in archive.getmembers():
                    if not member.isfile() or not member.name.endswith(".mmdb"):
                        continue
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        continue
                    return extracted.read(), member.name.split("/")[-1]
        except (tarfile.TarError, EOFError, OSError) as exc:
            raise MaxMindArchiveError(
                f"Downloaded archive for {edition_id} is invalid"
            ) from exc
        raise MaxMindArchiveError(
            f"Downloaded archive for {edition_id} did not contain an .mmdb file"
        )

    @staticmethod
    def _parse_expected_sha256(checksum_text: str, edition_id: str) -> str:
        tokens = checksum_text.split()
        if not tokens:
            raise MaxMindArchiveError(
                f"Checksum response for {edition_id} was empty"
            )
        checksum = tokens[0]
        if len(checksum) != 64 or any(
            character not in "0123456789abcdefABCDEF" for character in checksum
        ):
            raise MaxMindArchiveError(
                f"Checksum response for {edition_id} was invalid"
            )
        return checksum.lower()

    @classmethod
    def _prepare_database_archive(
        cls,
        archive_bytes: bytes,
        edition_id: str,
        expected_sha256: str,
    ) -> _PreparedDatabase:
        """Validate and unpack a downloaded database archive."""
        archive_sha256 = cls._sha256_bytes(archive_bytes)
        if expected_sha256 and archive_sha256.lower() != expected_sha256.lower():
            raise MaxMindArchiveError(f"SHA256 mismatch for {edition_id}")

        content, extracted_name = cls._extract_mmdb_from_tar(archive_bytes, edition_id)
        return _PreparedDatabase(
            archive_sha256=archive_sha256,
            content=content,
            content_sha256=cls._sha256_bytes(content),
            extracted_name=extracted_name,
        )

    async def _stored_database_matches_metadata(
        self,
        prefix: str,
        edition_id: str,
        metadata: dict[str, Any],
    ) -> bool:
        expected_hash = metadata.get("content_sha256")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            return False
        try:
            database_bytes = await self._get_object_bytes(
                self._storage_key(prefix, edition_id)
            )
        except MaxMindObjectNotFoundError:
            return False
        if not database_bytes:
            return False
        actual_hash = await asyncio.to_thread(self._sha256_bytes, database_bytes)
        return actual_hash.lower() == expected_hash.lower()

    async def _download_database(
        self,
        *,
        client: httpx.AsyncClient,
        auth: tuple[str, str],
        prefix: str,
        edition_id: str,
    ) -> dict[str, Any]:
        current_metadata = await self._load_metadata(prefix, edition_id)
        headers: dict[str, str] = {}
        if current_metadata.get("source_last_modified"):
            headers["If-Modified-Since"] = str(
                current_metadata["source_last_modified"]
            )

        download_url = MAXMIND_DOWNLOAD_URL.format(edition_id=edition_id)
        response = await client.get(download_url, auth=auth, headers=headers)
        if response.status_code == 304:
            if await self._stored_database_matches_metadata(
                prefix,
                edition_id,
                current_metadata,
            ):
                return {"status": "unchanged"}
            logger.warning(
                "MaxMind returned 304 for %s, but the stored database is absent "
                "or inconsistent; retrying without a condition",
                edition_id,
            )
            response = await client.get(download_url, auth=auth, headers={})
            if response.status_code == 304:
                raise MaxMindArchiveError(
                    f"MaxMind did not return database content for {edition_id}"
                )
        response.raise_for_status()

        sha_response = await client.get(
            MAXMIND_SHA256_URL.format(edition_id=edition_id),
            auth=auth,
        )
        sha_response.raise_for_status()
        expected_sha256 = self._parse_expected_sha256(
            sha_response.text,
            edition_id,
        )
        prepared = await asyncio.to_thread(
            self._prepare_database_archive,
            response.content,
            edition_id,
            expected_sha256,
        )
        await self._put_object_bytes(
            self._storage_key(prefix, edition_id),
            prepared.content,
            content_type="application/octet-stream",
        )

        now = datetime.now(timezone.utc)
        metadata = {
            "edition_id": edition_id,
            "downloaded_at": now.isoformat(),
            "source_last_modified": response.headers.get("last-modified"),
            "archive_sha256": prepared.archive_sha256,
            "content_sha256": prepared.content_sha256,
            "extracted_name": prepared.extracted_name,
            "file_size_bytes": len(prepared.content),
        }
        await self._save_metadata(prefix, edition_id, metadata)
        return {
            "status": "updated",
            "content_sha256": prepared.content_sha256,
            "file_size_bytes": len(prepared.content),
        }

    async def download_databases(self, db: AsyncSession) -> dict[str, Any]:
        _, cfg = await self._get_settings(db)
        account_id = cfg["account_id"]
        license_key = cfg["license_key"]
        edition_ids = cfg["edition_ids"]
        prefix = cfg["storage_prefix"]

        if not account_id or not license_key:
            raise MaxMindConfigurationError(
                "MaxMind account ID and license key must be configured before downloading databases"
            )
        if not edition_ids:
            raise MaxMindConfigurationError(
                "At least one MaxMind edition must be configured"
            )

        results: dict[str, Any] = {}
        failures: dict[str, str] = {}
        auth = (account_id, license_key)

        async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
            for edition_id in edition_ids:
                try:
                    results[edition_id] = await self._download_database(
                        client=client,
                        auth=auth,
                        prefix=prefix,
                        edition_id=edition_id,
                    )
                except httpx.HTTPError as exc:
                    if (
                        isinstance(exc, httpx.HTTPStatusError)
                        and 400 <= exc.response.status_code < 500
                        and exc.response.status_code != 429
                    ):
                        raise MaxMindConfigurationError(
                            f"MaxMind rejected the download request for {edition_id}"
                        ) from exc
                    failures[edition_id] = "http"
                    logger.warning(
                        "Failed MaxMind HTTP request for %s",
                        edition_id,
                        exc_info=True,
                    )
                except MaxMindArchiveError:
                    failures[edition_id] = "archive"
                    logger.warning(
                        "Failed MaxMind archive validation for %s",
                        edition_id,
                        exc_info=True,
                    )
                except MaxMindStorageError:
                    failures[edition_id] = "storage"
                    logger.warning(
                        "Failed MaxMind storage operation for %s",
                        edition_id,
                        exc_info=True,
                    )

                if edition_id in failures:
                    results[edition_id] = {
                        "status": "error",
                        "error": failures[edition_id],
                    }

        if failures:
            raise MaxMindUpdateError(failures, results)
        return results

    async def _sync_local_cache_edition(
        self,
        *,
        prefix: str,
        local_cache_dir: Path,
        edition_id: str,
    ) -> bool:
        metadata = await self._load_metadata(prefix, edition_id)
        object_bytes = await self._get_object_bytes(
            self._storage_key(prefix, edition_id)
        )
        if not object_bytes:
            raise MaxMindObjectNotFoundError(
                f"MaxMind storage object is empty: {edition_id}"
            )

        actual_hash = await asyncio.to_thread(self._sha256_bytes, object_bytes)
        metadata_hash = metadata.get("content_sha256")
        if metadata_hash and str(metadata_hash).lower() != actual_hash:
            raise MaxMindStorageError(
                f"MaxMind database metadata does not match stored content: {edition_id}"
            )

        db_path = self._local_db_path(str(local_cache_dir), edition_id)
        meta_path = self._local_meta_path(str(local_cache_dir), edition_id)
        if await asyncio.to_thread(
            self._cache_entry_is_current,
            db_path,
            meta_path,
            actual_hash,
        ):
            return False

        await asyncio.to_thread(
            self._write_local_cache_entry,
            db_path,
            object_bytes,
            meta_path,
            metadata,
        )
        return True

    async def sync_local_cache(self, *, settings: SettingsService) -> list[str]:
        edition_ids = self._validated_edition_ids(
            await settings.get("enrichment.maxmind.edition_ids", []),
            require_any=True,
        )

        prefix = str(
            await settings.get("enrichment.maxmind.storage_prefix", "maxmind/")
            or "maxmind/"
        )
        local_cache_dir = Path(
            str(
                await settings.get(
                    "enrichment.maxmind.local_cache_dir",
                    "/tmp/tmi-maxmind",
                )
                or "/tmp/tmi-maxmind"
            )
        )
        try:
            await asyncio.to_thread(
                local_cache_dir.mkdir,
                parents=True,
                exist_ok=True,
            )
        except OSError as exc:
            raise MaxMindCacheSyncError({"local-cache": "filesystem"}) from exc

        synced: list[str] = []
        failures: dict[str, str] = {}
        for edition_id in edition_ids:
            try:
                changed = await self._sync_local_cache_edition(
                    prefix=prefix,
                    local_cache_dir=local_cache_dir,
                    edition_id=edition_id,
                )
            except MaxMindObjectNotFoundError:
                failures[edition_id] = "missing"
                logger.warning(
                    "Configured MaxMind database is missing from storage: %s",
                    edition_id,
                    exc_info=True,
                )
            except MaxMindStorageError:
                failures[edition_id] = "storage"
                logger.warning(
                    "Failed to read MaxMind database from storage: %s",
                    edition_id,
                    exc_info=True,
                )
            except OSError:
                failures[edition_id] = "filesystem"
                logger.warning(
                    "Failed to update local MaxMind cache: %s",
                    edition_id,
                    exc_info=True,
                )
            else:
                if changed:
                    synced.append(edition_id)

        if failures:
            raise MaxMindCacheSyncError(failures)
        return synced

    @staticmethod
    def _missing_local_databases(
        local_cache_dir: str,
        edition_ids: set[str],
    ) -> bool:
        return any(
            not MaxMindService._local_db_path(local_cache_dir, edition_id).exists()
            for edition_id in edition_ids
        )

    def _reconcile_readers(self, local_cache_dir: str, desired_editions: set[str]) -> None:
        current_editions = set(self._readers)

        for removed in current_editions - desired_editions:
            state = self._readers.pop(removed, None)
            if state is not None:
                self._close_reader_state(state, removed)

        for edition_id in desired_editions:
            db_path = self._local_db_path(local_cache_dir, edition_id)
            if not db_path.exists():
                raise MaxMindReaderError(
                    f"Local MaxMind database is unavailable: {edition_id}"
                )

            try:
                mtime_ns = db_path.stat().st_mtime_ns
            except OSError as exc:
                raise MaxMindReaderError(
                    f"Local MaxMind database cannot be inspected: {edition_id}"
                ) from exc
            existing = self._readers.get(edition_id)
            if existing is not None and existing.path == str(db_path) and existing.mtime_ns == mtime_ns:
                continue

            try:
                reader = geoip2.database.Reader(str(db_path))
            except (InvalidDatabaseError, OSError) as exc:
                raise MaxMindReaderError(
                    f"Local MaxMind database is invalid: {edition_id}"
                ) from exc
            self._readers[edition_id] = _ReaderState(
                reader=reader,
                path=str(db_path),
                mtime_ns=mtime_ns,
            )
            if existing is not None:
                self._close_reader_state(existing, edition_id)

    @staticmethod
    def _close_reader_state(state: _ReaderState, edition_id: str) -> None:
        """Close one reader without preventing cleanup of the remaining readers."""
        try:
            state.reader.close()
        except Exception:
            logger.warning(
                "Failed to close MaxMind reader for %s",
                edition_id,
                exc_info=True,
            )

    @classmethod
    def _close_reader_states(cls, readers: list[tuple[str, _ReaderState]]) -> None:
        for edition_id, state in readers:
            cls._close_reader_state(state, edition_id)

    async def ensure_readers_loaded(self, *, settings: SettingsService) -> None:
        edition_ids = self._validated_edition_ids(
            await settings.get("enrichment.maxmind.edition_ids", []),
            require_any=True,
        )
        local_cache_dir = str(
            await settings.get(
                "enrichment.maxmind.local_cache_dir",
                "/tmp/tmi-maxmind",
            )
            or "/tmp/tmi-maxmind"
        )
        desired_editions = set(edition_ids)

        if await asyncio.to_thread(
            self._missing_local_databases,
            local_cache_dir,
            desired_editions,
        ):
            await self.sync_local_cache(settings=settings)

        async with self._reader_lock:
            await asyncio.to_thread(
                self._reconcile_readers,
                local_cache_dir,
                desired_editions,
            )

    async def close_readers(self) -> None:
        async with self._reader_lock:
            readers = list(self._readers.items())
            self._readers.clear()
            await asyncio.to_thread(self._close_reader_states, readers)

    def _lookup_ip_in_readers(self, ip: str) -> dict[str, Any]:
        databases: dict[str, Any] = {}
        for edition_id, state in self._readers.items():
            method_name = SUPPORTED_EDITIONS.get(edition_id)
            if not method_name:
                continue
            try:
                result = getattr(state.reader, method_name)(ip)
            except AddressNotFoundError:
                continue
            except (InvalidDatabaseError, OSError) as exc:
                raise MaxMindReaderError(
                    f"MaxMind lookup database failed: {edition_id}"
                ) from exc
            serialized = self._serialize_record(edition_id, result)
            if serialized:
                databases[edition_id] = serialized
        return databases

    async def lookup_ip(self, ip: str) -> dict[str, Any]:
        ipaddress.ip_address(ip)

        async with self._reader_lock:
            databases = await asyncio.to_thread(self._lookup_ip_in_readers, ip)

        return {
            "ip": ip,
            "databases": databases,
            "queried_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _local_database_statuses(
        local_cache_dir: str,
        edition_ids: list[str],
    ) -> dict[str, tuple[str | None, int | None]]:
        statuses: dict[str, tuple[str | None, int | None]] = {}
        for edition_id in edition_ids:
            path = MaxMindService._local_db_path(local_cache_dir, edition_id)
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                statuses[edition_id] = (None, None)
            else:
                statuses[edition_id] = (str(path), size)
        return statuses

    @staticmethod
    def _database_file_size(
        metadata: dict[str, Any],
        local_file_size: int | None,
        edition_id: str,
    ) -> int | None:
        stored_size = metadata.get("file_size_bytes")
        if stored_size in (None, ""):
            return local_file_size
        try:
            normalized_size = int(stored_size)
        except (TypeError, ValueError):
            logger.warning(
                "Ignoring invalid MaxMind file size metadata for %s",
                edition_id,
            )
            return local_file_size
        return normalized_size if normalized_size > 0 else local_file_size

    async def get_database_status(self, db: AsyncSession) -> list[dict[str, Any]]:
        settings, cfg = await self._get_settings(db, strict_editions=False)
        if not cfg["edition_ids"]:
            return []

        storage_available = True
        try:
            await self._ensure_storage_available()
        except MaxMindStorageError:
            storage_available = False
            logger.warning(
                "MaxMind storage unavailable while loading database status",
                exc_info=True,
            )

        if storage_available:
            try:
                await self.ensure_readers_loaded(settings=settings)
            except (
                MaxMindCacheSyncError,
                MaxMindConfigurationError,
                MaxMindReaderError,
            ):
                logger.warning(
                    "MaxMind readers could not be refreshed while loading database status",
                    exc_info=True,
                )

        statuses: list[dict[str, Any]] = []
        local_cache_dir = cfg["local_cache_dir"]
        prefix = cfg["storage_prefix"]
        local_statuses = await asyncio.to_thread(
            self._local_database_statuses,
            local_cache_dir,
            cfg["edition_ids"],
        )

        async with self._reader_lock:
            loaded_editions = set(self._readers)

        for edition_id in cfg["edition_ids"]:
            metadata: dict[str, Any] = {}
            available_in_storage = False
            if storage_available:
                try:
                    metadata = await self._load_metadata(prefix, edition_id)
                    await self._get_object_metadata(
                        self._storage_key(prefix, edition_id)
                    )
                except MaxMindObjectNotFoundError:
                    logger.debug(
                        "MaxMind database object is not available in storage: %s",
                        edition_id,
                    )
                except MaxMindStorageError:
                    storage_available = False
                    logger.warning(
                        "MaxMind storage became unavailable while loading database status",
                        exc_info=True,
                    )
                else:
                    available_in_storage = True
            local_path, local_file_size = local_statuses[edition_id]
            statuses.append(
                {
                    "edition_id": edition_id,
                    "available_in_storage": available_in_storage,
                    "loaded": edition_id in loaded_editions,
                    "local_path": local_path,
                    "file_size_bytes": self._database_file_size(
                        metadata,
                        local_file_size,
                        edition_id,
                    ),
                    "last_updated": parse_optional_utc_datetime(metadata.get("downloaded_at")),
                    "content_sha256": metadata.get("content_sha256"),
                }
            )

        return statuses

    async def enqueue_update(self, db: AsyncSession, *, reschedule: bool) -> str:
        settings = SettingsService(db)  # type: ignore[arg-type]
        enabled = bool(await settings.get("enrichment.maxmind.enabled", False))
        account_id = await settings.get("enrichment.maxmind.account_id", "")
        license_key = await settings.get("enrichment.maxmind.license_key", "")
        if not enabled:
            raise MaxMindConfigurationError("MaxMind provider is disabled")
        if not account_id or not license_key:
            raise MaxMindConfigurationError(
                "MaxMind account ID and license key must be configured"
            )

        from app.services.task_queue_service import get_task_queue_service
        from app.services.tasks import TASK_MAXMIND_UPDATE

        return await get_task_queue_service().enqueue(
            task_name=TASK_MAXMIND_UPDATE,
            payload={"reschedule": reschedule},
            priority=10,
        )

    async def enqueue_update_after_commit(
        self,
        db: AsyncSession,
        *,
        reschedule: bool,
    ) -> str | None:
        """Best-effort enqueue after MaxMind configuration is already durable."""
        try:
            return await self.enqueue_update(db, reschedule=reschedule)
        except Exception:
            await reset_post_commit_session(db, logger)
            logger.exception(
                "MaxMind settings were saved, but the database update could not be enqueued"
            )
            return None

    async def enqueue_next_scheduled_update(self, db: AsyncSession) -> str:
        settings = SettingsService(db)  # type: ignore[arg-type]
        try:
            frequency_hours = float(
                await settings.get(
                    "enrichment.maxmind.update_frequency_hours",
                    24,
                )
                or 24
            )
        except (TypeError, ValueError) as exc:
            raise MaxMindConfigurationError(
                "MaxMind update frequency must be numeric"
            ) from exc
        if not math.isfinite(frequency_hours):
            raise MaxMindConfigurationError(
                "MaxMind update frequency must be finite"
            )
        schedule_at = datetime.now(timezone.utc) + timedelta(hours=max(frequency_hours, 1))

        from app.services.task_queue_service import get_task_queue_service
        from app.services.tasks import TASK_MAXMIND_UPDATE

        return await get_task_queue_service().enqueue(
            task_name=TASK_MAXMIND_UPDATE,
            payload={"reschedule": True},
            priority=10,
            schedule_at=schedule_at,
        )

    @staticmethod
    def _record_network(record: Any) -> str | None:
        network = getattr(record, "network", None)
        return str(network) if network is not None else None

    def _serialize_record(self, edition_id: str, record: Any) -> dict[str, Any]:
        if edition_id in {"GeoLite2-City", "GeoIP2-City", "GeoIP2-Enterprise"}:
            return self._serialize_city_like(record)
        if edition_id in {"GeoLite2-Country", "GeoIP2-Country"}:
            return self._serialize_country_like(record)
        if edition_id == "GeoLite2-ASN":
            return {
                "autonomous_system_number": record.autonomous_system_number,
                "autonomous_system_organization": record.autonomous_system_organization,
                "network": self._record_network(record),
            }
        if edition_id == "GeoIP2-Anonymous-IP":
            return {
                "is_anonymous": record.is_anonymous,
                "is_anonymous_vpn": record.is_anonymous_vpn,
                "is_hosting_provider": record.is_hosting_provider,
                "is_public_proxy": record.is_public_proxy,
                "is_residential_proxy": getattr(record, "is_residential_proxy", None),
                "is_tor_exit_node": record.is_tor_exit_node,
                "network": self._record_network(record),
            }
        if edition_id == "GeoIP2-Connection-Type":
            return {
                "connection_type": record.connection_type,
                "network": self._record_network(record),
            }
        if edition_id == "GeoIP2-Domain":
            return {
                "domain": record.domain,
                "network": self._record_network(record),
            }
        if edition_id == "GeoIP2-ISP":
            return {
                "autonomous_system_number": record.autonomous_system_number,
                "autonomous_system_organization": record.autonomous_system_organization,
                "isp": record.isp,
                "organization": record.organization,
                "mobile_country_code": record.mobile_country_code,
                "mobile_network_code": record.mobile_network_code,
                "network": self._record_network(record),
            }
        return {}

    def _serialize_city_like(self, record: Any) -> dict[str, Any]:
        city = getattr(record, "city", None)
        location = getattr(record, "location", None)
        postal = getattr(record, "postal", None)
        data = self._serialize_country_like(record)
        data.update(
            {
                "city": {"name": getattr(city, "name", None)},
                "location": {
                    "accuracy_radius": getattr(location, "accuracy_radius", None),
                    "latitude": getattr(location, "latitude", None),
                    "longitude": getattr(location, "longitude", None),
                    "metro_code": getattr(location, "metro_code", None),
                    "time_zone": getattr(location, "time_zone", None),
                },
                "postal": {"code": getattr(postal, "code", None)},
                "subdivisions": [
                    {"iso_code": subdivision.iso_code, "name": subdivision.name}
                    for subdivision in getattr(record, "subdivisions", [])
                ],
            }
        )
        return data

    def _serialize_country_like(self, record: Any) -> dict[str, Any]:
        continent = getattr(record, "continent", None)
        country = getattr(record, "country", None)
        registered_country = getattr(record, "registered_country", None)
        represented_country = getattr(record, "represented_country", None)
        traits = getattr(record, "traits", None)
        traits_network = getattr(traits, "network", None)
        return {
            "continent": {
                "code": getattr(continent, "code", None),
                "name": getattr(continent, "name", None),
            },
            "country": {
                "iso_code": getattr(country, "iso_code", None),
                "name": getattr(country, "name", None),
            },
            "registered_country": {
                "iso_code": getattr(registered_country, "iso_code", None),
                "name": getattr(registered_country, "name", None),
            },
            "represented_country": {
                "iso_code": getattr(represented_country, "iso_code", None),
                "name": getattr(represented_country, "name", None),
            },
            "traits": {
                "network": str(traits_network) if traits_network is not None else None,
                "autonomous_system_number": getattr(
                    traits,
                    "autonomous_system_number",
                    None,
                ),
                "autonomous_system_organization": getattr(
                    traits,
                    "autonomous_system_organization",
                    None,
                ),
                "user_type": getattr(traits, "user_type", None),
            },
        }


maxmind_service = MaxMindService()
