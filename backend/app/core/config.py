from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.security.password_hasher import Argon2Parameters


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Allow extra fields from .env without validation errors
    )
    
    # Database
    database_url: str = "postgresql+asyncpg://intercept_user:intercept_password@localhost:5432/intercept_case_db"
    
    # OpenID Connect
    openid_connect_url: str = "http://localhost:8080/auth/realms/intercept-case"
    oidc_client_id: str = "intercept-case-backend"
    oidc_client_secret: str = "your-client-secret-here"
    
    # Security
    secret_key: str = "your-super-secret-key-change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Session cookie + timeout configuration
    session_cookie_name: str = Field(
        default="intercept_session",
        validation_alias="SESSION_COOKIE_NAME",
    )
    session_cookie_domain: Optional[str] = Field(
        default=None,
        validation_alias="SESSION_COOKIE_DOMAIN",
    )
    session_cookie_path: str = Field(
        default="/",
        validation_alias="SESSION_COOKIE_PATH",
    )
    session_cookie_secure: bool = Field(
        default=True,
        validation_alias="SESSION_COOKIE_SECURE",
    )
    session_cookie_http_only: bool = Field(
        default=True,
        validation_alias="SESSION_COOKIE_HTTP_ONLY",
    )
    session_cookie_same_site: Literal["lax", "strict", "none"] = Field(
        default="lax",
        validation_alias="SESSION_COOKIE_SAME_SITE",
    )
    session_idle_timeout_hours: int = Field(
        default=12,
        ge=1,
        validation_alias="SESSION_IDLE_TIMEOUT_HOURS",
    )
    session_absolute_timeout_hours: int = Field(
        default=48,
        ge=1,
        validation_alias="SESSION_ABSOLUTE_TIMEOUT_HOURS",
    )

    # Authentication protections
    login_lockout_threshold: int = Field(
        default=5,
        ge=1,
        validation_alias="LOGIN_LOCKOUT_THRESHOLD",
    )
    login_lockout_duration_minutes: int = Field(
        default=15,
        ge=1,
        validation_alias="LOGIN_LOCKOUT_DURATION_MINUTES",
    )
    login_rate_limit_attempts: int = Field(
        default=10,
        ge=1,
        validation_alias="LOGIN_RATE_LIMIT_ATTEMPTS",
    )
    login_rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        validation_alias="LOGIN_RATE_LIMIT_WINDOW_SECONDS",
    )

    # Session & password hashing defaults (override via env vars in production)
    # GDPR Note: Session data retained for 90 days after expiry for audit/forensic purposes.
    # Background cleanup job should purge sessions older than 90 days from `expires_at`.
    # User credential hashes retained indefinitely while account active; purged 30 days
    # after account deactivation per data retention policy.
    argon2_time_cost: int = Field(default=2, ge=1, validation_alias="ARGON2_TIME_COST")
    argon2_memory_cost_kib: int = Field(
        default=19_456,
        ge=8_192,
        validation_alias="ARGON2_MEMORY_COST_KIB",
    )
    argon2_parallelism: int = Field(
        default=1,
        ge=1,
        validation_alias="ARGON2_PARALLELISM",
    )
    argon2_hash_len: int = Field(
        default=32,
        ge=16,
        validation_alias="ARGON2_HASH_LEN",
    )
    argon2_salt_len: int = Field(
        default=16,
        ge=16,
        validation_alias="ARGON2_SALT_LEN",
    )
    argon2_encoding: str = Field(default="utf-8", validation_alias="ARGON2_ENCODING")
    
    # SMTP Configuration (for admin-issued password resets)
    smtp_host: str = Field(default="localhost", validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=1025, validation_alias="SMTP_PORT")
    smtp_username: Optional[str] = Field(default=None, validation_alias="SMTP_USERNAME")
    smtp_password: Optional[str] = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=False, validation_alias="SMTP_USE_TLS")
    smtp_from_address: str = Field(
        default="security-admin@example.com",
        validation_alias="SMTP_FROM_ADDRESS"
    )
    
    # MITRE ATT&CK
    mitre_attack_stix_path: Optional[str] = Field(
        default=None,
        validation_alias="MITRE_ATTACK_STIX_PATH",
        description="Path to MITRE ATT&CK STIX bundle JSON file. "
                    "Defaults to backend/app/models/enterprise-attack-18.1.json if not set."
    )
    
    # Application
    log_level: str = "INFO"
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",  # Vite default port
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173"
    ]

    def build_argon2_parameters(self) -> Argon2Parameters:
        """Return `Argon2Parameters` initialised from environment overrides."""

        return Argon2Parameters(
            time_cost=self.argon2_time_cost,
            memory_cost=self.argon2_memory_cost_kib,
            parallelism=self.argon2_parallelism,
            hash_len=self.argon2_hash_len,
            salt_len=self.argon2_salt_len,
            encoding=self.argon2_encoding,
        )

    @property
    def session_idle_timeout(self) -> timedelta:
        """Duration before an idle session expires."""

        return timedelta(hours=self.session_idle_timeout_hours)

    @property
    def session_absolute_timeout(self) -> timedelta:
        """Maximum lifetime for a session regardless of activity."""

        return timedelta(hours=self.session_absolute_timeout_hours)

    @property
    def login_lockout_duration(self) -> timedelta:
        """Duration that an account remains locked after repeated failures."""

        return timedelta(minutes=self.login_lockout_duration_minutes)

    def cookie_kwargs(
        self, expires_at: Optional[datetime | str | float | int] = None
    ) -> dict:
        """Return keyword arguments for `Response.set_cookie`.

        `expires_at` may be a datetime string/epoch seconds to satisfy Starlette.
        """

        kwargs: dict[str, object] = {
            "key": self.session_cookie_name,
            "httponly": self.session_cookie_http_only,
            "secure": self.session_cookie_secure,
            "samesite": self.session_cookie_same_site,
            "path": self.session_cookie_path,
        }

        if self.session_cookie_domain:
            kwargs["domain"] = self.session_cookie_domain

        if isinstance(expires_at, datetime):
            expiry = expires_at
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            else:
                expiry = expiry.astimezone(timezone.utc)
            kwargs["expires"] = expiry
        elif expires_at is not None:
            kwargs["expires"] = expires_at

        max_age = int(self.session_idle_timeout.total_seconds())
        kwargs["max_age"] = max_age

        return kwargs


settings = Settings()
