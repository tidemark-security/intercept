"""Integration tests for FastMCP-native local OAuth 2.1 + PKCE."""

from __future__ import annotations

import asyncio
import base64
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import api_app, app, compose_http_app
from app.mcp.local_oauth_provider import (
    PendingAuthorizationUnavailableError,
    create_local_oauth_provider,
)
from app.mcp.runtime import (
    MCPAuthMode,
    MCPAuthSnapshot,
    build_mcp_runtime,
)
from app.models.enums import UserStatus
from app.models.models import (
    MCPDCRRegistration,
    MCPOAuthAuthorizationCapacity,
    MCPOAuthAuthorizationCode,
    MCPOAuthClient,
    MCPOAuthConsent,
    MCPOAuthPendingAuthorization,
    MCPOAuthProviderGrantReference,
    MCPOAuthToken,
    UserAccount,
)
from app.services.mcp_registration_service import (
    MCPDCRRegistrationService,
    MCPOAuthAuthorizationCapacityService,
    MCPRegistrationExpiredError,
    MCPRegistrationPolicy,
)
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


PUBLIC_BASE_URL = "http://localhost:8000"
LOGIN_BASE_URL = "http://localhost:5173"
REDIRECT_URI = "http://127.0.0.1:49152/callback"
RESOURCE = f"{PUBLIC_BASE_URL}/mcp/streamable/"
CODE_VERIFIER = "a" * 64


def _code_challenge(verifier: str = CODE_VERIFIER) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


