"""Integration tests for MCP server functionality."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import UserRole, UserStatus, AccountType
from app.models.models import UserAccount, APIKey
from app.services.api_key_service import api_key_service


@pytest.mark.asyncio
async def test_mcp_tools_list_requires_authentication(
    client: AsyncClient,
) -> None:
    """Test that tool listing requires API key authentication."""
    response = await client.post("/mcp/v1/tools/list")
    
    assert response.status_code == 401
    data = response.json()
    assert "API key required" in data["message"]


@pytest.mark.asyncio
async def test_mcp_tools_list_with_valid_api_key(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Test tool listing with valid API key."""
    # Create a test user and API key
    async with session_maker() as session:
        user = UserAccount(
            username="mcp_test_user",
            email="mcp@test.com",
            role=UserRole.ANALYST,
            status=UserStatus.ACTIVE,
            account_type=AccountType.NHI,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # Create API key
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        api_key_result = await api_key_service.create_api_key(
            session,
            user_id=user.id,
            name="Test MCP Key",
            expires_at=expires_at,
        )
        raw_key = api_key_result.key
        await session.commit()
    
    # Make request with API key
    response = await client.post(
        "/mcp/v1/tools/list",
        headers={"Authorization": f"Bearer {raw_key}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "tools" in data or "result" in data  # FastMCP might wrap in result


@pytest.mark.asyncio
async def test_mcp_tools_list_with_x_api_key_header(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Test tool listing with X-API-Key header."""
    # Create user and API key
    async with session_maker() as session:
        user = UserAccount(
            username="mcp_test_user2",
            email="mcp2@test.com",
            role=UserRole.ANALYST,
            status=UserStatus.ACTIVE,
            account_type=AccountType.NHI,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        api_key_result = await api_key_service.create_api_key(
            session,
            user_id=user.id,
            name="Test MCP Key",
            expires_at=expires_at,
        )
        raw_key = api_key_result.key
        await session.commit()
    
    # Make request with X-API-Key header
    response = await client.post(
        "/mcp/v1/tools/list",
        headers={"X-API-Key": raw_key}
    )
    
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_mcp_rejects_expired_api_key(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Test that expired API keys are rejected."""
    # Create user with expired API key
    async with session_maker() as session:
        user = UserAccount(
            username="mcp_expired_user",
            email="expired@test.com",
            role=UserRole.ANALYST,
            status=UserStatus.ACTIVE,
            account_type=AccountType.NHI,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # Create expired API key
        expires_at = datetime.now(timezone.utc) - timedelta(days=1)  # Already expired
        api_key_result = await api_key_service.create_api_key(
            session,
            user_id=user.id,
            name="Expired Key",
            expires_at=expires_at,
        )
        raw_key = api_key_result.key
        await session.commit()
    
    # Make request with expired key
    response = await client.post(
        "/mcp/v1/tools/list",
        headers={"Authorization": f"Bearer {raw_key}"}
    )
    
    assert response.status_code == 401
    data = response.json()
    assert "expired" in data["message"].lower()


@pytest.mark.asyncio
async def test_mcp_rejects_revoked_api_key(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Test that revoked API keys are rejected."""
    # Create user and API key
    async with session_maker() as session:
        user = UserAccount(
            username="mcp_revoked_user",
            email="revoked@test.com",
            role=UserRole.ANALYST,
            status=UserStatus.ACTIVE,
            account_type=AccountType.NHI,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        api_key_result = await api_key_service.create_api_key(
            session,
            user_id=user.id,
            name="To Be Revoked",
            expires_at=expires_at,
        )
        raw_key = api_key_result.key
        api_key_id = api_key_result.api_key_id
        await session.commit()
        
        # Revoke the key
        await api_key_service.revoke_api_key(session, api_key_id)
        await session.commit()
    
    # Make request with revoked key
    response = await client.post(
        "/mcp/v1/tools/list",
        headers={"Authorization": f"Bearer {raw_key}"}
    )
    
    assert response.status_code == 401
    data = response.json()
    assert "revoked" in data["message"].lower()


@pytest.mark.asyncio
async def test_mcp_rejects_disabled_user(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Test that API keys for disabled users are rejected."""
    # Create disabled user
    async with session_maker() as session:
        user = UserAccount(
            username="mcp_disabled_user",
            email="disabled@test.com",
            role=UserRole.ANALYST,
            status=UserStatus.ACTIVE,  # Start active
            account_type=AccountType.NHI,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # Create API key
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        api_key_result = await api_key_service.create_api_key(
            session,
            user_id=user.id,
            name="Test Key",
            expires_at=expires_at,
        )
        raw_key = api_key_result.key
        await session.commit()
        
        # Now disable the user
        user.status = UserStatus.DISABLED
        session.add(user)
        await session.commit()
    
    # Make request with key for disabled user
    response = await client.post(
        "/mcp/v1/tools/list",
        headers={"Authorization": f"Bearer {raw_key}"}
    )
    
    assert response.status_code == 403
    data = response.json()
    assert "not active" in data["message"].lower()


@pytest.mark.asyncio
async def test_mcp_rejects_invalid_api_key(
    client: AsyncClient,
) -> None:
    """Test that invalid API keys are rejected."""
    response = await client.post(
        "/mcp/v1/tools/list",
        headers={"Authorization": "Bearer int_invalid_key_12345"}
    )
    
    assert response.status_code == 401
    data = response.json()
    assert "invalid" in data["message"].lower() or "API key" in data["message"]
