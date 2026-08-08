from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AlertStatus
from app.models.models import (
    Alert,
    Case,
    CaseAlertClosureUpdate,
    CaseLinkedAlertResolutionRequest,
    CaseUpdate,
)
from app.services import case_service as case_service_module
from app.services.case_service import CaseValidationError, case_service


def _postgresql_sql(statement: object) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_invalid_case_sort_raises_typed_validation_error() -> None:
    with pytest.raises(
        CaseValidationError,
        match="Unsupported case sort column: secret_field",
    ):
        await case_service.get_cases(
            cast(AsyncSession, None),
            sort_by="secret_field",
        )


@pytest.mark.asyncio
async def test_get_case_minimal_does_not_hide_database_errors() -> None:
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        await case_service.get_case_minimal(db, 42)


@pytest.mark.asyncio
async def test_case_mutation_loaders_lock_and_refresh_rows() -> None:
    case = Case(id=9, title="Case", created_by="analyst")
    task_result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [])
    )
    alert_result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [])
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda: case),
                task_result,
                alert_result,
            ]
        )
    )

    assert await case_service.lock_case_for_update(
        db,  # type: ignore[arg-type]
        9,
    ) is case
    assert await case_service._load_linked_items_for_update(  # noqa: SLF001
        db,  # type: ignore[arg-type]
        9,
    ) == ([], [])

    statements = [call.args[0] for call in db.execute.await_args_list]
    for statement in statements:
        sql = _postgresql_sql(statement)
        assert "FOR UPDATE" in sql
        assert statement.get_execution_options()["populate_existing"] is True
    assert "ORDER BY tasks.id" in _postgresql_sql(statements[1])
    assert "ORDER BY alerts.id" in _postgresql_sql(statements[2])


@pytest.mark.asyncio
async def test_update_case_returns_committed_model_after_response_read_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    committed_case = Case(id=9, title="Committed case", created_by="analyst")
    db = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
        expunge_all=Mock(),
    )
    monkeypatch.setattr(
        case_service,
        "lock_case_for_update",
        AsyncMock(return_value=committed_case),
    )
    monkeypatch.setattr(case_service, "_create_audit_log", AsyncMock())
    monkeypatch.setattr(
        case_service,
        "get_case",
        AsyncMock(side_effect=RuntimeError("response SELECT failed")),
    )
    monkeypatch.setattr(case_service_module, "emit_event", AsyncMock())

    result = await case_service.update_case(
        db,  # type: ignore[arg-type]
        9,
        CaseUpdate(title="Committed case"),
        updated_by="analyst",
    )

    assert result is committed_case
    db.commit.assert_awaited_once_with()
    db.expunge_all.assert_called_once_with()
    db.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_linked_alert_resolution_uses_prebuilt_response_after_reload_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    linked_alert = Alert(id=7, title="Linked alert", case_id=9)
    query_result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [linked_alert])
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=query_result),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        expunge_all=Mock(),
    )
    monkeypatch.setattr(
        case_service,
        "lock_case_for_update",
        AsyncMock(return_value=Case(id=9, title="Case", created_by="analyst")),
    )
    monkeypatch.setattr(
        case_service_module.triage_recommendation_service,
        "auto_reject_if_pending",
        AsyncMock(),
    )
    monkeypatch.setattr(case_service, "_audit_alert_resolution", AsyncMock())
    monkeypatch.setattr(case_service_module, "emit_event", AsyncMock())
    monkeypatch.setattr(
        case_service,
        "_load_linked_alert_resolution_response",
        AsyncMock(side_effect=RuntimeError("response SELECT failed")),
    )

    result = await case_service.resolve_linked_alerts(
        db,  # type: ignore[arg-type]
        9,
        CaseLinkedAlertResolutionRequest(
            alert_updates=[
                CaseAlertClosureUpdate(
                    alert_id=7,
                    status=AlertStatus.CLOSED_FP,
                )
            ]
        ),
        resolved_by="analyst",
    )

    assert result is not None
    assert result.updated_count == 1
    assert result.updated_alerts[0].status == AlertStatus.CLOSED_FP
    db.commit.assert_awaited_once_with()
    db.expunge_all.assert_called_once_with()
    db.rollback.assert_awaited_once_with()
