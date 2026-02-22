"""Object storage configuration for file uploads."""

from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class StorageConfig(BaseSettings):
    """Object storage configuration loaded from environment variables."""
    
    # Connection settings
    storage_endpoint: str = Field(
        default="localhost:9000",
        description="MinIO/S3 endpoint URL"
    )
    storage_access_key: str = Field(
        default="minioadmin",
        description="Storage access key"
    )
    storage_secret_key: str = Field(
        default="minioadmin",
        description="Storage secret key"
    )
    storage_bucket: str = Field(
        default="intercept-attachments",
        description="Storage bucket name"
    )
    storage_use_ssl: bool = Field(
        default=False,  # True in production
        description="Use SSL for storage connections"
    )
    storage_region: str = Field(
        default="us-east-1",
        description="Storage region"
    )
    
    # File validation settings
    allowed_file_types: List[str] = Field(
        default=[
            "image/png", "image/jpeg", "image/gif", "image/webp",
            "application/pdf",
            "text/plain", "application/json", "text/csv",
            "application/zip", "application/x-7z-compressed",
            "application/gzip", "application/vnd.tcpdump.pcap"
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
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global storage config instance
storage_config = StorageConfig()
