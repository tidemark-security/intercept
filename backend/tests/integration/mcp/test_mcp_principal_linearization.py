from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastmcp.server.auth import AccessToken
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.authorization_lock import acquire_authorization_lock
from app.mcp.auth import MCP_ACCESS_SCOPE
from app.mcp.principal import MCPPrincipalMiddleware, get_current_mcp_principal
from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import (
    ApiKey,
    MCPOAuthClient,
    MCPOAuthConsent,
    MCPOAuthProviderGrantReference,
    MCPOAuthToken,
    UserAccount,
)
from app.services.api_key_service import api_key_service
from app.services.mcp_oauth_service import mcp_oauth_service
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _persist_oidc_grant(
    db: AsyncSession,
    *,
    user: UserAccount,
    client_id: str,
    upstream_family_id: str,
) -> MCPOAuthConsent:
    reference_hash = hashlib.sha256(
        upstream_family_id.encode("utf-8")
    ).hexdigest()
    client = MCPOAuthClient(
        client_id=client_id,
        client_name="MCP linearization client",
    )
    db.add(client)
    await db.flush()
    consent = MCPOAuthConsent(
        user_id=user.id,
        client_db_id=client.id,
        provider_mode="oidc",
        provider_reference_hash=reference_hash,
    )
    db.add(consent)
    await db.flush()
    db.add(
        MCPOAuthProviderGrantReference(
            consent_id=consent.id,
            provider_reference_hash=reference_hash,
        )
    )
    await db.flush()
    return consent


