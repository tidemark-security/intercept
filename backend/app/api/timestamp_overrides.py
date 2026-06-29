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
    return normalize_timestamp_override(
        current_user=current_user,
        migration=migration,
        value=created_at,
        field_name="created_at",
        supplied=created_at is not None,
        allow_null=False,
    )


def normalize_timestamp_override(
    *,
    current_user: UserAccount,
    migration: bool,
    value: Optional[datetime],
    field_name: str,
    supplied: bool,
    allow_null: bool = False,
) -> Optional[datetime]:
    """Validate and normalize a migration-only timestamp override."""
    if not migration:
        if supplied:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name} can only be supplied when migration=true",
            )
        return None

    if current_user.account_type != AccountType.NHI or not current_user.override_timestamps:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="migration timestamp overrides require an NHI account with Override timestamps enabled",
        )

    if value is None:
        if supplied and allow_null:
            return None
        return None

    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} must include timezone information",
        )

    return value.astimezone(timezone.utc)


def reject_created_at_update(payload: dict) -> None:
    if "created_at" in payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="created_at is immutable and cannot be updated",
        )
