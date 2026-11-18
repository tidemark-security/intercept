from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import OIDCAuthRequest
from app.services.oidc_auth_request_service import OIDCAuthRequestLimitError
from app.services.oidc_service import OIDCService


@pytest.mark.asyncio
async def test_concurrent_oidc_login_global_outstanding_quota_is_atomic(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OIDCService()
    service._auth_request_policy = SimpleNamespace(
        global_outstanding_quota=1,
        per_source_outstanding_quota=10,
        global_rate_quota=100,
        per_source_rate_quota=100,
        rate_window_seconds=3600,
        retry_after_seconds=60,
    )
    both_ready = asyncio.Event()
    arrivals = 0

    async def fake_load_provider(_db: AsyncSession) -> SimpleNamespace:
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            both_ready.set()
        await both_ready.wait()
        return SimpleNamespace(
            authorization_endpoint="https://idp.example/authorize",
            client_id="intercept-client",
            redirect_uri="https://intercept.example/api/v1/auth/oidc/callback",
            scopes="openid email profile",
        )

    monkeypatch.setattr(service, "_load_provider_configuration", fake_load_provider)

    async def begin_from_worker() -> object:
        async with session_maker() as db:
            try:
                result = await service.begin_login(
                    db,
                    redirect_to="https://intercept.example/",
                )
                await db.commit()
                return result
            except Exception as exc:
                await db.rollback()
                return exc

    results = await asyncio.wait_for(
        asyncio.gather(begin_from_worker(), begin_from_worker()),
        timeout=5,
    )

    successes = [result for result in results if isinstance(result, tuple)]
    failures = [result for result in results if isinstance(result, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], OIDCAuthRequestLimitError)


@pytest.mark.asyncio
async def test_oidc_login_enforces_per_source_outstanding_quota_without_storing_ip(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OIDCService()
    service._auth_request_policy = SimpleNamespace(
        global_outstanding_quota=10,
        per_source_outstanding_quota=1,
        global_rate_quota=100,
        per_source_rate_quota=100,
        rate_window_seconds=3600,
        retry_after_seconds=60,
    )

    async def fake_load_provider(_db: AsyncSession) -> SimpleNamespace:
        return SimpleNamespace(
            authorization_endpoint="https://idp.example/authorize",
            client_id="intercept-client",
            redirect_uri="https://intercept.example/api/v1/auth/oidc/callback",
            scopes="openid email profile",
        )

    monkeypatch.setattr(service, "_load_provider_configuration", fake_load_provider)

    async def begin(source_address: str) -> None:
        async with session_maker() as db:
            await service.begin_login(
                db,
                redirect_to="https://intercept.example/",
                source_address=source_address,
            )
            await db.commit()

    await begin("198.51.100.10")
    with pytest.raises(OIDCAuthRequestLimitError):
        await begin("198.51.100.10")
    await begin("203.0.113.20")

    async with session_maker() as db:
        rows = list(await db.scalars(select(OIDCAuthRequest)))
    assert len(rows) == 2
    assert {row.source_fingerprint for row in rows}.isdisjoint(
        {"198.51.100.10", "203.0.113.20"}
    )
    assert len({row.source_fingerprint for row in rows}) == 2


@pytest.mark.asyncio
async def test_oidc_login_rate_window_retains_consumed_history_per_source(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OIDCService()
    service._auth_request_policy = SimpleNamespace(
        global_outstanding_quota=10,
        per_source_outstanding_quota=10,
        global_rate_quota=100,
        per_source_rate_quota=1,
        rate_window_seconds=3600,
        retry_after_seconds=60,
    )

    async def fake_load_provider(_db: AsyncSession) -> SimpleNamespace:
        return SimpleNamespace(
            authorization_endpoint="https://idp.example/authorize",
            client_id="intercept-client",
            redirect_uri="https://intercept.example/api/v1/auth/oidc/callback",
            scopes="openid email profile",
        )

    monkeypatch.setattr(service, "_load_provider_configuration", fake_load_provider)

    async def begin(source_address: str) -> None:
        async with session_maker() as db:
            await service.begin_login(
                db,
                redirect_to="https://intercept.example/",
                source_address=source_address,
            )
            await db.commit()

    await begin("198.51.100.10")
    async with session_maker() as db:
        first_request = (await db.scalars(select(OIDCAuthRequest))).one()
        first_request.consumed_at = datetime.now(timezone.utc)
        await db.commit()

    with pytest.raises(OIDCAuthRequestLimitError):
        await begin("198.51.100.10")
    await begin("203.0.113.20")

    async with session_maker() as db:
        rows = list(await db.scalars(select(OIDCAuthRequest)))
    assert len(rows) == 2
    assert sum(row.consumed_at is not None for row in rows) == 1


@pytest.mark.asyncio
async def test_oidc_login_global_rate_window_bounds_many_sources(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OIDCService()
    service._auth_request_policy = SimpleNamespace(
        global_outstanding_quota=10,
        per_source_outstanding_quota=10,
        global_rate_quota=1,
        per_source_rate_quota=10,
        rate_window_seconds=3600,
        retry_after_seconds=60,
    )

    async def fake_load_provider(_db: AsyncSession) -> SimpleNamespace:
        return SimpleNamespace(
            authorization_endpoint="https://idp.example/authorize",
            client_id="intercept-client",
            redirect_uri="https://intercept.example/api/v1/auth/oidc/callback",
            scopes="openid email profile",
        )

    monkeypatch.setattr(service, "_load_provider_configuration", fake_load_provider)

    async def begin(source_address: str) -> None:
        async with session_maker() as db:
            await service.begin_login(
                db,
                redirect_to="https://intercept.example/",
                source_address=source_address,
            )
            await db.commit()

    await begin("198.51.100.10")
    async with session_maker() as db:
        first_request = (await db.scalars(select(OIDCAuthRequest))).one()
        first_request.consumed_at = datetime.now(timezone.utc)
        await db.commit()

    with pytest.raises(OIDCAuthRequestLimitError):
        await begin("203.0.113.20")

    async with session_maker() as db:
        assert len(list(await db.scalars(select(OIDCAuthRequest)))) == 1


@pytest.mark.asyncio
async def test_oidc_login_cleans_old_terminal_history_but_retains_live_rows(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)

    def request_row(
        state: str,
        *,
        created_at: datetime,
        expires_at: datetime,
        consumed_at: datetime | None = None,
    ) -> OIDCAuthRequest:
        return OIDCAuthRequest(
            state=state,
            nonce=f"nonce-{state}",
            browser_binding_hash="b" * 64,
            source_fingerprint="f" * 64,
            redirect_to="https://intercept.example/",
            created_at=created_at,
            expires_at=expires_at,
            consumed_at=consumed_at,
        )

    async with session_maker() as db:
        db.add_all(
            [
                request_row(
                    "old-consumed",
                    created_at=now - timedelta(hours=2),
                    expires_at=now - timedelta(hours=1),
                    consumed_at=now - timedelta(hours=1),
                ),
                request_row(
                    "old-expired",
                    created_at=now - timedelta(hours=2),
                    expires_at=now - timedelta(hours=1),
                ),
                request_row(
                    "old-live",
                    created_at=now - timedelta(hours=2),
                    expires_at=now + timedelta(minutes=5),
                ),
                request_row(
                    "recent-consumed",
                    created_at=now - timedelta(minutes=5),
                    expires_at=now + timedelta(minutes=5),
                    consumed_at=now - timedelta(minutes=1),
                ),
            ]
        )
        await db.commit()

    service = OIDCService()
    service._auth_request_policy = SimpleNamespace(
        global_outstanding_quota=10,
        per_source_outstanding_quota=10,
        global_rate_quota=100,
        per_source_rate_quota=100,
        rate_window_seconds=3600,
        retry_after_seconds=60,
    )

    async def fake_load_provider(_db: AsyncSession) -> SimpleNamespace:
        return SimpleNamespace(
            authorization_endpoint="https://idp.example/authorize",
            client_id="intercept-client",
            redirect_uri="https://intercept.example/api/v1/auth/oidc/callback",
            scopes="openid email profile",
        )

    monkeypatch.setattr(service, "_load_provider_configuration", fake_load_provider)
    async with session_maker() as db:
        await service.begin_login(
            db,
            redirect_to="https://intercept.example/",
            source_address="203.0.113.20",
        )
        await db.commit()

    async with session_maker() as db:
        states = set(await db.scalars(select(OIDCAuthRequest.state)))
    assert "old-consumed" not in states
    assert "old-expired" not in states
    assert "old-live" in states
    assert "recent-consumed" in states
    assert len(states) == 3
