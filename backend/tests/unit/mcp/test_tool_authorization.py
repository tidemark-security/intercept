from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.mcp import tools as mcp_tools
from app.models.enums import UserRole


def _mcp_request_for_auditor() -> SimpleNamespace:
    user = SimpleNamespace(username="auditor-user", role=UserRole.AUDITOR)
    return SimpleNamespace(scope={"mcp_user": user})


@pytest.mark.asyncio
async def test_auditor_cannot_commit_mcp_triage_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_call = AsyncMock()
    monkeypatch.setattr(mcp_tools, "get_http_request", _mcp_request_for_auditor)
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
async def test_auditor_cannot_commit_mcp_timeline_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_call = AsyncMock()
    monkeypatch.setattr(mcp_tools, "get_http_request", _mcp_request_for_auditor)
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
