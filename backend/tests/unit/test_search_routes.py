from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import search as search_routes
from app.models.search_schemas import EntityType


def _assert_search_error(
    exc: HTTPException,
    *,
    error: str,
    code: str,
) -> None:
    assert exc.status_code == 400
    assert exc.detail == {"error": error, "code": code, "detail": None}


def test_invalid_date_preserves_search_error_shape() -> None:
    with pytest.raises(HTTPException) as exc_info:
        search_routes._parse_iso_date("not-a-date", "start_date")

    _assert_search_error(
        exc_info.value,
        error=(
            "Invalid date format for start_date. Use ISO8601 format "
            "(e.g., 2024-12-01T00:00:00Z)"
        ),
        code="INVALID_DATE_RANGE",
    )


def test_date_parser_does_not_mask_unexpected_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_unexpected(_value: str, *, parameter: str) -> None:
        raise ValueError(f"{parameter} parser defect")

    monkeypatch.setattr(
        search_routes,
        "parse_datetime_filter",
        raise_unexpected,
    )

    with pytest.raises(ValueError, match="start_date parser defect"):
        search_routes._parse_iso_date("2025-01-01T00:00:00Z", "start_date")


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        (
            "2025-01-02T00:00:00Z",
            "2025-01-01T00:00:00Z",
            "Start date must be before end date",
        ),
        (
            "2024-01-01T00:00:00Z",
            "2025-01-01T00:00:01Z",
            "Date range cannot exceed 1 year",
        ),
    ],
)
def test_invalid_date_range_preserves_search_error_shape(
    start: str,
    end: str,
    message: str,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        search_routes._parse_date_range(start, end)

    _assert_search_error(
        exc_info.value,
        error=message,
        code="INVALID_DATE_RANGE",
    )


@pytest.mark.asyncio
async def test_route_passes_normalization_and_range_defaults_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_response = object()
    paginated_search = AsyncMock(return_value=expected_response)
    monkeypatch.setattr(
        search_routes.search_service,
        "paginated_search",
        paginated_search,
    )
    end = datetime(2020, 1, 31, tzinfo=timezone.utc)

    response = await search_routes.unified_search(
        q="  credential   theft  ",
        entity_types=[EntityType.ALERT],
        skip=0,
        limit=20,
        start_date=None,
        end_date=end.isoformat(),
        tags=["  VIP  ", "vip"],
        db=cast(AsyncSession, None),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response is expected_response
    assert paginated_search.await_args.kwargs == {
        "db": None,
        "query": "credential theft",
        "entity_types": [EntityType.ALERT],
        "skip": 0,
        "limit": 20,
        "start_date": end - timedelta(days=30),
        "end_date": end,
        "tags": ["  VIP  ", "vip"],
        "user_id": "user-1",
    }


@pytest.mark.asyncio
async def test_route_does_not_mask_unexpected_search_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        search_routes.search_service,
        "paginated_search",
        AsyncMock(side_effect=RuntimeError("database defect")),
    )

    with pytest.raises(RuntimeError, match="database defect"):
        await search_routes.unified_search(
            q="credential theft",
            entity_types=None,
            skip=0,
            limit=20,
            start_date="2025-01-01T00:00:00Z",
            end_date="2025-01-02T00:00:00Z",
            tags=None,
            db=cast(AsyncSession, None),
            current_user=SimpleNamespace(id="user-1"),
        )
