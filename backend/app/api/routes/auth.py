from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers.exceptions import WebAuthnException

from app.api.error_schemas import ValidationErrorResponse, ValidationField
from app.api.route_utils import (
    generate_csrf_token,
    issue_authenticated_session_cookies,
    issue_csrf_cookie,
    read_session_cookie,
    revoke_authenticated_session_cookies,
)
from app.api.request_metadata import build_request_metadata
from app.core.client_address import request_client_address
from app.core.database import get_db
from app.models.enums import AccountType, SessionRevokedReason, UserRole, UserStatus
from app.models.models import UserAccount
from app.services.auth_service import (
    AccountDisabledError,
    AccountLockedError,
    InvalidCredentialsError,
    LoginResult,
    NHIPasswordLoginError,
    PasswordLoginDisabledError,
    PasswordChangeRequiredError,
    PasswordPolicyViolation,
    SessionNotFoundError,
    auth_service,
)
from app.services.passkey_service import (
    PasskeyChallengeNotFoundError,
    PasskeyConfigError,
    PasskeyCredentialNotFoundError,
    PasskeyLimitError,
    PasskeyOwnershipError,
    PasskeyPolicyError,
    passkey_service,
)
from app.services.passkey_challenge_request_service import (
    PasskeyChallengeRequestLimitError,
    passkey_source_fingerprint,
)
from app.services.password_hash_work_service import PasswordHashWorkCapacityError
from app.services.oidc_local_credential_policy import (
    LocalCredentialCapabilities,
    oidc_local_credential_policy,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


# ---------------------------------------------------------------------------
# Pydantic schemas (aligned with auth contract)
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Request payload for username/password login."""
    username: str = Field(
        min_length=1,
        max_length=1024,
        description="Username (case-insensitive)",
    )
    password: str = Field(
        min_length=1,
        max_length=1024,
        description="Password in plain text",
    )


class UserSummary(BaseModel):
    id: UUID
    username: str
    role: UserRole
    status: UserStatus


class SessionSummary(BaseModel):
    sessionId: UUID
    expiresAt: datetime


class LoginResponse(BaseModel):
    user: UserSummary
    session: SessionSummary
    mustChangePassword: bool = False
    localCredentialManagementAllowed: bool = True
    passwordLoginAllowed: bool = True
    passkeyAllowed: bool = True
    apiKeyAllowed: bool = True


class PasswordChangeRequest(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=1024)
    newPassword: str = Field(min_length=12, max_length=1024)


class PasswordResetTokenRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    newPassword: str = Field(min_length=12, max_length=1024)


class PasskeyBeginRegistrationRequest(BaseModel):
    displayName: Optional[str] = Field(default=None, max_length=100)


class PasskeyBeginAuthenticationRequest(BaseModel):
    username: str = Field(min_length=1, max_length=1024)


class PasskeyBeginResponse(BaseModel):
    challenge: str
    options: dict


class PasskeyFinishRegistrationRequest(BaseModel):
    challenge: str = Field(min_length=1, max_length=512)
    name: str = Field(min_length=1, max_length=100)
    credential: dict


class PasskeyFinishAuthenticationRequest(BaseModel):
    challenge: str = Field(min_length=1, max_length=512)
    credential: dict


class PasskeyRead(BaseModel):
    id: UUID
    name: str
    createdAt: datetime
    lastUsedAt: Optional[datetime] = None
    transports: List[str] = Field(default_factory=list)
    isBackedUp: bool = False


class PasskeyRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


async def _require_human_session_user(
    request: Request,
    db: AsyncSession,
    *,
    shared_authorization: bool = True,
) -> LoginResult:
    session_token = read_session_cookie(request)
    if not session_token:
        raise SessionNotFoundError()

    session = await auth_service.validate_session(
        db,
        session_token=session_token,
        shared_authorization=shared_authorization,
    )
    if session.user.account_type != AccountType.HUMAN:
        raise AccountDisabledError()
    return session


def _password_change_required_response() -> JSONResponse:
    return _validation_error(
        message="Password change required before accessing this resource",
        status_code=status.HTTP_403_FORBIDDEN,
    )


def _to_passkey_read(passkey) -> PasskeyRead:
    return PasskeyRead(
        id=passkey.id,
        name=passkey.name,
        createdAt=passkey.created_at,
        lastUsedAt=passkey.last_used_at,
        transports=passkey.transports,
        isBackedUp=passkey.is_backed_up,
    )


async def _local_credential_capabilities(
    db: AsyncSession,
    user: UserAccount,
) -> LocalCredentialCapabilities:
    return await oidc_local_credential_policy.capabilities_for(db, user=user)


async def _build_authenticated_login_response(
    *,
    response: Response,
    db: AsyncSession,
    result: LoginResult,
) -> LoginResponse:
    """Issue login cookies and build the shared successful-login payload."""
    issue_authenticated_session_cookies(
        response,
        result.session_token,
        result.session.expires_at,
    )
    capabilities = await _local_credential_capabilities(db, result.user)
    return LoginResponse(
        user=UserSummary(
            id=result.user.id,
            username=result.user.username,
            role=result.user.role,
            status=result.user.status,
        ),
        session=SessionSummary(
            sessionId=result.session.id,
            expiresAt=result.session.expires_at,
        ),
        mustChangePassword=result.user.must_change_password,
        localCredentialManagementAllowed=(
            capabilities.password_login_allowed
            and capabilities.passkey_allowed
            and capabilities.api_key_allowed
        ),
        passwordLoginAllowed=capabilities.password_login_allowed,
        passkeyAllowed=capabilities.passkey_allowed,
        apiKeyAllowed=capabilities.api_key_allowed,
    )


def _validation_error(
    *,
    message: str,
    status_code: int,
    fields: Optional[List[ValidationField]] = None,
) -> JSONResponse:
    payload = ValidationErrorResponse(message=message, fields=fields or [])
    return JSONResponse(status_code=status_code, content=payload.model_dump())


GENERIC_LOGIN_FAILURE_MESSAGE = "Unable to sign in with the provided credentials."


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with username and password.
    
    Returns a secure HTTP-only session cookie on success.
    
    **Error Responses:**
    - **401 Unauthorized**: Invalid credentials
    - **403 Forbidden**: Account is disabled
    - **423 Locked**: Account locked due to repeated failures (includes retry information)
    - **429 Too Many Requests**: Rate limit exceeded
    
    **Security:**
    - Passwords are verified using Argon2id hashing
    - Failed attempts are counted and trigger lockout after threshold
    - Rate limiting prevents brute-force attacks
    - All attempts are logged for audit
    """
    metadata = build_request_metadata(request)
    client_ip = metadata.ip_address or "unknown"

    allowed, retry_after = await auth_service.check_rate_limit(
        db,
        source_address=client_ip,
    )
    if not allowed:
        payload = ValidationErrorResponse(
            message="Too many login attempts. Please try again later.",
            fields=[],
        )
        limited_response = JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=payload.model_dump(),
        )
        limited_response.headers["Retry-After"] = str(retry_after)
        return limited_response

    try:
        result: LoginResult = await auth_service.login(
            db,
            username=body.username,
            password=body.password,
            metadata=metadata,
        )
    except PasswordHashWorkCapacityError as exc:
        limited = _validation_error(
            message="Password processing is busy. Please try again later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        limited.headers["Retry-After"] = str(exc.retry_after_seconds)
        return limited
    except (AccountLockedError, AccountDisabledError, NHIPasswordLoginError, InvalidCredentialsError, PasswordLoginDisabledError):
        return _validation_error(
            message=GENERIC_LOGIN_FAILURE_MESSAGE,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    return await _build_authenticated_login_response(
        response=response,
        db=db,
        result=result,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Terminate the active session.
    
    Revokes the session and clears the session cookie.
    
    **Authentication Required**: Must have active session cookie.
    
    **Error Responses:**
    - **401 Unauthorized**: No active session or session invalid
    """
    session_token = read_session_cookie(request)
    if not session_token:
        return _validation_error(
            message="No active session",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    metadata = build_request_metadata(request)

    try:
        await auth_service.logout(
            db,
            session_token=session_token,
            metadata=metadata,
            reason=SessionRevokedReason.USER_LOGOUT,
        )
    except SessionNotFoundError:
        error_response = _validation_error(
            message="Session is invalid or expired",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
        revoke_authenticated_session_cookies(error_response)
        return error_response

    logout_response = Response(status_code=status.HTTP_204_NO_CONTENT)
    revoke_authenticated_session_cookies(logout_response)
    return logout_response


@router.post("/passkeys/register/options", response_model=PasskeyBeginResponse)
async def begin_passkey_registration(
    request: Request,
    body: PasskeyBeginRegistrationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Begin WebAuthn registration for the authenticated human user."""
    try:
        login_result = await _require_human_session_user(
            request,
            db,
            shared_authorization=False,
        )
    except SessionNotFoundError:
        return _validation_error(
            message="No active session",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    except AccountDisabledError:
        return _validation_error(
            message="Passkey registration is available only for human accounts.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    except PasswordChangeRequiredError:
        return _password_change_required_response()

    try:
        begin_result = await passkey_service.begin_registration(
            db,
            user=login_result.user,
            user_display_name=body.displayName,
        )
    except PasskeyConfigError:
        return _validation_error(
            message="Passkey registration is currently unavailable.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except PasskeyPolicyError:
        return _validation_error(
            message="Passkey registration is disabled for this account.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    except PasskeyLimitError:
        return _validation_error(
            message="Maximum number of active passkeys reached.",
            status_code=status.HTTP_409_CONFLICT,
        )
    except PasskeyChallengeRequestLimitError as exc:
        await db.rollback()
        limit_response = _validation_error(
            message="Too many passkey registration attempts. Please try again later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        limit_response.headers["Retry-After"] = str(exc.retry_after_seconds)
        return limit_response

    return PasskeyBeginResponse(challenge=begin_result["challenge"], options=begin_result["options"])


@router.post("/passkeys/register/verify", response_model=PasskeyRead)
async def finish_passkey_registration(
    request: Request,
    body: PasskeyFinishRegistrationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify WebAuthn registration ceremony and persist passkey."""
    try:
        login_result = await _require_human_session_user(
            request,
            db,
            shared_authorization=False,
        )
    except SessionNotFoundError:
        return _validation_error(
            message="No active session",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    except AccountDisabledError:
        return _validation_error(
            message="Passkey registration is available only for human accounts.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    except PasswordChangeRequiredError:
        return _password_change_required_response()

    try:
        passkey = await passkey_service.finish_registration(
            db,
            user=login_result.user,
            challenge=body.challenge,
            credential=body.credential,
            name=body.name,
        )
    except PasskeyChallengeNotFoundError:
        return _validation_error(
            message="Registration challenge is invalid or expired.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except PasskeyPolicyError:
        return _validation_error(
            message="Passkey registration is disabled for this account.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    except PasskeyLimitError:
        return _validation_error(
            message="Maximum number of active passkeys reached.",
            status_code=status.HTTP_409_CONFLICT,
        )
    except WebAuthnException:
        return _validation_error(
            message="Unable to verify passkey registration.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except Exception:
        logger.exception("Unexpected error finishing passkey registration")
        raise

    return _to_passkey_read(passkey)


@router.post("/passkeys/authenticate/options", response_model=PasskeyBeginResponse)
async def begin_passkey_authentication(
    request: Request,
    body: PasskeyBeginAuthenticationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Begin username-first WebAuthn authentication."""
    try:
        begin_result, _user = await passkey_service.begin_authentication(
            db,
            username=body.username,
            source_address=request_client_address(request),
        )
    except PasskeyChallengeRequestLimitError as exc:
        await db.rollback()
        logger.warning(
            "Passkey authentication initiation rejected by durable capacity controls",
            extra={
                "security": {
                    "event": "passkey_authentication_initiation_limited",
                    "source_fingerprint": passkey_source_fingerprint(
                        request_client_address(request)
                    )[:16],
                    "retry_after_seconds": exc.retry_after_seconds,
                }
            },
        )
        limit_response = _validation_error(
            message="Too many passkey sign-in attempts. Please try again later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        limit_response.headers["Retry-After"] = str(exc.retry_after_seconds)
        return limit_response
    except (PasskeyCredentialNotFoundError, PasskeyPolicyError):
        return _validation_error(
            message="Passkey sign-in is unavailable for this account.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    except PasskeyConfigError:
        return _validation_error(
            message="Passkey sign-in is currently unavailable.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return PasskeyBeginResponse(challenge=begin_result["challenge"], options=begin_result["options"])


@router.post("/passkeys/authenticate/verify", response_model=LoginResponse)
async def finish_passkey_authentication(
    request: Request,
    response: Response,
    body: PasskeyFinishAuthenticationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Complete WebAuthn authentication and issue a normal application session."""
    metadata = build_request_metadata(request)

    try:
        auth_result = await passkey_service.finish_authentication(
            db,
            challenge=body.challenge,
            credential=body.credential,
        )
    except (
        PasskeyChallengeNotFoundError,
        PasskeyCredentialNotFoundError,
        PasskeyOwnershipError,
        PasskeyPolicyError,
        WebAuthnException,
    ):
        return _validation_error(
            message="Unable to verify passkey authentication.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    except Exception:
        logger.exception("Unexpected error finishing passkey authentication")
        raise

    auth_login = await auth_service.create_session_for_user(
        db,
        user=auth_result.user,
        metadata=metadata,
    )
    auth_result.user.last_login_at = datetime.now(timezone.utc)

    return await _build_authenticated_login_response(
        response=response,
        db=db,
        result=auth_login,
    )


@router.get("/passkeys", response_model=List[PasskeyRead])
async def list_own_passkeys(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        login_result = await _require_human_session_user(request, db)
    except SessionNotFoundError:
        return _validation_error(
            message="No active session",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    except AccountDisabledError:
        return _validation_error(
            message="Passkeys are available only for human accounts.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    except PasswordChangeRequiredError:
        return _password_change_required_response()

    passkeys = await passkey_service.list_user_passkeys(db, user_id=login_result.user.id, include_revoked=False)
    return [_to_passkey_read(item) for item in passkeys]


@router.patch("/passkeys/{passkey_id}", response_model=PasskeyRead)
async def rename_own_passkey(
    passkey_id: UUID,
    body: PasskeyRenameRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        login_result = await _require_human_session_user(
            request,
            db,
            shared_authorization=False,
        )
        passkey = await passkey_service.rename_passkey(
            db,
            user=login_result.user,
            passkey_id=passkey_id,
            name=body.name,
        )
    except SessionNotFoundError:
        return _validation_error(
            message="No active session",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    except PasswordChangeRequiredError:
        return _password_change_required_response()
    except PasskeyPolicyError:
        return _validation_error(
            message="Passkey management is disabled for this account.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    except (PasskeyCredentialNotFoundError, PasskeyOwnershipError):
        return _validation_error(
            message="Passkey not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return _to_passkey_read(passkey)


@router.delete("/passkeys/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_own_passkey(
    passkey_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        login_result = await _require_human_session_user(
            request,
            db,
            shared_authorization=False,
        )
        await passkey_service.revoke_passkey(
            db,
            passkey_id=passkey_id,
            user_id=login_result.user.id,
        )
    except SessionNotFoundError:
        return _validation_error(
            message="No active session",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    except PasswordChangeRequiredError:
        return _password_change_required_response()
    except (PasskeyCredentialNotFoundError, PasskeyOwnershipError):
        return _validation_error(
            message="Passkey not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/session", response_model=LoginResponse)
async def get_session(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current session information.
    
    Returns user and session details if there's an active session cookie.
    This endpoint is used to validate and refresh sessions on app load.
    
    **Authentication Required**: Must have active session cookie.
    
    **Error Responses:**
    - **401 Unauthorized**: No active session or session invalid/expired
    """
    session_token = read_session_cookie(request)
    if not session_token:
        return _validation_error(
            message="No active session",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        # Validate and get session details
        session_data = await auth_service.validate_session(
            db,
            session_token=session_token,
            allow_password_change_required=True,
            shared_lock=True,
        )
    except SessionNotFoundError:
        error_response = _validation_error(
            message="Session is invalid or expired",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
        revoke_authenticated_session_cookies(error_response)
        return error_response

    issue_csrf_cookie(response, generate_csrf_token(), session_data.session.expires_at)

    user_summary = UserSummary(
        id=session_data.user.id,
        username=session_data.user.username,
        role=session_data.user.role,
        status=session_data.user.status,
    )
    session_summary = SessionSummary(
        sessionId=session_data.session.id,
        expiresAt=session_data.session.expires_at,
    )

    capabilities = await _local_credential_capabilities(db, session_data.user)
    return LoginResponse(
        user=user_summary,
        session=session_summary,
        mustChangePassword=session_data.user.must_change_password,
        localCredentialManagementAllowed=(
            capabilities.password_login_allowed
            and capabilities.passkey_allowed
            and capabilities.api_key_allowed
        ),
        passwordLoginAllowed=capabilities.password_login_allowed,
        passkeyAllowed=capabilities.passkey_allowed,
        apiKeyAllowed=capabilities.api_key_allowed,
    )


@router.post("/password/change", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: Request,
    response: Response,
    body: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Change password for the authenticated user.
    
    Validates the current password and updates to new password if policy is met.
    All other active sessions for this user are revoked upon successful change.
    
    **Authentication Required**: Must have active session cookie.
    
    **Password Policy:**
    - Minimum 12 characters
    - Must include uppercase, lowercase, number, and special character
    
    **Error Responses:**
    - **400 Bad Request**: New password doesn't meet policy requirements
    - **401 Unauthorized**: Current password is incorrect or no active session
    """
    session_token = read_session_cookie(request)
    if not session_token:
        return _validation_error(
            message="No active session",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    metadata = build_request_metadata(request)

    try:
        new_login = await auth_service.change_password(
            db,
            session_token=session_token,
            current_password=body.currentPassword,
            new_password=body.newPassword,
            metadata=metadata,
        )
    except SessionNotFoundError:
        error_response = _validation_error(
            message="Session is invalid or expired",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
        revoke_authenticated_session_cookies(error_response)
        return error_response
    except PasswordLoginDisabledError:
        return _validation_error(
            message="Local password changes are disabled for this account",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    except PasswordHashWorkCapacityError as exc:
        limited = _validation_error(
            message="Password processing is busy. Please try again later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        limited.headers["Retry-After"] = str(exc.retry_after_seconds)
        return limited
    except InvalidCredentialsError:
        return _validation_error(
            message="Invalid current password",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    except PasswordPolicyViolation as exc:
        return _validation_error(
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    success_response = Response(status_code=status.HTTP_204_NO_CONTENT)
    issue_authenticated_session_cookies(
        success_response,
        new_login.session_token,
        new_login.session.expires_at,
    )
    return success_response


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password_with_token(
    request: Request,
    body: PasswordResetTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Set a new password using an admin-issued one-time reset token."""
    from app.services.admin_auth_service import (
        AdminAuthPolicyError,
        AdminAuthValidationError,
        admin_auth_service,
    )

    metadata = build_request_metadata(request)

    try:
        await admin_auth_service.consume_reset_token(
            token=body.token,
            new_password=body.newPassword,
            request_metadata=metadata,
            db=db,
        )
    except PasswordPolicyViolation as exc:
        return _validation_error(
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except AdminAuthPolicyError as exc:
        return _validation_error(
            message=str(exc),
            status_code=status.HTTP_403_FORBIDDEN,
        )
    except PasswordHashWorkCapacityError as exc:
        limited = _validation_error(
            message="Password processing is busy. Please try again later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        limited.headers["Retry-After"] = str(exc.retry_after_seconds)
        return limited
    except AdminAuthValidationError as exc:
        return _validation_error(
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
