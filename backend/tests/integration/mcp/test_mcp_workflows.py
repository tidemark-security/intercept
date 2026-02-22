"""End-to-end workflow tests for MCP server."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import UserRole, UserStatus, AccountType, CaseStatus, Priority, AlertStatus
from app.models.models import UserAccount, Case, Alert
from app.services.api_key_service import api_key_service


@pytest.fixture
async def workflow_api_key(
    session_maker: async_sessionmaker[AsyncSession],
) -> str:
    """Create a test API key for workflow tests."""
    async with session_maker() as session:
        user = UserAccount(
            username="workflow_user",
            email="workflow@test.com",
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
            name="Workflow Test Key",
            expires_at=expires_at,
        )
        await session.commit()
        
        return api_key_result.key


@pytest.mark.asyncio
async def test_complete_case_management_workflow(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    workflow_api_key: str,
) -> None:
    """Test complete case management workflow via MCP.
    
    Workflow:
    1. Create a new case
    2. Retrieve the case
    3. Update the case status
    4. Add a timeline item
    5. Close the case
    """
    headers = {"Authorization": f"Bearer {workflow_api_key}"}
    
    # Step 1: Create a new case
    create_response = await client.post(
        "/mcp/v1/tools/call",
        headers=headers,
        json={
            "name": "create_case_api_v1_cases_post",
            "arguments": {
                "title": "Security Incident - Phishing Campaign",
                "description": "Multiple users reported phishing emails",
                "priority": "HIGH"
            }
        }
    )
    
    assert create_response.status_code == 200
    create_data = create_response.json()
    
    # Extract case ID from response
    # Note: Response structure depends on FastMCP wrapping
    # We need to find the case in the database
    async with session_maker() as session:
        from sqlmodel import select
        stmt = select(Case).where(Case.title.contains("Phishing Campaign"))
        result = await session.execute(stmt)
        created_case = result.scalar_one_or_none()
        
        assert created_case is not None
        case_id = created_case.id
    
    # Step 2: Retrieve the case
    get_response = await client.post(
        "/mcp/v1/tools/call",
        headers=headers,
        json={
            "name": "get_case_api_v1_cases",
            "arguments": {
                "case_id": case_id
            }
        }
    )
    
    assert get_response.status_code == 200
    
    # Step 3: Update case status to IN_PROGRESS
    update_response = await client.post(
        "/mcp/v1/tools/call",
        headers=headers,
        json={
            "name": "update_case_api_v1_cases",
            "arguments": {
                "case_id": case_id,
                "status": "IN_PROGRESS"
            }
        }
    )
    
    assert update_response.status_code == 200
    
    # Verify update
    async with session_maker() as session:
        updated_case = await session.get(Case, case_id)
        assert updated_case is not None
        assert updated_case.status == CaseStatus.IN_PROGRESS
    
    # Step 4: Add timeline item (note)
    timeline_response = await client.post(
        "/mcp/v1/tools/call",
        headers=headers,
        json={
            "name": "update_case_api_v1_cases",
            "arguments": {
                "case_id": case_id,
                "timeline_items": [
                    {
                        "type": "note",
                        "description": "Initial investigation completed",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                ]
            }
        }
    )
    
    assert timeline_response.status_code == 200
    
    # Step 5: Close the case
    close_response = await client.post(
        "/mcp/v1/tools/call",
        headers=headers,
        json={
            "name": "update_case_api_v1_cases",
            "arguments": {
                "case_id": case_id,
                "status": "CLOSED"
            }
        }
    )
    
    assert close_response.status_code == 200
    
    # Final verification
    async with session_maker() as session:
        final_case = await session.get(Case, case_id)
        assert final_case is not None
        assert final_case.status == CaseStatus.CLOSED


@pytest.mark.asyncio
async def test_alert_triage_workflow(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    workflow_api_key: str,
) -> None:
    """Test alert triage workflow via MCP.
    
    Workflow:
    1. List new alerts
    2. Get specific alert details
    3. Triage alert as TRUE_POSITIVE
    4. Create case from alert
    5. Link alert to case
    """
    headers = {"Authorization": f"Bearer {workflow_api_key}"}
    
    # Setup: Create test alerts
    async with session_maker() as session:
        alert1 = Alert(
            title="Suspicious PowerShell Execution",
            description="PowerShell script executed with suspicious parameters",
            status=AlertStatus.NEW,
            priority=Priority.HIGH,
            source="EDR",
            created_at=datetime.now(timezone.utc),
        )
        alert2 = Alert(
            title="Unusual Login Location",
            description="User logged in from unexpected geographic location",
            status=AlertStatus.NEW,
            priority=Priority.MEDIUM,
            source="SIEM",
            created_at=datetime.now(timezone.utc),
        )
        session.add_all([alert1, alert2])
        await session.commit()
        await session.refresh(alert1)
        await session.refresh(alert2)
        alert1_id = alert1.id
        alert2_id = alert2.id
    
    # Step 1: List new alerts
    list_response = await client.post(
        "/mcp/v1/tools/call",
        headers=headers,
        json={
            "name": "get_alerts_api_v1_alerts_get",
            "arguments": {
                "status": ["NEW"],
                "limit": 10
            }
        }
    )
    
    assert list_response.status_code == 200
    
    # Step 2: Get specific alert details
    get_alert_response = await client.post(
        "/mcp/v1/tools/call",
        headers=headers,
        json={
            "name": "get_alert_api_v1_alerts",
            "arguments": {
                "alert_id": alert1_id
            }
        }
    )
    
    assert get_alert_response.status_code == 200
    
    # Step 3: Triage alert as TRUE_POSITIVE
    triage_response = await client.post(
        "/mcp/v1/tools/call",
        headers=headers,
        json={
            "name": "update_alert_api_v1_alerts",
            "arguments": {
                "alert_id": alert1_id,
                "status": "TRUE_POSITIVE"
            }
        }
    )
    
    assert triage_response.status_code == 200
    
    # Verify triage
    async with session_maker() as session:
        triaged_alert = await session.get(Alert, alert1_id)
        assert triaged_alert is not None
        assert triaged_alert.status == AlertStatus.TRUE_POSITIVE
    
    # Step 4: Create case from alert
    create_case_response = await client.post(
        "/mcp/v1/tools/call",
        headers=headers,
        json={
            "name": "create_case_api_v1_cases_post",
            "arguments": {
                "title": f"Investigation: {alert1.title}",
                "description": f"Case created from alert: {alert1.description}",
                "priority": "HIGH"
            }
        }
    )
    
    assert create_case_response.status_code == 200
    
    # Find the created case
    async with session_maker() as session:
        from sqlmodel import select
        stmt = select(Case).where(Case.title.contains("Investigation:"))
        result = await session.execute(stmt)
        investigation_case = result.scalar_one_or_none()
        
        assert investigation_case is not None
        case_id = investigation_case.id
    
    # Step 5: Link alert to case (via case update with alert timeline item)
    link_response = await client.post(
        "/mcp/v1/tools/call",
        headers=headers,
        json={
            "name": "update_alert_api_v1_alerts",
            "arguments": {
                "alert_id": alert1_id,
                "case_id": case_id
            }
        }
    )
    
    assert link_response.status_code == 200
    
    # Final verification
    async with session_maker() as session:
        linked_alert = await session.get(Alert, alert1_id)
        assert linked_alert is not None
        assert linked_alert.case_id == case_id


@pytest.mark.asyncio
async def test_batch_operations_workflow(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    workflow_api_key: str,
) -> None:
    """Test batch operations workflow via MCP.
    
    Workflow:
    1. List all open cases
    2. Filter cases by priority
    3. Bulk update case assignee
    """
    headers = {"Authorization": f"Bearer {workflow_api_key}"}
    
    # Setup: Create test cases
    async with session_maker() as session:
        cases = [
            Case(
                case_number=f"CASE-BATCH-{i}",
                title=f"Test Case {i}",
                status=CaseStatus.NEW,
                priority=Priority.HIGH if i % 2 == 0 else Priority.MEDIUM,
                created_at=datetime.now(timezone.utc),
            )
            for i in range(5)
        ]
        session.add_all(cases)
        await session.commit()
    
    # Step 1: List all open cases
    list_response = await client.post(
        "/mcp/v1/tools/call",
        headers=headers,
        json={
            "name": "get_cases_api_v1_cases_get",
            "arguments": {
                "status": ["NEW", "IN_PROGRESS"],
                "limit": 100
            }
        }
    )
    
    assert list_response.status_code == 200
    
    # Step 2: Filter high priority cases
    high_priority_response = await client.post(
        "/mcp/v1/tools/call",
        headers=headers,
        json={
            "name": "get_cases_api_v1_cases_get",
            "arguments": {
                "status": ["NEW"],
                "limit": 100
                # Note: Current API might not support priority filter
            }
        }
    )
    
    assert high_priority_response.status_code == 200
    
    # Step 3: Update assignee for each high priority case
    # (In a real scenario, this would be done programmatically)
    async with session_maker() as session:
        from sqlmodel import select
        stmt = select(Case).where(
            Case.case_number.like("CASE-BATCH-%"),
            Case.priority == Priority.HIGH
        )
        result = await session.execute(stmt)
        high_priority_cases = result.scalars().all()
        
        for case in high_priority_cases:
            update_response = await client.post(
                "/mcp/v1/tools/call",
                headers=headers,
                json={
                    "name": "update_case_api_v1_cases",
                    "arguments": {
                        "case_id": case.id,
                        "assignee": "senior_analyst"
                    }
                }
            )
            assert update_response.status_code == 200
    
    # Verify all high priority cases are assigned
    async with session_maker() as session:
        stmt = select(Case).where(
            Case.case_number.like("CASE-BATCH-%"),
            Case.priority == Priority.HIGH
        )
        result = await session.execute(stmt)
        assigned_cases = result.scalars().all()
        
        for case in assigned_cases:
            assert case.assignee == "senior_analyst"
