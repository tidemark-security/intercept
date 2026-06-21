from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi_pagination import Page
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.route_utils import create_human_id_decorator
from app.api.routes.admin_auth import require_admin_user, require_authenticated_user, require_non_auditor_user
from app.core.database import get_db
from app.models.enums import CaseTemplateStatus
from app.models.models import (
    CaseTemplateApplyRequest,
    CaseTemplateApplyResponse,
    CaseTemplateCreate,
    CaseTemplateRead,
    CaseTemplateUpdate,
    UserAccount,
)
from app.services.case_template_service import case_template_service
from app.services.case_template_validation import CaseTemplateValidationError


router = APIRouter(
    prefix="/case-templates",
    tags=["case-templates"],
    dependencies=[Depends(require_authenticated_user)],
)
handle_human_id = create_human_id_decorator("TPL-", "template_id")
handle_case_human_id = create_human_id_decorator("CAS-", "case_id")


@router.get("", response_model=Page[CaseTemplateRead])
async def list_case_templates(
    status: Optional[List[CaseTemplateStatus]] = Query(None, description="Template lifecycle statuses to include"),
    search: Optional[str] = Query(None, description="Search title, description, and Template Task text"),
    db: AsyncSession = Depends(get_db),
):
    return await case_template_service.list_templates(db, statuses=status, search=search)


@router.post("", response_model=CaseTemplateRead)
async def create_case_template(
    payload: CaseTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin_user),
):
    try:
        return await case_template_service.create_template(db, payload, current_user.username)
    except CaseTemplateValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{template_id}", response_model=CaseTemplateRead)
@handle_human_id()
async def get_case_template(
    template_id: int,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
):
    template = await case_template_service.get_template(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Case Template not found")
    return template


@router.put("/{template_id}", response_model=CaseTemplateRead)
@handle_human_id()
async def update_case_template(
    template_id: int,
    payload: CaseTemplateUpdate,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin_user),
):
    try:
        template = await case_template_service.update_template(db, template_id, payload, current_user.username)
        if template is None:
            raise HTTPException(status_code=404, detail="Case Template not found")
        return template
    except CaseTemplateValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{template_id}/publish", response_model=CaseTemplateRead)
@handle_human_id()
async def publish_case_template(
    template_id: int,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin_user),
):
    try:
        template = await case_template_service.update_template(
            db,
            template_id,
            CaseTemplateUpdate(status=CaseTemplateStatus.PUBLISHED),
            current_user.username,
        )
        if template is None:
            raise HTTPException(status_code=404, detail="Case Template not found")
        return template
    except CaseTemplateValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{template_id}/disable", response_model=CaseTemplateRead)
@handle_human_id()
async def disable_case_template(
    template_id: int,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin_user),
):
    try:
        template = await case_template_service.update_template(
            db,
            template_id,
            CaseTemplateUpdate(status=CaseTemplateStatus.DISABLED),
            current_user.username,
        )
        if template is None:
            raise HTTPException(status_code=404, detail="Case Template not found")
        return template
    except CaseTemplateValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{template_id}", response_model=CaseTemplateRead)
@handle_human_id()
async def delete_case_template(
    template_id: int,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin_user),
):
    template = await case_template_service.delete_template(db, template_id, current_user.username)
    if template is None:
        raise HTTPException(status_code=404, detail="Case Template not found")
    return template


@router.post("/cases/{case_id}/apply/{template_id}", response_model=CaseTemplateApplyResponse)
@handle_case_human_id()
@handle_human_id()
async def apply_case_template(
    case_id: int,
    template_id: int,
    payload: CaseTemplateApplyRequest,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user),
):
    try:
        return await case_template_service.apply_template(
            db,
            case_id=case_id,
            template_id=template_id,
            overrides=payload.task_overrides,
            user=current_user.username,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (CaseTemplateValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
