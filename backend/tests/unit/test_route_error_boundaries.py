from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.routes import alerts, cases, context_entries, dashboard, langflow, tasks
from app.main import global_exception_handler
from app.models.enums import AlertStatus
from app.models.models import (
    AlertBulkActionRequest,
    CaseUpdate,
    LangFlowSessionCreate,
    TaskUpdate,
    TimelineGraphPatch,
)
from app.services.context_service import (
    ContextEntryNotFoundError,
    ContextSerializationError,
    _read_model,
)
from app.services.alert_service import (
    AlertRelatedEntityNotFoundError,
    AlertValidationError,
)
from app.services.case_service import CaseValidationError
from app.services.task_service import TaskValidationError
from app.services.timeline_graph_service import TimelineGraphValidationError
from app.models.models import ContextEntry, ContextEntryUpdate
from app.services.settings_service import SettingConfigurationError


@pytest.mark.asyncio
async def test_unexpected_route_error_uses_sanitized_global_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "database-password-that-must-not-leak"
    monkeypatch.setattr(
        dashboard.dashboard_service,
        "get_sidebar_badge_counts",
        AsyncMock(side_effect=RuntimeError(secret)),
    )

    with pytest.raises(RuntimeError, match=secret) as exc_info:
        await dashboard.get_sidebar_badge_counts(
            db=cast(AsyncSession, None),
            _current_user=SimpleNamespace(username="analyst"),
        )

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/dashboard/sidebar-badge-counts",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
            "scheme": "http",
        }
    )
    response = await global_exception_handler(request, exc_info.value)

    assert response.status_code == 500
    assert response.body == b'{"detail":"Internal server error"}'
    assert secret.encode() not in response.body


