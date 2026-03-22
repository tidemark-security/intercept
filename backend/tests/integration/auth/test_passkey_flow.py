from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import passkey_service as auth_route_passkey_service
from app.models.models import PasskeyCredential, UserAccount
from app.services.passkey_service import PasskeyAuthenticationResult
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


@pytest.mark.asyncio
async def test_password_login_blocked_when_active_passkeys_exist(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    user = analyst_user_factory()
    passkey = PasskeyCredential(
        user_id=user.id,
        name="Primary key",
        credential_id="cred-1",
        credential_public_key="pub-1",
        sign_count=0,
        transports=["usb"],
    )

    async with session_maker() as session:
        session.add(user)
        session.add(passkey)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["message"] == "Unable to sign in with the provided credentials."


@pytest.mark.asyncio
async def test_self_passkey_list_rename_and_revoke(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    user = analyst_user_factory()

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login.status_code == 200
    session_cookie = login.cookies.get("intercept_session")
    assert session_cookie is not None

    passkey_id = uuid4()
    passkey = PasskeyCredential(
        id=passkey_id,
        user_id=user.id,
        name="Work key",
        credential_id="cred-2",
        credential_public_key="pub-2",
        sign_count=0,
        transports=["internal"],
    )

    async with session_maker() as session:
        session.add(passkey)
        await session.commit()

    list_response = await client.get(
        "/api/v1/auth/passkeys",
        cookies={"intercept_session": session_cookie},
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["name"] == "Work key"
    assert list_response.json()[0]["transports"] == ["internal"]

    rename_response = await client.patch(
        f"/api/v1/auth/passkeys/{passkey_id}",
        json={"name": "Renamed key"},
        cookies={"intercept_session": session_cookie},
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "Renamed key"
    assert rename_response.json()["transports"] == ["internal"]

    list_after_rename = await client.get(
        "/api/v1/auth/passkeys",
        cookies={"intercept_session": session_cookie},
    )
    assert list_after_rename.status_code == 200
    assert len(list_after_rename.json()) == 1
    assert list_after_rename.json()[0]["name"] == "Renamed key"
    assert list_after_rename.json()[0]["transports"] == ["internal"]

    revoke_response = await client.delete(
        f"/api/v1/auth/passkeys/{passkey_id}",
        cookies={"intercept_session": session_cookie},
    )
    assert revoke_response.status_code == 204

    list_after_revoke = await client.get(
        "/api/v1/auth/passkeys",
        cookies={"intercept_session": session_cookie},
    )
    assert list_after_revoke.status_code == 200
    assert list_after_revoke.json() == []


@pytest.mark.asyncio
async def test_admin_can_list_and_revoke_user_passkeys(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    analyst = analyst_user_factory()
    passkey_id = uuid4()

    passkey = PasskeyCredential(
        id=passkey_id,
        user_id=analyst.id,
        name="YubiKey",
        credential_id="cred-3",
        credential_public_key="pub-3",
        sign_count=1,
        transports=["usb", "nfc"],
    )

    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        session.add(passkey)
        await session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login.status_code == 200
    session_cookie = login.cookies.get("intercept_session")
    assert session_cookie is not None

    list_response = await client.get(
        f"/api/v1/admin/auth/users/{analyst.id}/passkeys",
        cookies={"intercept_session": session_cookie},
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["id"] == str(passkey_id)

    revoke_response = await client.delete(
        f"/api/v1/admin/auth/users/{analyst.id}/passkeys/{passkey_id}",
        cookies={"intercept_session": session_cookie},
    )
    assert revoke_response.status_code == 204

    list_after_revoke = await client.get(
        f"/api/v1/admin/auth/users/{analyst.id}/passkeys",
        cookies={"intercept_session": session_cookie},
    )
    assert list_after_revoke.status_code == 200
    assert len(list_after_revoke.json()) == 1
    assert list_after_revoke.json()[0]["revokedAt"] is not None


@pytest.mark.asyncio
async def test_passkey_auth_verify_issues_standard_session_cookie(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch,
) -> None:
    user = analyst_user_factory()

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    async def _fake_begin_authentication(_db, *, username: str):
        assert username == user.username
        return (
            {
                "challenge": "challenge-1",
                "options": {
                    "challenge": "challenge-1",
                    "allowCredentials": [],
                },
            },
            user,
        )

    async def _fake_finish_authentication(_db, *, challenge: str, credential: dict):
        assert challenge == "challenge-1"
        assert credential["id"] == "cred-x"
        synthetic_passkey = PasskeyCredential(
            id=uuid4(),
            user_id=user.id,
            name="Synthetic",
            credential_id="cred-x",
            credential_public_key="pub-x",
            sign_count=2,
            transports=["internal"],
            last_used_at=datetime.now(timezone.utc),
        )
        return PasskeyAuthenticationResult(user=user, passkey=synthetic_passkey)

    monkeypatch.setattr(auth_route_passkey_service, "begin_authentication", _fake_begin_authentication)
    monkeypatch.setattr(auth_route_passkey_service, "finish_authentication", _fake_finish_authentication)

    begin_response = await client.post(
        "/api/v1/auth/passkeys/authenticate/options",
        json={"username": user.username},
    )
    assert begin_response.status_code == 200
    assert begin_response.json()["challenge"] == "challenge-1"

    verify_response = await client.post(
        "/api/v1/auth/passkeys/authenticate/verify",
        json={"challenge": "challenge-1", "credential": {"id": "cred-x"}},
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["user"]["username"] == user.username

    set_cookie = verify_response.headers.get("set-cookie")
    assert set_cookie is not None and set_cookie.startswith("intercept_session=")