async def _wait_for_queued_authorization_writer(
    session_maker: async_sessionmaker[AsyncSession],
    writer_pid: int,
) -> list[int]:
    """Wait until PostgreSQL confirms the writer is queued on its advisory gate."""
    async with session_maker() as observer_db:
        while True:
            blockers = await observer_db.scalar(
                text(
                    "SELECT pg_blocking_pids(:pid) "
                    "FROM pg_locks "
                    "WHERE pid = :pid AND locktype = 'advisory' AND NOT granted"
                ),
                {"pid": writer_pid},
            )
            if blockers:
                return blockers
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_source", ["oidc", "oauth", "api_key"])
@pytest.mark.parametrize("queue_revocation", [True, False], ids=["revocation", "activity"])
async def test_parallel_mcp_tools_share_credential(
    session_maker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    admin_user_factory,
    monkeypatch: pytest.MonkeyPatch,
    auth_source: str,
    queue_revocation: bool,
) -> None:
    """Overlapping calls preserve writer priority and defer last-used telemetry."""
    name = f"mcp-parallel-{auth_source}"
    client_id = f"{name}-client"
    raw_token = f"{name}-test-credential"
    claims = {"auth_source": auth_source}
    resource = "http://localhost:8000/mcp/streamable/"
    if auth_source == "api_key":
        user = UserAccount(
            username=name,
            account_type=AccountType.NHI,
            role=UserRole.ANALYST,
            status=UserStatus.ACTIVE,
        )
    else:
        user = admin_user_factory(username=name)
    claims["intercept_user_id"] = str(user.id)

    async with session_maker() as setup_db:
        setup_db.add(user)
        await setup_db.flush()
        if auth_source == "oidc":
            consent = await _persist_oidc_grant(
                setup_db,
                user=user,
                client_id=client_id,
                upstream_family_id=f"{name}-family",
            )
            assert consent.provider_reference_hash is not None
            claims["oidc_grant_reference_hash"] = consent.provider_reference_hash
            revoke_id = consent.id
            activity_query = (
                select(
                    MCPOAuthClient.last_seen_at,
                    MCPOAuthConsent.last_used_at,
                    MCPOAuthProviderGrantReference.last_used_at,
                )
                .select_from(MCPOAuthConsent)
                .join(MCPOAuthClient)
                .join(MCPOAuthProviderGrantReference)
                .where(MCPOAuthConsent.id == revoke_id)
            )
        elif auth_source == "oauth":
            monkeypatch.setenv("MCP_OAUTH_ENABLED", "true")
            monkeypatch.setenv("MCP_OAUTH_PUBLIC_BASE_URL", "http://localhost:8000")
            monkeypatch.setenv("MCP_OAUTH_LOGIN_BASE_URL", "http://localhost:5173")
            monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
            oauth_client = MCPOAuthClient(client_id=client_id, client_name=name)
            setup_db.add(oauth_client)
            await setup_db.flush()
            consent = MCPOAuthConsent(user_id=user.id, client_db_id=oauth_client.id)
            setup_db.add_all(
                [
                    consent,
                    MCPOAuthToken(
                        token_hash=mcp_oauth_service._hash_secret(raw_token),  # noqa: SLF001
                        token_type="access",
                        client_db_id=oauth_client.id,
                        user_id=user.id,
                        resource=resource,
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                    ),
                ]
            )
            claims["client_id"] = client_id
            revoke_id = consent.id
            activity_query = (
                select(MCPOAuthClient.last_seen_at, MCPOAuthToken.last_used_at)
                .select_from(MCPOAuthToken)
                .join(MCPOAuthClient)
                .where(MCPOAuthClient.id == oauth_client.id)
            )
        else:
            api_key, raw_token = await api_key_service.create_api_key(
                setup_db,
                user_id=user.id,
                name=name,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                scopes={MCP_ACCESS_SCOPE},
            )
            client_id = f"api-key:{api_key.id}"
            claims["api_key_id"] = str(api_key.id)
            revoke_id = api_key.id
            activity_query = select(ApiKey.last_used_at).where(ApiKey.id == revoke_id)
        await setup_db.commit()

    csrf_headers: dict[str, str] = {}
    if auth_source == "oauth" and queue_revocation:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
        )
        assert login.status_code == 200
        csrf_token = client.cookies.get("XSRF-TOKEN")
        assert csrf_token is not None
        csrf_headers["X-XSRF-TOKEN"] = csrf_token

    token = AccessToken(
        token=raw_token,
        client_id=client_id,
        scopes=[MCP_ACCESS_SCOPE],
        resource=resource,
        claims=claims,
    )
    monkeypatch.setattr("app.mcp.principal.get_access_token", lambda: token)
    monkeypatch.setattr("app.mcp.principal.get_http_request", lambda: None)

    middleware = MCPPrincipalMiddleware(session_factory=session_maker)
    context = SimpleNamespace(method="tools/call", type="request")
    discovery_context = SimpleNamespace(method="tools/list", type="request")
    tool_entries: asyncio.Queue[None] = asyncio.Queue()
    release_tools = asyncio.Event()
    writer_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    revocation_ready = asyncio.Event()
    commit_revocation = asyncio.Event()

    async def pause_before_revocation_commit() -> None:
        revocation_ready.set()
        await commit_revocation.wait()

    async def slow_tool(_context):
        principal = get_current_mcp_principal()
        assert principal is not None
        assert principal.user.id == user.id
        assert principal.auth_source == auth_source
        tool_entries.put_nowait(None)
        await release_tools.wait()
        return "tool-complete"

    async def revoke_credential() -> None:
        if auth_source == "oauth":
            revoke_connected_client = mcp_oauth_service.revoke_connected_client

            async def observe_revocation(db, **kwargs):
                writer_pid.set_result(await db.scalar(text("SELECT pg_backend_pid()")))
                await revoke_connected_client(db, **kwargs)
                await pause_before_revocation_commit()

            monkeypatch.setattr(
                mcp_oauth_service, "revoke_connected_client", observe_revocation
            )
            revoked = await client.delete(
                f"/api/v1/mcp/oauth/clients/{revoke_id}",
                headers=csrf_headers,
            )
            assert revoked.status_code == 204
            return

        async with session_maker() as writer_db:
            writer_pid.set_result(await writer_db.scalar(text("SELECT pg_backend_pid()")))
            if auth_source == "api_key":
                await api_key_service.revoke_api_key(writer_db, api_key_id=revoke_id)
            else:
                await mcp_oauth_service.revoke_connected_client(
                    writer_db, user=user, consent_id=revoke_id
                )
            await pause_before_revocation_commit()
            await writer_db.commit()

    async def must_not_run(_context):
        pytest.fail("MCP request entered after revocation started")

    async def assert_rejected(status_code: int) -> None:
        for request_context in (context, discovery_context):
            with pytest.raises(HTTPException) as exc_info:
                await asyncio.wait_for(middleware(request_context, must_not_run), timeout=2)
            assert exc_info.value.status_code == status_code
            if auth_source == "oidc" and status_code == 401:
                assert exc_info.value.detail == "MCP OIDC grant is no longer valid"

    async def activity_timestamps() -> tuple[datetime | None, ...]:
        async with session_maker() as inspector:
            return tuple((await inspector.execute(activity_query)).one())

    async def wait_for_tools_to_complete() -> None:
        release_tools.set()
        assert await asyncio.wait_for(asyncio.gather(*tools), timeout=2) == [
            "tool-complete",
            "tool-complete",
        ]

    tools = [asyncio.create_task(middleware(context, slow_tool)) for _ in range(2)]
    writer = None
    try:
        await asyncio.wait_for(tool_entries.get(), timeout=2)
        await asyncio.wait_for(tool_entries.get(), timeout=2)
        assert all(timestamp is None for timestamp in await activity_timestamps())
        if not queue_revocation:
            await wait_for_tools_to_complete()
            assert all(timestamp is not None for timestamp in await activity_timestamps())
            return

        writer = asyncio.create_task(revoke_credential())
        completed, _ = await asyncio.wait(
            {writer, writer_pid}, return_when=asyncio.FIRST_COMPLETED, timeout=2
        )
        if writer in completed:
            writer.result()
        assert writer_pid in completed, "Revocation did not reach the database writer"
        blockers = await asyncio.wait_for(
            _wait_for_queued_authorization_writer(session_maker, writer_pid.result()),
            timeout=2,
        )
        assert len(set(blockers)) == 2
        await assert_rejected(503)

        await wait_for_tools_to_complete()
        await asyncio.wait_for(revocation_ready.wait(), timeout=2)
        await assert_rejected(503)

        commit_revocation.set()
        await asyncio.wait_for(writer, timeout=2)
        await assert_rejected(401)
    finally:
        release_tools.set()
        commit_revocation.set()
        tasks = [*tools, writer] if writer is not None else tools
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=2)


