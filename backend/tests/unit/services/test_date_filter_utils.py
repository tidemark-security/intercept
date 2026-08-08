from datetime import datetime, timezone

import pytest

from app.services.date_filter_utils import (
    DateFilterValidationError,
    parse_datetime_filter,
    parse_optional_utc_datetime,
    parse_utc_datetime,
)


def test_parse_datetime_filter_normalizes_supported_iso_forms_to_utc() -> None:
    assert parse_datetime_filter(
        "2026-01-02T03:04:05Z",
        parameter="start_date",
    ) == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert parse_datetime_filter(
        "2026-01-02T04:04:05+01:00",
        parameter="start_date",
    ) == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert parse_datetime_filter(
        "2026-01-02T03:04:05",
        parameter="start_date",
    ) == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def test_parse_datetime_filter_allows_absent_and_rejects_invalid_values() -> None:
    assert parse_datetime_filter(None, parameter="end_date") is None
    with pytest.raises(
        DateFilterValidationError,
        match="Invalid end_date format; expected an ISO-8601 timestamp",
    ):
        parse_datetime_filter(
            "not-a-date",
            parameter="end_date",
        )


def test_parse_utc_datetime_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        parse_utc_datetime("not-a-date")


@pytest.mark.parametrize("value", [None, "", "not-a-date", 123])
def test_parse_optional_utc_datetime_returns_none_for_unusable_values(value: object) -> None:
    assert parse_optional_utc_datetime(value) is None


def test_parse_optional_utc_datetime_normalizes_datetime_values() -> None:
    assert parse_optional_utc_datetime(datetime(2026, 1, 2, 4, tzinfo=timezone.utc)) == datetime(
        2026,
        1,
        2,
        4,
        tzinfo=timezone.utc,
    )
