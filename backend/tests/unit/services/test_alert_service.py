from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AlertStatus
from app.models.models import (
    Alert,
    AlertBulkActionRequest,
    AlertCreate,
    AlertRead,
    AlertUpdate,
    Case,
)
from app.services import (
    alert_service as alert_service_module,
    settings_service as settings_service_module,
)
from app.services.alert_service import (
    AlertValidationError,
    _BulkActionContext,
    _status_change_description,
    alert_service,
)
from app.services.case_service import case_service


def _postgresql_sql(statement: object) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        pytest.param(AlertStatus.NEW, "Alert status changed to New", id="new"),
        pytest.param(
            AlertStatus.IN_PROGRESS,
            "Alert status changed to In Progress",
            id="in-progress",
        ),
        pytest.param(
            AlertStatus.ESCALATED,
            "Alert status changed to Escalated",
            id="escalated",
        ),
        pytest.param(
            AlertStatus.CLOSED_TP,
            "Alert closed as True Positive",
            id="closed-true-positive",
        ),
        pytest.param(
            AlertStatus.CLOSED_BP,
            "Alert closed as True Positive Benign",
            id="closed-benign-positive",
        ),
        pytest.param(
            AlertStatus.CLOSED_FP,
            "Alert closed as False Positive",
            id="closed-false-positive",
        ),
        pytest.param(
            AlertStatus.CLOSED_UNRESOLVED,
            "Alert closed as Unresolved",
            id="closed-unresolved",
        ),
        pytest.param(
            AlertStatus.CLOSED_DUPLICATE,
            "Alert closed as Duplicate",
            id="closed-duplicate",
        ),
    ],
)
def test_status_change_description_uses_status_specific_note(
    status: AlertStatus,
    expected: str,
) -> None:
    assert _status_change_description(status) == expected


def test_status_change_description_preserves_fallback() -> None:
    unknown_status = cast(AlertStatus, "CUSTOM_STATUS")

    assert _status_change_description(unknown_status) == "Alert status changed to CUSTOM_STATUS"


@pytest.mark.asyncio
async def test_invalid_alert_sort_raises_typed_validation_error() -> None:
    with pytest.raises(
        AlertValidationError,
        match="Unsupported alert sort column: secret_field",
    ):
        await alert_service.get_alerts(
            cast(AsyncSession, None),
            sort_by="secret_field",
        )


@pytest.mark.asyncio
async def test_alert_mutation_loaders_lock_and_refresh_rows() -> None:
    alert = Alert(id=7, title="Alert")
    single_result = SimpleNamespace(scalar_one_or_none=lambda: alert)
    bulk_result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [alert])
    )
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[single_result, bulk_result]),
    )

    assert await alert_service._get_alert_for_update(  # noqa: SLF001
        db,  # type: ignore[arg-type]
        7,
    ) is alert
    assert await alert_service._load_alerts_for_bulk_action(  # noqa: SLF001
        db,  # type: ignore[arg-type]
        [7],
    ) == [alert]

    single_statement = db.execute.await_args_list[0].args[0]
    bulk_statement = db.execute.await_args_list[1].args[0]
    assert "FOR UPDATE" in _postgresql_sql(single_statement)
    assert single_statement.get_execution_options()["populate_existing"] is True
    bulk_sql = _postgresql_sql(bulk_statement)
    assert "ORDER BY alerts.id" in bulk_sql
    assert "FOR UPDATE" in bulk_sql
    assert bulk_statement.get_execution_options()["populate_existing"] is True


