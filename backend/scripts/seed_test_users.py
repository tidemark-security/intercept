#!/usr/bin/env python3
"""
Seed script to create test users for development and QA.

Creates the following test accounts:
- Admin user: username='admin', password='admin', role=ADMIN
- Analyst user: username='analyst', password='analyst', role=ANALYST
- Auditor user: username='auditor', password='auditor', role=AUDITOR

This script is idempotent and will reset existing users to their default state:
- Resets password to the default test password
- Clears must_change_password flag
- Sets status to ACTIVE
- Clears lockout and failed login attempts
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # type: ignore[attr-defined]
from sqlmodel import select

from app.core.settings_registry import get_local
from app.models.enums import UserRole, UserStatus
from app.models.models import UserAccount
from app.services.security.password_hasher import Argon2Parameters, PasswordHasher


# Test user configurations
TEST_USERS = [
    {
        "username": "admin",
        "email": "admin@intercept.local",
        "password": "admin",
        "role": UserRole.ADMIN,
        "must_change_password": False,
    },
    {
        "username": "analyst",
        "email": "analyst@intercept.local",
        "password": "analyst",
        "role": UserRole.ANALYST,
        "must_change_password": False,
    },
    {
        "username": "auditor",
        "email": "auditor@intercept.local",
        "password": "auditor",
        "role": UserRole.AUDITOR,
        "must_change_password": False,
    },
]


async def seed_test_users() -> None:
    """Create test users if they don't exist."""
    engine = create_async_engine(get_local("database.url"), echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    password_hasher = PasswordHasher(
        Argon2Parameters(
            time_cost=get_local("auth.argon2.time_cost"),
            memory_cost=get_local("auth.argon2.memory_cost_kib"),
            parallelism=get_local("auth.argon2.parallelism"),
            hash_len=get_local("auth.argon2.hash_len"),
            salt_len=get_local("auth.argon2.salt_len"),
            encoding=get_local("auth.argon2.encoding"),
        )
    )
    now = datetime.now(timezone.utc)
    
    print("=" * 60)
    print("Seeding Test Users")
    print("=" * 60)
    
    async with session_maker() as session:
        for user_config in TEST_USERS:
            # Check if user already exists
            result = await session.execute(
                select(UserAccount).where(UserAccount.username == user_config["username"])
            )
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                # Reset existing user to default state
                print(f"\n✓ {user_config['role'].value} user already exists - resetting to defaults")
                print(f"  Username: {existing_user.username}")
                print(f"  Old Status: {existing_user.status.value}")
                print(f"  Old must_change_password: {existing_user.must_change_password}")
                
                # Reset all parameters to defaults
                existing_user.password_hash = password_hasher.hash(user_config["password"])
                existing_user.password_updated_at = now
                existing_user.must_change_password = user_config["must_change_password"]
                existing_user.status = UserStatus.ACTIVE
                existing_user.lockout_expires_at = None
                existing_user.failed_login_attempts = 0
                existing_user.updated_at = now
                
                await session.commit()
                
                print(f"  New Status: {existing_user.status.value}")
                print(f"  New must_change_password: {existing_user.must_change_password}")
                print(f"  Password: reset to default")
                continue
            
            # Create new user
            new_user = UserAccount(
                username=user_config["username"],
                email=user_config["email"],
                role=user_config["role"],
                status=UserStatus.ACTIVE,
                password_hash=password_hasher.hash(user_config["password"]),
                password_updated_at=now,
                must_change_password=user_config["must_change_password"],
                failed_login_attempts=0,
                created_at=now,
                updated_at=now,
            )
            
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)
            
            print(f"\n✓ {user_config['role'].value} user created successfully!")
            print(f"  ID: {new_user.id}")
            print(f"  Username: {new_user.username}")
            print(f"  Email: {new_user.email}")
            print(f"  Password: same as username")
            print(f"  Role: {new_user.role.value}")
            print(f"  Status: {new_user.status.value}")
    
    print("\n" + "=" * 60)
    print("Test User Credentials")
    print("=" * 60)
    print("\nYou can now login at: http://localhost:5173/login")
    print()
    for user_config in TEST_USERS:
        print(f"  {user_config['role'].value}:")
        print(f"    Username: {user_config['username']}")
        print(f"    Password: same as username")
        print()
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_test_users())
