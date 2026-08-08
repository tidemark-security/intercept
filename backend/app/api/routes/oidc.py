from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
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
from app.api.request_metadata import build_request_metadata
from app.core.client_address import request_client_address
from app.services.auth_service import auth_service
from app.services.audit_service import get_audit_service
from app.services.oidc_auth_request_service import (
    OIDCAuthRequestLimitError,
    oidc_source_fingerprint,
)
from app.services.oidc_service import (
    OIDCAuthenticationError,
    OIDCConfigurationError,
    OIDCConsumedStateError,
    OIDCStateError,
    oidc_service,
)
from app.services.settings_service import SettingsService


router = APIRouter(prefix="/auth/oidc", tags=["authentication"])
logger = logging.getLogger(__name__)

_PROVIDER_ERROR_MESSAGES = {
    "access_denied": "OIDC sign-in was cancelled or denied",
    "interaction_required": "OIDC provider could not complete sign-in",
    "login_required": "OIDC provider could not complete sign-in",
    "account_selection_required": "OIDC provider could not complete sign-in",
    "consent_required": "OIDC provider could not complete sign-in",
    "invalid_request": "OIDC provider rejected the sign-in request",
    "unauthorized_client": "OIDC provider rejected the sign-in request",
    "unsupported_response_type": "OIDC provider rejected the sign-in request",
    "invalid_scope": "OIDC provider rejected the sign-in request",
    "server_error": "OIDC provider is temporarily unavailable",
    "temporarily_unavailable": "OIDC provider is temporarily unavailable",
}
_GENERIC_PROVIDER_ERROR_MESSAGE = "OIDC provider returned an authentication error"


class OIDCConfigResponse(BaseModel):
    enabled: bool
    providerName: str


class OIDCTestResponse(BaseModel):
    success: bool
    message: str


def _frontend_error_redirect(redirect_to: str, message: str) -> RedirectResponse:
    separator = "&" if "?" in redirect_to else "?"
    encoded_message = quote(message)
    return RedirectResponse(
        url=f"{redirect_to}{separator}error=oidc_failed&message={encoded_message}",
        status_code=status.HTTP_302_FOUND,
    )


async def _safe_error_redirect(
    db: AsyncSession,
    candidate: str,
    message: str,
) -> RedirectResponse:
    if not await oidc_service.is_safe_redirect_target(db, candidate):
        candidate = oidc_service.canonical_origin()
    return _frontend_error_redirect(candidate, message)


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
    if not await SettingsService(db).get("oidc.enabled", default=False):  # type: ignore[arg-type]
        return _frontend_error_redirect(
            oidc_service.canonical_origin(),
            "OIDC sign-in is disabled",
        )

    if not await oidc_service.is_safe_redirect_target(db, next):
        return _frontend_error_redirect(
            oidc_service.canonical_origin(),
            "Invalid OIDC return target",
        )

    try:
        source_address = request_client_address(request)
        authorization_url, expires_at, browser_binding_token = await oidc_service.begin_login(
            db,
            redirect_to=next,
            source_address=source_address,
        )
        response = RedirectResponse(
            url=authorization_url,
            status_code=status.HTTP_302_FOUND,
        )
        issue_oidc_browser_binding_cookie(
            response,
            browser_binding_token,
            expires_at,
        )
        await db.commit()
    except OIDCAuthRequestLimitError as exc:
        await db.rollback()
        source_fingerprint = oidc_source_fingerprint(request_client_address(request))
        logger.warning(
            "OIDC login initiation rejected by durable capacity controls",
            extra={
                "security": {
                    "event": "oidc_login_initiation_limited",
                    "source_fingerprint": source_fingerprint[:16],
                    "retry_after_seconds": exc.retry_after_seconds,
                }
            },
        )
        response = JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": "Too many OIDC sign-in attempts. Please try again later."
            },
        )
        response.headers["Retry-After"] = str(exc.retry_after_seconds)
        return response
    except OIDCConfigurationError as exc:
        await db.rollback()
        return _frontend_error_redirect(next, str(exc))

    return response


