"""Unit tests for the public MCP transport and application boundary."""

from __future__ import annotations

from types import SimpleNamespace

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route

from app.main import api_app, compose_http_app


def _ok(_request):
    return PlainTextResponse("ok")


def test_existing_api_app_does_not_own_mcp_or_oauth_protocol_routes() -> None:
    route_paths = [route.path for route in api_app.routes]

    assert not any(path.startswith("/.well-known/") for path in route_paths)
    assert not any(path.startswith("/oauth/") for path in route_paths)
    assert not any(path.startswith("/mcp/") for path in route_paths)


def test_top_level_composition_orders_discovery_mcp_then_api() -> None:
    discovery = Route("/.well-known/example", _ok)
    mounted_mcp = Starlette(routes=[Route("/streamable/", _ok)])
    runtime = SimpleNamespace(
        well_known_routes=[discovery],
        mounted_app=mounted_mcp,
    )

    composed = compose_http_app(api_app, runtime)

    assert composed.routes[0] is discovery
    assert isinstance(composed.routes[1], Mount)
    assert composed.routes[1].path == "/mcp"
    assert composed.routes[1].app is mounted_mcp
    assert isinstance(composed.routes[2], Mount)
    assert composed.routes[2].path == ""
    assert composed.routes[2].app is api_app


def test_streamable_http_is_the_only_mcp_transport() -> None:
    mounted_mcp = Starlette(routes=[Route("/streamable/", _ok)])
    runtime = SimpleNamespace(well_known_routes=[], mounted_app=mounted_mcp)

    composed = compose_http_app(api_app, runtime)
    mcp_mount = next(route for route in composed.routes if route.path == "/mcp")
    child_paths = [route.path for route in mcp_mount.app.routes]

    assert child_paths == ["/streamable/"]
    assert "/sse" not in child_paths
    assert "/messages" not in child_paths
