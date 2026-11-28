from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from webauthn.helpers.base64url_to_bytes import base64url_to_bytes
from webauthn.helpers.bytes_to_base64url import bytes_to_base64url
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.api.routes.auth import passkey_service as route_passkey_service
from app.models.models import PasskeyCredential, WebAuthnChallenge
from app.services.passkey_challenge_request_service import (
    PasskeyChallengeRequestLimitError,
    PasskeyChallengeRequestPolicy,
)
from app.services.passkey_service import PasskeyConfig, PasskeyService


def _passkey_config() -> PasskeyConfig:
    return PasskeyConfig(
        rp_id="localhost",
        rp_name="Tidemark Intercept",
        expected_origins=["http://localhost"],
        timeout_ms=60_000,
        challenge_ttl_seconds=300,
        user_verification=UserVerificationRequirement.REQUIRED,
        resident_key=ResidentKeyRequirement.PREFERRED,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_attachment=None,
    )


@pytest.mark.asyncio
async def test_concurrent_passkey_options_global_outstanding_quota_is_atomic(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = analyst_user_factory(username="passkey-global-quota")
    async with session_maker() as db:
        db.add_all(
            [
                user,
                PasskeyCredential(
                    user_id=user.id,
                    name="Primary passkey",
                    credential_id="cGFzc2tleS1nbG9iYWwtcXVvdGE",
                    credential_public_key="cHVibGljLWtleQ",
                    transports=["internal"],
                ),
            ]
        )
        await db.commit()

    service = PasskeyService()
    service._challenge_request_policy = SimpleNamespace(
        global_outstanding_quota=1,
        per_source_outstanding_quota=10,
        global_rate_quota=100,
        per_source_rate_quota=100,
        rate_window_seconds=3600,
        retry_after_seconds=60,
    )

    async def fixed_config(_db: AsyncSession) -> PasskeyConfig:
        return _passkey_config()

    monkeypatch.setattr(service, "_load_config", fixed_config)

    async def begin_from_worker(source_address: str) -> object:
        async with session_maker() as db:
            try:
                result = await service.begin_authentication(
                    db,
                    username=user.username,
                    source_address=source_address,
                )
                await db.commit()
                return result
            except Exception as exc:
                await db.rollback()
                return exc

    results = await asyncio.wait_for(
        asyncio.gather(
            begin_from_worker("198.51.100.10"),
            begin_from_worker("203.0.113.20"),
        ),
        timeout=5,
    )

    successes = [result for result in results if isinstance(result, tuple)]
    failures = [result for result in results if isinstance(result, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], PasskeyChallengeRequestLimitError)


@pytest.mark.parametrize(
    ("quota_name", "same_source", "same_user"),
    [
        ("per_source_outstanding_quota", True, False),
        ("global_rate_quota", False, False),
        ("per_source_rate_quota", True, False),
    ],
)
@pytest.mark.asyncio
async def test_concurrent_passkey_options_quota_dimensions_are_atomic(
    quota_name: str,
    same_source: bool,
    same_user: bool,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_user = analyst_user_factory(username=f"passkey-{quota_name}-one")
    second_user = analyst_user_factory(username=f"passkey-{quota_name}-two")
    async with session_maker() as db:
        db.add_all(
            [
                first_user,
                second_user,
                PasskeyCredential(
                    user_id=first_user.id,
                    name="First passkey",
                    credential_id=bytes_to_base64url(
                        f"first-key-{quota_name}".encode()
                    ),
                    credential_public_key="cHVibGljLWtleQ",
                ),
                PasskeyCredential(
                    user_id=second_user.id,
                    name="Second passkey",
                    credential_id=bytes_to_base64url(
                        f"second-key-{quota_name}".encode()
                    ),
                    credential_public_key="cHVibGljLWtleQ",
                ),
            ]
        )
        await db.commit()

    quotas = {
        "global_outstanding_quota": 10,
        "per_source_outstanding_quota": 10,
        "global_rate_quota": 100,
        "per_source_rate_quota": 100,
        "rate_window_seconds": 3600,
        "retry_after_seconds": 60,
    }
    quotas[quota_name] = 1
    service = PasskeyService()
    service._challenge_request_policy = SimpleNamespace(**quotas)

    async def fixed_config(_db: AsyncSession) -> PasskeyConfig:
        return _passkey_config()

    monkeypatch.setattr(service, "_load_config", fixed_config)

    async def begin_from_worker(username: str, source_address: str) -> object:
        async with session_maker() as db:
            try:
                result = await service.begin_authentication(
                    db,
                    username=username,
                    source_address=source_address,
                )
                await db.commit()
                return result
            except Exception as exc:
                await db.rollback()
                return exc

    results = await asyncio.wait_for(
        asyncio.gather(
            begin_from_worker(first_user.username, "198.51.100.10"),
            begin_from_worker(
                first_user.username if same_user else second_user.username,
                "198.51.100.10" if same_source else "203.0.113.20",
            ),
        ),
        timeout=5,
    )

    assert sum(isinstance(result, tuple) for result in results) == 1
    failures = [result for result in results if isinstance(result, Exception)]
    assert len(failures) == 1
    assert isinstance(failures[0], PasskeyChallengeRequestLimitError)


@pytest.mark.asyncio
async def test_attacker_chosen_username_cannot_consume_victim_specific_capacity(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public username input must never create a victim-specific denial lever."""

    service = PasskeyService(
        challenge_request_policy=PasskeyChallengeRequestPolicy(
            global_outstanding_quota=10,
            per_source_outstanding_quota=2,
            global_rate_quota=100,
            per_source_rate_quota=10,
            rate_window_seconds=3600,
            retry_after_seconds=60,
        )
    )

    async def fixed_config(_db: AsyncSession) -> PasskeyConfig:
        return _passkey_config()

    monkeypatch.setattr(service, "_load_config", fixed_config)

    for source_address in (
        "198.51.100.10",
        "198.51.100.11",
        "203.0.113.20",
    ):
        async with session_maker() as db:
            await service.begin_authentication(
                db,
                username="targeted-passkey-user",
                source_address=source_address,
            )
            await db.commit()


@pytest.mark.asyncio
async def test_passkey_options_cleanup_retains_rate_history_and_live_rows(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)

    def challenge_row(
        challenge: str,
        *,
        created_at: datetime,
        expires_at: datetime,
        consumed_at: datetime | None = None,
    ) -> WebAuthnChallenge:
        return WebAuthnChallenge(
            challenge=challenge,
            flow_type="authentication",
            source_fingerprint="s" * 64,
            user_fingerprint="u" * 64,
            created_at=created_at,
            expires_at=expires_at,
            consumed_at=consumed_at,
        )

    async with session_maker() as db:
        db.add_all(
            [
                challenge_row(
                    "old-expired",
                    created_at=now - timedelta(hours=2),
                    expires_at=now - timedelta(hours=1),
                ),
                challenge_row(
                    "recent-expired",
                    created_at=now - timedelta(minutes=5),
                    expires_at=now - timedelta(minutes=1),
                ),
                challenge_row(
                    "old-live",
                    created_at=now - timedelta(hours=2),
                    expires_at=now + timedelta(minutes=5),
                ),
                challenge_row(
                    "recent-consumed",
                    created_at=now - timedelta(minutes=5),
                    expires_at=now + timedelta(minutes=5),
                    consumed_at=now - timedelta(minutes=1),
                ),
            ]
        )
        await db.commit()

    service = PasskeyService(
        challenge_request_policy=SimpleNamespace(
            global_outstanding_quota=10,
            per_source_outstanding_quota=10,
            global_rate_quota=100,
            per_source_rate_quota=100,
            rate_window_seconds=3600,
            retry_after_seconds=60,
        )
    )

    async def fixed_config(_db: AsyncSession) -> PasskeyConfig:
        return _passkey_config()

    monkeypatch.setattr(service, "_load_config", fixed_config)
    async with session_maker() as db:
        await service.begin_authentication(
            db,
            username="unknown-cleanup-user",
            source_address="203.0.113.20",
        )
        await db.commit()

    async with session_maker() as db:
        challenges = set(await db.scalars(select(WebAuthnChallenge.challenge)))

    assert "old-expired" not in challenges
    assert "recent-expired" in challenges
    assert "old-live" in challenges
    assert "recent-consumed" in challenges
    assert len(challenges) == 4


@pytest.mark.asyncio
async def test_registration_cleanup_preserves_recent_expired_rate_ledger_rows(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory: Any,
) -> None:
    now = datetime.now(timezone.utc)
    user = analyst_user_factory(username="registration-cleanup-user")
    recent_ledger = WebAuthnChallenge(
        challenge="recent-expired-passkey-ledger",
        flow_type="authentication",
        source_fingerprint="s" * 64,
        user_fingerprint="u" * 64,
        created_at=now - timedelta(minutes=5),
        expires_at=now - timedelta(minutes=1),
    )
    old_ledger = WebAuthnChallenge(
        challenge="old-expired-passkey-ledger",
        flow_type="authentication",
        source_fingerprint="s" * 64,
        user_fingerprint="u" * 64,
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )
    legacy_expired = WebAuthnChallenge(
        challenge="legacy-expired-registration",
        flow_type="registration",
        created_at=now - timedelta(minutes=5),
        expires_at=now - timedelta(minutes=1),
    )
    async with session_maker() as db:
        db.add_all([user, recent_ledger, old_ledger, legacy_expired])
        await db.commit()

    service = PasskeyService(
        challenge_request_policy=PasskeyChallengeRequestPolicy()
    )
    async with session_maker() as db:
        await service._create_challenge(
            db,
            challenge="new-registration-challenge",
            flow_type="registration",
            user_id=user.id,
            ttl_seconds=300,
        )
        await db.commit()

    async with session_maker() as db:
        stored_challenges = set(
            await db.scalars(select(WebAuthnChallenge.challenge))
        )

    assert "recent-expired-passkey-ledger" in stored_challenges
    assert "old-expired-passkey-ledger" not in stored_challenges
    assert "legacy-expired-registration" not in stored_challenges
    assert "new-registration-challenge" in stored_challenges


@pytest.mark.asyncio
async def test_passkey_options_and_verification_do_not_enumerate_username(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = analyst_user_factory(username="known-passkey-user")
    async with session_maker() as db:
        db.add_all(
            [
                user,
                PasskeyCredential(
                    user_id=user.id,
                    name="Primary passkey",
                    credential_id="a25vd24tcGFzc2tleQ",
                    credential_public_key="cHVibGljLWtleQ",
                    transports=["internal"],
                ),
            ]
        )
        await db.commit()

    async def fixed_config(_db: AsyncSession) -> PasskeyConfig:
        return _passkey_config()

    monkeypatch.setattr(route_passkey_service, "_load_config", fixed_config)

    known_response = await client.post(
        "/api/v1/auth/passkeys/authenticate/options",
        json={"username": user.username},
    )
    unknown_response = await client.post(
        "/api/v1/auth/passkeys/authenticate/options",
        json={"username": "unknown-passkey-user"},
    )

    assert known_response.status_code == unknown_response.status_code == 200
    known_payload = known_response.json()
    unknown_payload = unknown_response.json()
    assert set(known_payload) == set(unknown_payload) == {"challenge", "options"}
    assert set(known_payload["options"]) == set(unknown_payload["options"])
    assert known_payload["options"]["allowCredentials"] == []
    assert unknown_payload["options"]["allowCredentials"] == []
    assert len(known_payload["options"]["allowCredentials"]) == len(
        unknown_payload["options"]["allowCredentials"]
    )
    known_credential_lengths = [
        len(credential["id"])
        for credential in known_payload["options"]["allowCredentials"]
    ]
    unknown_credential_lengths = [
        len(credential["id"])
        for credential in unknown_payload["options"]["allowCredentials"]
    ]
    assert known_credential_lengths == unknown_credential_lengths

    known_verify = await client.post(
        "/api/v1/auth/passkeys/authenticate/verify",
        json={
            "challenge": known_payload["challenge"],
            "credential": {"id": "not-a-real-credential"},
        },
    )
    unknown_verify = await client.post(
        "/api/v1/auth/passkeys/authenticate/verify",
        json={
            "challenge": unknown_payload["challenge"],
            "credential": {"id": "not-a-real-credential"},
        },
    )

    assert known_verify.status_code == unknown_verify.status_code == 401
    assert known_verify.json() == unknown_verify.json() == {
        "message": "Unable to verify passkey authentication.",
        "fields": [],
    }

    async with session_maker() as db:
        challenges = list(
            await db.scalars(
                select(WebAuthnChallenge).order_by(WebAuthnChallenge.created_at)
            )
        )
    assert len(challenges) == 2
    assert all(challenge.source_fingerprint for challenge in challenges)
    assert all(challenge.user_fingerprint for challenge in challenges)
    assert all(challenge.username is None for challenge in challenges)


@pytest.mark.asyncio
async def test_public_passkey_options_do_not_materialize_legacy_credentials(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_user = analyst_user_factory(username="legacy-excess-passkeys")
    async with session_maker() as db:
        db.add(legacy_user)
        db.add_all(
            [
                PasskeyCredential(
                    user_id=legacy_user.id,
                    name=f"Legacy passkey {index}",
                    credential_id=bytes_to_base64url(
                        index.to_bytes(2, "big") + (b"x" * 766)
                    ),
                    credential_public_key="cHVibGljLWtleQ",
                )
                for index in range(64)
            ]
        )
        await db.commit()

    async def fixed_config(_db: AsyncSession) -> PasskeyConfig:
        return _passkey_config()

    monkeypatch.setattr(route_passkey_service, "_load_config", fixed_config)
    response = await client.post(
        "/api/v1/auth/passkeys/authenticate/options",
        json={"username": "unknown-template-probe"},
    )

    assert response.status_code == 200
    descriptors = response.json()["options"]["allowCredentials"]
    assert descriptors == []
    assert sum(len(base64url_to_bytes(item["id"])) for item in descriptors) <= 16_384


@pytest.mark.asyncio
async def test_untrusted_forwarded_for_cannot_fan_out_passkey_source_quota(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_load_count = 0

    async def fixed_config(_db: AsyncSession) -> PasskeyConfig:
        nonlocal config_load_count
        config_load_count += 1
        return _passkey_config()

    monkeypatch.setattr(route_passkey_service, "_load_config", fixed_config)
    monkeypatch.setattr(
        route_passkey_service,
        "_challenge_request_policy",
        PasskeyChallengeRequestPolicy(
            global_outstanding_quota=10,
            per_source_outstanding_quota=1,
            global_rate_quota=100,
            per_source_rate_quota=100,
            rate_window_seconds=3600,
            retry_after_seconds=47,
        ),
    )

    first_response = await client.post(
        "/api/v1/auth/passkeys/authenticate/options",
        json={"username": "unknown-forwarded-one"},
        headers={"X-Forwarded-For": "198.51.100.10"},
    )
    second_response = await client.post(
        "/api/v1/auth/passkeys/authenticate/options",
        json={"username": "unknown-forwarded-two"},
        headers={"X-Forwarded-For": "203.0.113.20"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.headers["Retry-After"] == "47"
    assert second_response.json() == {
        "message": "Too many passkey sign-in attempts. Please try again later.",
        "fields": [],
    }
    assert config_load_count == 1


@pytest.mark.asyncio
async def test_passkey_options_rejects_unbounded_username_before_service_work(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def should_not_begin(*_args: Any, **_kwargs: Any) -> None:
        nonlocal called
        called = True
        raise AssertionError("oversized usernames must be rejected at validation")

    monkeypatch.setattr(
        route_passkey_service,
        "begin_authentication",
        should_not_begin,
    )

    response = await client.post(
        "/api/v1/auth/passkeys/authenticate/options",
        json={"username": "u" * 1025},
    )

    assert response.status_code == 422
    assert called is False


@pytest.mark.parametrize("chunked", [False, True])
@pytest.mark.asyncio
async def test_passkey_routes_reject_oversized_bodies_before_parsing(
    client: AsyncClient,
    chunked: bool,
) -> None:
    payload = (
        b'{"username":"body-limit-user","padding":"'
        + (b"x" * 300_000)
        + b'"}'
    )
    request_content: Any
    if chunked:
        async def chunks():
            yield payload[:100_000]
            yield payload[100_000:]

        request_content = chunks()
    else:
        request_content = payload

    response = await client.post(
        "/api/v1/auth/passkeys/authenticate/options",
        content=request_content,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json() == {
        "message": "Request body too large.",
        "fields": [],
    }
