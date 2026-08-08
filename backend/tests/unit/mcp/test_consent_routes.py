from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, call
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import AnyUrl

from app.api.routes import mcp_oauth
from app.core.request_body_limit import (
    MCP_CONSENT_CONTEXT_REQUEST_MAX_BODY_BYTES,
    MCP_CONSENT_CONTEXT_REQUEST_PATHS,
    RequestBodyLimitMiddleware,
)
from app.mcp.local_oauth_provider import PendingAuthorization


REQUEST_ID = UUID("16ad90ad-4cf0-4c56-b4e2-9f39c44ca001")
NOW = datetime(2026, 7, 19, tzinfo=timezone.utc)


class FakeProvider:
    def __init__(self) -> None:
        self.pending = PendingAuthorization(
            id=REQUEST_ID,
            client_id="client-1",
            state="state-1",
            scopes=["mcp:access"],
            code_challenge="challenge",
            redirect_uri="http://127.0.0.1:49152/callback",
            redirect_uri_provided_explicitly=True,
            resource="http://localhost:8080/mcp/streamable/",
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
        )
        self.client = SimpleNamespace(
            client_id="client-1",
            client_name="VS Code <unsafe>",
            client_uri=AnyUrl("https://code.visualstudio.com/"),
        )
        self.completed: list[tuple[UUID, object, bool]] = []

    async def get_pending_authorization(self, request_id: UUID):
        return self.pending if request_id == REQUEST_ID else None

    async def get_client(self, client_id: str):
        return self.client if client_id == "client-1" else None

    async def complete_authorization(
        self,
        request_id: UUID,
        *,
        user: object,
        approved: bool,
        context: object,
    ) -> str:
        self.completed.append((request_id, user, approved))
        return "http://127.0.0.1:49152/callback?code=issued"


@pytest.fixture
def consent_app(monkeypatch: pytest.MonkeyPatch):
    provider = FakeProvider()
    app = FastAPI()
    app.state.mcp_runtime = SimpleNamespace(
        provider=provider,
        snapshot=SimpleNamespace(
            login_origin="http://localhost:8080",
            public_origin="https://mcp.example.test",
        ),
    )
    app.include_router(mcp_oauth.consent_router, prefix="/api/v1")
    db = SimpleNamespace(commit=AsyncMock())

    async def fake_db():
        yield db

    app.dependency_overrides[mcp_oauth.get_db] = fake_db
    user = SimpleNamespace(id=UUID("26ad90ad-4cf0-4c56-b4e2-9f39c44ca002"))

    async def authenticated(_request, _db):
        return user

    monkeypatch.setattr(mcp_oauth, "_current_session_user", authenticated)
    return app, provider, user


@pytest.mark.asyncio
async def test_consent_get_displays_escaped_client_and_post_only_decisions(
    consent_app,
) -> None:
    app, _provider, _user = consent_app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost:8080"
    ) as client:
        response = await client.get(f"/api/v1/mcp/oauth/consent/{REQUEST_ID}")

    assert response.status_code == 200
    assert "VS Code &lt;unsafe&gt;" in response.text
    assert "http://127.0.0.1:49152/callback" in response.text
    assert 'method="post"' in response.text
    assert 'value="approve"' in response.text
    assert 'value="deny"' in response.text
    assert "X-XSRF-TOKEN" in response.text
    assert 'src="/api/v1/mcp/oauth/consent/client.js"' in response.text
    assert "<script>" not in response.text
    assert "?approve=1" not in response.text
    assert "?deny=1" not in response.text


@pytest.mark.asyncio
async def test_consent_get_redirects_through_configured_login_origin(
    consent_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _provider, _user = consent_app

    async def anonymous(_request, _db):
        return None

    monkeypatch.setattr(mcp_oauth, "_current_session_user", anonymous)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://backend:8000"
    ) as client:
        response = await client.get(
            f"/api/v1/mcp/oauth/consent/{REQUEST_ID}",
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"].startswith("http://localhost:8080/login?next=")
    assert (
        "https%3A%2F%2Fmcp.example.test%2Fapi%2Fv1%2Fmcp%2Foauth%2Fconsent%2F"
        in response.headers["location"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("decision", "approved"), [("approve", True), ("deny", False)])
async def test_consent_post_consumes_decision_and_returns_callback(
    consent_app,
    decision: str,
    approved: bool,
) -> None:
    app, provider, user = consent_app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost:8080"
    ) as client:
        response = await client.post(
            f"/api/v1/mcp/oauth/consent/{REQUEST_ID}",
            json={"decision": decision},
        )

    assert response.status_code == 200
    assert response.json() == {
        "redirect_to": "http://127.0.0.1:49152/callback?code=issued"
    }
    assert provider.completed == [(REQUEST_ID, user, approved)]


@pytest.mark.asyncio
async def test_missing_pending_consent_returns_gone(consent_app) -> None:
    app, _provider, _user = consent_app
    missing = UUID("36ad90ad-4cf0-4c56-b4e2-9f39c44ca003")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost:8080"
    ) as client:
        response = await client.get(f"/api/v1/mcp/oauth/consent/{missing}")

    assert response.status_code == 410


