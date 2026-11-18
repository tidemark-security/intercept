"""Shared parsing and UTC normalization for ISO-8601 timestamps."""

from __future__ import annotations

from datetime import datetime, timezone


class DateFilterValidationError(ValueError):
    """Raised when an API date-filter bound is not valid ISO-8601."""


def parse_utc_datetime(value: str | datetime) -> datetime:
    """Parse an ISO-8601 value and normalize naive/offset values to UTC."""
    if isinstance(value, datetime):
        parsed = value
    else:
        normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_optional_utc_datetime(value: object) -> datetime | None:
    """Return a normalized timestamp, or ``None`` for absent/invalid input."""
    if not isinstance(value, (str, datetime)):
        return None

    try:
        return parse_utc_datetime(value)
    except ValueError:
        return None


def parse_datetime_filter(
    value: str | None,
    *,
    parameter: str,
) -> datetime | None:
    """Parse an optional filter bound and reject malformed client input."""
    if not value:
        return None

    try:
        return parse_utc_datetime(value)
    except ValueError as exc:
        raise DateFilterValidationError(
            f"Invalid {parameter} format; expected an ISO-8601 timestamp"
        ) from exc