@pytest.mark.asyncio
async def test_mcp_tool_call_serializes_with_role_downgrade(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A downgrade may not commit between MCP authorization and tool use."""
    user = admin_user_factory(username="mcp-principal-role-race")
    async with session_maker() as setup_db:
        setup_db.add(user)
        await setup_db.flush()
        consent = await _persist_oidc_grant(
            setup_db,
            user=user,
            client_id="mcp-principal-role-race-client",
            upstream_family_id="mcp-principal-role-race-family",
        )
        await setup_db.commit()

    token = AccessToken(
        token="mcp-principal-role-race-token",
        client_id="mcp-principal-role-race-client",
        scopes=[MCP_ACCESS_SCOPE],
        claims={
            "intercept_user_id": str(user.id),
            "auth_source": "oidc",
            "oidc_grant_reference_hash": consent.provider_reference_hash,
        },
    )
    monkeypatch.setattr("app.mcp.principal.get_access_token", lambda: token)
    monkeypatch.setattr("app.mcp.principal.get_http_request", lambda: None)

    tool_entered = asyncio.Event()
    release_tool = asyncio.Event()
    downgrade_lock_attempted = asyncio.Event()
    downgrade_committed = asyncio.Event()
    middleware = MCPPrincipalMiddleware(session_factory=session_maker)

    async def call_next(_context):
        principal = get_current_mcp_principal()
        assert principal is not None
        assert principal.user.role == UserRole.ADMIN
        tool_entered.set()
        await release_tool.wait()
        return "tool-complete"

    async def downgrade_user() -> None:
        async with session_maker() as downgrade_db:
            downgrade_lock_attempted.set()
            locked_user = await downgrade_db.get(
                UserAccount,
                user.id,
                populate_existing=True,
                with_for_update=True,
            )
            assert locked_user is not None
            locked_user.role = UserRole.ANALYST
            await downgrade_db.commit()
            downgrade_committed.set()

    tool_task = asyncio.create_task(
        middleware(SimpleNamespace(method="tools/call", type="request"), call_next)
    )
    await asyncio.wait_for(tool_entered.wait(), timeout=2)

    downgrade_task = asyncio.create_task(downgrade_user())
    await asyncio.wait_for(downgrade_lock_attempted.wait(), timeout=2)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            asyncio.shield(downgrade_committed.wait()),
            timeout=0.2,
        )

    release_tool.set()
    assert await asyncio.wait_for(tool_task, timeout=2) == "tool-complete"
    await asyncio.wait_for(downgrade_task, timeout=2)
    assert downgrade_committed.is_set()


@pytest.mark.asyncio
async def test_slow_mcp_tool_does_not_queue_non_tool_protocol_requests(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protocol discovery can proceed while a tool holds authorization locks."""
    user = admin_user_factory(username="mcp-non-tool-lock-contention")
    async with session_maker() as setup_db:
        setup_db.add(user)
        await setup_db.flush()
        consent = await _persist_oidc_grant(
            setup_db,
            user=user,
            client_id="mcp-non-tool-lock-contention-client",
            upstream_family_id="mcp-non-tool-lock-contention-family",
        )
        await setup_db.commit()

    token = AccessToken(
        token="mcp-non-tool-lock-contention-token",
        client_id="mcp-non-tool-lock-contention-client",
        scopes=[MCP_ACCESS_SCOPE],
        claims={
            "intercept_user_id": str(user.id),
            "auth_source": "oidc",
            "oidc_grant_reference_hash": consent.provider_reference_hash,
        },
    )
    monkeypatch.setattr("app.mcp.principal.get_access_token", lambda: token)
    monkeypatch.setattr("app.mcp.principal.get_http_request", lambda: None)

    tool_entered = asyncio.Event()
    release_tool = asyncio.Event()
    middleware = MCPPrincipalMiddleware(session_factory=session_maker)

    async def slow_tool(_context):
        tool_entered.set()
        await release_tool.wait()
        return "tool-complete"

    async def protocol_response(_context):
        return "discovery-complete"

    async def invoke_non_tool() -> str:
        return await middleware(
            SimpleNamespace(method="tools/list", type="request"),
            protocol_response,
        )

    tool_task = asyncio.create_task(
        middleware(
            SimpleNamespace(method="tools/call", type="request"),
            slow_tool,
        )
    )
    await asyncio.wait_for(tool_entered.wait(), timeout=2)

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(invoke_non_tool() for _ in range(8))),
            timeout=2,
        )
        assert results == ["discovery-complete"] * 8
        async with session_maker() as inspector:
            activity = (
                await inspector.execute(
                    select(
                        MCPOAuthClient.last_seen_at,
                        MCPOAuthConsent.last_used_at,
                        MCPOAuthProviderGrantReference.last_used_at,
                    )
                    .join(MCPOAuthConsent, MCPOAuthConsent.client_db_id == MCPOAuthClient.id)
                    .join(
                        MCPOAuthProviderGrantReference,
                        MCPOAuthProviderGrantReference.consent_id == MCPOAuthConsent.id,
                    )
                    .where(MCPOAuthConsent.id == consent.id)
                )
            ).one()
        assert all(timestamp is not None for timestamp in activity)
        assert not tool_task.done()
    finally:
        release_tool.set()
        assert await asyncio.wait_for(tool_task, timeout=2) == "tool-complete"


