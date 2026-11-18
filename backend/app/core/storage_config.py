"""Object storage configuration for file uploads."""

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
    storage_access_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("STORAGE_ACCESS_KEY", "MINIO_ACCESS_KEY"),
        description="Storage access key. Leave blank to use AWS autodiscovered credentials."
    )
    storage_secret_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("STORAGE_SECRET_KEY", "MINIO_SECRET_KEY"),
        description="Storage secret key. Leave blank to use AWS autodiscovered credentials."
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
    storage_auto_create_bucket: bool = Field(
        default=True,
        validation_alias=AliasChoices("STORAGE_AUTO_CREATE_BUCKET", "MINIO_AUTO_CREATE_BUCKET"),
        description="Create the storage bucket lazily if it does not exist"
    )

    @field_validator("storage_access_key", "storage_secret_key", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        """Treat blank credential env vars the same as unset env vars."""
        if isinstance(value, str) and not value.strip():
            return None
        return value
    
    # URL expiration settings
    upload_timeout_minutes: int = Field(
        default=15,
        description="Presigned upload URL expiration time in minutes"
    )
    download_timeout_minutes: int = Field(
        default=30,
        description="Presigned download URL expiration time in minutes"
    )
    
# Global storage config instance
storage_config = StorageConfig()
