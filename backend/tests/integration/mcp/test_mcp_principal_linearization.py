from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastmcp.server.auth import AccessToken
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.authorization_lock import acquire_authorization_lock
from app.mcp.auth import MCP_ACCESS_SCOPE
from app.mcp.principal import MCPPrincipalMiddleware, get_current_mcp_principal
from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import (
    MCPOAuthClient,
    MCPOAuthConsent,
    MCPOAuthProviderGrantReference,
    MCPOAuthToken,
    UserAccount,
)
from app.services.api_key_service import api_key_service
from app.services.mcp_oauth_service import mcp_oauth_service


async def _persist_oidc_grant(
    db: AsyncSession,
    *,
    user: UserAccount,
    client_id: str,
    upstream_family_id: str,
) -> str:
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
    return reference_hash


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
        reference_hash = await _persist_oidc_grant(
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
            "oidc_grant_reference_hash": reference_hash,
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
    """Protocol discovery fails fast while a tool holds authorization locks."""
    user = admin_user_factory(username="mcp-non-tool-lock-contention")
    async with session_maker() as setup_db:
        setup_db.add(user)
        await setup_db.flush()
        reference_hash = await _persist_oidc_grant(
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
            "oidc_grant_reference_hash": reference_hash,
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

    try:
        statuses = await asyncio.wait_for(
            asyncio.gather(*(invoke_non_tool() for _ in range(8))),
            timeout=2,
        )
        assert statuses == [503] * 8
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
        reference_hash = await _persist_oidc_grant(
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
            "oidc_grant_reference_hash": reference_hash,
        },
    )
    monkeypatch.setattr("app.mcp.principal.get_access_token", lambda: token)
    monkeypatch.setattr("app.mcp.principal.get_http_request", lambda: None)

    tool_entered = asyncio.Event()
    release_tool = asyncio.Event()
    writer_waiting = asyncio.Event()
    writer_committed = asyncio.Event()
    middleware = MCPPrincipalMiddleware(session_factory=session_maker)

    async def slow_tool(_context):
        tool_entered.set()
        await release_tool.wait()
        return "tool-complete"

    async def queued_writer() -> None:
        async with session_maker() as writer_db:
            writer_waiting.set()
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
    await asyncio.wait_for(writer_waiting.wait(), timeout=2)
    await asyncio.sleep(0.1)

    try:
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
    """A cached native principal may not outlive explicit key revocation."""
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

    async with session_maker() as revocation_db:
        await api_key_service.revoke_api_key(
            revocation_db,
            api_key_id=api_key.id,
        )
        await revocation_db.commit()

    tool_called = False

    async def call_next(_context):
        nonlocal tool_called
        tool_called = True
        return "must-not-run"

    middleware = MCPPrincipalMiddleware(session_factory=session_maker)
    with pytest.raises(HTTPException) as exc_info:
        await middleware(
            SimpleNamespace(method="tools/call", type="request"),
            call_next,
        )

    assert exc_info.value.status_code == 401
    assert tool_called is False


@pytest.mark.asyncio
async def test_mcp_tool_fails_closed_behind_local_oauth_token_revocation(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cached native principal cannot bypass an in-progress token revocation."""

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
        return "must-not-run"

    async with session_maker() as revocation_db:
        locked_token = await revocation_db.get(
            MCPOAuthToken,
            access_row.id,
            with_for_update=True,
        )
        assert locked_token is not None
        locked_token.revoked_at = datetime.now(timezone.utc)

        middleware = MCPPrincipalMiddleware(session_factory=session_maker)
        with pytest.raises(HTTPException) as exc_info:
            await asyncio.wait_for(
                middleware(
                    SimpleNamespace(method="tools/call", type="request"),
                    call_next,
                ),
                timeout=2,
            )

        assert exc_info.value.status_code == 401
        assert tool_called is False


@pytest.mark.asyncio
async def test_mcp_tool_fails_closed_behind_oidc_grant_revocation(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cached OIDC principal cannot bypass an in-progress family revocation."""

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
        return "must-not-run"

    async with session_maker() as revocation_db:
        locked_reference = await revocation_db.get(
            MCPOAuthProviderGrantReference,
            reference.id,
            with_for_update=True,
        )
        assert locked_reference is not None
        locked_reference.revoked_at = datetime.now(timezone.utc)

        middleware = MCPPrincipalMiddleware(session_factory=session_maker)
        with pytest.raises(HTTPException) as exc_info:
            await asyncio.wait_for(
                middleware(
                    SimpleNamespace(method="tools/call", type="request"),
                    call_next,
                ),
                timeout=2,
            )

        assert exc_info.value.status_code == 401
        assert tool_called is False
