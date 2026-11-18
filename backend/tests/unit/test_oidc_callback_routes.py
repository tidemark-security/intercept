from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import oidc as oidc_routes
from app.core.settings_registry import get_local
from app.services.oidc_service import OIDCStateError


class _RecordingAuditService:
    def __init__(self) -> None:
        self.failure_reasons: list[str] = []

    async def oidc_login_failure(self, *, reason: str, **_kwargs: object) -> None:
        self.failure_reasons.append(reason)


class _FakeSession:
    def __init__(self) -> None:
        self.rollback_calls = 0

    async def rollback(self) -> None:
        self.rollback_calls += 1


def _callback_app(db: object) -> FastAPI:
    app = FastAPI()
    app.include_router(oidc_routes.router, prefix="/api/v1")

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, db)

    app.dependency_overrides[oidc_routes.get_db] = override_db
    return app


@pytest.mark.asyncio
async def test_disabled_oidc_callback_revokes_browser_binding_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_setting_get(_self, key: str, default: object = None) -> object:
        return False if key == "oidc.enabled" else default

    monkeypatch.setattr(oidc_routes.SettingsService, "get", fake_setting_get)
    app = _callback_app(object())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/auth/oidc/callback",
            params={"code": "auth-code", "state": "state-token"},
            cookies={
                get_local(
                    "oidc.browser_binding.cookie_name"
                ): "browser-binding-token"
            },
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"].startswith("http://localhost:8080?")
    binding_cookie_name = get_local("oidc.browser_binding.cookie_name")
    assert any(
        header.startswith(f"{binding_cookie_name}=") and "Max-Age=0" in header
        for header in response.headers.get_list("set-cookie")
    )


@pytest.mark.asyncio
async def test_unbound_provider_errors_do_not_create_failure_audits(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    audit_service = _RecordingAuditService()
    db = _FakeSession()

    async def fake_setting_get(_self, key: str, default: object = None) -> object:
        return True if key == "oidc.enabled" else default

    async def reject_unbound_error(
        _db: object,
        *,
        state: str,
        browser_binding_token: str | None,
    ) -> None:
        del state, browser_binding_token
        raise OIDCStateError("OIDC state is invalid or expired")

    monkeypatch.setattr(oidc_routes.SettingsService, "get", fake_setting_get)
    monkeypatch.setattr(
        oidc_routes.oidc_service,
        "consume_authorization_error",
        reject_unbound_error,
    )
    monkeypatch.setattr(
        oidc_routes,
        "get_audit_service",
        lambda _db: audit_service,
    )
    app = _callback_app(db)

    with caplog.at_level("WARNING", logger=oidc_routes.__name__):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            responses = [
                await client.get(
                    "/api/v1/auth/oidc/callback",
                    params={
                        "error": "attacker-private-error",
                        "error_description": "attacker-private-description",
                        "state": f"attacker-state-{attempt}",
                    },
                    cookies={
                        get_local(
                            "oidc.browser_binding.cookie_name"
                        ): "wrong-browser-binding"
                    },
                    follow_redirects=False,
                )
                for attempt in range(2)
            ]

    assert all(response.status_code == 302 for response in responses)
    assert all(
        "OIDC%20provider%20returned%20an%20authentication%20error"
        in response.headers["location"]
        for response in responses
    )
    assert audit_service.failure_reasons == []
    assert db.rollback_calls == 2
    captured = " ".join(record.getMessage() for record in caplog.records)
    assert "attacker-private" not in captured
    assert "attacker-state" not in captured
    binding_cookie_name = get_local("oidc.browser_binding.cookie_name")
    assert all(
        any(
            header.startswith(f"{binding_cookie_name}=") and "Max-Age=0" in header
            for header in response.headers.get_list("set-cookie")
        )
        for response in responses
    )


@pytest.mark.asyncio
async def test_incomplete_oidc_callback_redirects_and_revokes_binding_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_setting_get(_self, key: str, default: object = None) -> object:
        return True if key == "oidc.enabled" else default

    monkeypatch.setattr(oidc_routes.SettingsService, "get", fake_setting_get)
    app = _callback_app(object())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/auth/oidc/callback",
            cookies={
                get_local(
                    "oidc.browser_binding.cookie_name"
                ): "browser-binding-token"
            },
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"].startswith("http://localhost:8080?")
    assert "OIDC%20callback%20response%20is%20incomplete" in response.headers[
        "location"
    ]
    binding_cookie_name = get_local("oidc.browser_binding.cookie_name")
    assert any(
        header.startswith(f"{binding_cookie_name}=") and "Max-Age=0" in header
        for header in response.headers.get_list("set-cookie")
    )


@pytest.mark.asyncio
async def test_provider_denial_consumes_bound_state_and_returns_sanitized_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_service = _RecordingAuditService()
    consumed: list[tuple[str, str | None]] = []

    async def fake_setting_get(_self, key: str, default: object = None) -> object:
        return True if key == "oidc.enabled" else default

    async def consume_authorization_error(
        _db: object,
        *,
        state: str,
        browser_binding_token: str | None,
    ) -> None:
        consumed.append((state, browser_binding_token))

    monkeypatch.setattr(oidc_routes.SettingsService, "get", fake_setting_get)
    monkeypatch.setattr(
        oidc_routes.oidc_service,
        "consume_authorization_error",
        consume_authorization_error,
        raising=False,
    )
    monkeypatch.setattr(
        oidc_routes,
        "get_audit_service",
        lambda _db: audit_service,
    )
    app = _callback_app(object())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/auth/oidc/callback",
            params={
                "error": "access_denied",
                "error_description": "sensitive provider diagnostic",
                "state": "bound-state",
            },
            cookies={
                get_local(
                    "oidc.browser_binding.cookie_name"
                ): "browser-binding-token"
            },
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"].startswith("http://localhost:8080?")
    assert "sensitive" not in response.headers["location"]
    assert consumed == [("bound-state", "browser-binding-token")]
    assert audit_service.failure_reasons == [
        "OIDC sign-in was cancelled or denied"
    ]
    binding_cookie_name = get_local("oidc.browser_binding.cookie_name")
    assert any(
        header.startswith(f"{binding_cookie_name}=") and "Max-Age=0" in header
        for header in response.headers.get_list("set-cookie")
    )
