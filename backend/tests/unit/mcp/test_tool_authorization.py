from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.mcp import tools as mcp_tools
from app.models.enums import AccountType, UserRole


def _mcp_request_for_auditor() -> SimpleNamespace:
    user = SimpleNamespace(username="auditor-user", role=UserRole.AUDITOR)
    return SimpleNamespace(user=user)


def _mcp_request_for_nhi(*, override_timestamps: bool) -> SimpleNamespace:
    user = SimpleNamespace(
        username="svc-migration",
        role=UserRole.ANALYST,
        account_type=AccountType.NHI,
        override_timestamps=override_timestamps,
    )
    return SimpleNamespace(user=user)


@pytest.mark.asyncio
async def test_auditor_cannot_commit_mcp_triage_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_call = AsyncMock()
    monkeypatch.setattr(mcp_tools, "get_current_mcp_principal", _mcp_request_for_auditor)
    monkeypatch.setattr(mcp_tools.mcp_service, "record_triage_decision", service_call)

    with pytest.raises(HTTPException) as exc_info:
        await mcp_tools.record_triage_decision_tool(
            alert_id="ALT-0000001",
            disposition="NEEDS_INVESTIGATION",
            confidence=0.8,
            commit=True,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Auditor accounts have read-only access"
    service_call.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_timeline_created_at_requires_migration_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_call = AsyncMock()
    monkeypatch.setattr(
        mcp_tools,
        "get_current_mcp_principal",
        lambda: _mcp_request_for_nhi(override_timestamps=True),
    )
    monkeypatch.setattr(mcp_tools.mcp_service, "add_timeline_item", service_call)

    with pytest.raises(HTTPException) as exc_info:
        await mcp_tools.add_timeline_item_tool(
            target_kind="alert",
            target_id="ALT-0000001",
            item_id="migration-note",
            body="Blocked write",
            commit=True,
            created_at="2024-01-02T03:04:05+00:00",
        )

    assert exc_info.value.status_code == 400
    service_call.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_timeline_migration_requires_override_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_call = AsyncMock()
    monkeypatch.setattr(
        mcp_tools,
        "get_current_mcp_principal",
        lambda: _mcp_request_for_nhi(override_timestamps=False),
    )
    monkeypatch.setattr(mcp_tools.mcp_service, "add_timeline_item", service_call)

    with pytest.raises(HTTPException) as exc_info:
        await mcp_tools.add_timeline_item_tool(
            target_kind="alert",
            target_id="ALT-0000001",
            item_id="migration-note",
            body="Blocked write",
            commit=True,
            created_at="2024-01-02T03:04:05+00:00",
            migration=True,
        )

    assert exc_info.value.status_code == 403
    service_call.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_timeline_migration_passes_authorized_created_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_call = AsyncMock(
        return_value=SimpleNamespace(model_dump=lambda: {"mode": "committed"})
    )
    monkeypatch.setattr(
        mcp_tools,
        "get_current_mcp_principal",
        lambda: _mcp_request_for_nhi(override_timestamps=True),
    )
    monkeypatch.setattr(mcp_tools.mcp_service, "add_timeline_item", service_call)

    result = await mcp_tools.add_timeline_item_tool(
        target_kind="alert",
        target_id="ALT-0000001",
        item_id="migration-note",
        body="Imported note",
        commit=True,
        created_at="2024-01-02T03:04:05+10:00",
        migration=True,
    )

    assert result == {"mode": "committed"}
    service_call.assert_awaited_once()
    assert service_call.await_args.kwargs["created_at"].isoformat() == "2024-01-01T17:04:05+00:00"


@pytest.mark.asyncio
async def test_auditor_cannot_commit_mcp_timeline_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_call = AsyncMock()
    monkeypatch.setattr(mcp_tools, "get_current_mcp_principal", _mcp_request_for_auditor)
    monkeypatch.setattr(mcp_tools.mcp_service, "add_timeline_item", service_call)

    with pytest.raises(HTTPException) as exc_info:
        await mcp_tools.add_timeline_item_tool(
            target_kind="alert",
            target_id="ALT-0000001",
            item_id="auditor-note",
            body="Blocked write",
            commit=True,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Auditor accounts have read-only access"
    service_call.assert_not_called()
