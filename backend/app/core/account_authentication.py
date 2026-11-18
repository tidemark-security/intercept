from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.enums import UserStatus

if TYPE_CHECKING:
    from app.models.models import UserAccount


def non_password_authentication_allowed(user: UserAccount) -> bool:
    """Return whether a non-password factor may authenticate ``user``.

    A lock with no expiry is an administrator-controlled account lock and
    applies to every authentication factor. A lock with an expiry is the
    password brute-force throttle and must not disable independent factors.
    Password authentication enforces and clears its own temporary lock.
    """
    return user.status == UserStatus.ACTIVE or (
        user.status == UserStatus.LOCKED
        and getattr(user, "lockout_expires_at", None) is not None
    )