@pytest.mark.asyncio
async def test_update_alert_allows_ordinary_changes_after_case_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    linked_alert = Alert(
        id=42,
        title="Original title",
        status=AlertStatus.ESCALATED,
        case_id=19,
    )
    get_alert_model = AsyncMock(return_value=linked_alert)
    get_alert = AsyncMock(return_value=linked_alert)
    emit_event = AsyncMock()
    db = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
        expunge_all=Mock(),
    )
    monkeypatch.setattr(alert_service, "_get_alert_for_update", get_alert_model)
    monkeypatch.setattr(alert_service, "get_alert", get_alert)
    monkeypatch.setattr(alert_service_module, "emit_event", emit_event)

    result = await alert_service.update_alert(
        db,  # type: ignore[arg-type]
        42,
        AlertUpdate(title="Updated while linked"),
    )

    assert result is linked_alert
    assert linked_alert.title == "Updated while linked"
    assert linked_alert.case_id == 19
    db.commit.assert_awaited_once_with()
    db.rollback.assert_not_awaited()
    emit_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_alert_returns_committed_model_after_response_read_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    committed_alert = Alert(id=42, title="Committed title")
    db = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
        expunge_all=Mock(),
    )
    monkeypatch.setattr(
        alert_service,
        "_get_alert_for_update",
        AsyncMock(return_value=committed_alert),
    )
    monkeypatch.setattr(
        alert_service,
        "get_alert",
        AsyncMock(side_effect=RuntimeError("response SELECT failed")),
    )
    monkeypatch.setattr(alert_service_module, "emit_event", AsyncMock())

    result = await alert_service.update_alert(
        db,  # type: ignore[arg-type]
        42,
        AlertUpdate(title="Committed title"),
    )

    assert result is committed_alert
    db.commit.assert_awaited_once_with()
    db.expunge_all.assert_called_once_with()
    db.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_create_alert_survives_enqueue_cleanup_then_response_reload_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenSettings:
        def __init__(self, _db: object) -> None:
            pass

        async def get(self, _key: str) -> object:
            raise RuntimeError("settings SELECT failed")

    def assign_id(alert: Alert) -> None:
        alert.id = 13

    db = SimpleNamespace(
        add=Mock(side_effect=assign_id),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        expunge_all=Mock(),
    )
    monkeypatch.setattr(settings_service_module, "SettingsService", BrokenSettings)
    monkeypatch.setattr(
        alert_service,
        "get_alert",
        AsyncMock(side_effect=RuntimeError("response SELECT failed")),
    )

    result = await alert_service.create_alert(
        db,  # type: ignore[arg-type]
        AlertCreate(title="Committed alert"),
    )

    assert result.id == 13
    assert AlertRead.model_validate(result).triage_recommendation is None
    db.commit.assert_awaited_once_with()
    assert db.expunge_all.call_count == 2
    assert db.rollback.await_count == 2


@pytest.mark.asyncio
async def test_bulk_action_uses_prebuilt_response_after_reload_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    committed_alert = Alert(id=7, title="Committed alert", tags=["reviewed"])
    request = AlertBulkActionRequest(
        alert_ids=[7],
        action="add_tags",
        tags=["reviewed"],
    )
    db = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
        expunge_all=Mock(),
    )
    monkeypatch.setattr(
        alert_service,
        "_load_alerts_for_bulk_action",
        AsyncMock(return_value=[committed_alert]),
    )
    monkeypatch.setattr(
        alert_service,
        "_prepare_bulk_action",
        AsyncMock(return_value=_BulkActionContext()),
    )
    monkeypatch.setattr(
        alert_service,
        "_apply_bulk_action_to_alerts",
        AsyncMock(),
    )
    monkeypatch.setattr(
        alert_service,
        "_build_bulk_action_response",
        AsyncMock(side_effect=RuntimeError("response SELECT failed")),
    )

    result = await alert_service.bulk_action(
        db,  # type: ignore[arg-type]
        request,
        performed_by="analyst",
    )

    assert result.updated_count == 1
    assert result.updated_alerts[0].id == 7
    db.commit.assert_awaited_once_with()
    db.expunge_all.assert_called_once_with()
    db.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_alert_case_link_locks_parent_before_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alert = Alert(id=7, title="Alert")
    case = Case(id=9, title="Case", created_by="analyst")
    events: list[str] = []

    async def precheck(_db: object, _alert_id: int) -> Alert:
        events.append("alert_exists")
        return alert

    async def lock_case(_db: object, _case_id: int) -> Case:
        events.append("case_lock")
        return case

    async def lock_alert(_db: object, _alert_id: int) -> Alert:
        events.append("alert_lock")
        return alert

    db = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
        expunge_all=Mock(),
    )
    monkeypatch.setattr(alert_service, "_get_alert_model", AsyncMock(side_effect=precheck))
    monkeypatch.setattr(
        case_service,
        "lock_case_for_update",
        AsyncMock(side_effect=lock_case),
    )
    monkeypatch.setattr(
        alert_service,
        "_get_alert_for_update",
        AsyncMock(side_effect=lock_alert),
    )
    monkeypatch.setattr(alert_service, "get_alert", AsyncMock(return_value=alert))
    monkeypatch.setattr(
        alert_service_module.triage_recommendation_service,
        "auto_reject_if_pending",
        AsyncMock(),
    )

    result = await alert_service.link_alert_to_case(
        db,  # type: ignore[arg-type]
        7,
        9,
        linked_by="analyst",
    )

    assert result is alert
    assert events == ["alert_exists", "case_lock", "alert_lock"]