@pytest.mark.asyncio
async def test_non_tool_requests_fail_fast_behind_queued_account_writer(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A queued disable must not turn skip-locked auth into pool waiters."""
    user = admin_user_factory(username="mcp-advisory-writer-contention")
    async with session_maker() as setup_db:
        setup_db.add(user)
        await setup_db.flush()
        consent = await _persist_oidc_grant(
            setup_db,
            user=user,
            client_id="mcp-advisory-writer-contention-client",
            upstream_family_id="mcp-advisory-writer-contention-family",
        )
        await setup_db.commit()

    token = AccessToken(
        token="mcp-advisory-writer-contention-token",
        client_id="mcp-advisory-writer-contention-client",
        scopes=[MCP_ACCESS_SCOPE],
        claims={
            "intercept_user_id": str(user.id),
            "auth_source": "oidc",
            "oidc_grant_reference_hash": consent.provider_reference_hash,
        },
    )
    monkeypatch.setattr("app.mcp.principal.get_access_token", lambda: token)
    monkeypatch.setattr("app.mcp.principal.get_http_request", lambda: None)

    tool_entered = asyncio.Event()
    release_tool = asyncio.Event()
    writer_pid = asyncio.get_running_loop().create_future()
    writer_committed = asyncio.Event()
    middleware = MCPPrincipalMiddleware(session_factory=session_maker)

    async def slow_tool(_context):
        tool_entered.set()
        await release_tool.wait()
        return "tool-complete"

    async def queued_writer() -> None:
        async with session_maker() as writer_db:
            writer_pid.set_result(await writer_db.scalar(text("SELECT pg_backend_pid()")))
            await acquire_authorization_lock(
                writer_db,
                user_id=user.id,
                shared=False,
            )
            locked_user = await writer_db.get(
                UserAccount,
                user.id,
                populate_existing=True,
                with_for_update=True,
            )
            assert locked_user is not None
            locked_user.status = UserStatus.DISABLED
            await writer_db.commit()
            writer_committed.set()

    async def protocol_response(_context):
        return "must-not-run"

    async def invoke_non_tool() -> int:
        with pytest.raises(HTTPException) as exc_info:
            await middleware(
                SimpleNamespace(method="tools/list", type="request"),
                protocol_response,
            )
        return exc_info.value.status_code

    tool_task = asyncio.create_task(
        middleware(
            SimpleNamespace(method="tools/call", type="request"),
            slow_tool,
        )
    )
    await asyncio.wait_for(tool_entered.wait(), timeout=2)
    writer_task = asyncio.create_task(queued_writer())
    try:
        pid = await asyncio.wait_for(writer_pid, timeout=2)
        await asyncio.wait_for(
            _wait_for_queued_authorization_writer(session_maker, pid), timeout=2
        )
        statuses = await asyncio.wait_for(
            asyncio.gather(*(invoke_non_tool() for _ in range(8))),
            timeout=0.5,
        )
        assert statuses == [503] * 8
        assert not writer_committed.is_set()
    finally:
        release_tool.set()

    assert await asyncio.wait_for(tool_task, timeout=2) == "tool-complete"
    await asyncio.wait_for(writer_task, timeout=2)
    assert writer_committed.is_set()


@pytest.mark.asyncio
async def test_mcp_tool_revalidates_api_key_after_verifier_releases_locks(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cached native principal retries lock contention but rejects revocation."""
    user = UserAccount(
        username="mcp-principal-key-race",
        account_type=AccountType.NHI,
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
    )
    async with session_maker() as setup_db:
        setup_db.add(user)
        await setup_db.flush()
        api_key, raw_key = await api_key_service.create_api_key(
            setup_db,
            user_id=user.id,
            name="MCP principal race",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            scopes={MCP_ACCESS_SCOPE},
        )
        await setup_db.commit()

    token = AccessToken(
        token=raw_key,
        client_id=f"api-key:{api_key.id}",
        scopes=[MCP_ACCESS_SCOPE],
        claims={
            "intercept_user_id": str(user.id),
            "auth_source": "api_key",
            "api_key_id": str(api_key.id),
        },
    )
    monkeypatch.setattr("app.mcp.principal.get_access_token", lambda: token)
    monkeypatch.setattr("app.mcp.principal.get_http_request", lambda: None)

    tool_called = False

    async def call_next(_context):
        nonlocal tool_called
        tool_called = True
        return "tool-complete"

    middleware = MCPPrincipalMiddleware(session_factory=session_maker)
    context = SimpleNamespace(method="tools/call", type="request")
    async with session_maker() as locking_db:
        locked_key = await locking_db.get(ApiKey, api_key.id, with_for_update=True)
        assert locked_key is not None
        with pytest.raises(HTTPException) as exc_info:
            await asyncio.wait_for(middleware(context, call_next), timeout=2)
        assert exc_info.value.status_code == 503
        assert tool_called is False

    assert await middleware(context, call_next) == "tool-complete"
    tool_called = False

    async with session_maker() as revocation_db:
        await api_key_service.revoke_api_key(
            revocation_db,
            api_key_id=api_key.id,
        )
        await revocation_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await middleware(context, call_next)

    assert exc_info.value.status_code == 401
    assert tool_called is False


@pytest.mark.asyncio
async def test_mcp_tool_can_retry_local_oauth_token_row_contention(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unavailable local token row temporarily blocks tools using that token."""

    monkeypatch.setenv("MCP_OAUTH_ENABLED", "true")
    monkeypatch.setenv("MCP_OAUTH_PUBLIC_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("MCP_OAUTH_LOGIN_BASE_URL", "http://localhost:5173")
    raw_token = "mcp-local-oauth-revocation-race"
    user = UserAccount(
        username="mcp-local-oauth-revocation-race",
        account_type=AccountType.NHI,
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
    )
    client = MCPOAuthClient(
        client_id="mcp-local-oauth-revocation-client",
        client_name="Revocation race client",
    )
    async with session_maker() as setup_db:
        setup_db.add_all([user, client])
        await setup_db.flush()
        access_row = MCPOAuthToken(
            token_hash=mcp_oauth_service._hash_secret(raw_token),  # noqa: SLF001
            token_type="access",
            client_db_id=client.id,
            user_id=user.id,
            resource="http://localhost:8000/mcp/streamable/",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        setup_db.add(access_row)
        await setup_db.commit()

    token = AccessToken(
        token=raw_token,
        client_id=client.client_id,
        scopes=[MCP_ACCESS_SCOPE],
        resource="http://localhost:8000/mcp/streamable/",
        claims={
            "intercept_user_id": str(user.id),
            "auth_source": "oauth",
            "client_id": client.client_id,
        },
    )
    monkeypatch.setattr("app.mcp.principal.get_access_token", lambda: token)
    monkeypatch.setattr("app.mcp.principal.get_http_request", lambda: None)

    tool_called = False

    async def call_next(_context):
        nonlocal tool_called
        tool_called = True
        return "tool-complete"

    async with session_maker() as locking_db:
        locked_token = await locking_db.get(
            MCPOAuthToken,
            access_row.id,
            with_for_update=True,
        )
        assert locked_token is not None
        middleware = MCPPrincipalMiddleware(session_factory=session_maker)
        with pytest.raises(HTTPException) as exc_info:
            await asyncio.wait_for(
                middleware(
                    SimpleNamespace(method="tools/call", type="request"),
                    call_next,
                ),
                timeout=2,
            )

        assert exc_info.value.status_code == 503
        assert tool_called is False

    assert await middleware(
        SimpleNamespace(method="tools/call", type="request"),
        call_next,
    ) == "tool-complete"


@pytest.mark.asyncio
async def test_mcp_tool_can_retry_oidc_grant_row_contention(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unavailable OIDC family row temporarily blocks tools using that grant."""

    user = UserAccount(
        username="mcp-oidc-revocation-race",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        oidc_issuer="https://issuer.example",
        oidc_subject="mcp-oidc-revocation-race",
    )
    client = MCPOAuthClient(
        client_id="mcp-oidc-revocation-client",
        client_name="OIDC revocation race client",
    )
    family_id = "mcp-oidc-upstream-family"
    reference_hash = hashlib.sha256(family_id.encode("utf-8")).hexdigest()
    async with session_maker() as setup_db:
        setup_db.add_all([user, client])
        await setup_db.flush()
        consent = MCPOAuthConsent(
            user_id=user.id,
            client_db_id=client.id,
            provider_mode="oidc",
            provider_reference_hash=reference_hash,
        )
        setup_db.add(consent)
        await setup_db.flush()
        reference = MCPOAuthProviderGrantReference(
            consent_id=consent.id,
            provider_reference_hash=reference_hash,
        )
        setup_db.add(reference)
        await setup_db.commit()

    token = AccessToken(
        token="signed-fastmcp-oidc-reference-token",
        client_id=client.client_id,
        scopes=[MCP_ACCESS_SCOPE],
        claims={
            "intercept_user_id": str(user.id),
            "auth_source": "oidc",
            "oidc_grant_reference_hash": reference_hash,
        },
    )
    monkeypatch.setattr("app.mcp.principal.get_access_token", lambda: token)
    monkeypatch.setattr("app.mcp.principal.get_http_request", lambda: None)

    tool_called = False

    async def call_next(_context):
        nonlocal tool_called
        tool_called = True
        return "tool-complete"

    async with session_maker() as locking_db:
        locked_reference = await locking_db.get(
            MCPOAuthProviderGrantReference,
            reference.id,
            with_for_update=True,
        )
        assert locked_reference is not None
        middleware = MCPPrincipalMiddleware(session_factory=session_maker)
        with pytest.raises(HTTPException) as exc_info:
            await asyncio.wait_for(
                middleware(
                    SimpleNamespace(method="tools/call", type="request"),
                    call_next,
                ),
                timeout=2,
            )

        assert exc_info.value.status_code == 503
        assert tool_called is False

    assert await middleware(
        SimpleNamespace(method="tools/call", type="request"),
        call_next,
    ) == "tool-complete"
