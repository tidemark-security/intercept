from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import threading
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.authorization_lock import acquire_authorization_lock
from app.models.enums import AccountType, SettingType, UserRole, UserStatus
from app.models.models import (
    AppSetting,
    AuthSession,
    PasswordHashWorkLease,
    PasswordLoginAttempt,
    PasswordLoginFailureCounter,
    PasskeyCredential,
    UserAccount,
)
from app.services.audit_service import AuditContext
from app.services.auth_service import AuthService, InvalidCredentialsError, auth_service
from app.services.password_login_request_service import PasswordLoginRequestPolicy
from app.services.password_hash_work_service import (
    PasswordHashWorkCapacityError,
    PasswordHashWorkPolicy,
    password_hash_work_service,
)
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("username", "u" * 1025),
        ("password", "p" * 1025),
    ],
)
@pytest.mark.asyncio
async def test_password_login_rejects_oversized_credentials_before_authentication(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    from app.api.routes import auth as auth_routes

    called = False

    async def should_not_authenticate(*_args: Any, **_kwargs: Any) -> None:
        nonlocal called
        called = True
        raise AssertionError("oversized credentials must fail request validation")

    monkeypatch.setattr(auth_routes.auth_service, "login", should_not_authenticate)
    payload = {"username": "bounded.user", "password": "Password123!"}
    payload[field] = value

    response = await client.post("/api/v1/auth/login", json=payload)

    assert response.status_code == 422
    assert called is False


@pytest.mark.parametrize("chunked", [False, True])
@pytest.mark.asyncio
async def test_password_login_rejects_oversized_body_before_parsing(
    client: AsyncClient,
    chunked: bool,
) -> None:
    payload = (
        b'{"username":"bounded.user","password":"Password123!","padding":"'
        + (b"x" * 9_000)
        + b'"}'
    )
    request_content: bytes | AsyncIterator[bytes]
    if chunked:

        async def chunks() -> AsyncIterator[bytes]:
            yield payload[:4_000]
            yield payload[4_000:]

        request_content = chunks()
    else:
        request_content = payload

    response = await client.post(
        "/api/v1/auth/login",
        content=request_content,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json() == {
        "message": "Request body too large.",
        "fields": [],
    }


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/password/change",
        "/api/v1/auth/password/change/",
        "/api/v1/auth/reset-password",
        "/api/v1/auth/reset-password/",
    ],
)
@pytest.mark.parametrize("chunked", [False, True])
@pytest.mark.asyncio
async def test_password_mutations_reject_oversized_body_before_parsing(
    client: AsyncClient,
    path: str,
    chunked: bool,
) -> None:
    payload = b'{"padding":"' + (b"x" * 9_000) + b'"}'
    request_content: bytes | AsyncIterator[bytes]
    if chunked:

        async def chunks() -> AsyncIterator[bytes]:
            yield payload[:4_000]
            yield payload[4_000:]

        request_content = chunks()
    else:
        request_content = payload

    response = await client.post(
        path,
        content=request_content,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json() == {
        "message": "Request body too large.",
        "fields": [],
    }


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/auth/password/change",
            {"currentPassword": "x" * 1025, "newPassword": "NewPassword123!"},
        ),
        (
            "/api/v1/auth/password/change",
            {"currentPassword": "OldPassword123!", "newPassword": "x" * 1025},
        ),
        (
            "/api/v1/auth/reset-password",
            {"token": "x" * 513, "newPassword": "NewPassword123!"},
        ),
        (
            "/api/v1/auth/reset-password",
            {"token": "reset-token", "newPassword": "x" * 1025},
        ),
    ],
)
@pytest.mark.asyncio
async def test_password_mutations_reject_oversized_fields(
    client: AsyncClient,
    path: str,
    payload: dict[str, str],
) -> None:
    response = await client.post(path, json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rotating_usernames_cannot_bypass_source_login_limit(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import auth as auth_routes

    authentication_attempts: list[str] = []

    async def reject_login(_db: Any, **kwargs: Any) -> None:
        authentication_attempts.append(kwargs["username"])
        raise InvalidCredentialsError()

    async def strict_source_limit(_db: Any) -> tuple[int, int]:
        return 2, 60

    monkeypatch.setattr(auth_routes.auth_service, "login", reject_login)
    monkeypatch.setattr(
        auth_routes.auth_service,
        "_get_rate_limit_settings",
        strict_source_limit,
    )

    responses = [
        await client.post(
            "/api/v1/auth/login",
            json={
                "username": f"rotated-user-{index}",
                "password": "Password123!",
            },
        )
        for index in range(3)
    ]

    assert [response.status_code for response in responses] == [401, 401, 429]
    assert authentication_attempts == ["rotated-user-0", "rotated-user-1"]
    assert responses[-1].headers["Retry-After"]
    assert responses[-1].json() == {
        "message": "Too many login attempts. Please try again later.",
        "fields": [],
    }


class _ConstructionOnlyHasher:
    def hash(self, value: str) -> str:
        return f"hashed:{value}"


@pytest.mark.asyncio
async def test_concurrent_password_login_global_quota_is_atomic_and_hides_source(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AuthService(
        password_hasher=_ConstructionOnlyHasher(),  # type: ignore[arg-type]
        login_request_policy=PasswordLoginRequestPolicy(
            global_rate_quota=1,
            global_rate_window_seconds=3600,
            retry_after_seconds=60,
        ),
    )
    both_ready = asyncio.Event()
    arrivals = 0

    async def generous_source_limit(_db: AsyncSession) -> tuple[int, int]:
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            both_ready.set()
        await both_ready.wait()
        return 100, 3600

    monkeypatch.setattr(
        service,
        "_get_rate_limit_settings",
        generous_source_limit,
    )

    async def admit(source_address: str) -> tuple[bool, int | None]:
        async with session_maker() as db:
            return await service.check_rate_limit(
                db,
                source_address=source_address,
            )

    results = await asyncio.wait_for(
        asyncio.gather(
            admit("198.51.100.10"),
            admit("203.0.113.20"),
        ),
        timeout=5,
    )

    assert sorted(allowed for allowed, _retry_after in results) == [
        False,
        True,
    ]
    async with session_maker() as db:
        attempts = list(await db.scalars(select(PasswordLoginAttempt)))
    assert len(attempts) == 1
    assert len(attempts[0].source_fingerprint) == 64
    assert attempts[0].source_fingerprint not in {
        "198.51.100.10",
        "203.0.113.20",
    }


@pytest.mark.asyncio
async def test_password_verification_capacity_is_cross_worker_durable(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    policy = PasswordHashWorkPolicy(
        max_concurrent=1,
        lease_seconds=900,
        retry_after_seconds=30,
    )

    async with session_maker() as first_db:
        first_lease_id = await password_hash_work_service.reserve(
            first_db,
            work_kind="first_worker",
            policy=policy,
        )
        await first_db.commit()

    async with session_maker() as second_db:
        with pytest.raises(PasswordHashWorkCapacityError) as exc_info:
            await password_hash_work_service.reserve(
                second_db,
                work_kind="second_worker",
                policy=policy,
            )
        await second_db.commit()
    assert exc_info.value.retry_after_seconds == 30

    async with session_maker() as read_db:
        leases = list(await read_db.scalars(select(PasswordHashWorkLease)))
    assert len(leases) == 1
    assert leases[0].id == first_lease_id

    async with session_maker() as release_db:
        await password_hash_work_service.release(
            release_db,
            lease_id=first_lease_id,
        )

    async with session_maker() as third_db:
        third_lease_id = await password_hash_work_service.reserve(
            third_db,
            work_kind="third_worker",
            policy=policy,
        )
        await third_db.commit()
    async with session_maker() as release_db:
        await password_hash_work_service.release(
            release_db,
            lease_id=third_lease_id,
        )


class _ConcurrentLockoutVerifier:
    def __init__(self) -> None:
        self.correct_started = threading.Event()
        self.release_correct = threading.Event()
        self.invalid_barrier = threading.Barrier(3)

    def hash(self, _value: str) -> str:
        return "dummy-password-hash"

    def verify(self, _password_hash: str, password: str) -> bool:
        if password == "CorrectPassword123!":
            self.correct_started.set()
            assert self.release_correct.wait(timeout=5)
            return True
        self.invalid_barrier.wait(timeout=5)
        return False


@pytest.mark.asyncio
async def test_concurrent_failures_cannot_be_skipped_by_correct_password(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = analyst_user_factory(username="concurrent-lockout-account")
    async with session_maker() as db:
        db.add_all(
            [
                user,
                AppSetting(
                    key="auth.login.lockout_threshold",
                    value="3",
                    value_type=SettingType.NUMBER,
                    is_secret=False,
                    category="login",
                ),
            ]
        )
        await db.commit()

    verifier = _ConcurrentLockoutVerifier()
    monkeypatch.setattr(auth_service, "_password_hasher", verifier)

    correct = asyncio.create_task(
        client.post(
            "/api/v1/auth/login",
            json={
                "username": user.username,
                "password": "CorrectPassword123!",
            },
        )
    )
    assert await asyncio.to_thread(verifier.correct_started.wait, 3)

    invalid = [
        asyncio.create_task(
            client.post(
                "/api/v1/auth/login",
                json={
                    "username": user.username,
                    "password": f"InvalidPassword{index}!!",
                },
            )
        )
        for index in range(3)
    ]
    try:
        invalid_responses = await asyncio.wait_for(
            asyncio.gather(*invalid),
            timeout=8,
        )
    finally:
        verifier.release_correct.set()

    correct_response = await asyncio.wait_for(correct, timeout=5)
    assert [response.status_code for response in invalid_responses] == [401, 401, 401]
    assert correct_response.status_code == 401

    async with session_maker() as db:
        persisted = await db.get(UserAccount, user.id)
        sessions = list(
            await db.scalars(
                select(AuthSession).where(AuthSession.user_id == user.id)
            )
        )
    assert persisted is not None
    assert persisted.failed_login_attempts == 3
    assert persisted.status is UserStatus.LOCKED
    assert sessions == []


@pytest.mark.parametrize("initial_status", [UserStatus.LOCKED, UserStatus.DISABLED])
@pytest.mark.asyncio
async def test_rejected_password_guesses_cannot_defeat_administrative_recovery(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory: Any,
    analyst_user_factory: Any,
    initial_status: UserStatus,
) -> None:
    admin = admin_user_factory(username=f"failure-recovery-admin-{initial_status.value.lower()}")
    user = analyst_user_factory(
        username=f"failure-recovery-user-{initial_status.value.lower()}"
    )
    user.status = initial_status
    user.lockout_expires_at = None
    async with session_maker() as db:
        db.add_all([admin, user])
        await db.commit()

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert admin_login.status_code == 200

    for index in range(5):
        rejected = await client.post(
            "/api/v1/auth/login",
            json={
                "username": user.username,
                "password": f"AttackerGuess{index}Password!",
            },
        )
        assert rejected.status_code == 401

    recovery = await client.patch(
        f"/api/v1/admin/auth/users/{user.id}/status",
        json={"status": UserStatus.ACTIVE.value},
        cookies={
            "intercept_session": admin_login.cookies.get("intercept_session")
        },
    )
    assert recovery.status_code == 204

    accepted = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert accepted.status_code == 200

    async with session_maker() as db:
        persisted = await db.get(UserAccount, user.id)
        pending = list(
            await db.scalars(
                select(PasswordLoginFailureCounter).where(
                    PasswordLoginFailureCounter.user_id == user.id
                )
            )
        )
    assert persisted is not None
    assert persisted.status is UserStatus.ACTIVE
    assert persisted.failed_login_attempts == 0
    assert pending == []


@pytest.mark.asyncio
async def test_policy_rejected_guesses_do_not_preseed_later_password_lockout(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory: Any,
    analyst_user_factory: Any,
) -> None:
    admin = admin_user_factory(username="failure-policy-admin")
    user = analyst_user_factory(username="failure-policy-user")
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "failure-policy-user-subject"
    async with session_maker() as db:
        db.add_all(
            [
                admin,
                user,
                AppSetting(
                    key="oidc.enabled",
                    value="true",
                    value_type=SettingType.BOOLEAN,
                    is_secret=False,
                    category="oidc",
                ),
                AppSetting(
                    key="oidc.sso_bypass_users",
                    value="[]",
                    value_type=SettingType.JSON,
                    is_secret=False,
                    category="oidc",
                ),
            ]
        )
        await db.commit()

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert admin_login.status_code == 200

    for index in range(5):
        rejected = await client.post(
            "/api/v1/auth/login",
            json={
                "username": user.username,
                "password": f"PolicyRejectedGuess{index}!",
            },
        )
        assert rejected.status_code == 401

    enable_password = await client.put(
        "/api/v1/admin/settings/oidc.sso_bypass_users",
        json={"value": f'["{user.username}"]'},
        cookies={
            "intercept_session": admin_login.cookies.get("intercept_session")
        },
    )
    assert enable_password.status_code == 200

    accepted = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert accepted.status_code == 200

    async with session_maker() as db:
        persisted = await db.get(UserAccount, user.id)
        pending = list(
            await db.scalars(
                select(PasswordLoginFailureCounter).where(
                    PasswordLoginFailureCounter.user_id == user.id
                )
            )
        )
    assert persisted is not None
    assert persisted.status is UserStatus.ACTIVE
    assert persisted.failed_login_attempts == 0
    assert pending == []


class _RecordingPasswordVerifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def hash(self, _value: str) -> str:
        return "dummy-password-hash"

    def verify(self, password_hash: str, password: str) -> bool:
        self.calls.append((password_hash, password))
        return False


class _ConcurrentPasswordVerifier:
    def __init__(self) -> None:
        self.first_started = threading.Event()
        self.second_started = threading.Event()
        self.release_first = threading.Event()
        self._call_lock = threading.Lock()
        self._calls = 0

    def hash(self, _value: str) -> str:
        return "dummy-password-hash"

    def verify(self, _password_hash: str, _password: str) -> bool:
        with self._call_lock:
            call_number = self._calls
            self._calls += 1
        if call_number == 0:
            self.first_started.set()
            assert self.release_first.wait(timeout=3)
        else:
            self.second_started.set()
        return False


class _HeldSuccessfulPasswordVerifier:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def hash(self, _value: str) -> str:
        return "dummy-password-hash"

    def verify(self, _password_hash: str, _password: str) -> bool:
        self.started.set()
        assert self.release.wait(timeout=3)
        return True


@pytest.mark.asyncio
async def test_same_account_password_verification_does_not_hold_database_locks(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory: Any,
) -> None:
    """A slow hostile guess must not queue later Argon2 work for that account."""
    user = analyst_user_factory(username="parallel-password-verification")
    async with session_maker() as setup_db:
        setup_db.add(user)
        await setup_db.commit()

    verifier = _ConcurrentPasswordVerifier()
    service = AuthService(password_hasher=verifier)  # type: ignore[arg-type]

    async def reject_login(password: str) -> None:
        async with session_maker() as login_db:
            with pytest.raises(InvalidCredentialsError):
                await service.login(
                    login_db,
                    username=user.username,
                    password=password,
                    metadata=AuditContext(),
                )
            await login_db.rollback()

    first = asyncio.create_task(reject_login("FirstAttackerGuess123!"))
    assert await asyncio.to_thread(verifier.first_started.wait, 3)
    second = asyncio.create_task(reject_login("SecondAttackerGuess123!"))

    try:
        second_started_while_first_was_held = await asyncio.to_thread(
            verifier.second_started.wait,
            1,
        )
    finally:
        verifier.release_first.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=3)

    assert second_started_while_first_was_held is True


@pytest.mark.asyncio
async def test_invalid_password_does_not_wait_for_busy_account_gate(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory: Any,
) -> None:
    """A guess must fail promptly while an administrative writer owns the gate."""
    user = analyst_user_factory(username="busy-password-account-gate")
    async with session_maker() as setup_db:
        setup_db.add(user)
        await setup_db.commit()

    verifier = _RecordingPasswordVerifier()
    service = AuthService(password_hasher=verifier)  # type: ignore[arg-type]

    async with session_maker() as gate_db:
        await acquire_authorization_lock(
            gate_db,
            user_id=user.id,
            shared=False,
        )

        async def reject_login() -> None:
            async with session_maker() as login_db:
                with pytest.raises(InvalidCredentialsError):
                    await service.login(
                        login_db,
                        username=user.username,
                        password="AttackerGuess123!",
                        metadata=AuditContext(),
                    )
                await login_db.rollback()

        await asyncio.wait_for(reject_login(), timeout=1)

    assert len(verifier.calls) == 1


@pytest.mark.asyncio
async def test_password_rotated_during_verification_cannot_issue_session(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory: Any,
) -> None:
    user = analyst_user_factory(username="password-rotation-race")
    async with session_maker() as setup_db:
        setup_db.add(user)
        await setup_db.commit()

    verifier = _HeldSuccessfulPasswordVerifier()
    service = AuthService(password_hasher=verifier)  # type: ignore[arg-type]

    async def attempt_login() -> Exception | None:
        async with session_maker() as login_db:
            try:
                await service.login(
                    login_db,
                    username=user.username,
                    password="PreviouslyValidPassword123!",
                    metadata=AuditContext(),
                )
            except Exception as exc:  # asserted below after releasing the verifier
                await login_db.rollback()
                return exc
            return None

    async def rotate_password() -> None:
        async with session_maker() as update_db:
            stored_user = await update_db.get(UserAccount, user.id)
            assert stored_user is not None
            stored_user.password_hash = "rotated-password-hash"
            await update_db.commit()

    login_task = asyncio.create_task(attempt_login())
    assert await asyncio.to_thread(verifier.started.wait, 3)

    rotation_completed_during_verification = False
    try:
        await asyncio.wait_for(rotate_password(), timeout=1)
        rotation_completed_during_verification = True
    except TimeoutError:
        pass
    finally:
        verifier.release.set()

    outcome = await asyncio.wait_for(login_task, timeout=3)
    assert rotation_completed_during_verification is True
    assert isinstance(outcome, InvalidCredentialsError)

    async with session_maker() as read_db:
        sessions = list(
            await read_db.scalars(
                select(AuthSession).where(AuthSession.user_id == user.id)
            )
        )
    assert sessions == []


@pytest.mark.parametrize(
    "posture",
    ["unknown", "nhi", "disabled", "locked", "oidc_only", "passkey"],
)
@pytest.mark.asyncio
async def test_rejected_password_login_postures_each_perform_one_verification(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    username = f"timing-{posture}"
    records: list[Any] = []
    if posture == "nhi":
        user = UserAccount(
            username=username,
            account_type=AccountType.NHI,
            email=None,
            password_hash=None,
            role=UserRole.ANALYST,
            status=UserStatus.ACTIVE,
        )
        records.append(user)
    elif posture != "unknown":
        user = analyst_user_factory(username=username)
        if posture == "disabled":
            user.status = UserStatus.DISABLED
        elif posture == "locked":
            user.status = UserStatus.LOCKED
            user.lockout_expires_at = None
        elif posture == "oidc_only":
            user.oidc_issuer = "https://issuer.example"
            user.oidc_subject = "timing-oidc-subject"
            records.append(
                AppSetting(
                    key="oidc.enabled",
                    value="false",
                    value_type=SettingType.BOOLEAN,
                    is_secret=False,
                    category="oidc",
                )
            )
        elif posture == "passkey":
            records.append(
                PasskeyCredential(
                    user_id=user.id,
                    name="Timing test passkey",
                    credential_id=f"credential-{posture}",
                    credential_public_key="public-key",
                )
            )
        records.append(user)

    if records:
        async with session_maker() as db:
            db.add_all(records)
            await db.commit()

    verifier = _RecordingPasswordVerifier()
    monkeypatch.setattr(auth_service, "_password_hasher", verifier)

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "AttackerGuess123!"},
    )

    assert response.status_code == 401
    assert len(verifier.calls) == 1
    assert verifier.calls[0][1] == "AttackerGuess123!"
