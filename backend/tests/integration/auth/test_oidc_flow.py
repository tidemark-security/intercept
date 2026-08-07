from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.client_address import ClientAddressResolver
from app.core.security import hash_opaque_token
from app.core.settings_registry import get_local
from app.models.models import AuditLog, AuthSession, OIDCAuthRequest
from app.services.auth_service import LoginResult
from app.services.oidc_auth_request_service import OIDCAuthRequestLimitError
from app.services.oidc_service import (
    OIDCAuthenticationError,
    OIDCProviderConfiguration,
    OIDCStateError,
    oidc_service,
)


class _FakeAuditService:
    async def oidc_login_success(self, **_: Any) -> None:
        return None

    async def oidc_login_failure(self, **_: Any) -> None:
        return None


class _FakeOIDCResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeOIDCClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, *_args: object, **_kwargs: object) -> _FakeOIDCResponse:
        return _FakeOIDCResponse({"id_token": "pre-disable-id-token"})

    async def get(self, *_args: object, **_kwargs: object) -> _FakeOIDCResponse:
        return _FakeOIDCResponse({"keys": []})


@pytest.mark.asyncio
async def test_concurrent_oidc_callbacks_consume_state_exactly_once(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = "concurrent-one-use-state"
    browser_binding = "concurrent-browser-binding"
    async with session_maker() as db:
        db.add(
            OIDCAuthRequest(
                state=state,
                nonce="expected-nonce",
                browser_binding_hash=hash_opaque_token(browser_binding),
                source_fingerprint="c" * 64,
                redirect_to="http://localhost:5173/",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        )
        await db.commit()

    both_plain_reads_completed = asyncio.Event()
    plain_read_count = 0

    class _ConcurrentSession:
        def __init__(self, delegate: AsyncSession) -> None:
            self._delegate = delegate

        async def get(self, *args: object, **kwargs: object):
            # Deterministically exposes the old plain-get race. The fixed
            # SELECT FOR UPDATE path delegates execute directly and serializes
            # in PostgreSQL instead of waiting at this test seam.
            nonlocal plain_read_count
            result = await self._delegate.get(*args, **kwargs)
            plain_read_count += 1
            if plain_read_count == 2:
                both_plain_reads_completed.set()
            await both_plain_reads_completed.wait()
            return result

        def __getattr__(self, name: str):
            return getattr(self._delegate, name)

    exchange_count = 0

    async def fake_exchange_consumed_code(*_args: object, **_kwargs: object):
        nonlocal exchange_count
        exchange_count += 1
        return SimpleNamespace(), "issuer", "subject", "http://localhost:5173/"

    monkeypatch.setattr(
        oidc_service,
        "_exchange_consumed_code",
        fake_exchange_consumed_code,
    )

    async with session_maker() as first_db, session_maker() as second_db:
        results = await asyncio.gather(
            oidc_service.exchange_code(
                _ConcurrentSession(first_db),
                code="first-code",
                state=state,
                browser_binding_token=browser_binding,
            ),
            oidc_service.exchange_code(
                _ConcurrentSession(second_db),
                code="second-code",
                state=state,
                browser_binding_token=browser_binding,
            ),
            return_exceptions=True,
        )

    assert sum(isinstance(result, OIDCStateError) for result in results) == 1
    assert sum(isinstance(result, tuple) for result in results) == 1
    assert exchange_count == 1


@pytest.mark.asyncio
async def test_begin_oidc_login_sets_browser_binding_cookie(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.routes.oidc as oidc_routes

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    async def fake_is_safe_redirect_target(_db, target: str) -> bool:
        return target == "http://localhost:5173/"

    async def fake_setting_get(_self, key: str, default: object = None) -> object:
        return True if key == "oidc.enabled" else default

    async def fake_is_safe_redirect_target(_db, _target: str) -> bool:
        return True

    async def fake_begin_login(
        _db,
        *,
        redirect_to: str,
        source_address: str | None = None,
    ):
        assert redirect_to == "http://localhost:5173/"
        assert source_address in {None, "127.0.0.1"}
        return "https://idp.example/authorize", expires_at, "browser-binding-token"

    monkeypatch.setattr(oidc_routes.SettingsService, "get", fake_setting_get)
    monkeypatch.setattr(oidc_routes.oidc_service, "is_safe_redirect_target", fake_is_safe_redirect_target)
    monkeypatch.setattr(oidc_routes.oidc_service, "begin_login", fake_begin_login)

    response = await client.get(
        "/api/v1/auth/oidc/login",
        params={"next": "http://localhost:5173/"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "https://idp.example/authorize"
    assert response.cookies.get(get_local("oidc.browser_binding.cookie_name")) == "browser-binding-token"


@pytest.mark.asyncio
async def test_begin_oidc_login_limit_returns_429_without_binding_cookie(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import app.api.routes.oidc as oidc_routes

    received_sources: list[str | None] = []

    async def fake_setting_get(_self, key: str, default: object = None) -> object:
        return True if key == "oidc.enabled" else default

    async def fake_is_safe_redirect_target(_db, _target: str) -> bool:
        return True

    async def fake_begin_login(
        _db,
        *,
        redirect_to: str,
        source_address: str | None = None,
    ):
        assert redirect_to == "http://localhost:5173/"
        received_sources.append(source_address)
        raise OIDCAuthRequestLimitError(
            "The OIDC sign-in queue is full; retry later",
            retry_after_seconds=17,
        )

    monkeypatch.setattr(oidc_routes.SettingsService, "get", fake_setting_get)
    monkeypatch.setattr(
        oidc_routes.oidc_service,
        "is_safe_redirect_target",
        fake_is_safe_redirect_target,
    )
    monkeypatch.setattr(oidc_routes.oidc_service, "begin_login", fake_begin_login)

    with caplog.at_level(logging.WARNING, logger=oidc_routes.__name__):
        response = await client.get(
            "/api/v1/auth/oidc/login",
            params={"next": "http://localhost:5173/"},
            headers={"X-Forwarded-For": "198.51.100.99"},
            follow_redirects=False,
        )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "17"
    assert get_local("oidc.browser_binding.cookie_name") not in response.cookies
    assert received_sources == ["127.0.0.1"]
    limit_record = next(
        record
        for record in caplog.records
        if getattr(record, "security", {}).get("event")
        == "oidc_login_initiation_limited"
    )
    assert "198.51.100.99" not in repr(limit_record.__dict__)


@pytest.mark.asyncio
async def test_begin_oidc_login_uses_trusted_forwarded_client_address(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.routes.oidc as oidc_routes
    from app.main import api_app

    received_sources: list[str | None] = []
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    async def fake_setting_get(_self, key: str, default: object = None) -> object:
        return True if key == "oidc.enabled" else default

    async def fake_is_safe_redirect_target(_db, _target: str) -> bool:
        return True

    async def fake_begin_login(
        _db,
        *,
        redirect_to: str,
        source_address: str | None = None,
    ):
        received_sources.append(source_address)
        return "https://idp.example/authorize", expires_at, "browser-binding-token"

    monkeypatch.setattr(oidc_routes.SettingsService, "get", fake_setting_get)
    monkeypatch.setattr(
        oidc_routes.oidc_service,
        "is_safe_redirect_target",
        fake_is_safe_redirect_target,
    )
    monkeypatch.setattr(oidc_routes.oidc_service, "begin_login", fake_begin_login)
    monkeypatch.setattr(
        api_app.state,
        "client_address_resolver",
        ClientAddressResolver.from_cidrs(["127.0.0.1/32"]),
        raising=False,
    )

    response = await client.get(
        "/api/v1/auth/oidc/login",
        params={"next": "http://localhost:5173/"},
        headers={"X-Forwarded-For": "192.0.2.1, 203.0.113.42"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert received_sources == ["203.0.113.42"]


@pytest.mark.asyncio
async def test_oidc_callback_sets_session_and_csrf_cookies(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.routes.oidc as oidc_routes

    user = analyst_user_factory(username="oidc.user")
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    async def fake_setting_get(_self, key: str, default: object = None) -> object:
        return True if key == "oidc.enabled" else default

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    async def fake_exchange_code(
        _db,
        *,
        code: str,
        state: str,
        browser_binding_token: str | None,
    ):
        assert code == "auth-code"
        assert state == "state-token"
        assert browser_binding_token == "browser-binding-token"
        return user, "https://idp.example", "subject-123", "http://localhost:5173/"

    async def fake_create_session_for_user(_db, *, user, metadata):
        return LoginResult(
            user=user,
            session=AuthSession(
                id=uuid4(),
                user_id=user.id,
                issued_at=datetime.now(timezone.utc),
                last_seen_at=datetime.now(timezone.utc),
                expires_at=expires_at,
                session_token_hash="hash",
            ),
            session_token="oidc-session-token",
        )

    monkeypatch.setattr(oidc_routes.SettingsService, "get", fake_setting_get)
    monkeypatch.setattr(oidc_routes.oidc_service, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(oidc_routes.auth_service, "create_session_for_user", fake_create_session_for_user)
    monkeypatch.setattr(oidc_routes, "get_audit_service", lambda _db: _FakeAuditService())

    response = await client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "auth-code", "state": "state-token"},
        cookies={get_local("oidc.browser_binding.cookie_name"): "browser-binding-token"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:5173/"
    assert response.cookies.get(get_local("auth.session.cookie_name")) == "oidc-session-token"
    assert response.cookies.get(get_local("auth.csrf.cookie_name")) is not None


@pytest.mark.asyncio
async def test_oidc_callback_rejects_missing_browser_binding_cookie(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.routes.oidc as oidc_routes

    async def fake_exchange_code(
        _db,
        *,
        code: str,
        state: str,
        browser_binding_token: str | None,
    ):
        assert code == "auth-code"
        assert state == "state-token"
        assert browser_binding_token is None
        raise OIDCStateError("OIDC browser binding cookie is missing")

    monkeypatch.setattr(oidc_routes.oidc_service, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(oidc_routes, "get_audit_service", lambda _db: _FakeAuditService())

    response = await client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "auth-code", "state": "state-token"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "error=oidc_failed" in response.headers["location"]


@pytest.mark.asyncio
async def test_disabled_oidc_callback_revokes_browser_binding_cookie(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.routes.oidc as oidc_routes

    async def fake_setting_get(_self, key: str, default: object = None) -> object:
        return False if key == "oidc.enabled" else default

    monkeypatch.setattr(oidc_routes.SettingsService, "get", fake_setting_get)

    response = await client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "auth-code", "state": "state-token"},
        cookies={
            get_local("oidc.browser_binding.cookie_name"): "browser-binding-token"
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
async def test_oidc_callback_failure_audit_is_exactly_once_after_valid_state(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import app.api.routes.oidc as oidc_routes

    browser_binding = "valid-browser-binding"
    state = "valid-state-then-replayed"
    async with session_maker() as db:
        db.add(
            OIDCAuthRequest(
                state=state,
                nonce="expected-nonce",
                browser_binding_hash=hash_opaque_token(browser_binding),
                source_fingerprint="f" * 64,
                redirect_to="http://localhost:5173/",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        )
        await db.commit()

    async def fake_setting_get(_self, key: str, default: object = None) -> object:
        return True if key == "oidc.enabled" else default

    async def fake_provider_configuration(*_args: object, **_kwargs: object):
        return SimpleNamespace(
            token_endpoint="https://issuer.example/token",
            client_id="client-id",
            client_secret=None,
            redirect_uri="https://intercept.example/api/v1/auth/oidc/callback",
            jwks_uri="https://issuer.example/jwks",
            issuer="https://issuer.example",
        )

    def reject_id_token(**_kwargs: object) -> dict[str, Any]:
        raise OIDCAuthenticationError("OIDC ID token validation failed")

    monkeypatch.setattr(oidc_routes.SettingsService, "get", fake_setting_get)
    monkeypatch.setattr(
        oidc_routes.oidc_service,
        "_load_provider_configuration",
        fake_provider_configuration,
    )
    monkeypatch.setattr(
        oidc_routes.oidc_service,
        "validate_id_token",
        reject_id_token,
    )
    monkeypatch.setattr(
        "app.services.oidc_service.httpx.AsyncClient",
        lambda **_kwargs: _FakeOIDCClient(),
    )

    async def callback(callback_state: str):
        return await client.get(
            "/api/v1/auth/oidc/callback",
            params={"code": "authorization-code", "state": callback_state},
            cookies={
                get_local("oidc.browser_binding.cookie_name"): browser_binding
            },
            follow_redirects=False,
        )

    with caplog.at_level(logging.WARNING, logger=oidc_routes.__name__):
        first = await callback(state)
        assert first.status_code == 302
        async with session_maker() as db:
            assert await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.event_type == "auth.oidc.login.failure")
            ) == 1

        replay = await callback(state)
        random_state = await callback("attacker-controlled-random-state")

    assert replay.status_code == random_state.status_code == 302
    async with session_maker() as db:
        assert await db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.event_type == "auth.oidc.login.failure")
        ) == 1
    rejected_records = [
        record
        for record in caplog.records
        if getattr(record, "security", {}).get("event")
        == "oidc_login_callback_rejected"
    ]
    assert len(rejected_records) == 2
    assert all(state not in repr(record.__dict__) for record in rejected_records)
    assert all(
        "attacker-controlled-random-state" not in repr(record.__dict__)
        for record in rejected_records
    )


@pytest.mark.asyncio
async def test_oidc_provider_error_consumes_bound_state_and_audits_exactly_once(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.routes.oidc as oidc_routes

    state = "provider-denial-state"
    browser_binding = "provider-denial-browser-binding"
    sensitive_description = "provider diagnostic that must not persist"
    async with session_maker() as db:
        db.add(
            OIDCAuthRequest(
                state=state,
                nonce="unused-provider-denial-nonce",
                browser_binding_hash=hash_opaque_token(browser_binding),
                source_fingerprint="d" * 64,
                redirect_to="http://localhost:5173/",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        )
        await db.commit()

    async def fake_setting_get(_self, key: str, default: object = None) -> object:
        return True if key == "oidc.enabled" else default

    monkeypatch.setattr(oidc_routes.SettingsService, "get", fake_setting_get)

    async def callback():
        return await client.get(
            "/api/v1/auth/oidc/callback",
            params={
                "error": "access_denied",
                "error_description": sensitive_description,
                "state": state,
            },
            cookies={
                get_local("oidc.browser_binding.cookie_name"): browser_binding
            },
            follow_redirects=False,
        )

    first = await callback()
    replay = await callback()

    assert first.status_code == replay.status_code == 302
    assert first.headers["location"].startswith("http://localhost:8080?")
    assert sensitive_description not in first.headers["location"]
    binding_cookie_name = get_local("oidc.browser_binding.cookie_name")
    assert any(
        header.startswith(f"{binding_cookie_name}=") and "Max-Age=0" in header
        for header in first.headers.get_list("set-cookie")
    )

    async with session_maker() as db:
        auth_request = await db.get(OIDCAuthRequest, state)
        assert auth_request is not None
        assert auth_request.consumed_at is not None
        audit_rows = list(
            (
                await db.scalars(
                    select(AuditLog).where(
                        AuditLog.event_type == "auth.oidc.login.failure"
                    )
                )
            ).all()
        )

    assert len(audit_rows) == 1
    audit_payload = json.loads(audit_rows[0].new_value or "{}")
    assert audit_payload["reason"] == "OIDC sign-in was cancelled or denied"
    assert sensitive_description not in (audit_rows[0].new_value or "")


@pytest.mark.asyncio
async def test_delayed_oidc_callback_predating_account_cutoff_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        credentials_invalidated_at=datetime.fromtimestamp(200, tz=timezone.utc)
    )

    async def fake_consume_auth_request(*_args: object, **_kwargs: object):
        return SimpleNamespace(
            nonce="nonce",
            redirect_to="http://localhost:5173/",
            created_at=datetime.fromtimestamp(100, tz=timezone.utc),
        )

    async def fake_provider_configuration(
        *_args: object,
        **_kwargs: object,
    ) -> OIDCProviderConfiguration:
        return OIDCProviderConfiguration(
            discovery_url="https://issuer.example/.well-known/openid-configuration",
            authorization_endpoint="https://issuer.example/authorize",
            token_endpoint="https://issuer.example/token",
            jwks_uri="https://issuer.example/jwks",
            client_id="client-id",
            client_secret=None,
            scopes="openid email profile",
            provider_name="Example IdP",
            redirect_uri="https://intercept.example/api/v1/auth/oidc/callback",
            issuer="https://issuer.example",
        )

    async def fake_find_or_create_user(*_args: object, **_kwargs: object):
        return user

    async def fake_acquire_oidc_policy_lock(
        *_args: object,
        **_kwargs: object,
    ) -> None:
        return None

    async def fake_setting_get(
        _self: object,
        key: str,
        default: object = None,
    ) -> object:
        return True if key == "oidc.enabled" else default

    async def fake_is_safe_redirect_target(
        *_args: object,
        **_kwargs: object,
    ) -> bool:
        return True

    monkeypatch.setattr(oidc_service, "_consume_auth_request", fake_consume_auth_request)
    monkeypatch.setattr(
        oidc_service,
        "_load_provider_configuration",
        fake_provider_configuration,
    )
    monkeypatch.setattr(oidc_service, "find_or_create_user", fake_find_or_create_user)
    monkeypatch.setattr(
        oidc_service,
        "is_safe_redirect_target",
        fake_is_safe_redirect_target,
    )
    monkeypatch.setattr(
        "app.services.oidc_service.acquire_oidc_policy_lock",
        fake_acquire_oidc_policy_lock,
    )
    monkeypatch.setattr(
        "app.services.oidc_service.SettingsService.get",
        fake_setting_get,
    )
    monkeypatch.setattr(
        oidc_service,
        "validate_id_token",
        # A future-skewed IdP iat must not override the server auth-request clock.
        lambda **_kwargs: {"sub": "provider-subject", "iat": 250},
    )
    monkeypatch.setattr(
        "app.services.oidc_service.httpx.AsyncClient",
        lambda **_kwargs: _FakeOIDCClient(),
    )

    with pytest.raises(OIDCAuthenticationError, match="predates"):
        await oidc_service.exchange_code(
            object(),
            code="authorization-code",
            state="state-token",
            browser_binding_token="browser-binding-token",
        )


@pytest.mark.asyncio
async def test_invalid_return_target_uses_canonical_origin_not_forwarded_host(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.routes.oidc as oidc_routes

    async def fake_setting_get(_self, key: str, default: object = None) -> object:
        return True if key == "oidc.enabled" else default

    async def fake_is_safe_redirect_target(_db, _target: str) -> bool:
        return False

    monkeypatch.setattr(oidc_routes.SettingsService, "get", fake_setting_get)
    monkeypatch.setattr(
        oidc_routes.oidc_service,
        "is_safe_redirect_target",
        fake_is_safe_redirect_target,
    )

    response = await client.get(
        "/api/v1/auth/oidc/login",
        params={"next": "https://attacker.example/steal"},
        headers={"X-Forwarded-Host": "attacker.example"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"].startswith("http://localhost:8080?")
    assert "attacker.example" not in response.headers["location"]
