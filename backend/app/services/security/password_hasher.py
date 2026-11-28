from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError
from argon2.low_level import Type


@dataclass(slots=True)
class Argon2Parameters:
    """Container for Argon2id hashing parameters.

    Values default to recommendations captured in the authentication research
    document. These can be overridden with environment-specific settings via
    the settings registry.
    """

    time_cost: int = 2
    memory_cost: int = 19_456  # kibibytes (~19 MiB) per OWASP guidance
    parallelism: int = 1
    hash_len: int = 32
    salt_len: int = 16
    encoding: str = "utf-8"

    def build_hasher(self) -> Argon2PasswordHasher:
        return Argon2PasswordHasher(
            time_cost=self.time_cost,
            memory_cost=self.memory_cost,
            parallelism=self.parallelism,
            hash_len=self.hash_len,
            salt_len=self.salt_len,
            encoding=self.encoding,
            type=Type.ID,
        )


class PasswordHasher:
    """Thin wrapper around argon2-cffi to centralise password hashing logic."""

    def __init__(self, params: Optional[Argon2Parameters] = None) -> None:
        self._params = params or Argon2Parameters()
        self._hasher = self._params.build_hasher()

    @classmethod
    def from_local_settings(cls) -> "PasswordHasher":
        """Build a hasher from the canonical local-only Argon2 settings."""
        from app.core.settings_registry import get_local

        return cls(
            Argon2Parameters(
                time_cost=get_local("auth.argon2.time_cost"),
                memory_cost=get_local("auth.argon2.memory_cost_kib"),
                parallelism=get_local("auth.argon2.parallelism"),
                hash_len=get_local("auth.argon2.hash_len"),
                salt_len=get_local("auth.argon2.salt_len"),
                encoding=get_local("auth.argon2.encoding"),
            )
        )

    @property
    def parameters(self) -> Argon2Parameters:
        return self._params

    def hash(self, password: str) -> str:
        """Return an Argon2id hash for the supplied password."""
        if not isinstance(password, str):
            raise TypeError("password must be a string")

        password = password.strip()
        if not password:
            raise ValueError("password cannot be blank")

        return self._hasher.hash(password)

    def verify(self, hashed_password: str, password: str) -> bool:
        """Verify `password` against `hashed_password`.

        Returns ``True`` when the password is correct, ``False`` on mismatch.
        Raises ``ValueError`` if the stored hash is invalid/corrupted.
        """

        if not isinstance(hashed_password, str):
            raise TypeError("hashed_password must be a string")
        if not isinstance(password, str):
            raise TypeError("password must be a string")

        try:
            return self._hasher.verify(hashed_password, password)
        except VerifyMismatchError:
            return False
        except (InvalidHash, VerificationError) as exc:  # pragma: no cover - defensive
            raise ValueError("stored password hash is invalid") from exc
