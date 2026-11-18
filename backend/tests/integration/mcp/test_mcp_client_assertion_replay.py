"""Cluster-wide replay protection for FastMCP private_key_jwt assertions."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
from fastmcp.server.auth.cimd import CIMDClientManager, CIMDDocument
from fastmcp.server.auth.oauth_proxy.models import ProxyDCRClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.applications import Starlette

from app.mcp.cimd import BoundedCIMDClientManager
from app.mcp.local_oauth_provider import InterceptOAuthProvider
from app.models.models import MCPOAuthClientAssertionJTI
from app.services.mcp_client_assertion_replay_service import (
    MCP_CLIENT_ASSERTION_REPLAY_CAPACITY_LOCK_ID,
    MCPClientAssertionReplayBusyError,
    MCPClientAssertionReplayCapacityError,
    MCPClientAssertionReplayError,
    MCPClientAssertionReplayService,
    MCPClientAssertionReplayStoreError,
    assertion_replay_digests,
)


class _BogusGrantBackend:
    async def get_client(self, _client_id: str):
        return None

    async def register_client(self, _client_info) -> None:
        pass

    async def load_authorization_code(self, _client, _authorization_code: str):
        return None

    async def load_access_token(self, _token: str):
        return None

    async def load_refresh_token(self, _client, _refresh_token: str):
        return None


class _ConnectionRefusedSessionContext:
    async def __aenter__(self):
        raise ConnectionRefusedError("sensitive-db-host.internal:5432")

    async def __aexit__(self, *_args):
        return False


def _connection_refused_session_factory():
    return _ConnectionRefusedSessionContext()


def _private_cimd_client(client_id: str) -> ProxyDCRClient:
    document = CIMDDocument(
        client_id=client_id,
        client_name="Capacity Test Client",
        redirect_uris=["http://127.0.0.1:49152/callback"],
        token_endpoint_auth_method="private_key_jwt",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp:access",
        jwks={"keys": [{"kty": "OKP", "crv": "Ed25519", "x": "test"}]},
    )
    return ProxyDCRClient(
        client_id=client_id,
        redirect_uris=None,
        token_endpoint_auth_method=document.token_endpoint_auth_method,
        grant_types=document.grant_types,
        response_types=document.response_types,
        scope=document.scope,
        client_name=document.client_name,
        cimd_document=document,
    )


async def test_concurrent_workers_accept_exactly_one_assertion_jti(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    services = [
        MCPClientAssertionReplayService(session_factory=session_maker),
        MCPClientAssertionReplayService(session_factory=session_maker),
    ]
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    results = await asyncio.gather(
        *(
            services[index % len(services)].reserve(
                client_id="https://client.example/.well-known/oauth-client.json",
                jti="shared-jti",
                expires_at=expires_at,
            )
            for index in range(8)
        ),
        return_exceptions=True,
    )

    assert sum(result is None for result in results) == 1
    replays = [result for result in results if result is not None]
    assert len(replays) == 7
    assert all(
        isinstance(
            result,
            (MCPClientAssertionReplayError, MCPClientAssertionReplayBusyError),
        )
        for result in replays
    )

    async with session_maker() as db:
        stored = await db.scalar(select(func.count()).select_from(MCPOAuthClientAssertionJTI))
    assert stored == 1


async def test_concurrent_unique_assertions_cannot_exceed_global_capacity(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    services = [
        MCPClientAssertionReplayService(
            session_factory=session_maker,
            max_rows=3,
            max_rows_per_client=3,
        )
        for _ in range(10)
    ]
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    results = await asyncio.gather(
        *(
            service.reserve(
                client_id=f"https://client-{index}.example/client.json",
                jti=f"unique-jti-{index}",
                expires_at=expires_at,
            )
            for index, service in enumerate(services)
        ),
        return_exceptions=True,
    )

    assert 1 <= sum(result is None for result in results) <= 3
    assert all(
        result is None
        or isinstance(
            result,
            (
                MCPClientAssertionReplayBusyError,
                MCPClientAssertionReplayCapacityError,
            ),
        )
        for result in results
    )

    capacity_seen = False
    for index in range(10, 20):
        try:
            await services[0].reserve(
                client_id=f"https://client-{index}.example/client.json",
                jti=f"unique-jti-{index}",
                expires_at=expires_at,
            )
        except MCPClientAssertionReplayCapacityError:
            capacity_seen = True
            break
    assert capacity_seen
    async with session_maker() as db:
        stored = await db.scalar(
            select(func.count()).select_from(MCPOAuthClientAssertionJTI)
        )
    assert stored == 3


async def test_capacity_lock_contention_fails_fast_without_waiting_in_pool(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    service = MCPClientAssertionReplayService(session_factory=session_maker)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    async with session_maker() as blocker:
        await blocker.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": MCP_CLIENT_ASSERTION_REPLAY_CAPACITY_LOCK_ID},
        )
        started_at = asyncio.get_running_loop().time()
        with pytest.raises(MCPClientAssertionReplayBusyError):
            await asyncio.wait_for(
                service.reserve(
                    client_id="https://busy.example/client.json",
                    jti="busy-jti",
                    expires_at=expires_at,
                ),
                timeout=0.5,
            )
        assert asyncio.get_running_loop().time() - started_at < 0.5
        await blocker.rollback()


async def test_per_client_capacity_does_not_consume_other_clients_headroom(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    service = MCPClientAssertionReplayService(
        session_factory=session_maker,
        max_rows=3,
        max_rows_per_client=1,
    )
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    await service.reserve(
        client_id="https://first.example/client.json",
        jti="first-jti",
        expires_at=expires_at,
    )
    with pytest.raises(MCPClientAssertionReplayCapacityError):
        await service.reserve(
            client_id="https://first.example/client.json",
            jti="second-jti",
            expires_at=expires_at,
        )
    await service.reserve(
        client_id="https://second.example/client.json",
        jti="second-client-jti",
        expires_at=expires_at,
    )

    async with session_maker() as db:
        stored = await db.scalar(
            select(func.count()).select_from(MCPOAuthClientAssertionJTI)
        )
    assert stored == 2


async def test_bogus_grants_cannot_grow_ledger_past_capacity(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        CIMDClientManager,
        "validate_private_key_jwt",
        AsyncMock(return_value=True),
    )
    client_id = "https://client.example/oauth-client.json"
    manager = BoundedCIMDClientManager(
        enable_cimd=True,
        max_cache_entries=10,
        assertion_replay_service=MCPClientAssertionReplayService(
            session_factory=session_maker,
            max_rows=2,
            max_rows_per_client=2,
        ),
    )
    manager.get_client = AsyncMock(  # type: ignore[method-assign]
        return_value=_private_cimd_client(client_id)
    )
    provider = InterceptOAuthProvider(
        backend=_BogusGrantBackend(),  # type: ignore[arg-type]
        pending_authorizations=SimpleNamespace(),
        public_base_url="http://localhost:8080",
    )
    provider._cimd_manager = manager
    oauth_app = Starlette(routes=provider.get_routes("/streamable/"))

    responses: list[httpx.Response] = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=oauth_app),
        base_url="http://testserver",
    ) as oauth_client:
        for index in range(4):
            assertion = jwt.encode(
                {"jti": f"bogus-grant-{index}", "exp": int(time.time()) + 120},
                "test-only-signing-key-at-least-32-bytes",
                algorithm="HS256",
            )
            responses.append(
                await oauth_client.post(
                    "/token",
                    data={
                        "client_id": client_id,
                        "client_assertion_type": (
                            "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
                        ),
                        "client_assertion": assertion,
                        "grant_type": "authorization_code",
                        "code": f"bogus-code-{index}",
                        "redirect_uri": "http://127.0.0.1:49152/callback",
                        "code_verifier": "a" * 43,
                    },
                )
            )

    assert [response.status_code for response in responses] == [401, 401, 503, 503]
    assert [response.json()["error"] for response in responses] == [
        "invalid_grant",
        "invalid_grant",
        "server_error",
        "server_error",
    ]
    async with session_maker() as db:
        stored = await db.scalar(
            select(func.count()).select_from(MCPOAuthClientAssertionJTI)
        )
    assert stored == 2


async def test_connection_refusal_fails_closed_with_sanitized_oauth_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        CIMDClientManager,
        "validate_private_key_jwt",
        AsyncMock(return_value=True),
    )
    client_id = "https://client.example/oauth-client.json"
    manager = BoundedCIMDClientManager(
        enable_cimd=True,
        max_cache_entries=10,
        assertion_replay_service=MCPClientAssertionReplayService(
            session_factory=_connection_refused_session_factory,
        ),
    )
    manager.get_client = AsyncMock(  # type: ignore[method-assign]
        return_value=_private_cimd_client(client_id)
    )
    provider = InterceptOAuthProvider(
        backend=_BogusGrantBackend(),  # type: ignore[arg-type]
        pending_authorizations=SimpleNamespace(),
        public_base_url="http://localhost:8080",
    )
    provider._cimd_manager = manager
    oauth_app = Starlette(routes=provider.get_routes("/streamable/"))
    assertion = jwt.encode(
        {"jti": "connection-refused", "exp": int(time.time()) + 120},
        "test-only-signing-key-at-least-32-bytes",
        algorithm="HS256",
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=oauth_app),
        base_url="http://testserver",
    ) as oauth_client:
        response = await oauth_client.post(
            "/token",
            data={
                "client_id": client_id,
                "client_assertion_type": (
                    "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
                ),
                "client_assertion": assertion,
                "grant_type": "authorization_code",
                "code": "bogus-code",
                "redirect_uri": "http://127.0.0.1:49152/callback",
                "code_verifier": "a" * 43,
            },
        )

    assert response.status_code == 503
    assert response.json() == {
        "error": "server_error",
        "error_description": (
            "Client assertion replay protection is temporarily unavailable"
        ),
    }
    assert "sensitive-db-host" not in response.text


async def test_connection_refusal_is_wrapped_as_replay_store_error() -> None:
    service = MCPClientAssertionReplayService(
        session_factory=_connection_refused_session_factory,
    )

    with pytest.raises(MCPClientAssertionReplayStoreError) as exc_info:
        await service.reserve(
            client_id="https://client.example/client.json",
            jti="connection-refused-service",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
        )

    assert str(exc_info.value) == (
        "Client assertion replay protection is unavailable"
    )
    assert isinstance(exc_info.value.__cause__, ConnectionRefusedError)


async def test_expired_reservation_can_be_replaced_before_cron_cleanup(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    client_id = "https://client.example/.well-known/oauth-client.json"
    jti = "reusable-after-expiry"
    now = datetime.now(timezone.utc)
    client_id_hash, jti_hash = assertion_replay_digests(client_id, jti)
    async with session_maker() as db:
        db.add(
            MCPOAuthClientAssertionJTI(
                client_id_hash=client_id_hash,
                jti_hash=jti_hash,
                created_at=now - timedelta(minutes=10),
                expires_at=now - timedelta(minutes=5),
            )
        )
        await db.commit()

    replacement_expiry = now + timedelta(minutes=5)
    service = MCPClientAssertionReplayService(
        session_factory=session_maker,
        max_rows=1,
        max_rows_per_client=1,
    )
    await service.reserve(
        client_id=client_id,
        jti=jti,
        expires_at=replacement_expiry,
    )

    async with session_maker() as db:
        stored = (
            await db.execute(select(MCPOAuthClientAssertionJTI))
        ).scalar_one()
    assert stored.expires_at == replacement_expiry
    assert stored.created_at >= now


async def test_concurrent_reclaim_of_expired_reservation_has_one_winner(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    client_id = "https://client.example/.well-known/oauth-client.json"
    jti = "concurrent-expired-reclaim"
    now = datetime.now(timezone.utc)
    client_id_hash, jti_hash = assertion_replay_digests(client_id, jti)
    async with session_maker() as db:
        db.add(
            MCPOAuthClientAssertionJTI(
                client_id_hash=client_id_hash,
                jti_hash=jti_hash,
                created_at=now - timedelta(minutes=10),
                expires_at=now - timedelta(minutes=5),
            )
        )
        await db.commit()

    services = [
        MCPClientAssertionReplayService(session_factory=session_maker)
        for _ in range(4)
    ]
    replacement_expiry = now + timedelta(minutes=5)
    results = await asyncio.gather(
        *(
            service.reserve(
                client_id=client_id,
                jti=jti,
                expires_at=replacement_expiry,
            )
            for service in services
        ),
        return_exceptions=True,
    )

    assert sum(result is None for result in results) == 1
    assert all(
        result is None
        or isinstance(
            result,
            (MCPClientAssertionReplayError, MCPClientAssertionReplayBusyError),
        )
        for result in results
    )


async def test_database_clock_rejects_claim_after_absolute_deadline(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    database_now = datetime.now(timezone.utc)
    service = MCPClientAssertionReplayService(
        session_factory=session_maker,
        # Simulate an application worker whose clock is two minutes behind the DB.
        now=lambda: database_now - timedelta(minutes=2),
    )

    with pytest.raises(MCPClientAssertionReplayError):
        await service.reserve(
            client_id="https://client.example/client.json",
            jti="expired-on-database-clock",
            expires_at=database_now - timedelta(seconds=1),
        )

    async with session_maker() as db:
        stored = await db.scalar(
            select(func.count()).select_from(MCPOAuthClientAssertionJTI)
        )
    assert stored == 0


async def test_database_clock_rejects_claim_after_delete_conflict_wait(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    client_id = "https://client.example/delete-conflict.json"
    jti = "expires-while-delete-is-blocking"
    client_id_hash, jti_hash = assertion_replay_digests(client_id, jti)
    now = datetime.now(timezone.utc)
    async with session_maker() as db:
        db.add(
            MCPOAuthClientAssertionJTI(
                client_id_hash=client_id_hash,
                jti_hash=jti_hash,
                created_at=now - timedelta(minutes=10),
                expires_at=now - timedelta(minutes=5),
            )
        )
        await db.commit()

    service = MCPClientAssertionReplayService(session_factory=session_maker)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    reservation = None
    async with session_maker() as cleanup:
        await cleanup.execute(
            text(
                "DELETE FROM mcp_oauth_client_assertion_jtis "
                "WHERE client_id_hash = :client_id_hash "
                "AND jti_hash = :jti_hash"
            ),
            {"client_id_hash": client_id_hash, "jti_hash": jti_hash},
        )
        reservation = asyncio.create_task(
            service.reserve(
                client_id=client_id,
                jti=jti,
                expires_at=expires_at,
            )
        )
        try:
            await asyncio.sleep(0.2)
            assert not reservation.done()
            remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
            await asyncio.sleep(max(remaining + 0.1, 0))
        finally:
            await cleanup.commit()

    assert reservation is not None
    with pytest.raises(MCPClientAssertionReplayError):
        await reservation
    async with session_maker() as db:
        stored = await db.scalar(
            select(func.count()).select_from(MCPOAuthClientAssertionJTI)
        )
    assert stored == 0


async def test_request_claim_does_not_perform_scheduled_cleanup(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(timezone.utc)
    stale_client_hash, stale_jti_hash = assertion_replay_digests(
        "https://stale.example/client.json",
        "stale-jti",
    )
    async with session_maker() as db:
        db.add(
            MCPOAuthClientAssertionJTI(
                client_id_hash=stale_client_hash,
                jti_hash=stale_jti_hash,
                created_at=now - timedelta(minutes=10),
                expires_at=now - timedelta(minutes=5),
            )
        )
        await db.commit()

    service = MCPClientAssertionReplayService(session_factory=session_maker)
    await service.reserve(
        client_id="https://active.example/client.json",
        jti="active-jti",
        expires_at=now + timedelta(minutes=5),
    )

    async with session_maker() as db:
        stored = await db.scalar(
            select(func.count()).select_from(MCPOAuthClientAssertionJTI)
        )
    assert stored == 2


async def test_same_jti_is_independent_between_clients(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    service = MCPClientAssertionReplayService(session_factory=session_maker)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    await service.reserve(
        client_id="https://first-client.example/client.json",
        jti="client-local-jti",
        expires_at=expires_at,
    )
    await service.reserve(
        client_id="https://second-client.example/client.json",
        jti="client-local-jti",
        expires_at=expires_at,
    )

    async with session_maker() as db:
        stored = await db.scalar(select(func.count()).select_from(MCPOAuthClientAssertionJTI))
    assert stored == 2


async def test_active_replay_does_not_mutate_the_original_claim(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    service = MCPClientAssertionReplayService(session_factory=session_maker)
    first_expiry = datetime.now(timezone.utc) + timedelta(minutes=2)
    await service.reserve(
        client_id="https://client.example/client.json",
        jti="immutable-active-claim",
        expires_at=first_expiry,
    )
    async with session_maker() as db:
        original = (
            await db.execute(select(MCPOAuthClientAssertionJTI))
        ).scalar_one()
        original_created_at = original.created_at

    try:
        await service.reserve(
            client_id="https://client.example/client.json",
            jti="immutable-active-claim",
            expires_at=first_expiry + timedelta(minutes=1),
        )
    except MCPClientAssertionReplayError:
        pass
    else:  # pragma: no cover - assertion documents the security boundary
        raise AssertionError("Active client assertion replay was accepted")

    async with session_maker() as db:
        stored = (
            await db.execute(select(MCPOAuthClientAssertionJTI))
        ).scalar_one()
    assert stored.created_at == original_created_at
    assert stored.expires_at == first_expiry
