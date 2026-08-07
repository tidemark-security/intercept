from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.oidc_service as oidc_module
from app.models.enums import UserRole, UserStatus
from app.services.oidc_service import (
    OIDCAuthenticationError,
    OIDCIdentityPolicy,
    OIDCService,
)


class _Result:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, results: list[object | None]) -> None:
        self.results = list(results)
        self.flushed = False

    async def execute(self, _statement):
        return _Result(self.results.pop(0))

    async def flush(self) -> None:
        self.flushed = True


def _snapshot_policy(**updates) -> OIDCIdentityPolicy:
    values = {
        "jit_provisioning": False,
        "default_role": "ANALYST",
        "role_claim_path": "groups",
        "role_mapping": {"security-auditors": "AUDITOR"},
    }
    values.update(updates)
    return OIDCIdentityPolicy(**values)


def _settings_must_not_load(*_args, **_kwargs):
    raise AssertionError("MCP identity resolution must not re-read OIDC settings")


@pytest.mark.asyncio
async def test_snapshot_role_mapping_is_used_without_loading_current_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oidc_module, "SettingsService", _settings_must_not_load)

    role = await OIDCService().resolve_role(
        object(),
        claims={"groups": ["security-auditors"]},
        identity_policy=_snapshot_policy(),
    )

    assert role is UserRole.AUDITOR


@pytest.mark.asyncio
async def test_snapshot_jit_policy_cannot_be_changed_mid_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oidc_module, "SettingsService", _settings_must_not_load)
    session = _Session([None, None])

    with pytest.raises(
        OIDCAuthenticationError,
        match="not enabled for unprovisioned users",
    ):
        await OIDCService().find_or_create_user(
            session,
            claims={
                "sub": "subject-1",
                "email": "new-user@example.com",
                "preferred_username": "new-user@example.com",
            },
            issuer="https://issuer.example",
            identity_policy=_snapshot_policy(jit_provisioning=False),
        )


@pytest.mark.asyncio
async def test_snapshot_trusted_issuer_cannot_enable_email_account_linking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oidc_module, "SettingsService", _settings_must_not_load)
    existing_user = SimpleNamespace(
        id="user-id",
        username="person@example.com",
        email="person@example.com",
        status=UserStatus.ACTIVE,
        oidc_issuer=None,
        oidc_subject=None,
        updated_at=None,
    )
    session = _Session([None, existing_user])

    with pytest.raises(OIDCAuthenticationError, match="email collides"):
        await OIDCService().find_or_create_user(
            session,
            claims={"sub": "subject-1", "email": "person@example.com"},
            issuer="https://issuer.example",
            identity_policy=_snapshot_policy(jit_provisioning=True),
        )

    assert existing_user.oidc_issuer is None
    assert existing_user.oidc_subject is None
    assert session.flushed is False


@pytest.mark.asyncio
async def test_snapshot_preferred_username_does_not_replace_email_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oidc_module, "SettingsService", _settings_must_not_load)
    session = _Session([None])

    with pytest.raises(OIDCAuthenticationError, match="did not include an email address"):
        await OIDCService().find_or_create_user(
            session,
            claims={
                "sub": "entra-subject",
                "preferred_username": "Person@Example.com",
            },
            issuer="https://issuer.example",
            identity_policy=_snapshot_policy(jit_provisioning=True),
        )