@pytest_asyncio.fixture
async def local_oauth_client_factory(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MCP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("MCP_OAUTH_PUBLIC_BASE_URL", PUBLIC_BASE_URL)
    monkeypatch.setenv("MCP_OAUTH_LOGIN_BASE_URL", LOGIN_BASE_URL)
    monkeypatch.setenv("MCP_OAUTH_REFRESH_TOKEN_TTL_DAYS", "7")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")

    @asynccontextmanager
    async def factory(
        *,
        registration_policy: MCPRegistrationPolicy | None = None,
        now=None,
    ):
        policy = registration_policy or MCPRegistrationPolicy()
        registration_service = MCPDCRRegistrationService(
            session_factory=session_maker,
            policy=policy,
            now=now,
        )
        previous_http_app = app._http_app
        previous_runtime = app.runtime
        runtime = await build_mcp_runtime(
            snapshot=MCPAuthSnapshot(
                mode=MCPAuthMode.LOCAL_OAUTH,
                oauth_enabled=True,
                public_origin=PUBLIC_BASE_URL,
                login_origin=LOGIN_BASE_URL,
                access_token_ttl_seconds=3600,
                refresh_token_ttl_days=7,
                oidc=None,
                registration_policy=policy,
            ),
            database_url="postgresql://unused-in-local-mode",
            secret_key="test-fastmcp-local-oauth-secret",
            session_factory=session_maker,
            local_provider_factory=(
                lambda snapshot, token_hash_key: create_local_oauth_provider(
                    snapshot=snapshot,
                    session_factory=session_maker,
                    token_hash_key=token_hash_key,
                    registration_service=registration_service,
                )
            ),
        )
        app.install(compose_http_app(api_app, runtime), runtime)
        api_app.state.mcp_runtime = runtime
        try:
            yield client, runtime
        finally:
            app.install(previous_http_app, previous_runtime)
            api_app.state.mcp_runtime = previous_runtime

    yield factory


@pytest_asyncio.fixture
async def local_oauth_client(local_oauth_client_factory):
    async with local_oauth_client_factory() as installed:
        yield installed


async def _register_client(client: AsyncClient) -> str:
    response = await client.post(
        "/mcp/register",
        json={
            "client_name": "Codex Test Client",
            "client_uri": "https://codex.example.test",
            "redirect_uris": [REDIRECT_URI],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "scope": "mcp:access",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["client_id"]


def _registration_payload(*, name: str = "Codex Test Client") -> dict[str, object]:
    return {
        "client_name": name,
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "scope": "mcp:access",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "requested_method",
    [None, "client_secret_post", "client_secret_basic"],
)
async def test_dynamic_registration_is_always_public_and_secretless(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    requested_method: str | None,
) -> None:
    client, _runtime = local_oauth_client
    registration = {
        "client_name": "Public DCR Client",
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "scope": "mcp:access",
    }
    if requested_method is not None:
        registration["token_endpoint_auth_method"] = requested_method

    response = await client.post("/mcp/register", json=registration)

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["token_endpoint_auth_method"] == "none"
    assert payload.get("client_secret") is None
    assert payload.get("client_secret_expires_at") is None

    async with session_maker() as session:
        stored = (
            await session.execute(
                select(MCPOAuthClient).where(
                    MCPOAuthClient.client_id == payload["client_id"]
                )
            )
        ).scalar_one()
    assert stored.token_endpoint_auth_method == "none"
    assert "client_secret" not in stored.client_metadata


@pytest.mark.asyncio
async def test_authorization_metadata_advertises_only_supported_client_auth(
    local_oauth_client,
) -> None:
    client, _runtime = local_oauth_client

    response = await client.get(
        "/.well-known/oauth-authorization-server/mcp"
    )

    assert response.status_code == 200, response.text
    metadata = response.json()
    assert metadata["token_endpoint_auth_methods_supported"] == [
        "none",
        "private_key_jwt",
    ]
    assert metadata["revocation_endpoint_auth_methods_supported"] == [
        "none",
        "private_key_jwt",
    ]


@pytest.mark.asyncio
async def test_dynamic_registration_pending_quota_is_atomic_under_concurrency(
    local_oauth_client_factory,
) -> None:
    async with local_oauth_client_factory(
        registration_policy=MCPRegistrationPolicy(
            pending_quota=1,
            per_ip_quota=10,
        )
    ) as (client, _runtime):
        responses = await asyncio.gather(
            client.post("/mcp/register", json=_registration_payload(name="Client A")),
            client.post("/mcp/register", json=_registration_payload(name="Client B")),
        )

    assert sorted(response.status_code for response in responses) == [201, 400]
    rejected = next(response for response in responses if response.status_code == 400)
    assert "registration queue is full" in rejected.json()[
        "error_description"
    ].lower()


@pytest.mark.asyncio
async def test_dynamic_registration_rate_limit_uses_direct_asgi_peer(
    local_oauth_client_factory,
) -> None:
    async with local_oauth_client_factory(
        registration_policy=MCPRegistrationPolicy(
            pending_quota=10,
            per_ip_quota=1,
        )
    ) as (client, _runtime):
        first = await client.post(
            "/mcp/register",
            headers={"X-Forwarded-For": "198.51.100.10"},
            json=_registration_payload(name="First"),
        )
        second = await client.post(
            "/mcp/register",
            headers={"X-Forwarded-For": "203.0.113.20"},
            json=_registration_payload(name="Second"),
        )

    assert first.status_code == 201
    assert second.status_code == 400
    assert "too many" in second.json()["error_description"].lower()


@pytest.mark.asyncio
async def test_pending_authorization_per_client_quota_is_atomic(
    local_oauth_client_factory,
) -> None:
    async with local_oauth_client_factory(
        registration_policy=MCPRegistrationPolicy(
            pending_quota=10,
            per_ip_quota=10,
            pending_authorization_global_quota=10,
            pending_authorization_per_client_quota=1,
        )
    ) as (client, _runtime):
        client_id = await _register_client(client)
        responses = await asyncio.gather(
            client.get(
                "/mcp/authorize",
                params=_authorize_params(client_id),
                follow_redirects=False,
            ),
            client.get(
                "/mcp/authorize",
                params={**_authorize_params(client_id), "state": "second"},
                follow_redirects=False,
            ),
        )

    locations = [response.headers["location"] for response in responses]
    assert sum("/mcp/oauth/consent/" in location for location in locations) == 1
    assert sum("error=" in location for location in locations) == 1


@pytest.mark.asyncio
async def test_pending_authorization_global_quota_bounds_distinct_clients(
    local_oauth_client_factory,
) -> None:
    async with local_oauth_client_factory(
        registration_policy=MCPRegistrationPolicy(
            pending_quota=10,
            per_ip_quota=10,
            pending_authorization_global_quota=1,
            pending_authorization_per_client_quota=1,
        )
    ) as (client, _runtime):
        first_client_id = await _register_client(client)
        second_client_id = await _register_client(client)

        first = await client.get(
            "/mcp/authorize",
            params=_authorize_params(first_client_id),
            follow_redirects=False,
        )
        second = await client.get(
            "/mcp/authorize",
            params=_authorize_params(second_client_id),
            follow_redirects=False,
        )

    assert "/mcp/oauth/consent/" in first.headers["location"]
    assert "error=" in second.headers["location"]


@pytest.mark.asyncio
async def test_pending_authorization_per_source_quota_is_atomic_across_clients(
    local_oauth_client_factory,
) -> None:
    async with local_oauth_client_factory(
        registration_policy=MCPRegistrationPolicy(
            pending_quota=10,
            per_ip_quota=10,
            pending_authorization_global_quota=10,
            pending_authorization_per_client_quota=1,
            pending_authorization_per_source_quota=1,
        )
    ) as (client, _runtime):
        first_client_id = await _register_client(client)
        second_client_id = await _register_client(client)
        responses = await asyncio.gather(
            client.get(
                "/mcp/authorize",
                params=_authorize_params(first_client_id),
                follow_redirects=False,
            ),
            client.get(
                "/mcp/authorize",
                params={
                    **_authorize_params(second_client_id),
                    "state": "second",
                },
                follow_redirects=False,
            ),
        )

    locations = [response.headers["location"] for response in responses]
    assert sum("/mcp/oauth/consent/" in location for location in locations) == 1
    assert sum("error=" in location for location in locations) == 1


@pytest.mark.asyncio
async def test_pending_authorization_default_per_source_quota_bounds_client_fanout(
    local_oauth_client_factory,
) -> None:
    async with local_oauth_client_factory(
        registration_policy=MCPRegistrationPolicy(
            pending_quota=100,
            total_quota=100,
            per_ip_quota=100,
            pending_authorization_global_quota=100,
            pending_authorization_per_client_quota=1,
        )
    ) as (client, _runtime):
        client_ids = [await _register_client(client) for _ in range(51)]
        responses = [
            await client.get(
                "/mcp/authorize",
                params={
                    **_authorize_params(client_id),
                    "state": f"source-fanout-{index}",
                },
                follow_redirects=False,
            )
            for index, client_id in enumerate(client_ids)
        ]

    locations = [response.headers["location"] for response in responses]
    assert sum("/mcp/oauth/consent/" in location for location in locations) == 50
    assert sum("error=" in location for location in locations) == 1


@pytest.mark.asyncio
async def test_consumed_pending_authorization_releases_capacity_and_is_cleaned(
    local_oauth_client_factory,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    async with local_oauth_client_factory(
        registration_policy=MCPRegistrationPolicy(
            pending_quota=10,
            per_ip_quota=10,
            pending_authorization_global_quota=1,
            pending_authorization_per_client_quota=1,
        )
    ) as (client, _runtime):
        client_id = await _register_client(client)
        await _login(client, session_maker, analyst_user_factory)
        consent_path = await _begin_authorization(client, client_id)
        approval = await client.post(consent_path, json={"decision": "approve"})
        assert approval.status_code == 200

        next_consent_path = await _begin_authorization(client, client_id)
        assert next_consent_path != consent_path

    async with session_maker() as session:
        pending_rows = tuple(
            await session.scalars(select(MCPOAuthPendingAuthorization))
        )
        capacity_count = await session.scalar(
            select(func.count()).select_from(MCPOAuthAuthorizationCapacity)
        )
    assert len(pending_rows) == 1
    assert pending_rows[0].consumed_at is None
    assert capacity_count == 1


@pytest.mark.asyncio
async def test_active_capacity_protects_inflight_cimd_projection_from_cleanup(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    clock = [datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc)]
    service = MCPOAuthAuthorizationCapacityService(
        session_factory=session_maker,
        policy=MCPRegistrationPolicy(
            pending_authorization_global_quota=10,
            pending_authorization_per_client_quota=2,
        ),
        now=lambda: clock[0],
    )
    cimd_client_id = "https://client.example/.well-known/oauth-client.json"
    await service.reserve(
        reservation_id="inflight-cimd",
        client_id=cimd_client_id,
        provider_mode="local-cimd-fetch",
        ttl_seconds=60,
    )
    async with session_maker() as session:
        session.add(
            MCPOAuthClient(
                client_id=cimd_client_id,
                client_name="In-flight CIMD client",
                redirect_uris=[REDIRECT_URI],
                grant_types=["authorization_code"],
                response_types=["code"],
                token_endpoint_auth_method="none",
            )
        )
        await session.commit()

    await service.reserve(
        reservation_id="concurrent-authorization",
        client_id="other-client",
        provider_mode="local",
        ttl_seconds=60,
    )
    async with session_maker() as session:
        protected_projection = await session.scalar(
            select(MCPOAuthClient).where(MCPOAuthClient.client_id == cimd_client_id)
        )
    assert protected_projection is not None

    clock[0] += timedelta(seconds=61)
    await service.reserve(
        reservation_id="post-expiry-authorization",
        client_id="replacement-client",
        provider_mode="local",
        ttl_seconds=60,
    )
    async with session_maker() as session:
        expired_projection = await session.scalar(
            select(MCPOAuthClient).where(MCPOAuthClient.client_id == cimd_client_id)
        )
    assert expired_projection is None


@pytest.mark.asyncio
async def test_oidc_transaction_promotion_allocates_fresh_database_epoch(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    service = MCPOAuthAuthorizationCapacityService(
        session_factory=session_maker,
        policy=MCPRegistrationPolicy(),
    )

    prefetch_epoch = await service.reserve(
        reservation_id="oidc-prefetch-epoch",
        client_id="https://client.example/.well-known/oauth-client.json",
        provider_mode="oidc-cimd-fetch",
        ttl_seconds=60,
    )
    transaction_epoch = await service.promote(
        reservation_id="oidc-prefetch-epoch",
        pending_id="oidc-transaction-epoch",
        client_id="https://client.example/.well-known/oauth-client.json",
        ttl_seconds=900,
    )

    assert transaction_epoch > prefetch_epoch
    assert (
        await service.require_authorization_epoch("oidc-transaction-epoch")
        == transaction_epoch
    )


@pytest.mark.asyncio
async def test_abandoned_registration_expires_and_is_cleaned_up(
    local_oauth_client_factory,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    clock = [datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc)]
    async with local_oauth_client_factory(
        registration_policy=MCPRegistrationPolicy(
            pending_quota=1,
            per_ip_quota=10,
            abandoned_ttl_seconds=60,
        ),
        now=lambda: clock[0],
    ) as (client, _runtime):
        expired_client_id = await _register_client(client)

        clock[0] += timedelta(seconds=61)
        expired_authorization = await client.get(
            "/mcp/authorize",
            params=_authorize_params(expired_client_id),
            follow_redirects=False,
        )
        assert expired_authorization.status_code == 302
        expired_query = parse_qs(
            urlparse(expired_authorization.headers["location"]).query
        )
        assert expired_query["error"] == ["invalid_request"]
        assert "/mcp/oauth/consent/" not in expired_authorization.headers[
            "location"
        ]

        replacement_client_id = await _register_client(client)

        assert replacement_client_id != expired_client_id
    async with session_maker() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(MCPDCRRegistration)
            )
            == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(MCPOAuthClient))
            == 1
        )


@pytest.mark.asyncio
async def test_finalized_expired_registration_is_never_accepted_as_legacy(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    clock = [datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc)]
    service = MCPDCRRegistrationService(
        session_factory=session_maker,
        policy=MCPRegistrationPolicy(
            per_ip_quota=10,
            rate_window_seconds=60,
            abandoned_ttl_seconds=60,
        ),
        now=lambda: clock[0],
    )
    await service.reserve(
        client_id="expired-oidc-client",
        provider_mode="oidc",
        source_ip="127.0.0.1",
    )

    clock[0] += timedelta(seconds=61)
    cleanup = await service.reserve(
        client_id="replacement-oidc-client",
        provider_mode="oidc",
        source_ip="127.0.0.1",
    )
    assert cleanup.expired_client_ids == ("expired-oidc-client",)
    await service.finalize_expired(cleanup.expired_client_ids)

    with pytest.raises(
        MCPRegistrationExpiredError,
        match="not recognized|expired",
    ):
        await service.require_valid("expired-oidc-client")


@pytest.mark.asyncio
async def test_concurrent_oidc_cleanup_assigns_each_expired_client_once(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    clock = [datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc)]
    service = MCPDCRRegistrationService(
        session_factory=session_maker,
        policy=MCPRegistrationPolicy(
            pending_quota=10,
            total_quota=10,
            per_ip_quota=10,
            rate_window_seconds=60,
            abandoned_ttl_seconds=60,
        ),
        now=lambda: clock[0],
    )
    expired_client_id = "expired-oidc-cleanup-owner"
    await service.reserve(
        client_id=expired_client_id,
        provider_mode="oidc",
        source_ip="127.0.0.1",
    )

    clock[0] += timedelta(seconds=61)
    cleanup_results = await asyncio.gather(
        service.reserve(
            client_id="replacement-oidc-cleanup-one",
            provider_mode="oidc",
            source_ip="127.0.0.1",
        ),
        service.reserve(
            client_id="replacement-oidc-cleanup-two",
            provider_mode="oidc",
            source_ip="127.0.0.1",
        ),
    )

    cleanup_owners = [
        result
        for result in cleanup_results
        if expired_client_id in result.expired_client_ids
    ]
    assert len(cleanup_owners) == 1
    assert cleanup_owners[0].expired_client_ids == (expired_client_id,)


@pytest.mark.asyncio
async def test_failed_oidc_native_cleanup_is_not_reassigned_and_stays_invalid(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    clock = [datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc)]
    service = MCPDCRRegistrationService(
        session_factory=session_maker,
        policy=MCPRegistrationPolicy(
            pending_quota=10,
            total_quota=10,
            per_ip_quota=10,
            rate_window_seconds=60,
            abandoned_ttl_seconds=60,
        ),
        now=lambda: clock[0],
    )
    expired_client_id = "expired-oidc-failed-native-cleanup"
    await service.reserve(
        client_id=expired_client_id,
        provider_mode="oidc",
        source_ip="127.0.0.1",
    )

    clock[0] += timedelta(seconds=61)
    cleanup = await service.reserve(
        client_id="replacement-after-native-cleanup-failure",
        provider_mode="oidc",
        source_ip="127.0.0.1",
    )
    assert cleanup.expired_client_ids == (expired_client_id,)

    # Model the caller failing before native deletion/finalization. Ownership
    # must remain consumed so public registration cannot amplify the failure.
    retry = await service.reserve(
        client_id="next-registration-after-native-cleanup-failure",
        provider_mode="oidc",
        source_ip="127.0.0.1",
    )

    assert retry.expired_client_ids == ()
    with pytest.raises(MCPRegistrationExpiredError, match="not recognized"):
        await service.require_valid(expired_client_id)


@pytest.mark.asyncio
async def test_registration_removed_after_validation_cannot_be_activated(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    clock = [datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc)]
    service = MCPDCRRegistrationService(
        session_factory=session_maker,
        policy=MCPRegistrationPolicy(
            per_ip_quota=10,
            rate_window_seconds=60,
            abandoned_ttl_seconds=60,
        ),
        now=lambda: clock[0],
    )
    await service.reserve(
        client_id="validated-before-cleanup",
        provider_mode="oidc",
        source_ip="127.0.0.1",
    )
    assert await service.require_valid("validated-before-cleanup")

    clock[0] += timedelta(seconds=61)
    cleanup = await service.reserve(
        client_id="cleanup-trigger",
        provider_mode="oidc",
        source_ip="127.0.0.1",
    )
    await service.finalize_expired(cleanup.expired_client_ids)

    with pytest.raises(
        MCPRegistrationExpiredError,
        match="not recognized|expired",
    ):
        await service.activate("validated-before-cleanup")


@pytest.mark.asyncio
async def test_only_approved_authorization_claims_pending_quota_slot(
    local_oauth_client_factory,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    async with local_oauth_client_factory(
        registration_policy=MCPRegistrationPolicy(
            pending_quota=1,
            per_ip_quota=10,
        )
    ) as (client, _runtime):
        first_client_id = await _register_client(client)

        consent_path = await _begin_authorization(client, first_client_id)
        still_pending = await client.post(
            "/mcp/register",
            json=_registration_payload(name="Blocked before approval"),
        )
        assert still_pending.status_code == 400

        await _login(client, session_maker, analyst_user_factory)
        approval = await client.post(consent_path, json={"decision": "approve"})
        assert approval.status_code == 200
        after_approval = await client.post(
            "/mcp/register",
            json=_registration_payload(name="Allowed after approval"),
        )

    assert after_approval.status_code == 201, after_approval.text


@pytest.mark.asyncio
async def test_expired_registration_cannot_be_resurrected_by_consent(
    local_oauth_client_factory,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    clock = [datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc)]
    async with local_oauth_client_factory(
        registration_policy=MCPRegistrationPolicy(
            pending_quota=1,
            per_ip_quota=10,
            abandoned_ttl_seconds=60,
        ),
        now=lambda: clock[0],
    ) as (client, _runtime):
        client_id = await _register_client(client)
        consent_path = await _begin_authorization(client, client_id)
        await _login(client, session_maker, analyst_user_factory)

        clock[0] += timedelta(seconds=61)
        approval = await client.post(consent_path, json={"decision": "approve"})

    assert approval.status_code == 410


@pytest.mark.asyncio
async def test_expired_active_registration_rejects_authorization_code_exchange(
    local_oauth_client_factory,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    clock = [datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc)]
    async with local_oauth_client_factory(
        registration_policy=MCPRegistrationPolicy(
            pending_quota=1,
            per_ip_quota=10,
            active_ttl_seconds=60,
        ),
        now=lambda: clock[0],
    ) as (client, _runtime):
        client_id = await _register_client(client)
        await _login(client, session_maker, analyst_user_factory)
        code = await _approve_client(client, client_id)

        clock[0] += timedelta(seconds=61)
        rejected = await client.post(
            "/mcp/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": CODE_VERIFIER,
                "resource": RESOURCE,
            },
        )

    assert rejected.status_code == 401
    assert rejected.json()["error"] == "invalid_grant"


async def _login(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
):
    user = analyst_user_factory(
        username="mcp_oauth_user",
        email="mcp_oauth_user@example.test",
    )
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return user


def _authorize_params(client_id: str) -> dict[str, str]:
    return {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "code_challenge": _code_challenge(),
        "code_challenge_method": "S256",
        "scope": "mcp:access",
        "resource": RESOURCE,
        "state": "state-123",
    }


async def _begin_authorization(client: AsyncClient, client_id: str) -> str:
    response = await client.get(
        "/mcp/authorize",
        params=_authorize_params(client_id),
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.startswith(f"{LOGIN_BASE_URL}/api/v1/mcp/oauth/consent/")
    return urlparse(location).path


async def _approve_client(client: AsyncClient, client_id: str) -> str:
    consent_path = await _begin_authorization(client, client_id)
    approval = await client.post(consent_path, json={"decision": "approve"})
    assert approval.status_code == 200, approval.text
    return parse_qs(urlparse(approval.json()["redirect_to"]).query)["code"][0]


async def _exchange_code(
    client: AsyncClient,
    client_id: str,
    authorization_code: str,
) -> dict[str, Any]:
    response = await client.post(
        "/mcp/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": authorization_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
            "resource": RESOURCE,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_forced_password_change_blocks_existing_local_oauth_grants(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    client, runtime = local_oauth_client
    client_id = await _register_client(client)
    user = await _login(client, session_maker, analyst_user_factory)
    initial_code = await _approve_client(client, client_id)
    tokens = await _exchange_code(client, client_id, initial_code)
    pending_code = await _approve_client(client, client_id)

    async with session_maker() as session:
        persisted_user = await session.get(UserAccount, user.id)
        assert persisted_user is not None
        persisted_user.must_change_password = True
        await session.commit()

    refresh_response = await client.post(
        "/mcp/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": tokens["refresh_token"],
            "scope": "mcp:access",
            "resource": RESOURCE,
        },
    )
    exchange_response = await client.post(
        "/mcp/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": pending_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
            "resource": RESOURCE,
        },
    )

    assert refresh_response.status_code == 401
    assert refresh_response.json()["error"] == "invalid_grant"
    assert exchange_response.status_code == 401
    assert exchange_response.json()["error"] == "invalid_grant"
    assert await runtime.provider.load_access_token(tokens["access_token"]) is None


@pytest.mark.asyncio
async def test_disabled_user_access_token_stays_invalid_after_reenable(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    admin_user_factory,
) -> None:
    client, runtime = local_oauth_client
    client_id = await _register_client(client)
    user = await _login(client, session_maker, analyst_user_factory)
    initial_code = await _approve_client(client, client_id)
    tokens = await _exchange_code(client, client_id, initial_code)

    admin = admin_user_factory(
        username="mcp_grant_admin",
        email="mcp_grant_admin@example.test",
    )
    async with session_maker() as session:
        session.add(admin)
        await session.commit()

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert admin_login.status_code == 200, admin_login.text

    disabled = await client.patch(
        f"/api/v1/admin/auth/users/{user.id}/status",
        json={"status": "DISABLED"},
    )
    assert disabled.status_code == 204, disabled.text
    enabled = await client.patch(
        f"/api/v1/admin/auth/users/{user.id}/status",
        json={"status": "ACTIVE"},
    )
    assert enabled.status_code == 204, enabled.text

    assert await runtime.provider.load_access_token(tokens["access_token"]) is None

    relogin = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert relogin.status_code == 401, relogin.text


@pytest.mark.asyncio
async def test_disabled_user_refresh_token_stays_invalid_after_reenable(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    admin_user_factory,
) -> None:
    client, _runtime = local_oauth_client
    client_id = await _register_client(client)
    user = await _login(client, session_maker, analyst_user_factory)
    initial_code = await _approve_client(client, client_id)
    tokens = await _exchange_code(client, client_id, initial_code)

    admin = admin_user_factory(
        username="mcp_refresh_admin",
        email="mcp_refresh_admin@example.test",
    )
    async with session_maker() as session:
        session.add(admin)
        await session.commit()

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert admin_login.status_code == 200, admin_login.text
    for status_value in ("DISABLED", "ACTIVE"):
        response = await client.patch(
            f"/api/v1/admin/auth/users/{user.id}/status",
            json={"status": status_value},
        )
        assert response.status_code == 204, response.text

    refresh_response = await client.post(
        "/mcp/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": tokens["refresh_token"],
            "scope": "mcp:access",
            "resource": RESOURCE,
        },
    )

    assert refresh_response.status_code == 401
    assert refresh_response.json()["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_disabled_user_authorization_code_stays_invalid_after_reenable(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    admin_user_factory,
) -> None:
    client, _runtime = local_oauth_client
    client_id = await _register_client(client)
    user = await _login(client, session_maker, analyst_user_factory)
    pending_code = await _approve_client(client, client_id)

    admin = admin_user_factory(
        username="mcp_code_admin",
        email="mcp_code_admin@example.test",
    )
    async with session_maker() as session:
        session.add(admin)
        await session.commit()

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert admin_login.status_code == 200, admin_login.text
    for status_value in ("DISABLED", "ACTIVE"):
        response = await client.patch(
            f"/api/v1/admin/auth/users/{user.id}/status",
            json={"status": status_value},
        )
        assert response.status_code == 204, response.text

    exchange_response = await client.post(
        "/mcp/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": pending_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
            "resource": RESOURCE,
        },
    )

    assert exchange_response.status_code == 401
    assert exchange_response.json()["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_stale_active_consent_principal_cannot_mint_code_after_disable(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    client, runtime = local_oauth_client
    client_id = await _register_client(client)
    consent_path = await _begin_authorization(client, client_id)
    detached_user = await _login(client, session_maker, analyst_user_factory)
    request_id = UUID(consent_path.rsplit("/", 1)[-1])
    async with session_maker() as session:
        persisted_user = await session.get(UserAccount, detached_user.id)
        assert persisted_user is not None
        persisted_user.status = UserStatus.DISABLED
        persisted_user.credentials_invalidated_at = datetime.now(timezone.utc)
        await session.commit()

    with pytest.raises(PendingAuthorizationUnavailableError):
        await runtime.provider.complete_authorization(
            request_id,
            user=detached_user,
            approved=True,
        )

    async with session_maker() as session:
        code_count = await session.scalar(
            select(func.count())
            .select_from(MCPOAuthAuthorizationCode)
            .where(MCPOAuthAuthorizationCode.user_id == detached_user.id)
        )
    assert code_count == 0


@pytest.mark.asyncio
async def test_authorization_exchange_serializes_with_disable_and_revokes_new_tokens(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    admin_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, runtime = local_oauth_client
    client_id = await _register_client(client)
    user = await _login(client, session_maker, analyst_user_factory)
    code = await _approve_client(client, client_id)

    admin = admin_user_factory(
        username="mcp-exchange-race-admin",
        email="mcp-exchange-race-admin@example.test",
    )
    async with session_maker() as session:
        session.add(admin)
        await session.commit()
    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert admin_login.status_code == 200, admin_login.text

    service = runtime.provider._backend.service  # noqa: SLF001
    original_load = service._load_authorization_code  # noqa: SLF001
    grant_lock_requested = asyncio.Event()
    release_exchange = asyncio.Event()

    async def pause_before_grant_lock(db, *, code: str, for_update: bool = False):
        if for_update:
            grant_lock_requested.set()
            await release_exchange.wait()
        return await original_load(db, code=code, for_update=for_update)

    monkeypatch.setattr(service, "_load_authorization_code", pause_before_grant_lock)
    exchange_task = asyncio.create_task(
        client.post(
            "/mcp/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": CODE_VERIFIER,
                "resource": RESOURCE,
            },
        )
    )
    disable_task = None
    user_lock_was_held = False
    disable_waited_for_exchange = False
    try:
        await asyncio.wait_for(grant_lock_requested.wait(), timeout=2)
        async with session_maker() as probe:
            try:
                await probe.execute(
                    select(UserAccount)
                    .where(UserAccount.id == user.id)
                    .with_for_update(nowait=True)
                )
            except DBAPIError:
                user_lock_was_held = True
                await probe.rollback()

        disable_task = asyncio.create_task(
            client.patch(
                f"/api/v1/admin/auth/users/{user.id}/status",
                json={"status": "DISABLED"},
            )
        )
        await asyncio.sleep(0.1)
        disable_waited_for_exchange = not disable_task.done()
    finally:
        release_exchange.set()

    exchange_response = await exchange_task
    assert disable_task is not None
    disable_response = await disable_task
    assert exchange_response.status_code == 200, exchange_response.text
    assert disable_response.status_code == 204, disable_response.text
    assert user_lock_was_held
    assert disable_waited_for_exchange

    enabled = await client.patch(
        f"/api/v1/admin/auth/users/{user.id}/status",
        json={"status": "ACTIVE"},
    )
    assert enabled.status_code == 204, enabled.text
    assert (
        await runtime.provider.load_access_token(
            exchange_response.json()["access_token"]
        )
        is None
    )

    async with session_maker() as session:
        tokens = list(
            (
                await session.execute(
                    select(MCPOAuthToken).where(MCPOAuthToken.user_id == user.id)
                )
            ).scalars()
        )
    assert tokens and all(token.revoked_at is not None for token in tokens)


@pytest.mark.asyncio
async def test_disabling_user_revokes_persisted_mcp_grants(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    admin_user_factory,
) -> None:
    client, _runtime = local_oauth_client
    client_id = await _register_client(client)
    user = await _login(client, session_maker, analyst_user_factory)
    initial_code = await _approve_client(client, client_id)
    await _exchange_code(client, client_id, initial_code)
    await _approve_client(client, client_id)

    admin = admin_user_factory(
        username="mcp-revocation-admin",
        email="mcp-revocation-admin@example.test",
    )
    async with session_maker() as session:
        consent = (
            await session.execute(
                select(MCPOAuthConsent).where(MCPOAuthConsent.user_id == user.id)
            )
        ).scalar_one()
        session.add(admin)
        session.add(
            MCPOAuthProviderGrantReference(
                consent_id=consent.id,
                provider_reference_hash="pre-disable-provider-reference",
            )
        )
        await session.commit()

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert admin_login.status_code == 200, admin_login.text
    disabled = await client.patch(
        f"/api/v1/admin/auth/users/{user.id}/status",
        json={"status": "DISABLED"},
    )
    assert disabled.status_code == 204, disabled.text

    async with session_maker() as session:
        codes = list(
            (
                await session.execute(
                    select(MCPOAuthAuthorizationCode).where(
                        MCPOAuthAuthorizationCode.user_id == user.id
                    )
                )
            ).scalars()
        )
        tokens = list(
            (
                await session.execute(
                    select(MCPOAuthToken).where(MCPOAuthToken.user_id == user.id)
                )
            ).scalars()
        )
        consent = (
            await session.execute(
                select(MCPOAuthConsent).where(MCPOAuthConsent.user_id == user.id)
            )
        ).scalar_one()
        reference = (
            await session.execute(select(MCPOAuthProviderGrantReference))
        ).scalar_one()

    assert codes and all(code.consumed_at is not None for code in codes)
    assert tokens and all(token.revoked_at is not None for token in tokens)
    assert consent.revoked_at is not None
    assert reference.revoked_at is not None


@pytest.mark.asyncio
async def test_total_registration_quota_includes_authorized_clients(
    local_oauth_client_factory,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    async with local_oauth_client_factory(
        registration_policy=MCPRegistrationPolicy(
            pending_quota=1,
            total_quota=1,
            per_ip_quota=10,
        )
    ) as (client, _runtime):
        first_client_id = await _register_client(client)
        await _login(client, session_maker, analyst_user_factory)
        await _approve_client(client, first_client_id)

        rejected = await client.post(
            "/mcp/register",
            json=_registration_payload(name="Over total capacity"),
        )

    assert rejected.status_code == 400
    assert "registration capacity is full" in rejected.json()[
        "error_description"
    ].lower()


@pytest.mark.asyncio
async def test_inactive_authorized_client_and_oauth_state_are_expired(
    local_oauth_client_factory,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    clock = [datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc)]
    async with local_oauth_client_factory(
        registration_policy=MCPRegistrationPolicy(
            pending_quota=1,
            total_quota=1,
            per_ip_quota=10,
            active_ttl_seconds=60,
        ),
        now=lambda: clock[0],
    ) as (client, runtime):
        expired_client_id = await _register_client(client)
        await _login(client, session_maker, analyst_user_factory)
        code = await _approve_client(client, expired_client_id)
        tokens = await _exchange_code(client, expired_client_id, code)
        assert await runtime.provider.load_access_token(tokens["access_token"])

        clock[0] += timedelta(seconds=61)
        expired_refresh = await client.post(
            "/mcp/token",
            data={
                "grant_type": "refresh_token",
                "client_id": expired_client_id,
                "refresh_token": tokens["refresh_token"],
                "scope": "mcp:access",
                "resource": RESOURCE,
            },
        )
        assert expired_refresh.status_code == 401
        assert expired_refresh.json()["error"] == "invalid_grant"

        replacement_client_id = await _register_client(client)

        assert replacement_client_id != expired_client_id
        assert await runtime.provider.load_access_token(tokens["access_token"]) is None

    async with session_maker() as session:
        assert await session.scalar(
            select(func.count()).select_from(MCPDCRRegistration)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(MCPOAuthClient)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(MCPOAuthConsent)
        ) == 0
        assert await session.scalar(
            select(func.count()).select_from(MCPOAuthToken)
        ) == 0


@pytest.mark.asyncio
async def test_successful_refresh_extends_registration_activity_lease(
    local_oauth_client_factory,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    clock = [datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc)]
    async with local_oauth_client_factory(
        registration_policy=MCPRegistrationPolicy(
            pending_quota=1,
            total_quota=1,
            per_ip_quota=10,
            active_ttl_seconds=60,
        ),
        now=lambda: clock[0],
    ) as (client, _runtime):
        client_id = await _register_client(client)
        await _login(client, session_maker, analyst_user_factory)
        code = await _approve_client(client, client_id)
        tokens = await _exchange_code(client, client_id, code)

        clock[0] += timedelta(seconds=50)
        refreshed = await client.post(
            "/mcp/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": tokens["refresh_token"],
                "scope": "mcp:access",
                "resource": RESOURCE,
            },
        )
        assert refreshed.status_code == 200, refreshed.text

        clock[0] += timedelta(seconds=20)
        still_at_capacity = await client.post(
            "/mcp/register",
            json=_registration_payload(name="Before refreshed lease expires"),
        )
        assert still_at_capacity.status_code == 400
        assert "registration capacity is full" in still_at_capacity.json()[
            "error_description"
        ].lower()

        clock[0] += timedelta(seconds=41)
        after_expiry = await client.post(
            "/mcp/register",
            json=_registration_payload(name="After refreshed lease expires"),
        )
        assert after_expiry.status_code == 201, after_expiry.text


@pytest.mark.asyncio
async def test_native_discovery_and_challenge_use_external_streamable_resource(
    local_oauth_client,
) -> None:
    client, _runtime = local_oauth_client

    metadata = await client.get(
        "/.well-known/oauth-protected-resource/mcp/streamable"
    )
    assert metadata.status_code == 200
    assert metadata.json()["resource"] == RESOURCE
    assert "localhost:8000" in metadata.text

    challenge = await client.post(
        "/mcp/streamable/",
        headers={"Accept": "application/json, text/event-stream"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "challenge-test", "version": "1"},
            },
        },
    )
    assert challenge.status_code == 401
    assert "localhost:8000" in challenge.headers["www-authenticate"]
    assert "localhost:8080" not in challenge.headers["www-authenticate"]
    assert "/mcp/streamable\"" in challenge.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_native_local_oauth_pkce_flow_uses_intercept_session(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    client, runtime = local_oauth_client
    client_id = await _register_client(client)
    consent_path = await _begin_authorization(client, client_id)

    anonymous_consent = await client.get(consent_path, follow_redirects=False)
    assert anonymous_consent.status_code == 302
    assert anonymous_consent.headers["location"].startswith(
        f"{LOGIN_BASE_URL}/login?next="
    )

    user = await _login(client, session_maker, analyst_user_factory)
    consent = await client.get(consent_path)
    assert consent.status_code == 200
    assert "Authorize MCP access" in consent.text
    assert "Codex Test Client" in consent.text
    assert 'method="post"' in consent.text

    approval = await client.post(consent_path, json={"decision": "approve"})
    assert approval.status_code == 200
    callback_query = parse_qs(urlparse(approval.json()["redirect_to"]).query)
    auth_code = callback_query["code"][0]
    assert callback_query["state"] == ["state-123"]

    token_response = await client.post(
        "/mcp/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
            "resource": RESOURCE,
        },
    )
    assert token_response.status_code == 200, token_response.text
    token_payload = token_response.json()
    assert token_payload["access_token"]
    assert token_payload["refresh_token"]
    assert token_payload["scope"] == "mcp:access"

    refresh_response = await client.post(
        "/mcp/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": token_payload["refresh_token"],
            "scope": "mcp:access",
            "resource": RESOURCE,
        },
    )
    assert refresh_response.status_code == 200, refresh_response.text
    refreshed_payload = refresh_response.json()
    assert refreshed_payload["access_token"] != token_payload["access_token"]
    assert refreshed_payload["refresh_token"] != token_payload["refresh_token"]
    token_payload = refreshed_payload

    access = await runtime.provider.load_access_token(token_payload["access_token"])
    assert access is not None
    assert access.claims["intercept_user_id"] == str(user.id)

    async with runtime.http_app.lifespan(runtime.http_app):
        initialized = await client.post(
            "/mcp/streamable/",
            headers={
                "Authorization": f"Bearer {token_payload['access_token']}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "oauth-test", "version": "1"},
                },
            },
        )
    assert initialized.status_code == 200, initialized.text

    connected = await client.get("/api/v1/mcp/oauth/clients")
    assert connected.status_code == 200
    clients = connected.json()
    assert len(clients) == 1
    assert clients[0]["client_name"] == "Codex Test Client"

    revoked = await client.delete(f"/api/v1/mcp/oauth/clients/{clients[0]['id']}")
    assert revoked.status_code == 204
    assert await runtime.provider.load_access_token(token_payload["access_token"]) is None


