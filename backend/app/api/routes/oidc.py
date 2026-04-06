from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin_auth import require_admin_user
from app.api.route_utils import (
    issue_authenticated_session_cookies,
    issue_oidc_browser_binding_cookie,
    read_oidc_browser_binding_cookie,
    revoke_oidc_browser_binding_cookie,
)
from app.core.database import get_db
from app.services.auth_service import RequestMetadata, auth_service
from app.services.audit_service import get_audit_service
from app.services.oidc_service import (
    OIDCAuthenticationError,
    OIDCConfigurationError,
    OIDCStateError,
    oidc_service,
)


router = APIRouter(prefix="/auth/oidc", tags=["authentication"])


class OIDCConfigResponse(BaseModel):
    enabled: bool
    providerName: str


class OIDCTestResponse(BaseModel):
    success: bool
    message: str


def _build_metadata(request: Request) -> RequestMetadata:
    client_host: Optional[str] = None
    if request.client:
        client_host = request.client.host
    return RequestMetadata(
        ip_address=client_host,
        user_agent=request.headers.get("user-agent"),
        correlation_id=request.headers.get("x-request-id"),
    )


def _frontend_error_redirect(redirect_to: str, message: str) -> RedirectResponse:
    separator = "&" if "?" in redirect_to else "?"
    encoded_message = quote(message)
    return RedirectResponse(
        url=f"{redirect_to}{separator}error=oidc_failed&message={encoded_message}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/config", response_model=OIDCConfigResponse)
async def get_oidc_config(db: AsyncSession = Depends(get_db)) -> OIDCConfigResponse:
    config = await oidc_service.get_public_config(db)
    return OIDCConfigResponse(**config)


@router.get("/login")
async def begin_oidc_login(
    request: Request,
    db: AsyncSession = Depends(get_db),
    next: str = Query(..., description="Absolute frontend URL to return to after authentication"),
):
    if not await oidc_service.is_safe_redirect_target(db, next):
        return _frontend_error_redirect(str(request.base_url).rstrip("/"), "Invalid OIDC return target")

    callback_url = str(request.url_for("finish_oidc_login"))
    try:
        authorization_url, expires_at, browser_binding_token = await oidc_service.begin_login(
            db,
            redirect_to=next,
            callback_url=callback_url,
        )
        await db.commit()
    except OIDCConfigurationError as exc:
        await db.rollback()
        return _frontend_error_redirect(next, str(exc))

    response = RedirectResponse(url=authorization_url, status_code=status.HTTP_302_FOUND)
    issue_oidc_browser_binding_cookie(response, browser_binding_token, expires_at)
    return response


@router.get("/callback", name="finish_oidc_login")
async def finish_oidc_login(
    request: Request,
    db: AsyncSession = Depends(get_db),
    code: str = Query(...),
    state: str = Query(...),
):
    callback_url = str(request.url_for("finish_oidc_login"))
    metadata = _build_metadata(request)
    fallback_redirect = request.headers.get("origin") or str(request.base_url).rstrip("/")
    browser_binding_token = read_oidc_browser_binding_cookie(request)

    try:
        user, issuer, subject, redirect_to = await oidc_service.exchange_code(
            db,
            code=code,
            state=state,
            callback_url=callback_url,
            browser_binding_token=browser_binding_token,
        )
        auth_result = await auth_service.create_session_for_user(
            db,
            user=user,
            metadata=metadata,
        )
        await get_audit_service(db).oidc_login_success(
            user_id=user.id,
            username=user.username,
            role=user.role,
            oidc_issuer=issuer,
            oidc_subject=subject,
            session_id=auth_result.session.id,
            context=metadata.to_audit_context(),
        )
        await db.commit()
    except (OIDCConfigurationError, OIDCAuthenticationError, OIDCStateError) as exc:
        await db.rollback()
        await get_audit_service(db).oidc_login_failure(
            reason=str(exc),
            oidc_issuer=None,
            context=metadata.to_audit_context(),
        )
        response = _frontend_error_redirect(fallback_redirect, str(exc))
        revoke_oidc_browser_binding_cookie(response)
        return response

    response = RedirectResponse(url=redirect_to, status_code=status.HTTP_302_FOUND)
    revoke_oidc_browser_binding_cookie(response)
    issue_authenticated_session_cookies(response, auth_result.session_token, auth_result.session.expires_at)
    return response


@router.get("/test-discovery", response_model=OIDCTestResponse)
async def test_oidc_discovery(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin_user),
) -> OIDCTestResponse:
    result = await oidc_service.test_discovery(db)
    return OIDCTestResponse(**result)