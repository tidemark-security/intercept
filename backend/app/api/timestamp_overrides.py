from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

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


def _convert_timeline_item_or_400(
    payload: dict[str, Any],
    converter: Callable[[dict[str, Any]], Any],
) -> Any:
    """Translate only payload-conversion failures at the HTTP seam."""
    try:
        return converter(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def prepare_timeline_item_create(
    payload: dict[str, Any],
    *,
    converter: Callable[[dict[str, Any]], Any],
    current_user: UserAccount,
    migration: bool,
) -> tuple[Any, Optional[datetime]]:
    """Convert a timeline payload and apply the shared creation timestamp policy."""
    has_created_at = "created_at" in payload
    item = _convert_timeline_item_or_400(payload, converter)
    created_at_override = normalize_created_at_override(
        current_user=current_user,
        migration=migration,
        created_at=item.created_at if has_created_at else None,
    )
    if created_at_override is not None:
        item.created_at = created_at_override
    return item, created_at_override


def prepare_timeline_item_update(
    payload: dict[str, Any],
    *,
    converter: Callable[[dict[str, Any]], Any],
) -> Any:
    """Reject immutable fields and convert a timeline update payload."""
    reject_created_at_update(payload)
    return _convert_timeline_item_or_400(payload, converter)
