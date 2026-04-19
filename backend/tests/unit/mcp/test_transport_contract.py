"""Unit tests for the MCP transport routing contract."""
from __future__ import annotations

from fastapi.routing import Mount

from app.main import (
    app,
    authenticated_mcp_sse_app,
    authenticated_mcp_streamable_app,
    mcp_sse_app,
    mcp_streamable_app,
)


def test_mcp_mounts_expose_expected_public_paths() -> None:
    mcp_mounts = [route for route in app.routes if isinstance(route, Mount) and route.path.startswith("/mcp")]
    mount_paths = [route.path for route in mcp_mounts]

    assert mount_paths == ["/mcp/streamable", "/mcp"]
    assert mcp_mounts[0].app is authenticated_mcp_streamable_app
    assert mcp_mounts[1].app is authenticated_mcp_sse_app


def test_sse_transport_keeps_legacy_child_paths() -> None:
    child_paths = [route.path for route in mcp_sse_app.routes]

    assert "/sse" in child_paths
    assert "/messages" in child_paths


def test_streamable_transport_is_rooted_at_mount_prefix() -> None:
    child_paths = [route.path for route in mcp_streamable_app.routes]

    assert child_paths == ["/"]


def test_auth_wrappers_target_the_expected_transport_apps() -> None:
    assert authenticated_mcp_sse_app.app is mcp_sse_app
    assert authenticated_mcp_streamable_app.app is mcp_streamable_app