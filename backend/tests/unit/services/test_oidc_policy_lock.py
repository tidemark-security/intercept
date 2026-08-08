from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import settings as settings_routes
from app.core.csrf import API_KEY_AUTH_RESULT_SCOPE_KEY
from app.core.oidc_policy_lock import (
    acquire_oidc_policy_lock,
    oidc_setting_requires_policy_gate,
)
from app.models.enums import UserRole
from app.services import settings_service as settings_module
from app.services.settings_service import SettingsService


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("oidc.enabled", True),
        ("oidc.discovery_url", True),
        ("oidc.client_id", True),
        ("oidc.client_secret", True),
        ("oidc.scopes", True),
        ("oidc.jit_provisioning", True),
        ("oidc.default_role", True),
        ("oidc.role_claim_path", True),
        ("oidc.role_mapping", True),
        ("oidc.sso_bypass_users", True),
        ("oidc.allowed_redirect_origins", True),
        # Display text cannot affect authentication or authorization.
        ("oidc.provider_name", False),
        # Local-only settings cannot be mutated through the DB settings API.
        ("oidc.redirect_uri", False),
        ("oidc.clock_skew_seconds", False),
        ("oidc.browser_binding.cookie_name", False),
        ("unrelated.setting", False),
    ],
)
def test_oidc_authorization_policy_setting_classification(
    key: str,
    expected: bool,
) -> None:
    assert oidc_setting_requires_policy_gate(key) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("shared", "function_name"),
    [
        (True, "pg_advisory_xact_lock_shared"),
        (False, "pg_advisory_xact_lock"),
    ],
)
async def test_oidc_policy_gate_uses_transaction_scoped_advisory_lock(
    shared: bool,
    function_name: str,
) -> None:
    execute = AsyncMock()
    db = cast(AsyncSession, SimpleNamespace(execute=execute))

    await acquire_oidc_policy_lock(db, shared=shared)

    statement, parameters = execute.await_args.args
    assert function_name in str(statement)
    assert parameters["lock_key"] > 0


@pytest.mark.asyncio
async def test_oidc_enabled_service_writes_take_exclusive_policy_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquire = AsyncMock()
    monkeypatch.setattr(settings_module, "acquire_oidc_policy_lock", acquire)
    db = cast(AsyncSession, SimpleNamespace())
    service = SettingsService(db)

    await service._acquire_oidc_policy_write_gate("oidc.client_secret")
    await service._acquire_oidc_policy_write_gate("oidc.provider_name")

    acquire.assert_awaited_once_with(db, shared=False)


@pytest.mark.asyncio
async def test_oidc_policy_route_releases_initial_auth_then_reauthenticates_under_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    events: list[str] = []
    initial_user = SimpleNamespace(
        id=user_id,
        username="admin",
        role=UserRole.ADMIN,
        must_change_password=False,
    )
    reauthorized_user = SimpleNamespace(
        id=user_id,
        username="admin",
        role=UserRole.ADMIN,
        must_change_password=False,
    )

    async def commit() -> None:
        events.append("release_initial_auth")

    async def acquire(_db: Any, *, shared: bool) -> None:
        assert shared is False
        events.append("exclusive_gate")

    async def authenticate(_request: Any, _db: Any) -> Any:
        events.append("reauthenticate")
        return reauthorized_user

    def require_admin_scope(_request: Any) -> None:
        events.append("admin_scope")

    request = cast(
        Request,
        SimpleNamespace(scope={API_KEY_AUTH_RESULT_SCOPE_KEY: object()}),
    )
    db = cast(AsyncSession, SimpleNamespace(commit=commit))
    monkeypatch.setattr(settings_routes, "acquire_oidc_policy_lock", acquire)
    monkeypatch.setattr(settings_routes, "_authenticate_from_request", authenticate)
    monkeypatch.setattr(
        settings_routes,
        "require_api_key_admin_scope",
        require_admin_scope,
    )

    result = await settings_routes._reauthorize_oidc_policy_writer(
        request=request,
        key="oidc.role_mapping",
        current_user=initial_user,
        db=db,
    )

    assert result is reauthorized_user
    assert API_KEY_AUTH_RESULT_SCOPE_KEY not in request.scope
    assert events == [
        "release_initial_auth",
        "exclusive_gate",
        "reauthenticate",
        "admin_scope",
    ]
