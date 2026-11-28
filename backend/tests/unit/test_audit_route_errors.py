from typing import cast

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import audit as audit_routes
from app.services.date_filter_utils import DateFilterValidationError


class _FailingAuditService:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def get_audit_logs(self, **_kwargs):
        raise self._error


@pytest.mark.asyncio
async def test_audit_route_maps_invalid_date_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = DateFilterValidationError("Invalid audit log start_date format")
    monkeypatch.setattr(
        audit_routes,
        "AuditService",
        lambda _db: _FailingAuditService(error),
    )

    with pytest.raises(HTTPException) as exc_info:
        await audit_routes.get_audit_logs(db=cast(AsyncSession, object()))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == str(error)


@pytest.mark.asyncio
async def test_audit_route_does_not_misclassify_unexpected_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        audit_routes,
        "AuditService",
        lambda _db: _FailingAuditService(ValueError("audit defect")),
    )

    with pytest.raises(ValueError, match="audit defect"):
        await audit_routes.get_audit_logs(db=cast(AsyncSession, object()))
