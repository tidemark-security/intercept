from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status

from app.models.enums import AccountType
from app.models.models import UserAccount


def normalize_created_at_override(
    *,
    current_user: UserAccount,
    migration: bool,
    created_at: Optional[datetime],
) -> Optional[datetime]:
    """Validate and normalize a migration-only created_at override."""
    if not migration:
        if created_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="created_at can only be supplied when migration=true",
            )
        return None

    if current_user.account_type != AccountType.NHI or not current_user.override_timestamps:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="migration timestamp overrides require an NHI account with Override timestamps enabled",
        )

    if created_at is None:
        return None

    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail="created_at must include timezone information",
        )

    return created_at.astimezone(timezone.utc)


def reject_created_at_update(payload: dict) -> None:
    if "created_at" in payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="created_at is immutable and cannot be updated",
        )
