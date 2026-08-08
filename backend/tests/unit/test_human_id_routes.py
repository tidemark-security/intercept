from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request, status
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import alerts, case_runbooks, cases, tasks, triage_recommendations
from app.api.routes.admin_auth import (
    require_admin_user,
    require_authenticated_user,
    require_non_auditor_user,
)
from app.core.database import get_db
from app.models.enums import UserRole
from app.models.models import UserAccount


@pytest.mark.parametrize(
    ("router", "path_param"),
    [
        (alerts.router, "alert_id"),
        (tasks.router, "task_id"),
        (cases.router, "case_id"),
        (case_runbooks.router, "runbook_id"),
        (case_runbooks.router, "case_id"),
        (triage_recommendations.router, "alert_id"),
    ],
)
def test_all_human_id_routes_accept_numeric_or_human_ids_and_receive_http_requests(
    router: Any,
    path_param: str,
) -> None:
    routes = [
        route
        for route in router.routes
        if isinstance(route, APIRoute) and f"{{{path_param}}}" in route.path
    ]
    assert routes

    for route in routes:
        parameters = inspect.signature(route.endpoint).parameters
        assert parameters[path_param].annotation == (int | str), route.path
        assert any(
            parameter.annotation is Request for parameter in parameters.values()
        ), route.path


@pytest.fixture
def human_id_app() -> FastAPI:
    app = FastAPI()
    for router in (
        alerts.router,
        tasks.router,
        cases.router,
        case_runbooks.router,
        triage_recommendations.router,
    ):
        app.include_router(router, prefix="/api/v1")

    async def override_get_db() -> AsyncSession:
        return cast(AsyncSession, None)

    async def override_current_user() -> UserAccount:
        return cast(
            UserAccount,
            SimpleNamespace(username="route-test-user", role=UserRole.ADMIN),
        )

    app.dependency_overrides[get_db] = override_get_db
    for dependency in (
        require_authenticated_user,
        require_admin_user,
        require_non_auditor_user,
    ):
        app.dependency_overrides[dependency] = override_current_user
    return app


def test_openapi_accepts_numeric_or_human_path_ids_and_returns_integer_entity_ids(
    human_id_app: FastAPI,
) -> None:
    schema = human_id_app.openapi()
    alert_id_parameter = next(
        parameter
        for parameter in schema["paths"]["/api/v1/alerts/{alert_id}"]["get"]["parameters"]
        if parameter["name"] == "alert_id"
    )

    assert alert_id_parameter["schema"]["anyOf"] == [
        {"type": "integer"},
        {"type": "string"},
    ]
    for response_schema in ("AlertRead", "CaseRead", "TaskRead", "CaseRunbookRead"):
        id_schema = schema["components"]["schemas"][response_schema]["properties"]["id"]
        assert id_schema["type"] == "integer"


async def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
) -> Response:
    request_kwargs = {"json": json} if json is not None else {}
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        return await client.request(method, path, **request_kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "expected_location"),
    [
        ("/api/v1/alerts/ALT-0000042", "/api/v1/alerts/42"),
        ("/api/v1/cases/CAS-0000042", "/api/v1/cases/42"),
        ("/api/v1/tasks/TSK-0000042", "/api/v1/tasks/42"),
    ],
)
async def test_entity_human_ids_redirect_to_numeric_paths(
    human_id_app: FastAPI,
    path: str,
    expected_location: str,
) -> None:
    response = await _request(human_id_app, "GET", path)

    assert response.status_code == status.HTTP_308_PERMANENT_REDIRECT
    assert response.headers["location"] == expected_location


