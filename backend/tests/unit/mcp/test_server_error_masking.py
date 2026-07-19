from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastmcp.exceptions import ToolError

from app.mcp import server as mcp_server
from app.mcp import tools as mcp_tools
from app.services.mcp_errors import (
    McpConflictError,
    McpNotFoundError,
    McpTimeoutError,
    McpUnavailableError,
    McpValidationError,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (McpValidationError("invalid input"), 400),
        (McpNotFoundError("missing item"), 404),
        (McpConflictError("stale state"), 409),
        (McpUnavailableError("validator unavailable"), 503),
        (McpTimeoutError("validator timed out"), 504),
    ],
)
async def test_tool_seam_translates_only_typed_service_errors(
    error: Exception,
    expected_status: int,
) -> None:
    async def fail() -> None:
        raise error

    with pytest.raises(HTTPException) as exc_info:
        await mcp_tools._run_service_call(fail())

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == str(error)


@pytest.mark.asyncio
async def test_tool_seam_does_not_mask_unexpected_service_errors() -> None:
    async def fail() -> None:
        raise ValueError("programming defect")

    with pytest.raises(ValueError, match="programming defect"):
        await mcp_tools._run_service_call(fail())


@pytest.mark.asyncio
async def test_unexpected_tool_failure_does_not_expose_internal_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_summary(*_args, **_kwargs):
        raise RuntimeError("postgresql://secret-user:secret-password@database")

    monkeypatch.setattr(mcp_server, "get_summary_tool", fail_summary)

    with pytest.raises(ToolError) as exc_info:
        await mcp_server.mcp.call_tool(
            "get_summary",
            {"kind": "alert", "id": "ALT-0000001"},
        )

    message = str(exc_info.value)
    assert message == "Error calling tool 'get_summary'"
    assert "secret-password" not in message


@pytest.mark.asyncio
async def test_curated_http_tool_error_remains_actionable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject_summary(*_args, **_kwargs):
        raise HTTPException(status_code=404, detail="Alert ALT-0000001 not found")

    monkeypatch.setattr(mcp_server, "get_summary_tool", reject_summary)

    with pytest.raises(ToolError, match="Alert ALT-0000001 not found"):
        await mcp_server.mcp.call_tool(
            "get_summary",
            {"kind": "alert", "id": "ALT-0000001"},
        )


@pytest.mark.asyncio
async def test_structured_http_error_is_not_exposed_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject_summary(*_args, **_kwargs):
        raise HTTPException(
            status_code=400,
            detail={"internal": "database host secret"},
        )

    monkeypatch.setattr(mcp_server, "get_summary_tool", reject_summary)

    with pytest.raises(ToolError) as exc_info:
        await mcp_server.mcp.call_tool(
            "get_summary",
            {"kind": "alert", "id": "ALT-0000001"},
        )

    assert str(exc_info.value) == "Tool request rejected"
