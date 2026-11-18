from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import CaseRunbook, CaseRunbookCreate, CaseRunbookUpdate
from app.services import case_runbook_service as case_runbook_module
from app.services.case_runbook_service import CaseRunbookService, parse_case_runbook_id
from app.services.case_runbook_validation import CaseRunbookValidationError


_TITLE_UNIQUE_INDEX = "uq_case_runbooks_active_title_normalized"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(12, 12), ("12", 12), ("RUN-0000012", 12), ("run-12", 12)],
)
def test_parse_case_runbook_id_uses_canonical_entity_parser(
    raw: int | str,
    expected: int,
) -> None:
    assert parse_case_runbook_id(raw) == expected


def test_parse_case_runbook_id_rejects_other_entity_prefixes() -> None:
    with pytest.raises(ValueError, match="Invalid Case Runbook ID"):
        parse_case_runbook_id("ALT-0000012")


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _TitleRaceSession:
    def __init__(self, *query_results: Any, constraint_name: str = _TITLE_UNIQUE_INDEX) -> None:
        self._query_results = iter(query_results)
        self._runbook = next((result for result in query_results if isinstance(result, CaseRunbook)), None)
        self._constraint_name = constraint_name
        self.written_title_normalized: str | None = None
        self.rollback_called = False

    async def execute(self, _statement: Any) -> _ScalarResult:
        return _ScalarResult(next(self._query_results))

    def add(self, instance: Any) -> None:
        if isinstance(instance, CaseRunbook):
            self._runbook = instance

    def _record_pending_title(self) -> None:
        if self._runbook is not None:
            self.written_title_normalized = self._runbook.title_normalized

    def _integrity_error(self) -> IntegrityError:
        return IntegrityError(
            "INSERT OR UPDATE case_runbooks",
            {},
            Exception(f'duplicate key violates unique constraint "{self._constraint_name}"'),
        )

    async def flush(self) -> None:
        self._record_pending_title()
        raise self._integrity_error()

    async def commit(self) -> None:
        self._record_pending_title()
        raise self._integrity_error()

    async def rollback(self) -> None:
        self.rollback_called = True


class _AuditService:
    async def log_event(self, **_kwargs: Any) -> None:
        pass


class _SuccessfulRunbookSession:
    def __init__(self) -> None:
        self.runbook: CaseRunbook | None = None
        self.committed = False
        self.refresh_called = False

    async def execute(self, _statement: Any) -> _ScalarResult:
        return _ScalarResult(None)

    def add(self, instance: Any) -> None:
        if isinstance(instance, CaseRunbook):
            self.runbook = instance

    async def flush(self) -> None:
        if self.runbook is not None and self.runbook.id is None:
            self.runbook.id = 17

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _instance: Any) -> None:
        self.refresh_called = True
        raise AssertionError("response hydration must not run after commit")


def test_case_runbook_model_declares_active_normalized_title_unique_index() -> None:
    index = next(
        index
        for index in CaseRunbook.__table__.indexes
        if index.name == _TITLE_UNIQUE_INDEX
    )

    assert index.unique is True
    assert str(index.dialect_options["postgresql"]["where"]) == (
        "status != 'DELETED' AND title_normalized IS NOT NULL"
    )


@pytest.mark.asyncio
async def test_create_runbook_returns_precommit_response_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CaseRunbookService()
    db = _SuccessfulRunbookSession()
    monkeypatch.setattr(case_runbook_module, "get_audit_service", lambda _db: _AuditService())

    result = await service.create_runbook(
        cast(AsyncSession, db),
        CaseRunbookCreate(title="Investigation"),
        "analyst",
    )

    assert result.id == 17
    assert result.title == "Investigation"
    assert db.committed is True
    assert db.refresh_called is False


@pytest.mark.asyncio
async def test_create_runbook_translates_concurrent_title_conflict() -> None:
    service = CaseRunbookService()
    db = _TitleRaceSession(None)

    with pytest.raises(CaseRunbookValidationError, match="titles must be unique"):
        await service.create_runbook(
            cast(AsyncSession, db),
            CaseRunbookCreate(title=" DLP   Response "),
            "analyst",
        )

    assert db.written_title_normalized == "dlp response"
    assert db.rollback_called is True


@pytest.mark.asyncio
async def test_update_runbook_translates_concurrent_title_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CaseRunbookService()
    runbook = CaseRunbook(
        id=1,
        title="Original",
        title_normalized="original",
        created_by="author",
        updated_by="author",
    )
    db = _TitleRaceSession(runbook, None)
    monkeypatch.setattr(case_runbook_module, "get_audit_service", lambda _db: _AuditService())

    with pytest.raises(CaseRunbookValidationError, match="titles must be unique"):
        await service.update_runbook(
            cast(AsyncSession, db),
            1,
            CaseRunbookUpdate(title="Concurrent title"),
            "analyst",
        )

    assert db.written_title_normalized == "concurrent title"
    assert db.rollback_called is True


@pytest.mark.asyncio
async def test_create_runbook_does_not_mask_unrelated_integrity_errors() -> None:
    service = CaseRunbookService()
    db = _TitleRaceSession(None, constraint_name="uq_unrelated")

    with pytest.raises(IntegrityError):
        await service.create_runbook(
            cast(AsyncSession, db),
            CaseRunbookCreate(title="DLP Response"),
            "analyst",
        )

    assert db.rollback_called is True
