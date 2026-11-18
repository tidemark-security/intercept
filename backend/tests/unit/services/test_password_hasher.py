import pytest

from app.models.models import PasswordChangeRequest
from app.services.security import password_hasher as password_hasher_module
from app.services.security.password_hasher import Argon2Parameters, PasswordHasher


def test_hash_and_verify_round_trip() -> None:
    hasher = PasswordHasher()

    hashed = hasher.hash("CorrectHorseBatteryStaple!")

    assert isinstance(hashed, str)
    assert hasher.verify(hashed, "CorrectHorseBatteryStaple!") is True
    assert hasher.verify(hashed, "incorrect") is False


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


def test_configured_hasher_reads_all_canonical_argon2_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = {
        "auth.argon2.time_cost": 3,
        "auth.argon2.memory_cost_kib": 24_000,
        "auth.argon2.parallelism": 2,
        "auth.argon2.hash_len": 40,
        "auth.argon2.salt_len": 20,
        "auth.argon2.encoding": "utf-8",
    }
    monkeypatch.setattr(
        "app.core.settings_registry.get_local",
        configured.__getitem__,
    )

    hasher = PasswordHasher.from_local_settings()

    assert hasher.parameters == Argon2Parameters(
        time_cost=3,
        memory_cost=24_000,
        parallelism=2,
        hash_len=40,
        salt_len=20,
        encoding="utf-8",
    )


def test_argon2_builder_forwards_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class StubArgon2PasswordHasher:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        password_hasher_module,
        "Argon2PasswordHasher",
        StubArgon2PasswordHasher,
    )

    Argon2Parameters(encoding="latin-1").build_hasher()

    assert captured["encoding"] == "latin-1"


def test_password_change_request_enforces_policy() -> None:
    with pytest.raises(ValueError):
        PasswordChangeRequest(current_password="old", new_password="short")
