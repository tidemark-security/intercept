from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import UUID, uuid4

import pytest

from app.core.settings_registry import get_local
from app.models.enums import UserRole, UserStatus
from app.models.models import UserAccount
from app.services.security.password_hasher import Argon2Parameters, PasswordHasher

DEFAULT_TEST_PASSWORD = "ValidTestPass123!"


@pytest.fixture
def password_hasher() -> PasswordHasher:
    """Return a PasswordHasher configured with runtime settings."""

    return PasswordHasher(
        Argon2Parameters(
            time_cost=get_local("auth.argon2.time_cost"),
            memory_cost=get_local("auth.argon2.memory_cost_kib"),
            parallelism=get_local("auth.argon2.parallelism"),
            hash_len=get_local("auth.argon2.hash_len"),
            salt_len=get_local("auth.argon2.salt_len"),
            encoding=get_local("auth.argon2.encoding"),
        )
    )


@pytest.fixture
def hash_password(password_hasher: PasswordHasher) -> Callable[[str], str]:
    """Helper that hashes passwords for seeded accounts."""

    def _hash(password: str = DEFAULT_TEST_PASSWORD) -> str:
        return password_hasher.hash(password)

    return _hash


@pytest.fixture
def analyst_user_factory(hash_password: Callable[[str], str]) -> Callable[..., UserAccount]:
    """Factory fixture producing active analyst accounts with hashed passwords."""

    def _factory(
        *,
        user_id: UUID | None = None,
        username: str | None = None,
        email: str | None = None,
        password: str = DEFAULT_TEST_PASSWORD,
    ) -> UserAccount:
        now = datetime.now(timezone.utc)
        unique_suffix = uuid4().hex[:6]
        return UserAccount(
            id=user_id or uuid4(),
            username=(username or f"analyst_{unique_suffix}"),
            email=(email or f"analyst_{unique_suffix}@example.com"),
            role=UserRole.ANALYST,
            status=UserStatus.ACTIVE,
            password_hash=hash_password(password),
            password_updated_at=now,
            must_change_password=False,
            failed_login_attempts=0,
            created_at=now,
            updated_at=now,
        )

    return _factory


@pytest.fixture
def admin_user_factory(hash_password: Callable[[str], str]) -> Callable[..., UserAccount]:
    """Factory fixture producing admin accounts for management tests."""

    def _factory(
        *,
        user_id: UUID | None = None,
        username: str | None = None,
        email: str | None = None,
        password: str = DEFAULT_TEST_PASSWORD,
    ) -> UserAccount:
        now = datetime.now(timezone.utc)
        unique_suffix = uuid4().hex[:6]
        return UserAccount(
            id=user_id or uuid4(),
            username=(username or f"admin_{unique_suffix}"),
            email=(email or f"admin_{unique_suffix}@example.com"),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            password_hash=hash_password(password),
            password_updated_at=now,
            must_change_password=False,
            failed_login_attempts=0,
            created_at=now,
            updated_at=now,
        )

    return _factory


@pytest.fixture
def auditor_user_factory(hash_password: Callable[[str], str]) -> Callable[..., UserAccount]:
    """Factory fixture producing active auditor accounts with hashed passwords."""

    def _factory(
        *,
        user_id: UUID | None = None,
        username: str | None = None,
        email: str | None = None,
        password: str = DEFAULT_TEST_PASSWORD,
    ) -> UserAccount:
        now = datetime.now(timezone.utc)
        unique_suffix = uuid4().hex[:6]
        return UserAccount(
            id=user_id or uuid4(),
            username=(username or f"auditor_{unique_suffix}"),
            email=(email or f"auditor_{unique_suffix}@example.com"),
            role=UserRole.AUDITOR,
            status=UserStatus.ACTIVE,
            password_hash=hash_password(password),
            password_updated_at=now,
            must_change_password=False,
            failed_login_attempts=0,
            created_at=now,
            updated_at=now,
        )

    return _factory
