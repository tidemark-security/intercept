"""Object storage configuration for file uploads."""

from typing import List
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageConfig(BaseSettings):
    """Object storage configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")
    
    # Connection settings
    storage_endpoint: str = Field(
        default="localhost:9000",
        validation_alias=AliasChoices("STORAGE_ENDPOINT", "MINIO_ENDPOINT"),
        description="MinIO/S3 endpoint URL"
    )
    storage_access_key: str = Field(
        default="minioadmin",
        validation_alias=AliasChoices("STORAGE_ACCESS_KEY", "MINIO_ACCESS_KEY"),
        description="Storage access key"
    )
    storage_secret_key: str = Field(
        default="minioadmin",
        validation_alias=AliasChoices("STORAGE_SECRET_KEY", "MINIO_SECRET_KEY"),
        description="Storage secret key"
    )
    storage_bucket: str = Field(
        default="intercept-attachments",
        validation_alias=AliasChoices("STORAGE_BUCKET", "MINIO_BUCKET"),
        description="Storage bucket name"
    )
    storage_use_ssl: bool = Field(
        default=False,  # True in production
        validation_alias=AliasChoices("STORAGE_USE_SSL", "MINIO_USE_SSL"),
        description="Use SSL for storage connections"
    )
    storage_region: str = Field(
        default="us-east-1",
        validation_alias=AliasChoices("STORAGE_REGION", "MINIO_REGION"),
        description="Storage region"
    )
    
    # File validation settings
    allowed_file_types: List[str] = Field(
        default=[
            # Images
            "image/png", "image/jpeg", "image/gif", "image/webp",
            "image/svg+xml", "image/bmp", "image/tiff",
            # Documents
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            # Text / data
            "text/plain", "application/json", "text/csv",
            "text/html", "text/markdown", "application/xml",
            # Archives
            "application/zip", "application/x-7z-compressed",
            "application/gzip", "application/x-tar",
            # Forensics / network captures
            "application/vnd.tcpdump.pcap",
            # Generic binary (e.g. memory dumps, firmware)
            "application/octet-stream",
        ],
        description="Comma-separated list of allowed MIME types"
    )
    max_upload_size_mb: int = Field(
        default=50,
        description="Maximum upload size in megabytes"
    )
    
    # URL expiration settings
    upload_timeout_minutes: int = Field(
        default=15,
        description="Presigned upload URL expiration time in minutes"
    )
    download_timeout_minutes: int = Field(
        default=30,
        description="Presigned download URL expiration time in minutes"
    )
    
    @field_validator('allowed_file_types', mode='before')
    @classmethod
    def parse_allowed_types(cls, v):
        """Parse comma-separated string to list."""
        if isinstance(v, str):
            return [t.strip() for t in v.split(',')]
        return v
    
# Global storage config instance
storage_config = StorageConfig()
