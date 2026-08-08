"""Bounds and durable assertion replay protection for FastMCP CIMD clients."""

import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
import pytest
from fastmcp.server.auth.cimd import CIMDClientManager

from app.mcp.cimd import (
    BoundedCIMDClientManager,
    cimd_fetch_requires_network,
    trim_cimd_cache,
)
from app.services.mcp_client_assertion_replay_service import (
    MCPClientAssertionReplayError,
    MCPClientAssertionReplayStoreError,
)


def test_cimd_cache_trimming_evicts_oldest_entries() -> None:
    cache = {"first": object(), "second": object(), "third": object()}
    manager = SimpleNamespace(_fetcher=SimpleNamespace(_cache=cache))

    trim_cimd_cache(manager, max_entries=2)

    assert list(cache) == ["second", "third"]


def test_cimd_network_admission_skips_only_fresh_cached_documents() -> None:
    fresh = SimpleNamespace(must_revalidate=False, expires_at=time.time() + 60)
    stale = SimpleNamespace(must_revalidate=False, expires_at=time.time() - 1)
    manager = SimpleNamespace(
        _fetcher=SimpleNamespace(_cache={"fresh": fresh, "stale": stale})
    )

    assert cimd_fetch_requires_network(manager, "fresh") is False
    assert cimd_fetch_requires_network(manager, "stale") is True
    assert cimd_fetch_requires_network(manager, "missing") is True


@pytest.mark.asyncio
async def test_validated_private_key_assertion_is_reserved_durably(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validated = AsyncMock(return_value=True)
    monkeypatch.setattr(
        CIMDClientManager,
        "validate_private_key_jwt",
        validated,
    )
    replay_service = SimpleNamespace(reserve=AsyncMock(return_value=None))
    manager = BoundedCIMDClientManager(
        enable_cimd=True,
        max_cache_entries=10,
        assertion_replay_service=replay_service,
    )
    client_id = "https://client.example/.well-known/oauth-client.json"
    expires_at = int(time.time()) + 120
    assertion = jwt.encode(
        {"jti": "one-time-assertion", "exp": expires_at},
        "test-only-signing-key-at-least-32-bytes",
        algorithm="HS256",
    )
    client = SimpleNamespace(client_id=client_id)

    assert await manager.validate_private_key_jwt(
        assertion,
        client,
        "https://intercept.example/mcp/token",
    )

    validated.assert_awaited_once()
    replay_service.reserve.assert_awaited_once_with(
        client_id=client_id,
        jti="one-time-assertion",
        expires_at=datetime.fromtimestamp(expires_at + 60, tz=timezone.utc),
    )


@pytest.mark.asyncio
async def test_private_key_assertion_fails_closed_without_shared_replay_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        CIMDClientManager,
        "validate_private_key_jwt",
        AsyncMock(return_value=True),
    )
    manager = BoundedCIMDClientManager(
        enable_cimd=True,
        max_cache_entries=10,
    )
    assertion = jwt.encode(
        {"jti": "unprotected-assertion", "exp": int(time.time()) + 120},
        "test-only-signing-key-at-least-32-bytes",
        algorithm="HS256",
    )

    with pytest.raises(ValueError, match="replay protection is unavailable"):
        await manager.validate_private_key_jwt(
            assertion,
            SimpleNamespace(client_id="https://client.example/client.json"),
            "https://intercept.example/mcp/token",
        )


@pytest.mark.asyncio
async def test_failed_cryptographic_validation_does_not_burn_jti(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        CIMDClientManager,
        "validate_private_key_jwt",
        AsyncMock(return_value=False),
    )
    replay_service = SimpleNamespace(reserve=AsyncMock(return_value=None))
    manager = BoundedCIMDClientManager(
        enable_cimd=True,
        max_cache_entries=10,
        assertion_replay_service=replay_service,
    )
    assertion = jwt.encode(
        {"jti": "unvalidated-jti", "exp": int(time.time()) + 120},
        "test-only-signing-key-at-least-32-bytes",
        algorithm="HS256",
    )

    with pytest.raises(ValueError, match="Client assertion validation failed"):
        await manager.validate_private_key_jwt(
            assertion,
            SimpleNamespace(client_id="https://client.example/client.json"),
            "https://intercept.example/mcp/token",
        )
    replay_service.reserve.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_local_raw_jti_cache_is_not_authoritative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def emulate_fastmcp_validation(
        manager,
        assertion: str,
        client,
        token_endpoint: str,
    ) -> bool:
        del client, token_endpoint
        claims = jwt.decode(assertion, options={"verify_signature": False})
        jti = claims["jti"]
        if jti in manager._assertion_validator._jti_cache:
            raise ValueError("raw JTI collision")
        manager._assertion_validator._jti_cache[jti] = claims["exp"]
        return True

    monkeypatch.setattr(
        CIMDClientManager,
        "validate_private_key_jwt",
        emulate_fastmcp_validation,
    )
    replay_service = SimpleNamespace(reserve=AsyncMock(return_value=None))
    manager = BoundedCIMDClientManager(
        enable_cimd=True,
        max_cache_entries=10,
        assertion_replay_service=replay_service,
    )
    assertion = jwt.encode(
        {"jti": "same-value", "exp": int(time.time()) + 120},
        "test-only-signing-key-at-least-32-bytes",
        algorithm="HS256",
    )

    assert await manager.validate_private_key_jwt(
        assertion,
        SimpleNamespace(client_id="https://first.example/client.json"),
        "https://intercept.example/mcp/token",
    )
    assert await manager.validate_private_key_jwt(
        assertion,
        SimpleNamespace(client_id="https://second.example/client.json"),
        "https://intercept.example/mcp/token",
    )

    assert manager._assertion_validator._jti_cache == {}
    assert replay_service.reserve.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "service_error",
    [
        MCPClientAssertionReplayError("attacker-controlled-jti"),
        MCPClientAssertionReplayStoreError("ledger unavailable"),
    ],
)
async def test_replay_failures_do_not_fall_back_or_expose_the_jti(
    monkeypatch: pytest.MonkeyPatch,
    service_error: Exception,
) -> None:
    monkeypatch.setattr(
        CIMDClientManager,
        "validate_private_key_jwt",
        AsyncMock(return_value=True),
    )
    manager = BoundedCIMDClientManager(
        enable_cimd=True,
        max_cache_entries=10,
        assertion_replay_service=SimpleNamespace(
            reserve=AsyncMock(side_effect=service_error)
        ),
    )
    assertion = jwt.encode(
        {"jti": "attacker-controlled-jti", "exp": int(time.time()) + 120},
        "test-only-signing-key-at-least-32-bytes",
        algorithm="HS256",
    )

    with pytest.raises((ValueError, MCPClientAssertionReplayStoreError)) as exc_info:
        await manager.validate_private_key_jwt(
            assertion,
            SimpleNamespace(client_id="https://client.example/client.json"),
            "https://intercept.example/mcp/token",
        )

    assert "attacker-controlled-jti" not in str(exc_info.value)