@pytest.mark.asyncio
async def test_revoked_connected_client_cannot_exchange_pre_revocation_code(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """Revocation consumes every still-pending code in the consent epoch."""

    client, _runtime = local_oauth_client
    client_id = await _register_client(client)
    consent_path = await _begin_authorization(client, client_id)
    await _login(client, session_maker, analyst_user_factory)
    approval = await client.post(consent_path, json={"decision": "approve"})
    assert approval.status_code == 200, approval.text
    auth_code = parse_qs(urlparse(approval.json()["redirect_to"]).query)["code"][0]

    connected_response = await client.get("/api/v1/mcp/oauth/clients")
    assert connected_response.status_code == 200, connected_response.text
    connected = connected_response.json()
    assert len(connected) == 1
    consent_id = UUID(connected[0]["id"])
    async with session_maker() as db:
        authorized_consent = await db.get(MCPOAuthConsent, consent_id)
    assert authorized_consent is not None
    first_authorization_epoch = authorized_consent.last_authorization_epoch
    assert first_authorization_epoch > 0
    revoked = await client.delete(
        f"/api/v1/mcp/oauth/clients/{connected[0]['id']}"
    )
    assert revoked.status_code == 204
    async with session_maker() as db:
        revoked_consent = await db.get(MCPOAuthConsent, consent_id)
    assert revoked_consent is not None
    revocation_epoch = revoked_consent.revocation_epoch
    assert revocation_epoch is not None
    assert revocation_epoch > first_authorization_epoch

    exchange = await client.post(
        "/mcp/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
            "resource": RESOURCE,
        },
    )

    assert exchange.status_code == 401
    assert exchange.json()["error"] == "invalid_grant"

    fresh_consent_path = await _begin_authorization(client, client_id)
    fresh_approval = await client.post(
        fresh_consent_path,
        json={"decision": "approve"},
    )
    assert fresh_approval.status_code == 200, fresh_approval.text
    async with session_maker() as db:
        reauthorized_consent = await db.get(MCPOAuthConsent, consent_id)
    assert reauthorized_consent is not None
    assert reauthorized_consent.revocation_epoch is None
    assert reauthorized_consent.last_authorization_epoch > revocation_epoch
    fresh_code = parse_qs(
        urlparse(fresh_approval.json()["redirect_to"]).query
    )["code"][0]
    fresh_exchange = await client.post(
        "/mcp/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": fresh_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
            "resource": RESOURCE,
        },
    )
    assert fresh_exchange.status_code == 200, fresh_exchange.text


