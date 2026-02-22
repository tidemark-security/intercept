import pytest

from app.models.models import PasswordChangeRequest, UserAccountCreate
from app.services.security.password_hasher import Argon2Parameters, PasswordHasher


def test_hash_and_verify_round_trip() -> None:
    hasher = PasswordHasher()

    hashed = hasher.hash("CorrectHorseBatteryStaple!")

    assert isinstance(hashed, str)
    assert hasher.verify(hashed, "CorrectHorseBatteryStaple!") is True
    assert hasher.verify(hashed, "incorrect") is False


def test_needs_rehash_when_parameters_change() -> None:
    old_params = Argon2Parameters(time_cost=2, memory_cost=32 * 1024, parallelism=1)
    hasher_old = PasswordHasher(old_params)
    hashed = hasher_old.hash("AnotherSecret123!")

    new_params = Argon2Parameters(time_cost=4, memory_cost=64 * 1024, parallelism=2)
    hasher_new = PasswordHasher(new_params)

    assert hasher_new.needs_rehash(hashed) is True


@pytest.mark.parametrize("password", [123, None, b"bytes"])  # type: ignore[list-item]
def test_hash_rejects_non_string_inputs(password) -> None:  # type: ignore[no-untyped-def]
    hasher = PasswordHasher()

    with pytest.raises(TypeError):
        hasher.hash(password)  # type: ignore[arg-type]


def test_verify_raises_on_invalid_hash() -> None:
    hasher = PasswordHasher()

    with pytest.raises(ValueError):
        hasher.verify("not-a-real-hash", "secret")


def test_hash_contains_argon2id_prefix() -> None:
    hasher = PasswordHasher()

    hashed = hasher.hash("ValidTestPass123!")

    assert hashed.startswith("$argon2id$")


def test_user_account_create_enforces_password_policy() -> None:
    with pytest.raises(ValueError):
        UserAccountCreate(
            username="analyst",
            email="analyst@example.com",
            password="weakpass",
        )


def test_password_change_request_enforces_policy() -> None:
    with pytest.raises(ValueError):
        PasswordChangeRequest(current_password="old", new_password="short")