@pytest.mark.asyncio
async def test_deliberate_domain_error_mapping_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        alerts.alert_service,
        "bulk_action",
        AsyncMock(side_effect=AlertValidationError("unsupported bulk transition")),
    )
    payload = AlertBulkActionRequest(
        alert_ids=[1],
        action="update_status",
        status=AlertStatus.NEW,
    )

    with pytest.raises(HTTPException) as exc_info:
        await alerts.bulk_alert_action(
            bulk_request=payload,
            db=cast(AsyncSession, None),
            current_user=SimpleNamespace(username="analyst"),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "unsupported bulk transition"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route_module", "service", "method_name", "route_name", "error_type"),
    [
        (
            alerts,
            alerts.alert_service,
            "get_alerts",
            "get_alerts",
            AlertValidationError,
        ),
        (
            cases,
            cases.case_service,
            "get_cases",
            "get_cases",
            CaseValidationError,
        ),
        (
            tasks,
            tasks.task_service,
            "get_tasks",
            "get_tasks",
            TaskValidationError,
        ),
    ],
)
async def test_invalid_sort_field_is_a_client_error(
    monkeypatch: pytest.MonkeyPatch,
    route_module,
    service,
    method_name: str,
    route_name: str,
    error_type: type[ValueError],
) -> None:
    monkeypatch.setattr(
        service,
        method_name,
        AsyncMock(side_effect=error_type("Unsupported sort column")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await getattr(route_module, route_name)(db=cast(AsyncSession, None))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Unsupported sort column"


@pytest.mark.asyncio
async def test_task_relationship_validation_is_a_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks.task_service,
        "update_task",
        AsyncMock(side_effect=TaskValidationError("Case 99 not found")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await tasks.update_task(
            task_id=1,
            task_update=TaskUpdate(case_id=99),
            request=cast(Request, None),
            db=cast(AsyncSession, None),
            current_user=SimpleNamespace(username="analyst"),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Case 99 not found"


@pytest.mark.asyncio
async def test_case_closure_validation_is_a_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cases.case_service,
        "update_case",
        AsyncMock(side_effect=CaseValidationError("Invalid closure status")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await cases.update_case(
            case_id=1,
            request=cast(Request, None),
            case_update=CaseUpdate(),
            migration=False,
            db=cast(AsyncSession, None),
            current_user=SimpleNamespace(username="analyst"),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid closure status"


@pytest.mark.asyncio
async def test_alert_link_maps_only_typed_related_entity_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        alerts.alert_service,
        "link_alert_to_case",
        AsyncMock(side_effect=AlertRelatedEntityNotFoundError("Case 99 not found")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await alerts.link_alert_to_case(
            alert_id=1,
            case_id=99,
            request=cast(Request, None),
            db=cast(AsyncSession, None),
            current_user=SimpleNamespace(username="analyst"),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Case 99 not found"


@pytest.mark.asyncio
async def test_alert_link_does_not_mislabel_unexpected_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        alerts.alert_service,
        "link_alert_to_case",
        AsyncMock(side_effect=ValueError("internal defect")),
    )

    with pytest.raises(ValueError, match="internal defect"):
        await alerts.link_alert_to_case(
            alert_id=1,
            case_id=99,
            request=cast(Request, None),
            db=cast(AsyncSession, None),
            current_user=SimpleNamespace(username="analyst"),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route_module", "service", "method_name", "route_name"),
    [
        (alerts, alerts.alert_service, "get_alerts", "get_alerts"),
        (cases, cases.case_service, "get_cases", "get_cases"),
        (tasks, tasks.task_service, "get_tasks", "get_tasks"),
    ],
)
@pytest.mark.parametrize("error_type", [ValueError, RuntimeError])
async def test_entity_routes_do_not_mislabel_unexpected_service_errors(
    monkeypatch: pytest.MonkeyPatch,
    route_module,
    service,
    method_name: str,
    route_name: str,
    error_type: type[Exception],
) -> None:
    monkeypatch.setattr(
        service,
        method_name,
        AsyncMock(side_effect=error_type("internal defect")),
    )

    with pytest.raises(error_type, match="internal defect"):
        await getattr(route_module, route_name)(db=cast(AsyncSession, None))


@pytest.mark.asyncio
async def test_timeline_graph_route_maps_typed_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks.timeline_graph_service,
        "patch_graph",
        AsyncMock(side_effect=TimelineGraphValidationError("move_node requires position")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await tasks.patch_timeline_graph(
            task_id=1,
            request=cast(Request, None),
            patch=TimelineGraphPatch(base_revision=0),
            db=cast(AsyncSession, None),
            current_user=SimpleNamespace(username="analyst"),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "move_node requires position"


@pytest.mark.asyncio
async def test_timeline_graph_route_does_not_mislabel_unexpected_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks.timeline_graph_service,
        "patch_graph",
        AsyncMock(side_effect=ValueError("graph implementation defect")),
    )

    with pytest.raises(ValueError, match="graph implementation defect"):
        await tasks.patch_timeline_graph(
            task_id=1,
            request=cast(Request, None),
            patch=TimelineGraphPatch(base_revision=0),
            db=cast(AsyncSession, None),
            current_user=SimpleNamespace(username="analyst"),
        )


@pytest.mark.asyncio
async def test_context_not_found_uses_typed_route_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SimpleNamespace(
        update_entry=AsyncMock(
            side_effect=ContextEntryNotFoundError("Context entry not found")
        )
    )
    monkeypatch.setattr(context_entries, "ContextService", Mock(return_value=service))
    monkeypatch.setattr(context_entries, "build_audit_context", Mock(return_value=None))

    with pytest.raises(HTTPException) as exc_info:
        await context_entries.update_context_entry(
            entry_id=42,
            request=cast(Request, None),
            payload=ContextEntryUpdate(body="updated context"),
            db=cast(AsyncSession, None),
            current_user=SimpleNamespace(username="analyst"),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Context entry not found"


@pytest.mark.asyncio
async def test_context_route_does_not_mislabel_unexpected_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SimpleNamespace(
        update_entry=AsyncMock(side_effect=ValueError("serialization defect"))
    )
    monkeypatch.setattr(context_entries, "ContextService", Mock(return_value=service))
    monkeypatch.setattr(context_entries, "build_audit_context", Mock(return_value=None))

    with pytest.raises(ValueError, match="serialization defect"):
        await context_entries.update_context_entry(
            entry_id=42,
            request=cast(Request, None),
            payload=ContextEntryUpdate(body="updated context"),
            db=cast(AsyncSession, None),
            current_user=SimpleNamespace(username="analyst"),
        )


def test_unsaved_context_model_is_an_internal_serialization_error() -> None:
    with pytest.raises(ContextSerializationError):
        _read_model(ContextEntry(body="body", criteria=[], author="analyst"))


@pytest.mark.asyncio
async def test_langflow_session_maps_missing_flow_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        get_flow_id_for_context=AsyncMock(
            side_effect=SettingConfigurationError("No flow ID configured")
        )
    )
    monkeypatch.setattr(langflow, "SettingsService", Mock(return_value=settings))

    with pytest.raises(HTTPException) as exc_info:
        await langflow.create_session(
            session_create=LangFlowSessionCreate(),
            db=cast(AsyncSession, None),
            current_user=SimpleNamespace(id="user-id"),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "No flow ID configured"


@pytest.mark.asyncio
async def test_langflow_session_does_not_mislabel_unexpected_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        get_flow_id_for_context=AsyncMock(side_effect=ValueError("internal defect"))
    )
    monkeypatch.setattr(langflow, "SettingsService", Mock(return_value=settings))

    with pytest.raises(ValueError, match="internal defect"):
        await langflow.create_session(
            session_create=LangFlowSessionCreate(),
            db=cast(AsyncSession, None),
            current_user=SimpleNamespace(id="user-id"),
        )
