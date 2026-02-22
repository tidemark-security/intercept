"""Service for handling file uploads to object storage (MinIO/S3)."""

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, BinaryIO
import asyncio
from concurrent.futures import ThreadPoolExecutor

from minio import Minio
from minio.error import S3Error

from app.core.storage_config import storage_config

logger = logging.getLogger(__name__)

# Thread pool for blocking MinIO operations
_executor = ThreadPoolExecutor(max_workers=10)


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
        # Ensure bucket exists before generating URL
        self._ensure_bucket_exists()
        
        if expires_minutes is None:
            expires_minutes = storage_config.upload_timeout_minutes
        
        expiry = timedelta(minutes=expires_minutes)
        
        # Run blocking MinIO call in thread pool
        loop = asyncio.get_event_loop()
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
        expires_minutes: Optional[int] = None
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
        
        # Run blocking MinIO call in thread pool
        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(
            _executor,
            lambda: self.client.presigned_get_object(
                self.bucket_name,
                storage_key,
                expires=expiry
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
            loop = asyncio.get_event_loop()
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
    
    async def delete_file(self, storage_key: str) -> None:
        """
        Delete a file from storage.
        
        Args:
            storage_key: Object storage key (path)
        """
        try:
            loop = asyncio.get_event_loop()
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
        return mime_type in storage_config.allowed_file_types
    
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
