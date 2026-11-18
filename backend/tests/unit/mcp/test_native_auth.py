from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.responses import JSONResponse

from app.core.client_address import ClientAddressResolver
from app.mcp.auth import (
    MCP_ACCESS_SCOPE,
    MCPConfigurationError,
    InterceptApiKeyVerifier,
    MCPRegistrationRequestMiddleware,
    XApiKeyToBearerMiddleware,
    derive_mcp_keys,
    validate_public_origin,
)
from app.services.api_key_service import ApiKeyNotFoundError, ApiKeyScopeError
from app.services.mcp_registration_service import (
    authorization_request_active,
    registration_source_ip,
)


class _Session:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _session_factory(session: _Session):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


@pytest.mark.asyncio
async def test_api_key_verifier_returns_native_principal_claims() -> None:
    user_id = uuid4()
    user = SimpleNamespace(id=user_id, username="automation", role=SimpleNamespace(value="ANALYST"))
    api_key = SimpleNamespace(id=uuid4())
    service = SimpleNamespace(
        validate_api_key=AsyncMock(return_value=SimpleNamespace(user=user, api_key=api_key))
    )
    session = _Session()
    verifier = InterceptApiKeyVerifier(
        session_factory=_session_factory(session),
        api_key_service=service,
        resource_url="https://intercept.example/mcp/streamable/",
    )

    token = await verifier.verify_token("tmi_secret")

    assert token is not None
    assert token.token == "tmi_secret"
    assert token.client_id == f"api-key:{api_key.id}"
    assert token.scopes == [MCP_ACCESS_SCOPE]
    assert token.resource == "https://intercept.example/mcp/streamable/"
    assert token.claims == {
        "intercept_user_id": str(user_id),
        "auth_source": "api_key",
        "api_key_id": str(api_key.id),
    }
    assert session.committed is True
    assert service.validate_api_key.await_args.kwargs["required_scopes"] == {
        MCP_ACCESS_SCOPE
    }


@pytest.mark.asyncio
async def test_api_key_verifier_treats_service_rejections_as_non_matches() -> None:
    service = SimpleNamespace(
        validate_api_key=AsyncMock(side_effect=ApiKeyNotFoundError())
    )
    session = _Session()
    verifier = InterceptApiKeyVerifier(
        session_factory=_session_factory(session),
        api_key_service=service,
        resource_url="https://intercept.example/mcp/streamable/",
    )

    assert await verifier.verify_token("not-a-key") is None
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_api_key_verifier_rejects_key_without_mcp_scope() -> None:
    service = SimpleNamespace(
        validate_api_key=AsyncMock(
            side_effect=ApiKeyScopeError({MCP_ACCESS_SCOPE})
        )
    )
    session = _Session()
    verifier = InterceptApiKeyVerifier(
        session_factory=_session_factory(session),
        api_key_service=service,
        resource_url="https://intercept.example/mcp/streamable/",
    )

    assert await verifier.verify_token("rest-only-key") is None
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_x_api_key_is_normalized_only_when_authorization_is_absent() -> None:
    seen_headers: list[list[tuple[bytes, bytes]]] = []

    async def downstream(scope, receive, send) -> None:
        seen_headers.append(list(scope["headers"]))

    middleware = XApiKeyToBearerMiddleware(downstream)
    receive = AsyncMock()
    send = AsyncMock()

    await middleware(
        {"type": "http", "headers": [(b"x-api-key", b"tmi_from_header")]},
        receive,
        send,
    )
    await middleware(
        {
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer oauth-token"),
                (b"x-api-key", b"tmi_ignored"),
            ],
        },
        receive,
        send,
    )

    assert (b"authorization", b"Bearer tmi_from_header") in seen_headers[0]
    assert seen_headers[1].count((b"authorization", b"Bearer oauth-token")) == 1
    assert (b"authorization", b"Bearer tmi_ignored") not in seen_headers[1]


