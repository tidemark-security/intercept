"""Administrative collector operations and authenticated validation callbacks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin_auth import require_admin_user, require_authenticated_user
from app.core.database import get_db
from app.models.enums import AccountType
from app.models.models import CollectorEvent, CollectorEventRevision, CollectorFinding, CollectorRun, UserAccount
from app.services.collectors.models import (
    CollectorRunEnqueueResponse,
    CollectorRunRequest,
    CollectorRunTrigger,
    ValidationResult,
)
from app.services.collectors.registry import collector_registry
from app.services.collectors.security import CollectorSecurityError
from app.services.collectors.service import collector_service

admin_router = APIRouter(
    prefix="/admin/collectors",
    tags=["admin", "collectors"],
    dependencies=[Depends(require_admin_user)],
)
callback_router = APIRouter(
    prefix="/collectors",
    tags=["collectors"],
    dependencies=[Depends(require_authenticated_user)],
)


def _provider_or_404(provider_id: str):
    provider = collector_registry.get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collector provider not found")
    return provider


def _safe_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, CollectorSecurityError):
        status_code = (
            status.HTTP_409_CONFLICT
            if exc.code.value == "STALE_REVISION"
            else status.HTTP_403_FORBIDDEN
            if exc.code.value in {"AUTHENTICATION_FAILED", "AUTHORIZATION_FAILED"}
            else status.HTTP_400_BAD_REQUEST
        )
        return HTTPException(
            status_code=status_code,
            detail={"code": exc.code.value, "message": exc.summary},
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "CONFIGURATION_INVALID", "message": "Collector request could not be completed"},
    )


@admin_router.get("")
async def list_collectors(db: AsyncSession = Depends(get_db)):
    return await collector_service.provider_statuses(db)


@admin_router.get("/{provider_id}")
async def get_collector(provider_id: str, db: AsyncSession = Depends(get_db)):
    _provider_or_404(provider_id)
    statuses = await collector_service.provider_statuses(db)
    return next(item for item in statuses if item.provider_id == provider_id)


@admin_router.post("/{provider_id}/test")
async def test_collector(
    provider_id: str,
    stream_key: str = Query(default="default", min_length=1, max_length=255),
    db: AsyncSession = Depends(get_db),
):
    _provider_or_404(provider_id)
    return await collector_service.test_provider(db, provider_id, stream_key)


@admin_router.post("/{provider_id}/run", response_model=CollectorRunEnqueueResponse)
async def run_collector(
    provider_id: str,
    request: CollectorRunRequest,
    db: AsyncSession = Depends(get_db),
) -> CollectorRunEnqueueResponse:
    _provider_or_404(provider_id)
    try:
        if request.dry_run:
            counts = await collector_service.poll(
                db,
                provider_id=provider_id,
                stream_key=request.stream_key,
                dry_run=True,
                max_pages=request.max_pages,
                since=request.since,
            )
            return CollectorRunEnqueueResponse(
                enqueued=False,
                dry_run=True,
                counts=counts,
            )

        trigger = (
            CollectorRunTrigger.BACKFILL
            if request.mode == "backfill"
            else CollectorRunTrigger.MANUAL
        )
        run, task_id = await collector_service.enqueue_run(
            db,
            provider_id=provider_id,
            stream_key=request.stream_key,
            trigger=trigger,
            max_pages=request.max_pages,
            since=request.since,
        )
        return CollectorRunEnqueueResponse(
            enqueued=True,
            task_id=task_id,
            run_id=run.id,
        )
    except Exception as exc:
        raise _safe_http_error(exc) from exc


@admin_router.get("/{provider_id}/runs")
async def list_collector_runs(
    provider_id: str,
    stream_key: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    _provider_or_404(provider_id)
    statement = select(CollectorRun).where(CollectorRun.provider_id == provider_id)
    if stream_key:
        statement = statement.where(CollectorRun.stream_key == stream_key)
    result = await db.execute(
        statement.order_by(CollectorRun.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all())


@admin_router.get("/{provider_id}/events")
async def list_collector_events(
    provider_id: str,
    event_status: str | None = Query(default=None, alias="status", max_length=40),
    stream_key: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    _provider_or_404(provider_id)
    statement = select(CollectorEvent).where(CollectorEvent.provider_id == provider_id)
    if event_status:
        statement = statement.where(CollectorEvent.status == event_status)
    if stream_key:
        statement = statement.where(CollectorEvent.stream_key == stream_key)
    result = await db.execute(
        statement.order_by(CollectorEvent.updated_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all())


@admin_router.get("/{provider_id}/events/{event_id}/findings")
async def list_collector_findings(
    provider_id: str,
    event_id: int,
    db: AsyncSession = Depends(get_db),
):
    _provider_or_404(provider_id)
    event = await db.get(CollectorEvent, event_id)
    if event is None or event.provider_id != provider_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collector event not found")
    result = await db.execute(
        select(CollectorFinding)
        .where(CollectorFinding.collector_event_id == event_id)
        .order_by(CollectorFinding.created_at)
    )
    return list(result.scalars().all())


@admin_router.get("/{provider_id}/events/{event_id}/revisions")
async def list_collector_event_revisions(
    provider_id: str,
    event_id: int,
    db: AsyncSession = Depends(get_db),
):
    _provider_or_404(provider_id)
    event = await db.get(CollectorEvent, event_id)
    if event is None or event.provider_id != provider_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collector event not found")
    result = await db.execute(
        select(CollectorEventRevision)
        .where(CollectorEventRevision.collector_event_id == event_id)
        .order_by(CollectorEventRevision.revision.desc())
    )
    return list(result.scalars().all())


@admin_router.post("/{provider_id}/events/{event_id}/retry")
async def retry_collector_event(
    provider_id: str,
    event_id: int,
    db: AsyncSession = Depends(get_db),
):
    _provider_or_404(provider_id)
    event = await db.get(CollectorEvent, event_id)
    if event is None or event.provider_id != provider_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collector event not found")
    try:
        task_id = await collector_service.retry_event(db, event)
        return {"enqueued": True, "task_id": task_id, "revision": event.revision}
    except Exception as exc:
        raise _safe_http_error(exc) from exc


@admin_router.post("/{provider_id}/events/{event_id}/validation")
async def record_admin_validation(
    provider_id: str,
    event_id: int,
    result: ValidationResult,
    db: AsyncSession = Depends(get_db),
):
    _provider_or_404(provider_id)
    try:
        await collector_service.record_validation(
            db,
            provider_id=provider_id,
            event_id=event_id,
            validator_identity=result.validator_id,
            result=result,
        )
        return {"recorded": True, "revision": result.event_revision}
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collector event not found") from exc
        raise _safe_http_error(exc) from exc
    except Exception as exc:
        raise _safe_http_error(exc) from exc


@callback_router.post("/{provider_id}/events/{event_id}/validation")
async def record_nhi_validation(
    provider_id: str,
    event_id: int,
    result: ValidationResult,
    current_user: UserAccount = Depends(require_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    _provider_or_404(provider_id)
    if current_user.account_type is not AccountType.NHI:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "AUTHORIZATION_FAILED", "message": "An NHI API key is required"},
        )
    try:
        await collector_service.record_validation(
            db,
            provider_id=provider_id,
            event_id=event_id,
            validator_identity=current_user.username,
            result=result,
        )
        return {"recorded": True, "revision": result.event_revision}
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collector event not found") from exc
        raise _safe_http_error(exc) from exc
    except Exception as exc:
        raise _safe_http_error(exc) from exc