@router.get("/callback", name="finish_oidc_login")
async def finish_oidc_login(
    request: Request,
    db: AsyncSession = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    if not await SettingsService(db).get("oidc.enabled", default=False):  # type: ignore[arg-type]
        response = _frontend_error_redirect(
            oidc_service.canonical_origin(),
            "OIDC sign-in is disabled",
        )
        revoke_oidc_browser_binding_cookie(response)
        return response

    metadata = build_request_metadata(request)
    fallback_redirect = oidc_service.canonical_origin()
    browser_binding_token = read_oidc_browser_binding_cookie(request)

    if error is not None:
        # Provider-controlled descriptions can contain sensitive diagnostics;
        # accept the standard field but never reflect, persist, or log it.
        del error_description
        reason = _PROVIDER_ERROR_MESSAGES.get(
            error,
            _GENERIC_PROVIDER_ERROR_MESSAGE,
        )
        state_was_consumed = False
        if state:
            try:
                await oidc_service.consume_authorization_error(
                    db,
                    state=state,
                    browser_binding_token=browser_binding_token,
                )
                state_was_consumed = True
            except OIDCStateError as exc:
                await db.rollback()
                logger.warning(
                    "OIDC provider error callback rejected before a valid state was consumed",
                    extra={
                        "security": {
                            "event": "oidc_login_callback_rejected",
                            "source_fingerprint": oidc_source_fingerprint(
                                request_client_address(request)
                            )[:16],
                            "reason_category": type(exc).__name__,
                        }
                    },
                )
        else:
            logger.warning(
                "OIDC provider error callback did not include state",
                extra={
                    "security": {
                        "event": "oidc_login_callback_rejected",
                        "source_fingerprint": oidc_source_fingerprint(
                            request_client_address(request)
                        )[:16],
                        "reason_category": "MissingState",
                    }
                },
            )

        if state_was_consumed:
            await get_audit_service(db).oidc_login_failure(
                reason=reason,
                oidc_issuer=None,
                context=metadata,
            )
        response = _frontend_error_redirect(fallback_redirect, reason)
        revoke_oidc_browser_binding_cookie(response)
        return response

    if not code or not state:
        logger.warning(
            "OIDC login callback did not include a complete authorization response",
            extra={
                "security": {
                    "event": "oidc_login_callback_rejected",
                    "source_fingerprint": oidc_source_fingerprint(
                        request_client_address(request)
                    )[:16],
                    "reason_category": "IncompleteAuthorizationResponse",
                }
            },
        )
        response = _frontend_error_redirect(
            fallback_redirect,
            "OIDC callback response is incomplete",
        )
        revoke_oidc_browser_binding_cookie(response)
        return response

    try:
        user, issuer, subject, redirect_to = await oidc_service.exchange_code(
            db,
            code=code,
            state=state,
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
            context=metadata,
        )
        response = RedirectResponse(
            url=redirect_to,
            status_code=status.HTTP_302_FOUND,
        )
        revoke_oidc_browser_binding_cookie(response)
        issue_authenticated_session_cookies(
            response,
            auth_result.session_token,
            auth_result.session.expires_at,
        )
        # exchange_code acquired the shared OIDC policy gate in this transaction;
        # commit the session before releasing that gate to an OIDC policy writer.
        await db.commit()
    except OIDCConsumedStateError as exc:
        await db.rollback()
        await get_audit_service(db).oidc_login_failure(
            reason=str(exc),
            oidc_issuer=None,
            context=metadata,
        )
        response = await _safe_error_redirect(db, fallback_redirect, str(exc))
        revoke_oidc_browser_binding_cookie(response)
        return response
    except (OIDCConfigurationError, OIDCAuthenticationError, OIDCStateError) as exc:
        await db.rollback()
        logger.warning(
            "OIDC login callback rejected before a valid state was consumed",
            extra={
                "security": {
                    "event": "oidc_login_callback_rejected",
                    "source_fingerprint": oidc_source_fingerprint(
                        request_client_address(request)
                    )[:16],
                    "reason_category": type(exc).__name__,
                }
            },
        )
        response = await _safe_error_redirect(db, fallback_redirect, str(exc))
        revoke_oidc_browser_binding_cookie(response)
        return response

    return response


@router.get("/test-discovery", response_model=OIDCTestResponse)
async def test_oidc_discovery(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin_user),
) -> OIDCTestResponse:
    result = await oidc_service.test_discovery(db)
    return OIDCTestResponse(**result)
