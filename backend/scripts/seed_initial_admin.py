#!/usr/bin/env python3
"""Ensure the default local admin user exists for bootstrap environments."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # type: ignore[attr-defined]
from sqlmodel import select

from app.core.settings_registry import get_local
from app.models.enums import UserRole, UserStatus
from app.models.models import UserAccount
from app.services.security.password_hasher import Argon2Parameters, PasswordHasher


DEFAULT_ADMIN = {
    "username": "admin",
    "email": "admin@intercept.local",
    "password": "admin",
    "role": UserRole.ADMIN,
}


def _create_password_hasher() -> PasswordHasher:
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


async def ensure_initial_admin() -> None:
    """Create the default admin account when it does not already exist."""
    engine = create_async_engine(get_local("database.url"), echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    password_hasher = _create_password_hasher()
    now = datetime.now(timezone.utc)

    async with session_maker() as session:
        result = await session.execute(
            select(UserAccount).where(UserAccount.username == DEFAULT_ADMIN["username"])
        )
        existing_user = result.scalar_one_or_none()

        if existing_user is not None:
            print(f"✓ Admin user already exists: {existing_user.username}")
            await engine.dispose()
            return

        admin_user = UserAccount(
            username=DEFAULT_ADMIN["username"],
            email=DEFAULT_ADMIN["email"],
            role=DEFAULT_ADMIN["role"],
            status=UserStatus.ACTIVE,
            password_hash=password_hasher.hash(DEFAULT_ADMIN["password"]),
            password_updated_at=now,
            must_change_password=False,
            failed_login_attempts=0,
            created_at=now,
            updated_at=now,
        )
        session.add(admin_user)
        await session.commit()
        await session.refresh(admin_user)

        print(f"✓ Created initial admin user: {admin_user.username}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(ensure_initial_admin())