@pytest.mark.asyncio
async def test_registration_middleware_separates_trusted_forwarded_clients() -> None:
    seen_sources: list[str] = []

    async def downstream(scope, receive, send) -> None:
        seen_sources.append(registration_source_ip())

    middleware = MCPRegistrationRequestMiddleware(
        downstream,
        max_body_bytes=1024,
        client_address_resolver=ClientAddressResolver.from_cidrs(
            ["172.31.250.0/24"]
        ),
    )
    send = AsyncMock()

    for client_address in ("203.0.113.42", "203.0.113.43"):
        receive = AsyncMock(
            return_value={
                "type": "http.request",
                "body": b"{}",
                "more_body": False,
            }
        )
        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/mcp/register",
                "client": ("172.31.250.10", 43123),
                "headers": [
                    (b"content-length", b"2"),
                    (
                        b"x-forwarded-for",
                        f"192.0.2.99, {client_address}".encode(),
                    ),
                ],
            },
            receive,
            send,
        )

    assert seen_sources == ["203.0.113.42", "203.0.113.43"]


@pytest.mark.asyncio
async def test_authorization_middleware_binds_trusted_source_for_all_route_forms() -> None:
    seen_sources: list[str] = []

    async def downstream(scope, receive, send) -> None:
        seen_sources.append(registration_source_ip())

    middleware = MCPRegistrationRequestMiddleware(
        downstream,
        max_body_bytes=1024,
        client_address_resolver=ClientAddressResolver.from_cidrs(
            ["172.31.250.0/24"]
        ),
    )
    receive = AsyncMock(
        return_value={
            "type": "http.request",
            "body": b"",
            "more_body": False,
        }
    )
    send = AsyncMock()
    requests = (
        ("GET", "/authorize", "203.0.113.40", "172.31.250.10"),
        ("POST", "/authorize/", "203.0.113.41", "172.31.250.10"),
        ("GET", "/mcp/authorize", "203.0.113.42", "172.31.250.10"),
        ("POST", "/mcp/authorize/", "203.0.113.43", "172.31.250.10"),
        # An untrusted direct peer cannot spoof a different source with XFF.
        ("GET", "/mcp/authorize", "198.51.100.99", "203.0.113.44"),
    )

    for method, path, forwarded_for, peer_address in requests:
        await middleware(
            {
                "type": "http",
                "method": method,
                "path": path,
                "client": (peer_address, 43123),
                "headers": [
                    (b"x-forwarded-for", forwarded_for.encode("ascii")),
                ],
            },
            receive,
            send,
        )

    assert seen_sources == [
        "203.0.113.40",
        "203.0.113.41",
        "203.0.113.42",
        "203.0.113.43",
        "203.0.113.44",
    ]


@pytest.mark.asyncio
async def test_authorization_middleware_rejects_oversized_post_body() -> None:
    async def downstream(scope, receive, send) -> None:
        response = JSONResponse({"downstream": True})
        await response(scope, receive, send)

    middleware = MCPRegistrationRequestMiddleware(
        downstream,
        max_body_bytes=8,
    )

    async def oversized_body():
        yield b"12345"
        yield b"67890"

    async with AsyncClient(
        transport=ASGITransport(app=middleware),
        base_url="https://intercept.example",
    ) as client:
        response = await client.post(
            "/mcp/authorize/",
            content=oversized_body(),
        )

    assert response.status_code == 413
    assert response.json() == {
        "error": "invalid_request",
        "error_description": "MCP authorization request body is too large",
    }