@pytest.mark.asyncio
async def test_oidc_consent_context_is_validated_and_never_cached() -> None:
    context = {
        "transaction_id": "transaction-id",
        "csrf_token": "csrf-token",
        "client_name": "VS Code",
        "client_id": "client-id",
        "client_uri": "https://code.visualstudio.com/",
        "redirect_uri": "http://127.0.0.1:49152/callback",
        "scopes": ["mcp:access"],
        "verified_domain": None,
    }
    provider = SimpleNamespace(
        get_consent_context=AsyncMock(return_value=context)
    )
    app = FastAPI()
    app.state.mcp_runtime = SimpleNamespace(provider=provider)
    app.include_router(mcp_oauth.consent_router, prefix="/api/v1")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost:8080"
    ) as client:
        response = await client.post(
            "/api/v1/mcp/oauth/consent/oidc",
            json={"transaction_id": "transaction-id"},
        )

    assert response.status_code == 200
    assert response.json() == context
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    provider.get_consent_context.assert_awaited_once_with("transaction-id")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_state",
    ["disabled", "expired", "invalid", "unavailable"],
)
async def test_oidc_consent_terminal_errors_are_never_cached(
    provider_state: str,
) -> None:
    if provider_state == "disabled":
        provider = SimpleNamespace()
        expected_status = 404
    elif provider_state == "expired":
        provider = SimpleNamespace(get_consent_context=AsyncMock(return_value=None))
        expected_status = 410
    elif provider_state == "unavailable":
        provider = SimpleNamespace(
            get_consent_context=AsyncMock(side_effect=RuntimeError("store offline"))
        )
        expected_status = 503
    else:
        provider = SimpleNamespace(
            get_consent_context=AsyncMock(return_value={"client_id": "incomplete"})
        )
        expected_status = 500
    app = FastAPI()
    app.state.mcp_runtime = SimpleNamespace(provider=provider)
    app.include_router(mcp_oauth.consent_router, prefix="/api/v1")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost:8080"
    ) as client:
        response = await client.post(
            "/api/v1/mcp/oauth/consent/oidc",
            json={"transaction_id": "unknown-transaction"},
        )

    assert response.status_code == expected_status
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