@pytest.mark.asyncio
async def test_connected_client_revocation_serializes_with_code_exchange(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whichever operation obtains the consent epoch first wins safely."""

    client, runtime = local_oauth_client
    client_id = await _register_client(client)
    consent_path = await _begin_authorization(client, client_id)
    user = await _login(client, session_maker, analyst_user_factory)
    approval = await client.post(consent_path, json={"decision": "approve"})
    assert approval.status_code == 200, approval.text
    auth_code = parse_qs(urlparse(approval.json()["redirect_to"]).query)["code"][0]
    connected_response = await client.get("/api/v1/mcp/oauth/clients")
    assert connected_response.status_code == 200, connected_response.text
    connected = connected_response.json()
    assert len(connected) == 1

    service = runtime.provider._backend.service  # noqa: SLF001
    original_load = service._load_authorization_code  # noqa: SLF001
    exchange_holds_epoch = asyncio.Event()
    release_exchange = asyncio.Event()

    async def pause_after_epoch_lock(db, *, code: str, for_update: bool = False):
        if for_update:
            exchange_holds_epoch.set()
            await release_exchange.wait()
        return await original_load(db, code=code, for_update=for_update)

    monkeypatch.setattr(
        service,
        "_load_authorization_code",
        pause_after_epoch_lock,
    )
    exchange_task = asyncio.create_task(
        client.post(
            "/mcp/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": auth_code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": CODE_VERIFIER,
                "resource": RESOURCE,
            },
        )
    )
    revoke_task = None
    revoke_waited_for_exchange = False
    try:
        await asyncio.wait_for(exchange_holds_epoch.wait(), timeout=2)

        async def revoke_connected_client() -> None:
            async with session_maker() as db:
                await service.revoke_connected_client(
                    db,
                    user=user,
                    consent_id=UUID(connected[0]["id"]),
                )
                await db.commit()

        revoke_task = asyncio.create_task(revoke_connected_client())
        await asyncio.sleep(0.1)
        revoke_waited_for_exchange = not revoke_task.done()
    finally:
        release_exchange.set()

    exchange = await exchange_task
    assert revoke_task is not None
    await revoke_task
    assert exchange.status_code == 200, exchange.text
    assert revoke_waited_for_exchange
    assert (
        await runtime.provider.load_access_token(exchange.json()["access_token"])
        is None
    )


@pytest.mark.asyncio
async def test_public_oauth_tokens_reject_wrong_client_and_replay(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    client, runtime = local_oauth_client
    client_id = await _register_client(client)
    another_client_id = (
        await client.post(
            "/mcp/register",
            json=_registration_payload(name="Another Client"),
        )
    ).json()["client_id"]
    consent_path = await _begin_authorization(client, client_id)
    await _login(client, session_maker, analyst_user_factory)
    approval = await client.post(consent_path, json={"decision": "approve"})
    auth_code = parse_qs(urlparse(approval.json()["redirect_to"]).query)["code"][0]

    wrong_client = await client.post(
        "/mcp/token",
        data={
            "grant_type": "authorization_code",
            "client_id": another_client_id,
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
        },
    )
    assert wrong_client.status_code == 401
    assert wrong_client.json()["error"] == "invalid_grant"

    issued = await client.post(
        "/mcp/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
        },
    )
    assert issued.status_code == 200, issued.text
    issued_payload = issued.json()

    replayed_code = await client.post(
        "/mcp/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
        },
    )
    assert replayed_code.status_code == 401
    assert replayed_code.json()["error"] == "invalid_grant"

    wrong_refresh_client = await client.post(
        "/mcp/token",
        data={
            "grant_type": "refresh_token",
            "client_id": another_client_id,
            "refresh_token": issued_payload["refresh_token"],
        },
    )
    assert wrong_refresh_client.status_code == 401
    assert wrong_refresh_client.json()["error"] == "invalid_grant"

    rotated = await client.post(
        "/mcp/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": issued_payload["refresh_token"],
        },
    )
    assert rotated.status_code == 200, rotated.text
    rotated_payload = rotated.json()

    replayed_refresh = await client.post(
        "/mcp/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": issued_payload["refresh_token"],
        },
    )
    assert replayed_refresh.status_code == 401
    assert replayed_refresh.json()["error"] == "invalid_grant"
    assert (
        await runtime.provider.load_access_token(rotated_payload["access_token"])
        is None
    )


@pytest.mark.asyncio
async def test_native_token_endpoint_rejects_invalid_pkce_verifier(
    local_oauth_client,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    client, _runtime = local_oauth_client
    client_id = await _register_client(client)
    consent_path = await _begin_authorization(client, client_id)
    await _login(client, session_maker, analyst_user_factory)
    approval = await client.post(consent_path, json={"decision": "approve"})
    auth_code = parse_qs(urlparse(approval.json()["redirect_to"]).query)["code"][0]

    response = await client.post(
        "/mcp/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": "b" * 64,
            "resource": RESOURCE,
        },
    )

    # FastMCP intentionally maps invalid_grant to 401 for the MCP token contract.
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_legacy_oauth_and_sse_routes_are_not_aliased(local_oauth_client) -> None:
    client, _runtime = local_oauth_client

    responses = [
        await client.post("/oauth/register", json={}),
        await client.get("/oauth/authorize"),
        await client.post("/oauth/token"),
        await client.post("/oauth/revoke"),
        await client.get("/mcp/sse"),
        await client.post("/mcp/messages"),
    ]
    assert all(response.status_code in {404, 405} for response in responses)
