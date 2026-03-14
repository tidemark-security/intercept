from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import tarfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import geoip2.database
import httpx
from geoip2.errors import AddressNotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage_config import storage_config
from app.services.settings_service import SettingsService
from app.services.storage_service import storage_service

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


@dataclass(slots=True)
class _ReaderState:
    reader: geoip2.database.Reader
    path: str
    mtime_ns: int


class MaxMindService:
    def __init__(self) -> None:
        self._reader_lock = asyncio.Lock()
        self._readers: dict[str, _ReaderState] = {}

    def parse_geoip_conf(self, text: str) -> Dict[str, Any]:
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
            raise ValueError("GeoIP.conf is missing AccountID")
        if not license_key:
            raise ValueError("GeoIP.conf is missing LicenseKey")
        if not edition_ids:
            raise ValueError("GeoIP.conf is missing EditionIDs")
        unsupported = [edition for edition in edition_ids if edition not in SUPPORTED_EDITIONS]
        if unsupported:
            raise ValueError(f"Unsupported MaxMind edition IDs: {', '.join(unsupported)}")

        return {
            "account_id": account_id,
            "license_key": license_key,
            "edition_ids": edition_ids,
        }

    def serialize_edition_ids(self, edition_ids: Iterable[str]) -> str:
        return json.dumps(list(edition_ids))

    async def _get_settings(
        self,
        db: AsyncSession,
        *,
        strict_editions: bool = True,
    ) -> tuple[SettingsService, dict[str, Any]]:
        settings = SettingsService(db)  # type: ignore[arg-type]
        edition_ids = await settings.get("enrichment.maxmind.edition_ids", ["GeoLite2-ASN", "GeoLite2-City", "GeoLite2-Country"])
        if isinstance(edition_ids, str):
            try:
                edition_ids = json.loads(edition_ids)
            except json.JSONDecodeError:
                edition_ids = [item.strip() for item in edition_ids.split(",") if item.strip()]

        normalized_editions = [str(item).strip() for item in edition_ids or [] if str(item).strip()]
        unsupported = [edition for edition in normalized_editions if edition not in SUPPORTED_EDITIONS]
        if unsupported:
            if strict_editions:
                raise ValueError(f"Unsupported MaxMind edition IDs: {', '.join(unsupported)}")
            logger.warning("Ignoring unsupported MaxMind edition IDs: %s", ", ".join(unsupported))

        supported_editions = [edition for edition in normalized_editions if edition in SUPPORTED_EDITIONS]

        return settings, {
            "account_id": str(await settings.get("enrichment.maxmind.account_id", "") or ""),
            "license_key": str(await settings.get("enrichment.maxmind.license_key", "") or ""),
            "edition_ids": supported_editions if not strict_editions else normalized_editions,
            "storage_prefix": str(await settings.get("enrichment.maxmind.storage_prefix", "maxmind/") or "maxmind/"),
            "local_cache_dir": str(await settings.get("enrichment.maxmind.local_cache_dir", "/tmp/tmi-maxmind") or "/tmp/tmi-maxmind"),
            "ttl_seconds": int(await settings.get("enrichment.maxmind.ttl_seconds", 604800) or 604800),
            "update_frequency_hours": float(await settings.get("enrichment.maxmind.update_frequency_hours", 24) or 24),
        }

    def _storage_key(self, prefix: str, edition_id: str) -> str:
        return f"{prefix.rstrip('/')}/{edition_id}.mmdb"

    def _metadata_key(self, prefix: str, edition_id: str) -> str:
        return f"{prefix.rstrip('/')}/{edition_id}.json"

    def _local_db_path(self, local_cache_dir: str, edition_id: str) -> Path:
        return Path(local_cache_dir) / f"{edition_id}.mmdb"

    def _local_meta_path(self, local_cache_dir: str, edition_id: str) -> Path:
        return Path(local_cache_dir) / f"{edition_id}.json"

    async def _ensure_bucket(self) -> None:
        await asyncio.to_thread(storage_service._ensure_bucket_exists)

    async def _put_object(self, key: str, data: bytes, content_type: str) -> None:
        await self._ensure_bucket()
        await asyncio.to_thread(
            storage_service.client.put_object,
            storage_config.storage_bucket,
            key,
            BytesIO(data),
            len(data),
            content_type=content_type,
        )

    async def _get_object_bytes(self, key: str) -> Optional[bytes]:
        try:
            await self._ensure_bucket()
        except Exception as exc:
            logger.warning("MaxMind storage unavailable while reading %s: %s", key, exc)
            return None

        def _read() -> Optional[bytes]:
            response = None
            try:
                response = storage_service.client.get_object(storage_config.storage_bucket, key)
                return response.read()
            except Exception:
                return None
            finally:
                if response is not None:
                    response.close()
                    response.release_conn()

        return await asyncio.to_thread(_read)

    async def _stat_object(self, key: str) -> Any:
        try:
            await self._ensure_bucket()
        except Exception as exc:
            logger.warning("MaxMind storage unavailable while checking %s: %s", key, exc)
            return None

        def _stat() -> Any:
            try:
                return storage_service.client.stat_object(storage_config.storage_bucket, key)
            except Exception:
                return None

        return await asyncio.to_thread(_stat)

    async def _load_metadata(self, prefix: str, edition_id: str) -> dict[str, Any]:
        metadata_bytes = await self._get_object_bytes(self._metadata_key(prefix, edition_id))
        if not metadata_bytes:
            return {}
        try:
            return json.loads(metadata_bytes.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning("Invalid MaxMind metadata JSON for %s", edition_id)
            return {}

    async def _save_metadata(self, prefix: str, edition_id: str, metadata: dict[str, Any]) -> None:
        payload = json.dumps(metadata, sort_keys=True).encode("utf-8")
        await self._put_object(self._metadata_key(prefix, edition_id), payload, "application/json")

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

    def _extract_mmdb_from_tar(self, archive_bytes: bytes, edition_id: str) -> tuple[bytes, str]:
        with tarfile.open(fileobj=BytesIO(archive_bytes), mode="r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile() or not member.name.endswith(".mmdb"):
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                return extracted.read(), member.name.split("/")[-1]
        raise ValueError(f"Downloaded archive for {edition_id} did not contain an .mmdb file")

    async def download_databases(self, db: AsyncSession) -> dict[str, Any]:
        settings, cfg = await self._get_settings(db)
        account_id = cfg["account_id"]
        license_key = cfg["license_key"]
        edition_ids = cfg["edition_ids"]
        prefix = cfg["storage_prefix"]

        if not account_id or not license_key:
            raise ValueError("MaxMind account ID and license key must be configured before downloading databases")
        if not edition_ids:
            raise ValueError("At least one MaxMind edition must be configured")

        results: dict[str, Any] = {}
        auth = (account_id, license_key)

        async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
            for edition_id in edition_ids:
                try:
                    current_metadata = await self._load_metadata(prefix, edition_id)
                    headers: dict[str, str] = {}
                    if current_metadata.get("source_last_modified"):
                        headers["If-Modified-Since"] = str(current_metadata["source_last_modified"])

                    download_url = MAXMIND_DOWNLOAD_URL.format(edition_id=edition_id)
                    response = await client.get(download_url, auth=auth, headers=headers)
                    if response.status_code == 304:
                        results[edition_id] = {"status": "unchanged"}
                        continue
                    response.raise_for_status()

                    sha_response = await client.get(MAXMIND_SHA256_URL.format(edition_id=edition_id), auth=auth)
                    sha_response.raise_for_status()
                    expected_sha256 = sha_response.text.strip().split()[0]
                    archive_bytes = response.content
                    archive_sha256 = self._sha256_bytes(archive_bytes)
                    if expected_sha256 and archive_sha256.lower() != expected_sha256.lower():
                        raise ValueError(f"SHA256 mismatch for {edition_id}")

                    mmdb_bytes, extracted_name = self._extract_mmdb_from_tar(archive_bytes, edition_id)
                    content_sha256 = self._sha256_bytes(mmdb_bytes)
                    await self._put_object(
                        self._storage_key(prefix, edition_id),
                        mmdb_bytes,
                        "application/octet-stream",
                    )

                    now = datetime.now(timezone.utc)
                    metadata = {
                        "edition_id": edition_id,
                        "downloaded_at": now.isoformat(),
                        "source_last_modified": response.headers.get("last-modified"),
                        "archive_sha256": archive_sha256,
                        "content_sha256": content_sha256,
                        "extracted_name": extracted_name,
                        "file_size_bytes": len(mmdb_bytes),
                    }
                    await self._save_metadata(prefix, edition_id, metadata)
                    results[edition_id] = {
                        "status": "updated",
                        "content_sha256": content_sha256,
                        "file_size_bytes": len(mmdb_bytes),
                    }
                except Exception as exc:
                    logger.warning("Failed MaxMind download for %s: %s", edition_id, exc)
                    results[edition_id] = {"status": "error", "error": str(exc)}

        return results

    async def sync_local_cache(self, *, settings: SettingsService) -> list[str]:
        edition_ids = await settings.get("enrichment.maxmind.edition_ids", [])
        if isinstance(edition_ids, str):
            try:
                edition_ids = json.loads(edition_ids)
            except json.JSONDecodeError:
                edition_ids = [item.strip() for item in edition_ids.split(",") if item.strip()]
        prefix = str(await settings.get("enrichment.maxmind.storage_prefix", "maxmind/") or "maxmind/")
        local_cache_dir = Path(str(await settings.get("enrichment.maxmind.local_cache_dir", "/tmp/tmi-maxmind") or "/tmp/tmi-maxmind"))
        local_cache_dir.mkdir(parents=True, exist_ok=True)

        synced: list[str] = []
        for edition_id in [str(item).strip() for item in edition_ids or [] if str(item).strip()]:
            metadata = await self._load_metadata(prefix, edition_id)
            object_bytes = await self._get_object_bytes(self._storage_key(prefix, edition_id))
            if not object_bytes:
                continue

            db_path = self._local_db_path(str(local_cache_dir), edition_id)
            meta_path = self._local_meta_path(str(local_cache_dir), edition_id)
            desired_hash = metadata.get("content_sha256") or self._sha256_bytes(object_bytes)
            current_hash = self._sha256_path(db_path) if db_path.exists() else None
            if current_hash == desired_hash and meta_path.exists():
                continue

            db_path.write_bytes(object_bytes)
            meta_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
            synced.append(edition_id)

        return synced

    async def ensure_readers_loaded(self, *, settings: SettingsService) -> None:
        edition_ids = await settings.get("enrichment.maxmind.edition_ids", [])
        if isinstance(edition_ids, str):
            try:
                edition_ids = json.loads(edition_ids)
            except json.JSONDecodeError:
                edition_ids = [item.strip() for item in edition_ids.split(",") if item.strip()]
        local_cache_dir = str(await settings.get("enrichment.maxmind.local_cache_dir", "/tmp/tmi-maxmind") or "/tmp/tmi-maxmind")
        desired_editions = {str(item).strip() for item in edition_ids or [] if str(item).strip()}

        if any(not self._local_db_path(local_cache_dir, edition_id).exists() for edition_id in desired_editions):
            await self.sync_local_cache(settings=settings)

        async with self._reader_lock:
            current_editions = set(self._readers)

            for removed in current_editions - desired_editions:
                state = self._readers.pop(removed, None)
                if state is not None:
                    await asyncio.to_thread(state.reader.close)

            for edition_id in desired_editions:
                db_path = self._local_db_path(local_cache_dir, edition_id)
                if not db_path.exists():
                    continue

                mtime_ns = db_path.stat().st_mtime_ns
                existing = self._readers.get(edition_id)
                if existing is not None and existing.path == str(db_path) and existing.mtime_ns == mtime_ns:
                    continue

                reader = await asyncio.to_thread(geoip2.database.Reader, str(db_path))
                self._readers[edition_id] = _ReaderState(reader=reader, path=str(db_path), mtime_ns=mtime_ns)
                if existing is not None:
                    await asyncio.to_thread(existing.reader.close)

    async def close_readers(self) -> None:
        async with self._reader_lock:
            readers = list(self._readers.values())
            self._readers.clear()
        for state in readers:
            await asyncio.to_thread(state.reader.close)

    async def lookup_ip(self, ip: str) -> Dict[str, Any]:
        ipaddress.ip_address(ip)

        async with self._reader_lock:
            readers = [(edition_id, state.reader) for edition_id, state in self._readers.items()]

        databases: dict[str, Any] = {}
        for edition_id, reader in readers:
            method_name = SUPPORTED_EDITIONS.get(edition_id)
            if not method_name:
                continue
            try:
                result = await asyncio.to_thread(getattr(reader, method_name), ip)
            except AddressNotFoundError:
                continue
            except Exception as exc:
                logger.debug("MaxMind lookup failed for %s with %s: %s", ip, edition_id, exc)
                continue
            serialized = self._serialize_record(edition_id, result)
            if serialized:
                databases[edition_id] = serialized

        return {
            "ip": ip,
            "databases": databases,
            "queried_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_database_status(self, db: AsyncSession) -> list[dict[str, Any]]:
        settings, cfg = await self._get_settings(db, strict_editions=False)
        storage_available = True
        try:
            await self._ensure_bucket()
        except Exception as exc:
            storage_available = False
            logger.warning("MaxMind storage unavailable while loading database status: %s", exc)

        if storage_available:
            await self.ensure_readers_loaded(settings=settings)

        statuses: list[dict[str, Any]] = []
        local_cache_dir = cfg["local_cache_dir"]
        prefix = cfg["storage_prefix"]

        async with self._reader_lock:
            loaded_editions = set(self._readers)

        for edition_id in cfg["edition_ids"]:
            metadata: dict[str, Any] = {}
            object_stat = None
            if storage_available:
                metadata = await self._load_metadata(prefix, edition_id)
                object_stat = await self._stat_object(self._storage_key(prefix, edition_id))
            local_path = self._local_db_path(local_cache_dir, edition_id)
            last_updated = metadata.get("downloaded_at")
            statuses.append(
                {
                    "edition_id": edition_id,
                    "available_in_storage": object_stat is not None,
                    "loaded": edition_id in loaded_editions,
                    "local_path": str(local_path) if local_path.exists() else None,
                    "file_size_bytes": int(metadata.get("file_size_bytes") or 0) or (local_path.stat().st_size if local_path.exists() else None),
                    "last_updated": datetime.fromisoformat(last_updated) if isinstance(last_updated, str) else None,
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
            raise ValueError("MaxMind provider is disabled")
        if not account_id or not license_key:
            raise ValueError("MaxMind account ID and license key must be configured")

        from app.services.task_queue_service import get_task_queue_service
        from app.services.tasks import TASK_MAXMIND_UPDATE

        return await get_task_queue_service().enqueue(
            task_name=TASK_MAXMIND_UPDATE,
            payload={"reschedule": reschedule},
            priority=10,
        )

    async def enqueue_next_scheduled_update(self, db: AsyncSession) -> str:
        settings = SettingsService(db)  # type: ignore[arg-type]
        frequency_hours = float(await settings.get("enrichment.maxmind.update_frequency_hours", 24) or 24)
        schedule_at = datetime.now(timezone.utc) + timedelta(hours=max(frequency_hours, 1))

        from app.services.task_queue_service import get_task_queue_service
        from app.services.tasks import TASK_MAXMIND_UPDATE

        return await get_task_queue_service().enqueue(
            task_name=TASK_MAXMIND_UPDATE,
            payload={"reschedule": True},
            priority=10,
            schedule_at=schedule_at,
        )

    def _serialize_record(self, edition_id: str, record: Any) -> Dict[str, Any]:
        if edition_id in {"GeoLite2-City", "GeoIP2-City", "GeoIP2-Enterprise"}:
            return self._serialize_city_like(record)
        if edition_id in {"GeoLite2-Country", "GeoIP2-Country"}:
            return self._serialize_country_like(record)
        if edition_id == "GeoLite2-ASN":
            return {
                "autonomous_system_number": record.autonomous_system_number,
                "autonomous_system_organization": record.autonomous_system_organization,
                "network": str(record.network) if getattr(record, "network", None) else None,
            }
        if edition_id == "GeoIP2-Anonymous-IP":
            return {
                "is_anonymous": record.is_anonymous,
                "is_anonymous_vpn": record.is_anonymous_vpn,
                "is_hosting_provider": record.is_hosting_provider,
                "is_public_proxy": record.is_public_proxy,
                "is_residential_proxy": getattr(record, "is_residential_proxy", None),
                "is_tor_exit_node": record.is_tor_exit_node,
                "network": str(record.network) if getattr(record, "network", None) else None,
            }
        if edition_id == "GeoIP2-Connection-Type":
            return {
                "connection_type": record.connection_type,
                "network": str(record.network) if getattr(record, "network", None) else None,
            }
        if edition_id == "GeoIP2-Domain":
            return {
                "domain": record.domain,
                "network": str(record.network) if getattr(record, "network", None) else None,
            }
        if edition_id == "GeoIP2-ISP":
            return {
                "autonomous_system_number": record.autonomous_system_number,
                "autonomous_system_organization": record.autonomous_system_organization,
                "isp": record.isp,
                "organization": record.organization,
                "mobile_country_code": record.mobile_country_code,
                "mobile_network_code": record.mobile_network_code,
                "network": str(record.network) if getattr(record, "network", None) else None,
            }
        return {}

    def _serialize_city_like(self, record: Any) -> Dict[str, Any]:
        data = self._serialize_country_like(record)
        data.update(
            {
                "city": {"name": getattr(getattr(record, "city", None), "name", None)},
                "location": {
                    "accuracy_radius": getattr(getattr(record, "location", None), "accuracy_radius", None),
                    "latitude": getattr(getattr(record, "location", None), "latitude", None),
                    "longitude": getattr(getattr(record, "location", None), "longitude", None),
                    "metro_code": getattr(getattr(record, "location", None), "metro_code", None),
                    "time_zone": getattr(getattr(record, "location", None), "time_zone", None),
                },
                "postal": {"code": getattr(getattr(record, "postal", None), "code", None)},
                "subdivisions": [
                    {"iso_code": subdivision.iso_code, "name": subdivision.name}
                    for subdivision in getattr(record, "subdivisions", [])
                ],
            }
        )
        return data

    def _serialize_country_like(self, record: Any) -> Dict[str, Any]:
        return {
            "continent": {
                "code": getattr(getattr(record, "continent", None), "code", None),
                "name": getattr(getattr(record, "continent", None), "name", None),
            },
            "country": {
                "iso_code": getattr(getattr(record, "country", None), "iso_code", None),
                "name": getattr(getattr(record, "country", None), "name", None),
            },
            "registered_country": {
                "iso_code": getattr(getattr(record, "registered_country", None), "iso_code", None),
                "name": getattr(getattr(record, "registered_country", None), "name", None),
            },
            "represented_country": {
                "iso_code": getattr(getattr(record, "represented_country", None), "iso_code", None),
                "name": getattr(getattr(record, "represented_country", None), "name", None),
            },
            "traits": {
                "network": str(getattr(getattr(record, "traits", None), "network", None)) if getattr(getattr(record, "traits", None), "network", None) else None,
                "autonomous_system_number": getattr(getattr(record, "traits", None), "autonomous_system_number", None),
                "autonomous_system_organization": getattr(getattr(record, "traits", None), "autonomous_system_organization", None),
                "user_type": getattr(getattr(record, "traits", None), "user_type", None),
            },
        }


maxmind_service = MaxMindService()