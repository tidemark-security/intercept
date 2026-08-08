from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers.bytes_to_base64url import bytes_to_base64url
from webauthn.helpers.structs import UserVerificationRequirement

from app.api.routes.auth import passkey_service as auth_route_passkey_service
from app.models.models import (
    AuthSession,
    PasskeyCredential,
    PasswordLoginFailureCounter,
    UserAccount,
    WebAuthnChallenge,
)
from app.services.audit_service import AuditContext
from app.services.auth_service import auth_service
from app.services.passkey_challenge_request_service import PasskeyChallengeRequestPolicy
from app.services.passkey_service import (
    PasskeyAuthenticationResult,
    PasskeyChallengeNotFoundError,
    PasskeyCredentialNotFoundError,
    passkey_service,
)
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

    async with session_maker() as session:
        session.add(
            PasswordLoginFailureCounter(
                user_id=user.id,
                password_fingerprint="b" * 64,
                failed_attempts=5,
            )
        )
        await session.commit()

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
    async with session_maker() as session:
        pending = list(
            await session.scalars(
                select(PasswordLoginFailureCounter).where(
                    PasswordLoginFailureCounter.user_id == user.id
                )
            )
        )
    assert pending == []


@pytest.mark.asyncio
async def test_passkey_registration_clears_pending_password_failures(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = analyst_user_factory(username="passkey-transition-failure-clear")
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

    begin = await client.post(
        "/api/v1/auth/passkeys/register/options",
        json={},
        cookies={"intercept_session": session_cookie},
    )
    assert begin.status_code == 200

    async with session_maker() as session:
        session.add(
            PasswordLoginFailureCounter(
                user_id=user.id,
                password_fingerprint="a" * 64,
                failed_attempts=5,
            )
        )
        await session.commit()

    monkeypatch.setattr(
        "app.services.passkey_service.verify_registration_response",
        lambda **_kwargs: SimpleNamespace(
            credential_id=b"transition-credential",
            credential_public_key=b"public-key",
            sign_count=0,
            aaguid=None,
            credential_device_type="single_device",
            credential_backed_up=False,
        ),
    )
    finish = await client.post(
        "/api/v1/auth/passkeys/register/verify",
        json={
            "challenge": begin.json()["challenge"],
            "name": "Transition passkey",
            "credential": {"id": "transition-credential"},
        },
        cookies={"intercept_session": session_cookie},
    )
    assert finish.status_code == 200

    async with session_maker() as session:
        pending = list(
            await session.scalars(
                select(PasswordLoginFailureCounter).where(
                    PasswordLoginFailureCounter.user_id == user.id
                )
            )
        )
    assert pending == []


@pytest.mark.asyncio
async def test_passkey_registration_rejects_an_eleventh_active_credential(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    user = analyst_user_factory(username="passkey-ceiling-user")
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    session_cookie = login.cookies.get("intercept_session")
    assert login.status_code == 200
    assert session_cookie is not None

    async with session_maker() as session:
        session.add_all(
            [
                PasskeyCredential(
                    user_id=user.id,
                    name=f"Passkey {index}",
                    credential_id=bytes_to_base64url(
                        f"ceiling-credential-{index}".encode()
                    ),
                    credential_public_key="cHVibGljLWtleQ",
                )
                for index in range(10)
            ]
        )
        await session.commit()

    response = await client.post(
        "/api/v1/auth/passkeys/register/options",
        json={},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 409
    assert response.json() == {
        "message": "Maximum number of active passkeys reached.",
        "fields": [],
    }


@pytest.mark.asyncio
async def test_passkey_registration_rechecks_the_ceiling_at_completion(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = analyst_user_factory(username="passkey-completion-ceiling-user")
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    session_cookie = login.cookies.get("intercept_session")
    assert login.status_code == 200
    assert session_cookie is not None

    async with session_maker() as session:
        session.add_all(
            [
                PasskeyCredential(
                    user_id=user.id,
                    name=f"Existing passkey {index}",
                    credential_id=bytes_to_base64url(
                        f"completion-existing-{index}".encode()
                    ),
                    credential_public_key="cHVibGljLWtleQ",
                )
                for index in range(9)
            ]
        )
        await session.commit()

    begin_response = await client.post(
        "/api/v1/auth/passkeys/register/options",
        json={},
        cookies={"intercept_session": session_cookie},
    )
    assert begin_response.status_code == 200

    async with session_maker() as session:
        session.add(
            PasskeyCredential(
                user_id=user.id,
                name="Concurrent tenth passkey",
                credential_id=bytes_to_base64url(b"completion-concurrent-tenth"),
                credential_public_key="cHVibGljLWtleQ",
            )
        )
        await session.commit()

    monkeypatch.setattr(
        "app.services.passkey_service.verify_registration_response",
        lambda **_kwargs: SimpleNamespace(
            credential_id=b"completion-rejected-eleventh",
            credential_public_key=b"public-key",
            sign_count=0,
            aaguid=None,
            credential_device_type="single_device",
            credential_backed_up=False,
        ),
    )
    finish_response = await client.post(
        "/api/v1/auth/passkeys/register/verify",
        json={
            "challenge": begin_response.json()["challenge"],
            "name": "Rejected eleventh passkey",
            "credential": {"id": "completion-rejected-eleventh"},
        },
        cookies={"intercept_session": session_cookie},
    )

    assert finish_response.status_code == 409
    assert finish_response.json() == {
        "message": "Maximum number of active passkeys reached.",
        "fields": [],
    }
    async with session_maker() as session:
        credentials = list(
            (
                await session.execute(
                    select(PasskeyCredential).where(
                        PasskeyCredential.user_id == user.id,
                        PasskeyCredential.revoked_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(credentials) == 10


@pytest.mark.asyncio
async def test_passkey_registration_requires_a_discoverable_credential(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    user = analyst_user_factory(username="discoverable-passkey-user")
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    session_cookie = login.cookies.get("intercept_session")
    assert login.status_code == 200
    assert session_cookie is not None

    response = await client.post(
        "/api/v1/auth/passkeys/register/options",
        json={},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    selection = response.json()["options"]["authenticatorSelection"]
    assert selection["residentKey"] == "required"
    assert selection["requireResidentKey"] is True


@pytest.mark.asyncio
async def test_repeated_registration_options_keep_only_one_live_challenge(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    user = analyst_user_factory(username="bounded-registration-challenges")
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    session_cookie = login.cookies.get("intercept_session")
    assert login.status_code == 200
    assert session_cookie is not None

    for _ in range(2):
        response = await client.post(
            "/api/v1/auth/passkeys/register/options",
            json={},
            cookies={"intercept_session": session_cookie},
        )
        assert response.status_code == 200

    async with session_maker() as session:
        challenges = list(
            (
                await session.execute(
                    select(WebAuthnChallenge).where(
                        WebAuthnChallenge.flow_type == "registration",
                        WebAuthnChallenge.user_id == user.id,
                        WebAuthnChallenge.consumed_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(challenges) == 1


@pytest.mark.asyncio
async def test_registration_options_enforce_a_durable_per_account_rate(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = analyst_user_factory(username="rate-limited-registration-challenges")
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    session_cookie = login.cookies.get("intercept_session")
    assert login.status_code == 200
    assert session_cookie is not None
    monkeypatch.setattr(
        auth_route_passkey_service,
        "_challenge_request_policy",
        PasskeyChallengeRequestPolicy(
            registration_global_outstanding_quota=10,
            registration_global_rate_quota=10,
            registration_per_user_rate_quota=2,
            retry_after_seconds=47,
        ),
    )

    responses = [
        await client.post(
            "/api/v1/auth/passkeys/register/options",
            json={},
            cookies={"intercept_session": session_cookie},
        )
        for _ in range(3)
    ]

    assert [response.status_code for response in responses] == [200, 200, 429]
    assert responses[-1].headers["Retry-After"] == "47"
    assert responses[-1].json() == {
        "message": "Too many passkey registration attempts. Please try again later.",
        "fields": [],
    }


@pytest.mark.asyncio
async def test_discoverable_passkey_options_can_complete_authentication(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = analyst_user_factory(username="discoverable-authentication-user")
    credential_id = bytes_to_base64url(b"discoverable-authentication-credential")
    passkey = PasskeyCredential(
        user_id=user.id,
        name="Discoverable credential",
        credential_id=credential_id,
        credential_public_key=bytes_to_base64url(b"public-key"),
        sign_count=0,
        transports=["internal"],
    )
    async with session_maker() as session:
        session.add_all([user, passkey])
        await session.commit()

    begin_response = await client.post(
        "/api/v1/auth/passkeys/authenticate/options",
        json={"username": user.username},
    )
    assert begin_response.status_code == 200
    begin_payload = begin_response.json()
    assert begin_payload["options"]["allowCredentials"] == []

    async with session_maker() as session:
        challenge = await session.scalar(
            select(WebAuthnChallenge).where(
                WebAuthnChallenge.challenge == begin_payload["challenge"]
            )
        )
        assert challenge is not None
        assert challenge.user_id is None

    monkeypatch.setattr(
        "app.services.passkey_service.verify_authentication_response",
        lambda **_kwargs: SimpleNamespace(
            new_sign_count=1,
            credential_backed_up=False,
        ),
    )
    finish_response = await client.post(
        "/api/v1/auth/passkeys/authenticate/verify",
        json={
            "challenge": begin_payload["challenge"],
            "credential": {"id": credential_id},
        },
    )

    assert finish_response.status_code == 200
    assert finish_response.json()["user"]["id"] == str(user.id)
    assert finish_response.cookies.get("intercept_session") is not None


@pytest.mark.asyncio
async def test_oidc_policy_blocks_passkey_rename_and_revokes_credential(
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
    async with session_maker() as session:
        persisted_user = await session.get(UserAccount, user.id)
        assert persisted_user is not None
        persisted_user.oidc_issuer = "https://issuer.example"
        persisted_user.oidc_subject = "subject-after-login"
        session.add(
            PasskeyCredential(
                id=passkey_id,
                user_id=user.id,
                name="Original name",
                credential_id="cred-policy-rename",
                credential_public_key="pub-policy-rename",
                sign_count=0,
                transports=["internal"],
            )
        )
        await session.commit()

    rename_response = await client.patch(
        f"/api/v1/auth/passkeys/{passkey_id}",
        json={"name": "Renamed despite policy"},
        cookies={"intercept_session": session_cookie},
    )

    assert rename_response.status_code == 403
    assert rename_response.json()["message"] == (
        "Passkey management is disabled for this account."
    )

    async with session_maker() as session:
        persisted_passkey = await session.get(PasskeyCredential, passkey_id)
        assert persisted_passkey is not None
        assert persisted_passkey.name == "Original name"
        assert persisted_passkey.revoked_at is not None


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
async def test_disable_consumes_user_bound_webauthn_challenges(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory(username="passkey-lifecycle-admin")
    analyst = analyst_user_factory(username="passkey-lifecycle-target")
    challenge = WebAuthnChallenge(
        challenge="pre-disable-registration-challenge",
        flow_type="registration",
        user_id=analyst.id,
        username=analyst.username,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    async with session_maker() as session:
        session.add_all([admin, analyst, challenge])
        await session.commit()

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    admin_cookie = admin_login.cookies.get("intercept_session")
    for status_value in ("DISABLED", "ACTIVE"):
        response = await client.patch(
            f"/api/v1/admin/auth/users/{analyst.id}/status",
            json={"status": status_value},
            cookies={"intercept_session": admin_cookie},
        )
        assert response.status_code == 204, response.text

    async with session_maker() as session:
        persisted = await session.get(WebAuthnChallenge, challenge.id)
        assert persisted is not None
        assert persisted.consumed_at is not None


@pytest.mark.asyncio
async def test_pre_cutoff_registration_challenge_committed_after_disable_is_rejected(
    session_maker: Any,
    analyst_user_factory,
) -> None:
    analyst = analyst_user_factory(username="passkey-race-target")
    cutoff = datetime.now(timezone.utc)
    analyst.credentials_invalidated_at = cutoff
    challenge = WebAuthnChallenge(
        challenge="pre-cutoff-challenge-committed-after-disable",
        flow_type="registration",
        user_id=analyst.id,
        username=analyst.username,
        created_at=cutoff - timedelta(seconds=1),
        expires_at=cutoff + timedelta(minutes=5),
    )
    async with session_maker() as session:
        session.add_all([analyst, challenge])
        await session.commit()

    async with session_maker() as session:
        with pytest.raises(PasskeyChallengeNotFoundError):
            await passkey_service._consume_challenge(
                session,
                challenge=challenge.challenge,
                flow_type="registration",
                user_id=analyst.id,
            )
        await session.commit()

    async with session_maker() as session:
        persisted = await session.get(WebAuthnChallenge, challenge.id)
        assert persisted is not None
        assert persisted.consumed_at is not None


@pytest.mark.asyncio
async def test_pre_cutoff_passkey_cannot_authenticate_after_missed_row_revocation(
    session_maker: Any,
    analyst_user_factory,
) -> None:
    cutoff = datetime.now(timezone.utc)
    analyst = analyst_user_factory(username="passkey-cutoff-target")
    analyst.credentials_invalidated_at = cutoff
    passkey = PasskeyCredential(
        user_id=analyst.id,
        name="Pre-cutoff passkey",
        credential_id="pre-cutoff-credential",
        credential_public_key="unused-before-cutoff-rejection",
        sign_count=0,
        transports=["internal"],
        created_at=cutoff - timedelta(seconds=1),
    )
    challenge = WebAuthnChallenge(
        challenge="post-cutoff-authentication-challenge",
        flow_type="authentication",
        user_id=analyst.id,
        username=analyst.username,
        created_at=cutoff + timedelta(seconds=1),
        expires_at=cutoff + timedelta(minutes=5),
    )
    async with session_maker() as session:
        session.add_all([analyst, passkey, challenge])
        await session.commit()

    async with session_maker() as session:
        with pytest.raises(PasskeyCredentialNotFoundError):
            await passkey_service.finish_authentication(
                session,
                challenge=challenge.challenge,
                credential={"id": passkey.credential_id},
            )
        await session.commit()

    async with session_maker() as session:
        persisted_passkey = await session.get(PasskeyCredential, passkey.id)
        persisted_challenge = await session.get(WebAuthnChallenge, challenge.id)
        assert persisted_passkey is not None
        assert persisted_passkey.revoked_at is not None
        assert persisted_challenge is not None
        assert persisted_challenge.consumed_at is not None


@pytest.mark.asyncio
async def test_passkey_revocation_cannot_commit_between_verification_and_session_issue(
    session_maker: Any,
    analyst_user_factory,
    monkeypatch,
) -> None:
    """Revocation and authentication must have one transaction order.

    Once passkey authentication has locked the credential, an administrative
    revocation must wait for that authentication transaction to either issue
    its session or roll back. This prevents a revoked credential from issuing
    a session after the revocation has already committed.
    """
    user = analyst_user_factory(username="passkey-revocation-race")
    challenge_value = bytes_to_base64url(b"passkey-race-challenge")
    credential_id = bytes_to_base64url(b"passkey-race-credential")
    passkey = PasskeyCredential(
        user_id=user.id,
        name="Race credential",
        credential_id=credential_id,
        credential_public_key=bytes_to_base64url(b"public-key"),
        sign_count=0,
        transports=["internal"],
    )
    challenge = WebAuthnChallenge(
        challenge=challenge_value,
        flow_type="authentication",
        user_id=user.id,
        username=user.username,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    async with session_maker() as session:
        session.add_all([user, passkey, challenge])
        await session.commit()

    authentication_paused = asyncio.Event()
    continue_authentication = asyncio.Event()
    authentication_committed = asyncio.Event()
    revocation_committed = asyncio.Event()

    async def _pause_after_credential_lock(_db):
        authentication_paused.set()
        await continue_authentication.wait()
        return SimpleNamespace(
            rp_id="localhost",
            expected_origins=["https://localhost"],
            user_verification=UserVerificationRequirement.REQUIRED,
        )

    monkeypatch.setattr(passkey_service, "_load_config", _pause_after_credential_lock)
    monkeypatch.setattr(
        "app.services.passkey_service.verify_authentication_response",
        lambda **_kwargs: SimpleNamespace(
            new_sign_count=1,
            credential_backed_up=False,
        ),
    )

    async def _authenticate_and_issue_session() -> None:
        async with session_maker() as session:
            result = await passkey_service.finish_authentication(
                session,
                challenge=challenge_value,
                credential={"id": credential_id},
            )
            await auth_service.create_session_for_user(
                session,
                user=result.user,
                metadata=AuditContext(),
            )
            await session.commit()
            authentication_committed.set()

    async def _revoke() -> None:
        async with session_maker() as session:
            await passkey_service.revoke_passkey(
                session,
                passkey_id=passkey.id,
                user_id=user.id,
            )
            await session.commit()
            revocation_committed.set()

    authentication_task = asyncio.create_task(_authenticate_and_issue_session())
    await asyncio.wait_for(authentication_paused.wait(), timeout=3)
    revocation_task = asyncio.create_task(_revoke())

    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                asyncio.shield(revocation_committed.wait()),
                timeout=0.25,
            )
    finally:
        continue_authentication.set()

    await asyncio.wait_for(authentication_task, timeout=3)
    await asyncio.wait_for(revocation_task, timeout=3)

    assert authentication_committed.is_set()
    assert revocation_committed.is_set()
    async with session_maker() as session:
        persisted_passkey = await session.get(PasskeyCredential, passkey.id)
        issued_sessions = list(
            (
                await session.execute(
                    select(AuthSession).where(AuthSession.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
        assert persisted_passkey is not None
        assert persisted_passkey.revoked_at is not None
        assert len(issued_sessions) == 1


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

    async def _fake_begin_authentication(
        _db,
        *,
        username: str,
        source_address: str | None = None,
    ):
        assert username == user.username
        assert source_address == "127.0.0.1"
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
