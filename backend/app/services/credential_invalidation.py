"""Durable account credential-invalidation cutoff checks."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Protocol


class AccountCredentialCutoff(Protocol):
    """Account shape required by credential cutoff checks."""

    credentials_invalidated_at: datetime | None


def credential_was_issued_after_cutoff(
    account: AccountCredentialCutoff,
    *,
    issued_at: datetime | int | float | None,
) -> bool:
    """Return whether a credential remains valid for an account cutoff.

    Accounts without a cutoff retain legacy credentials. Once a cutoff exists,
    a missing, malformed, or equal issuance marker fails closed.
    """

    cutoff = getattr(account, "credentials_invalidated_at", None)
    if cutoff is None:
        return True

    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    else:
        cutoff = cutoff.astimezone(timezone.utc)

    if isinstance(issued_at, datetime):
        issued = issued_at
        if issued.tzinfo is None:
            issued = issued.replace(tzinfo=timezone.utc)
        else:
            issued = issued.astimezone(timezone.utc)
    elif (
        isinstance(issued_at, (int, float))
        and not isinstance(issued_at, bool)
        and math.isfinite(float(issued_at))
    ):
        try:
            issued = datetime.fromtimestamp(float(issued_at), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return False
    else:
        return False

    return issued > cutoff


__all__ = ["AccountCredentialCutoff", "credential_was_issued_after_cutoff"]
