from __future__ import annotations

from typing import Any

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.main import api_app, compose_http_app


async def _probe(_request: Any) -> PlainTextResponse:
    return PlainTextResponse("ok")


def _composed_app() -> Starlette:
    runtime = type(
        "Runtime",
        (),
        {
            "well_known_routes": [Route("/.well-known/probe", _probe)],
            "mounted_app": Starlette(routes=[Route("/probe", _probe)]),
        },
    )()
    return compose_http_app(api_app, runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/health", "/mcp/probe", "/.well-known/probe"],
)
async def test_untrusted_host_is_rejected_across_composed_application(path: str) -> None:
    transport = httpx.ASGITransport(app=_composed_app())
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://attacker.example",
    ) as client:
        response = await client.get(path)

    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/health", "/mcp/probe", "/.well-known/probe"],
)
async def test_configured_test_host_remains_accepted(path: str) -> None:
    transport = httpx.ASGITransport(app=_composed_app())
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get(path)

    assert response.status_code == 200