@pytest.mark.asyncio
async def test_human_id_redirect_preserves_query_string(human_id_app: FastAPI) -> None:
    response = await _request(
        human_id_app,
        "GET",
        "/api/v1/alerts/ALT-0000042?include_linked_timelines=true&source=console",
    )

    assert response.status_code == status.HTTP_308_PERMANENT_REDIRECT
    assert response.headers["location"] == (
        "/api/v1/alerts/42?include_linked_timelines=true&source=console"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload", "expected_location"),
    [
        (
            "POST",
            "/api/v1/alerts/ALT-0000042/timeline/attachments/upload-url",
            {"filename": "evidence.txt", "file_size": 8, "mime_type": "text/plain"},
            "/api/v1/alerts/42/timeline/attachments/upload-url",
        ),
        (
            "PATCH",
            "/api/v1/alerts/ALT-0000042/timeline/items/item-1/status",
            {"status": "COMPLETE"},
            "/api/v1/alerts/42/timeline/items/item-1/status",
        ),
        (
            "GET",
            "/api/v1/alerts/ALT-0000042/timeline/items/item-1/download-url?download=true",
            None,
            "/api/v1/alerts/42/timeline/items/item-1/download-url?download=true",
        ),
        (
            "POST",
            "/api/v1/cases/CAS-0000042/timeline/attachments/upload-url",
            {"filename": "evidence.txt", "file_size": 8, "mime_type": "text/plain"},
            "/api/v1/cases/42/timeline/attachments/upload-url",
        ),
        (
            "PATCH",
            "/api/v1/cases/CAS-0000042/timeline/items/item-1/status",
            {"status": "COMPLETE"},
            "/api/v1/cases/42/timeline/items/item-1/status",
        ),
        (
            "GET",
            "/api/v1/cases/CAS-0000042/timeline/items/item-1/download-url?download=true",
            None,
            "/api/v1/cases/42/timeline/items/item-1/download-url?download=true",
        ),
        (
            "GET",
            "/api/v1/tasks/TSK-0000042/timeline/items/item-1/download-url?download=true",
            None,
            "/api/v1/tasks/42/timeline/items/item-1/download-url?download=true",
        ),
    ],
)
async def test_attachment_routes_accept_human_ids(
    human_id_app: FastAPI,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    expected_location: str,
) -> None:
    response = await _request(human_id_app, method, path, json=payload)

    assert response.status_code == status.HTTP_308_PERMANENT_REDIRECT
    assert response.headers["location"] == expected_location


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload", "expected_location"),
    [
        (
            "GET",
            "/api/v1/alerts/ALT-0000042/triage-recommendation",
            None,
            "/api/v1/alerts/42/triage-recommendation",
        ),
        (
            "POST",
            "/api/v1/alerts/ALT-0000042/triage-recommendation/enqueue",
            None,
            "/api/v1/alerts/42/triage-recommendation/enqueue",
        ),
        (
            "POST",
            "/api/v1/alerts/ALT-0000042/triage-recommendation/accept",
            {},
            "/api/v1/alerts/42/triage-recommendation/accept",
        ),
        (
            "POST",
            "/api/v1/alerts/ALT-0000042/triage-recommendation/reject",
            {"category": "MISSING_CONTEXT"},
            "/api/v1/alerts/42/triage-recommendation/reject",
        ),
    ],
)
async def test_triage_routes_resolve_the_http_request_by_type(
    human_id_app: FastAPI,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    expected_location: str,
) -> None:
    response = await _request(human_id_app, method, path, json=payload)

    assert response.status_code == status.HTTP_308_PERMANENT_REDIRECT
    assert response.headers["location"] == expected_location


@pytest.mark.asyncio
async def test_dual_human_ids_redirect_independently_then_reach_service_as_integers(
    human_id_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply_runbook = AsyncMock(
        return_value={
            "case_id": 42,
            "case_human_id": "CAS-0000042",
            "runbook_id": 7,
            "runbook_human_id": "RUN-0000007",
            "created_task_ids": [],
            "skipped_task_titles": [],
            "duplicate_warnings": [],
        }
    )
    monkeypatch.setattr(case_runbooks.case_runbook_service, "apply_runbook", apply_runbook)

    first_response = await _request(
        human_id_app,
        "POST",
        "/api/v1/case-runbooks/cases/CAS-0000042/apply/RUN-0000007",
        json={},
    )
    assert first_response.status_code == status.HTTP_308_PERMANENT_REDIRECT
    assert first_response.headers["location"] == (
        "/api/v1/case-runbooks/cases/42/apply/RUN-0000007"
    )

    second_response = await _request(
        human_id_app,
        "POST",
        first_response.headers["location"],
        json={},
    )
    assert second_response.status_code == status.HTTP_308_PERMANENT_REDIRECT
    assert second_response.headers["location"] == (
        "/api/v1/case-runbooks/cases/42/apply/7"
    )

    final_response = await _request(
        human_id_app,
        "POST",
        second_response.headers["location"],
        json={},
    )
    assert final_response.status_code == status.HTTP_200_OK
    apply_runbook.assert_awaited_once()
    assert apply_runbook.await_args.kwargs["case_id"] == 42
    assert apply_runbook.await_args.kwargs["runbook_id"] == 7
