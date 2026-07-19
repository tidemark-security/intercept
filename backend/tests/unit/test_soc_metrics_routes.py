from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import soc_metrics


ADMIN_USER = SimpleNamespace(role=SimpleNamespace(value="ADMIN"))

ENDPOINT_CASES = [
    pytest.param(
        soc_metrics.get_metrics,
        "get_soc_metrics",
        {
            "type": "soc",
            "priority": None,
            "source": None,
            "analyst": None,
            "group_by": "source",
            "current_user": ADMIN_USER,
        },
        id="multiplex",
    ),
    pytest.param(
        soc_metrics.get_soc_metrics,
        "get_soc_metrics",
        {"priority": None, "source": None, "current_user": ADMIN_USER},
        id="soc",
    ),
    pytest.param(
        soc_metrics.get_analyst_metrics,
        "get_analyst_metrics",
        {"analyst": None, "admin_user": ADMIN_USER},
        id="analyst",
    ),
    pytest.param(
        soc_metrics.get_alert_metrics,
        "get_alert_metrics",
        {
            "source": None,
            "priority": None,
            "group_by": "source",
            "current_user": ADMIN_USER,
        },
        id="alert",
    ),
    pytest.param(
        soc_metrics.get_ai_triage_metrics,
        "get_ai_triage_metrics",
        {"current_user": ADMIN_USER},
        id="ai-triage",
    ),
    pytest.param(
        soc_metrics.get_ai_chat_metrics,
        "get_ai_chat_metrics",
        {"current_user": ADMIN_USER},
        id="ai-chat",
    ),
    pytest.param(
        soc_metrics.get_ai_triage_recommendations_drilldown,
        "get_triage_recommendations_drilldown",
        {
            "disposition": None,
            "rejection_category": None,
            "status": None,
            "limit": 50,
            "offset": 0,
            "admin_user": ADMIN_USER,
        },
        id="triage-drilldown",
    ),
    pytest.param(
        soc_metrics.get_ai_chat_feedback_drilldown,
        "get_chat_feedback_drilldown",
        {
            "feedback": None,
            "limit": 50,
            "offset": 0,
            "admin_user": ADMIN_USER,
        },
        id="chat-drilldown",
    ),
]

TIME_RANGE_CASES = [
    pytest.param(None, None, None, None, id="defaults"),
    pytest.param(
        "2025-12-01T00:00:00Z",
        None,
        datetime(2025, 12, 1, tzinfo=timezone.utc),
        None,
        id="start-only-z",
    ),
    pytest.param(
        None,
        "2025-12-08T05:30:00+05:30",
        None,
        datetime(
            2025,
            12,
            8,
            5,
            30,
            tzinfo=timezone(timedelta(hours=5, minutes=30)),
        ),
        id="end-only-offset",
    ),
    pytest.param(
        "2025-12-01T00:00:00",
        "2025-12-08T00:00:00Z",
        datetime(2025, 12, 1, tzinfo=timezone.utc),
        datetime(2025, 12, 8, tzinfo=timezone.utc),
        id="both-naive-and-z",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("endpoint", "service_method", "extra_kwargs"), ENDPOINT_CASES)
@pytest.mark.parametrize(
    ("start", "end", "expected_start", "expected_end"),
    TIME_RANGE_CASES,
)
async def test_metrics_endpoints_preserve_time_range_parsing(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: Any,
    service_method: str,
    extra_kwargs: dict[str, Any],
    start: str | None,
    end: str | None,
    expected_start: datetime | None,
    expected_end: datetime | None,
) -> None:
    expected_response = object()
    service_call = AsyncMock(return_value=expected_response)
    monkeypatch.setattr(soc_metrics.metrics_service, service_method, service_call)

    response = await endpoint(
        start=start,
        end=end,
        db=cast(AsyncSession, None),
        **extra_kwargs,
    )

    assert response is expected_response
    assert service_call.await_args.kwargs["start_time"] == expected_start
    assert service_call.await_args.kwargs["end_time"] == expected_end


@pytest.mark.parametrize(
    ("value", "param_name"),
    [("not-a-date", "start"), ("still-not-a-date", "end")],
)
def test_parse_datetime_preserves_exact_invalid_date_response(
    value: str,
    param_name: str,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        soc_metrics.parse_datetime(value, param_name)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == (
        f"Invalid {param_name} format. Use ISO8601 "
        f"(e.g., '2025-12-01T00:00:00Z'): Invalid isoformat string: '{value}'"
    )


def test_parse_datetime_does_not_misclassify_unexpected_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_unexpected(_value: str, *, parameter: str) -> None:
        raise ValueError(f"{parameter} parser defect")

    monkeypatch.setattr(
        soc_metrics,
        "parse_datetime_filter",
        raise_unexpected,
    )

    with pytest.raises(ValueError, match="start parser defect"):
        soc_metrics.parse_datetime("2025-12-01T00:00:00Z", "start")


@pytest.mark.asyncio
@pytest.mark.parametrize(("endpoint", "service_method", "extra_kwargs"), ENDPOINT_CASES)
async def test_metrics_endpoints_preserve_invalid_start_response(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: Any,
    service_method: str,
    extra_kwargs: dict[str, Any],
) -> None:
    service_call = AsyncMock()
    monkeypatch.setattr(soc_metrics.metrics_service, service_method, service_call)

    with pytest.raises(HTTPException) as exc_info:
        await endpoint(
            start="not-a-date",
            end=None,
            db=cast(AsyncSession, None),
            **extra_kwargs,
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == (
        "Invalid start format. Use ISO8601 (e.g., '2025-12-01T00:00:00Z'): "
        "Invalid isoformat string: 'not-a-date'"
    )
    service_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_soc_shorthand_preserves_reversed_range_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_call = AsyncMock(return_value=object())
    monkeypatch.setattr(soc_metrics.metrics_service, "get_soc_metrics", service_call)

    await soc_metrics.get_soc_metrics(
        start="2025-12-08T00:00:00Z",
        end="2025-12-01T00:00:00Z",
        priority=None,
        source=None,
        db=cast(AsyncSession, None),
        current_user=ADMIN_USER,
    )

    assert service_call.await_args.kwargs["start_time"] == datetime(
        2025, 12, 8, tzinfo=timezone.utc
    )
    assert service_call.await_args.kwargs["end_time"] == datetime(
        2025, 12, 1, tzinfo=timezone.utc
    )
