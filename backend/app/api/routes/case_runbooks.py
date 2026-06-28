from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi_pagination import Page
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.route_utils import create_human_id_decorator
from app.api.routes.admin_auth import require_admin_user, require_authenticated_user, require_non_auditor_user
from app.core.database import get_db
from app.models.enums import CaseRunbookStatus
from app.models.models import (
    CaseRunbookApplyRequest,
    CaseRunbookApplyResponse,
    CaseRunbookCreate,
    CaseRunbookRead,
    CaseRunbookUpdate,
    UserAccount,
)
from app.services.case_runbook_service import case_runbook_service
from app.services.case_runbook_validation import CaseRunbookValidationError


router = APIRouter(
    prefix="/case-runbooks",
    tags=["case-runbooks"],
    dependencies=[Depends(require_authenticated_user)],
)
handle_human_id = create_human_id_decorator("RUN-", "runbook_id")
handle_case_human_id = create_human_id_decorator("CAS-", "case_id")


@router.get("", response_model=Page[CaseRunbookRead])
async def list_case_runbooks(
    status: Optional[List[CaseRunbookStatus]] = Query(None, description="Runbook lifecycle statuses to include"),
    search: Optional[str] = Query(None, description="Search title, description, and Runbook Task text"),
    db: AsyncSession = Depends(get_db),
):
    return await case_runbook_service.list_runbooks(db, statuses=status, search=search)


@router.post("", response_model=CaseRunbookRead)
async def create_case_runbook(
    payload: CaseRunbookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin_user),
):
    try:
        return await case_runbook_service.create_runbook(db, payload, current_user.username)
    except CaseRunbookValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{runbook_id}", response_model=CaseRunbookRead)
@handle_human_id()
async def get_case_runbook(
    runbook_id: int,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
):
    runbook = await case_runbook_service.get_runbook(db, runbook_id)
    if runbook is None:
        raise HTTPException(status_code=404, detail="Case Runbook not found")
    return runbook


@router.put("/{runbook_id}", response_model=CaseRunbookRead)
@handle_human_id()
async def update_case_runbook(
    runbook_id: int,
    payload: CaseRunbookUpdate,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin_user),
):
    try:
        runbook = await case_runbook_service.update_runbook(db, runbook_id, payload, current_user.username)
        if runbook is None:
            raise HTTPException(status_code=404, detail="Case Runbook not found")
        return runbook
    except CaseRunbookValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{runbook_id}/publish", response_model=CaseRunbookRead)
@handle_human_id()
async def publish_case_runbook(
    runbook_id: int,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin_user),
):
    try:
        runbook = await case_runbook_service.update_runbook(
            db,
            runbook_id,
            CaseRunbookUpdate(status=CaseRunbookStatus.PUBLISHED),
            current_user.username,
        )
        if runbook is None:
            raise HTTPException(status_code=404, detail="Case Runbook not found")
        return runbook
    except CaseRunbookValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{runbook_id}/disable", response_model=CaseRunbookRead)
@handle_human_id()
async def disable_case_runbook(
    runbook_id: int,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin_user),
):
    try:
        runbook = await case_runbook_service.update_runbook(
            db,
            runbook_id,
            CaseRunbookUpdate(status=CaseRunbookStatus.DISABLED),
            current_user.username,
        )
        if runbook is None:
            raise HTTPException(status_code=404, detail="Case Runbook not found")
        return runbook
    except CaseRunbookValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{runbook_id}", response_model=CaseRunbookRead)
@handle_human_id()
async def delete_case_runbook(
    runbook_id: int,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin_user),
):
    runbook = await case_runbook_service.delete_runbook(db, runbook_id, current_user.username)
    if runbook is None:
        raise HTTPException(status_code=404, detail="Case Runbook not found")
    return runbook


@router.post("/cases/{case_id}/apply/{runbook_id}", response_model=CaseRunbookApplyResponse)
@handle_case_human_id()
@handle_human_id()
async def apply_case_runbook(
    case_id: int,
    runbook_id: int,
    payload: CaseRunbookApplyRequest,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user),
):
    try:
        return await case_runbook_service.apply_runbook(
            db,
            case_id=case_id,
            runbook_id=runbook_id,
            overrides=payload.task_overrides,
            user=current_user.username,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (CaseRunbookValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