@pytest.mark.asyncio
async def test_oauth_form_middleware_binds_source_without_authorization_context() -> None:
    seen_contexts: list[tuple[str, bool]] = []

    async def downstream(scope, receive, send) -> None:
        seen_contexts.append(
            (registration_source_ip(), authorization_request_active())
        )

    middleware = MCPRegistrationRequestMiddleware(
        downstream,
        max_body_bytes=1024,
        client_address_resolver=ClientAddressResolver.from_cidrs(
            ["172.31.250.0/24"]
        ),
    )
    send = AsyncMock()
    paths = (
        "/consent",
        "/consent/",
        "/mcp/consent",
        "/mcp/consent/",
        "/token",
        "/token/",
        "/mcp/token",
        "/mcp/token/",
        "/revoke",
        "/revoke/",
        "/mcp/revoke",
        "/mcp/revoke/",
    )

    for path in paths:
        receive = AsyncMock(
            return_value={
                "type": "http.request",
                "body": b"client_id=test",
                "more_body": False,
            }
        )
        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": path,
                "client": ("172.31.250.10", 43123),
                "headers": [(b"x-forwarded-for", b"203.0.113.42")],
            },
            receive,
            send,
        )

    assert seen_contexts == [("203.0.113.42", False)] * len(paths)
    assert registration_source_ip() == "unknown"
    assert authorization_request_active() is False


@pytest.mark.asyncio
async def test_mcp_transport_middleware_binds_source_without_authorization_context() -> None:
    seen_contexts: list[tuple[str, bool]] = []

    async def downstream(scope, receive, send) -> None:
        seen_contexts.append(
            (registration_source_ip(), authorization_request_active())
        )

    middleware = MCPRegistrationRequestMiddleware(
        downstream,
        max_body_bytes=1024,
        client_address_resolver=ClientAddressResolver.from_cidrs(
            ["172.31.250.0/24"]
        ),
    )
    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/mcp/streamable/",
            "client": ("172.31.250.10", 43123),
            "headers": [(b"x-forwarded-for", b"203.0.113.43")],
        },
        AsyncMock(),
        AsyncMock(),
    )

    assert seen_contexts == [("203.0.113.43", False)]
    assert registration_source_ip() == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    (
        "/consent",
        "/consent/",
        "/mcp/consent",
        "/mcp/consent/",
        "/token",
        "/token/",
        "/mcp/token",
        "/mcp/token/",
        "/revoke",
        "/revoke/",
        "/mcp/revoke",
        "/mcp/revoke/",
    ),
)
async def test_oauth_form_middleware_rejects_oversized_chunked_body(
    path: str,
) -> None:
    async def downstream(scope, receive, send) -> None:
        response = JSONResponse({"downstream": True})
        await response(scope, receive, send)

    middleware = MCPRegistrationRequestMiddleware(
        downstream,
        max_body_bytes=8,
    )

    async def oversized_body():
        yield b"12345"
        yield b"67890"

    async with AsyncClient(
        transport=ASGITransport(app=middleware),
        base_url="https://intercept.example",
    ) as client:
        response = await client.post(path, content=oversized_body())

    assert response.status_code == 413
    assert response.json() == {
        "error": "invalid_request",
        "error_description": "MCP OAuth request body is too large",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://intercept.example", "https://intercept.example"),
        ("https://intercept.example/", "https://intercept.example"),
        ("http://localhost:8080", "http://localhost:8080"),
        ("http://127.0.0.1:8080", "http://127.0.0.1:8080"),
    ],
)
def test_validate_public_origin_accepts_https_and_loopback(
    value: str, expected: str
) -> None:
    assert validate_public_origin(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "http://intercept.example",
        "https://intercept.example/some-path",
        "https://user:password@intercept.example",
        "https://intercept.example?tenant=one",
        "https://intercept.example/#fragment",
        "localhost:8080",
    ],
)
def test_validate_public_origin_rejects_unsafe_or_non_origin_values(value: str) -> None:
    with pytest.raises(MCPConfigurationError):
        validate_public_origin(value)


def test_mcp_keys_are_stable_and_domain_separated() -> None:
    first = derive_mcp_keys("shared-secret")
    second = derive_mcp_keys("shared-secret")

    assert first == second
    assert first.jwt_signing_key != first.storage_fernet_key
    assert first.token_hash_key not in {
        first.jwt_signing_key,
        first.storage_fernet_key,
    }
    assert len(first.jwt_signing_key) == 32
    assert len(first.storage_fernet_key) == 44
    assert len(first.token_hash_key) == 32
