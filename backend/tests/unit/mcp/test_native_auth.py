from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.mcp.auth import (
    MCP_ACCESS_SCOPE,
    MCPConfigurationError,
    InterceptApiKeyVerifier,
    XApiKeyToBearerMiddleware,
    derive_mcp_keys,
    validate_public_origin,
)
from app.services.api_key_service import ApiKeyNotFoundError


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