@pytest.mark.asyncio
async def test_oidc_consent_context_rejects_oversized_body_before_parsing() -> None:
    app = FastAPI()
    app.state.mcp_runtime = SimpleNamespace(
        provider=SimpleNamespace(get_consent_context=AsyncMock(return_value=None))
    )
    app.include_router(mcp_oauth.consent_router, prefix="/api/v1")
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=MCP_CONSENT_CONTEXT_REQUEST_MAX_BODY_BYTES,
        paths=MCP_CONSENT_CONTEXT_REQUEST_PATHS,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost:8080"
    ) as client:
        response = await client.post(
            "/api/v1/mcp/oauth/consent/oidc",
            content=b"x" * (MCP_CONSENT_CONTEXT_REQUEST_MAX_BODY_BYTES + 1),
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b'{"transaction_id":""}',
        b'{"transaction_id":"' + (b"x" * 257) + b'"}',
    ],
)
async def test_oidc_consent_context_rejects_invalid_body_without_caching(
    body: bytes,
) -> None:
    app = FastAPI()
    app.state.mcp_runtime = SimpleNamespace(
        provider=SimpleNamespace(get_consent_context=AsyncMock(return_value=None))
    )
    app.include_router(mcp_oauth.consent_router, prefix="/api/v1")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost:8080"
    ) as client:
        response = await client.post(
            "/api/v1/mcp/oauth/consent/oidc",
            content=body,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


@pytest.mark.asyncio
async def test_oidc_connected_client_revokes_native_grant_before_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=UUID("46ad90ad-4cf0-4c56-b4e2-9f39c44ca004"))
    consent = SimpleNamespace(
        id=REQUEST_ID,
        provider_mode="oidc",
        provider_reference_hash="reference-hash",
    )
    references = [
        SimpleNamespace(
            id=UUID("66ad90ad-4cf0-4c56-b4e2-9f39c44ca006"),
            provider_reference_hash="reference-one",
            revoked_at=None,
        ),
        SimpleNamespace(
            id=UUID("76ad90ad-4cf0-4c56-b4e2-9f39c44ca007"),
            provider_reference_hash="reference-two",
            revoked_at=None,
        ),
    ]
    native_provider = SimpleNamespace(revoke_projected_client=AsyncMock(return_value=True))
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    resolve_projection = AsyncMock(return_value=(consent, SimpleNamespace()))
    list_references = AsyncMock(return_value=references)
    lock_reference = AsyncMock(return_value=references[1])
    mark_projection = AsyncMock()
    monkeypatch.setattr(
        mcp_oauth.mcp_oauth_service,
        "resolve_connected_client",
        resolve_projection,
    )
    monkeypatch.setattr(
        mcp_oauth.mcp_oauth_service,
        "list_active_provider_grant_references",
        list_references,
    )
    monkeypatch.setattr(
        mcp_oauth.mcp_oauth_service,
        "lock_active_provider_grant_reference",
        lock_reference,
    )
    monkeypatch.setattr(
        mcp_oauth.mcp_oauth_service,
        "revoke_connected_client",
        mark_projection,
    )

    app = FastAPI()
    app.state.mcp_runtime = SimpleNamespace(provider=native_provider)
    app.include_router(mcp_oauth.management_router, prefix="/api/v1")

    async def fake_db():
        yield db

    async def authenticated_user():
        return user

    app.dependency_overrides[mcp_oauth.get_db] = fake_db
    app.dependency_overrides[mcp_oauth.require_authenticated_user] = authenticated_user
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost:8080"
    ) as client:
        response = await client.delete(
            f"/api/v1/mcp/oauth/clients/{REQUEST_ID}"
        )

    assert response.status_code == 204
    assert native_provider.revoke_projected_client.await_args_list == [
        call(user_id=user.id, provider_reference_hash="reference-one"),
        call(user_id=user.id, provider_reference_hash="reference-two"),
    ]
    assert all(reference.revoked_at is not None for reference in references)
    lock_reference.assert_awaited_once_with(
        db,
        consent_id=consent.id,
        reference_id=references[1].id,
    )
    mark_projection.assert_awaited_once()
    assert db.commit.await_count == 3


@pytest.mark.asyncio
async def test_oidc_connected_client_keeps_projection_when_native_revoke_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=UUID("56ad90ad-4cf0-4c56-b4e2-9f39c44ca005"))
    consent = SimpleNamespace(
        id=REQUEST_ID,
        provider_mode="oidc",
        provider_reference_hash="reference-hash",
    )
    reference = SimpleNamespace(
        id=UUID("86ad90ad-4cf0-4c56-b4e2-9f39c44ca008"),
        provider_reference_hash="reference-hash",
        revoked_at=None,
    )
    native_provider = SimpleNamespace(
        revoke_projected_client=AsyncMock(return_value=False)
    )
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    monkeypatch.setattr(
        mcp_oauth.mcp_oauth_service,
        "resolve_connected_client",
        AsyncMock(return_value=(consent, SimpleNamespace())),
    )
    monkeypatch.setattr(
        mcp_oauth.mcp_oauth_service,
        "list_active_provider_grant_references",
        AsyncMock(return_value=[reference]),
    )
    mark_projection = AsyncMock()
    monkeypatch.setattr(
        mcp_oauth.mcp_oauth_service,
        "revoke_connected_client",
        mark_projection,
    )

    app = FastAPI()
    app.state.mcp_runtime = SimpleNamespace(provider=native_provider)
    app.include_router(mcp_oauth.management_router, prefix="/api/v1")

    async def fake_db():
        yield db

    async def authenticated_user():
        return user

    app.dependency_overrides[mcp_oauth.get_db] = fake_db
    app.dependency_overrides[mcp_oauth.require_authenticated_user] = authenticated_user
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost:8080"
    ) as client:
        response = await client.delete(f"/api/v1/mcp/oauth/clients/{REQUEST_ID}")

    assert response.status_code == 503
    mark_projection.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()
