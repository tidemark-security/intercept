"""Service for handling file uploads to object storage (MinIO/S3)."""

import base64
import binascii
import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from typing import Optional, BinaryIO
import asyncio
from concurrent.futures import ThreadPoolExecutor

from minio import Minio
from minio.commonconfig import CopySource
from minio.error import S3Error

from app.core.storage_config import storage_config

logger = logging.getLogger(__name__)

# Thread pool for blocking MinIO operations
_executor = ThreadPoolExecutor(max_workers=10)
SCRIPT_CAPABLE_MIME_TYPES = {"text/html", "image/svg+xml", "application/xhtml+xml"}
MIME_SNIFF_BYTES = 1024 * 1024
_magika = None


@dataclass(frozen=True)
class ObjectMetadata:
    """Object metadata needed for attachment finalization."""

    size: int
    content_type: str | None
    sha256: str | None


class StorageService:
    """Service for object storage operations using MinIO/S3."""
    
    def __init__(self):
        """Initialize MinIO client with configuration from environment."""
        self.client = Minio(
            storage_config.storage_endpoint,
            access_key=storage_config.storage_access_key,
            secret_key=storage_config.storage_secret_key,
            secure=storage_config.storage_use_ssl,
            region=storage_config.storage_region
        )
        self.bucket_name = storage_config.storage_bucket
        # Don't ensure bucket exists at initialization - do it lazily
        self._bucket_checked = False
    
    def _ensure_bucket_exists(self) -> None:
        """Ensure the storage bucket exists, create if not."""
        if self._bucket_checked:
            return
            
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created storage bucket: {self.bucket_name}")
            self._bucket_checked = True
        except S3Error as e:
            logger.error(f"Failed to create bucket {self.bucket_name}: {e}")
            raise
    
    async def generate_presigned_upload_url(
        self,
        storage_key: str,
        expires_minutes: Optional[int] = None
    ) -> str:
        """
        Generate a presigned PUT URL for direct upload to storage.
        
        Args:
            storage_key: Object storage key (path)
            expires_minutes: URL expiration time in minutes (defaults to config)
        
        Returns:
            Presigned PUT URL
        """
        # Ensure bucket exists before generating URL (run in executor to avoid blocking)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._ensure_bucket_exists)
        
        if expires_minutes is None:
            expires_minutes = storage_config.upload_timeout_minutes
        
        expiry = timedelta(minutes=expires_minutes)
        
        # Run blocking MinIO call in thread pool
        url = await loop.run_in_executor(
            _executor,
            lambda: self.client.presigned_put_object(
                self.bucket_name,
                storage_key,
                expires=expiry
            )
        )
        
        logger.info(
            f"Generated presigned upload URL for {storage_key}, "
            f"expires in {expires_minutes} minutes"
        )
        return url
    
    async def generate_presigned_download_url(
        self,
        storage_key: str,
        expires_minutes: Optional[int] = None,
        filename: Optional[str] = None,
        as_attachment: bool = False,
    ) -> str:
        """
        Generate a presigned GET URL for direct download from storage.
        
        Args:
            storage_key: Object storage key (path)
            expires_minutes: URL expiration time in minutes (defaults to config)
        
        Returns:
            Presigned GET URL
        """
        if expires_minutes is None:
            expires_minutes = storage_config.download_timeout_minutes
        
        expiry = timedelta(minutes=expires_minutes)
        response_headers = None

        if as_attachment:
            safe_filename = self.sanitize_filename(filename or storage_key.rsplit('/', 1)[-1] or 'download')
            encoded_filename = quote(safe_filename)
            response_headers = {
                'response-content-disposition': (
                    f'attachment; filename="{safe_filename}"; '
                    f"filename*=UTF-8''{encoded_filename}"
                )
            }
        
        # Run blocking MinIO call in thread pool
        loop = asyncio.get_running_loop()
        url = await loop.run_in_executor(
            _executor,
            lambda: self.client.presigned_get_object(
                self.bucket_name,
                storage_key,
                expires=expiry,
                response_headers=response_headers,
            )
        )
        
        logger.info(
            f"Generated presigned download URL for {storage_key}, "
            f"expires in {expires_minutes} minutes"
        )
        return url
    
    async def verify_file_exists(self, storage_key: str) -> bool:
        """
        Verify that a file exists in storage.
        
        Args:
            storage_key: Object storage key (path)
        
        Returns:
            True if file exists, False otherwise
        """
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                _executor,
                lambda: self.client.stat_object(self.bucket_name, storage_key)
            )
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            logger.error(f"Error checking file existence for {storage_key}: {e}")
            raise

    @staticmethod
    def _get_header(headers: object, name: str) -> str | None:
        """Return a header value from urllib3/HTTPHeaderDict or a plain mapping."""
        if not headers:
            return None
        getter = getattr(headers, "get", None)
        if getter:
            value = getter(name)
            if value is not None:
                return str(value)
            value = getter(name.lower())
            if value is not None:
                return str(value)
        if isinstance(headers, dict):
            wanted = name.lower()
            for key, value in headers.items():
                if str(key).lower() == wanted:
                    return str(value)
        return None

    @classmethod
    def _checksum_sha256_hex(cls, headers: object) -> str | None:
        """Convert S3's base64 SHA256 checksum metadata to lowercase hex."""
        checksum = cls._get_header(headers, "x-amz-checksum-sha256")
        if not checksum:
            return None
        checksum = checksum.strip()
        if len(checksum) == 64 and all(char in "0123456789abcdefABCDEF" for char in checksum):
            return checksum.lower()
        try:
            raw = base64.b64decode(checksum, validate=True)
        except (binascii.Error, ValueError):
            return None
        if len(raw) != 32:
            return None
        return raw.hex()

    async def get_object_metadata(self, storage_key: str, *, require_checksum: bool = False) -> ObjectMetadata:
        """Read object size, content type, and optional storage checksum without fetching the body."""
        def _stat() -> ObjectMetadata:
            extra_headers = {"x-amz-checksum-mode": "ENABLED"} if require_checksum else None
            stat = self.client.stat_object(
                self.bucket_name,
                storage_key,
                extra_headers=extra_headers,
            )
            return ObjectMetadata(
                size=int(stat.size or 0),
                content_type=stat.content_type,
                sha256=self._checksum_sha256_hex(stat.metadata),
            )

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _stat)

    async def copy_object(self, source_key: str, destination_key: str) -> None:
        """Copy an object inside the bucket without streaming it through the app."""
        def _copy() -> None:
            source = CopySource(self.bucket_name, source_key)
            headers = source.gen_copy_headers()
            headers["x-amz-checksum-algorithm"] = "SHA256"
            self.client._execute(  # pylint: disable=protected-access
                "PUT",
                self.bucket_name,
                object_name=destination_key,
                headers=headers,
            )

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, _copy)

    async def get_object_bytes(self, storage_key: str, *, max_bytes: int | None = None) -> bytes:
        """Read an object from storage for server-side validation."""
        if max_bytes is not None and max_bytes <= 0:
            return b""

        def _read() -> bytes:
            response = self.client.get_object(
                self.bucket_name,
                storage_key,
                offset=0,
                length=max_bytes if max_bytes is not None else 0,
            )
            try:
                data = response.read()
            finally:
                response.close()
                response.release_conn()
            return data

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _read)

    async def detect_mime_type(self, storage_key: str) -> str:
        """Detect an object's MIME type with Magika."""
        data = await self.get_object_bytes(storage_key, max_bytes=MIME_SNIFF_BYTES)
        return await self.detect_mime_type_from_bytes(data)

    async def detect_mime_type_from_bytes(self, data: bytes) -> str:
        """Detect a byte buffer's MIME type with Magika."""
        def _detect() -> str:
            global _magika
            if _magika is None:
                from magika import Magika

                _magika = Magika()
            result = _magika.identify_bytes(data)
            return str(result.output.mime_type)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _detect)
    
    async def delete_file(self, storage_key: str) -> None:
        """
        Delete a file from storage.
        
        Args:
            storage_key: Object storage key (path)
        """
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                _executor,
                lambda: self.client.remove_object(self.bucket_name, storage_key)
            )
            logger.info(f"Deleted file from storage: {storage_key}")
        except S3Error as e:
            logger.error(f"Failed to delete file {storage_key}: {e}")
            raise
    
    def validate_file_type(self, mime_type: str) -> bool:
        """
        Validate that a MIME type is in the allowed list.
        
        Args:
            mime_type: MIME type to validate
        
        Returns:
            True if allowed, False otherwise
        """
        normalized = (mime_type or "").strip().lower()
        if not normalized or normalized in SCRIPT_CAPABLE_MIME_TYPES:
            return False
        return normalized in {item.lower() for item in storage_config.allowed_file_types}
    
    def validate_file_size(self, file_size: int) -> bool:
        """
        Validate that a file size is within the allowed limit.
        
        Args:
            file_size: File size in bytes
        
        Returns:
            True if within limit, False otherwise
        """
        max_size_bytes = storage_config.max_upload_size_mb * 1024 * 1024
        return file_size <= max_size_bytes
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize a filename to prevent path traversal attacks.
        
        Args:
            filename: Original filename
        
        Returns:
            Sanitized filename
        """
        # Remove path separators and dangerous sequences
        sanitized = filename.replace('/', '').replace('\\', '').replace('..', '')
        sanitized = sanitized.replace('"', '').replace('\r', '').replace('\n', '').replace('\x00', '')
        # Remove any remaining directory components
        sanitized = sanitized.split('/')[-1].split('\\')[-1]
        return sanitized
    
    @staticmethod
    def generate_storage_key(parent_id: int, item_id: str, filename: str, parent_type: str = "alerts") -> str:
        """
        Generate a storage key (path) for a file.
        
        Args:
            parent_id: Alert or Case ID
            item_id: Timeline item ID
            filename: Sanitized filename
            parent_type: Type of parent ("alerts" or "cases")
        
        Returns:
            Storage key in format: {parent_type}/{parent_id}/attachments/{item_id}/{uuid}.{ext}
        """
        # Generate unique filename to prevent collisions
        unique_id = str(uuid.uuid4())
        
        # Preserve file extension
        if '.' in filename:
            ext = filename.rsplit('.', 1)[1]
            unique_filename = f"{unique_id}.{ext}"
        else:
            unique_filename = unique_id
        
        return f"{parent_type}/{parent_id}/attachments/{item_id}/{unique_filename}"

    @staticmethod
    def generate_upload_storage_key(parent_id: int, item_id: str, parent_type: str = "alerts") -> str:
        """Generate a temporary staging key for a direct client upload."""
        return f"_uploads/{parent_type}/{parent_id}/attachments/{item_id}/{uuid.uuid4()}"
    
    @staticmethod
    def calculate_file_hash(file_data: bytes) -> str:
        """
        Calculate SHA256 hash of file data.
        
        Args:
            file_data: File binary data
        
        Returns:
            Hex-encoded SHA256 hash
        """
        return hashlib.sha256(file_data).hexdigest()


# Global storage service instance
storage_service = StorageService()
