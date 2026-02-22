from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.route_utils import (
    issue_session_cookie,
    read_session_cookie,
    revoke_session_cookie,
)
from app.core.config import settings
from app.core.database import get_db
from app.models.enums import AccountType, SessionRevokedReason, UserRole, UserStatus
from app.services.auth_service import (
    AccountDisabledError,
    AccountLockedError,
    InvalidCredentialsError,
    LoginResult,
    NHIPasswordLoginError,
    PasswordLoginDisabledError,
    PasswordPolicyViolation,
    RequestMetadata,
    SessionNotFoundError,
    auth_service,
)
from app.services.passkey_service import (
    PasskeyChallengeNotFoundError,
    PasskeyConfigError,
    PasskeyCredentialNotFoundError,
    PasskeyOwnershipError,
    passkey_service,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


# ---------------------------------------------------------------------------
# Pydantic schemas (aligned with auth contract)
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Request payload for username/password login."""
    username: str = Field(min_length=1, description="Username (case-insensitive)")
    password: str = Field(min_length=1, description="Password in plain text")


class ValidationField(BaseModel):
    field: str
    error: str


class ValidationErrorResponse(BaseModel):
    message: str
    fields: List[ValidationField] = Field(default_factory=list)


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


class PasswordChangeRequest(BaseModel):
    currentPassword: str = Field(min_length=1)
    newPassword: str = Field(min_length=12)


class PasskeyBeginRegistrationRequest(BaseModel):
    displayName: Optional[str] = None


class PasskeyBeginAuthenticationRequest(BaseModel):
    username: str = Field(min_length=1)


class PasskeyBeginResponse(BaseModel):
    challenge: str
    options: dict


class PasskeyFinishRegistrationRequest(BaseModel):
    challenge: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=100)
    credential: dict


class PasskeyFinishAuthenticationRequest(BaseModel):
    challenge: str = Field(min_length=1)
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


async def _require_human_session_user(request: Request, db: AsyncSession) -> LoginResult:
    session_token = read_session_cookie(request)
    if not session_token:
        raise SessionNotFoundError()

    session = await auth_service.validate_session(db, session_token=session_token)
    if session.user.account_type != AccountType.HUMAN:
        raise AccountDisabledError()
    return session


def _to_passkey_read(passkey) -> PasskeyRead:
    return PasskeyRead(
        id=passkey.id,
        name=passkey.name,
        createdAt=passkey.created_at,
        lastUsedAt=passkey.last_used_at,
        transports=passkey.transports,
        isBackedUp=passkey.is_backed_up,
    )


def _build_metadata(request: Request) -> RequestMetadata:
    client_host: Optional[str] = None
    if request.client:
        client_host = request.client.host
    return RequestMetadata(
        ip_address=client_host,
        user_agent=request.headers.get("user-agent"),
        correlation_id=request.headers.get("x-request-id"),
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
    metadata = _build_metadata(request)
    client_ip = metadata.ip_address or "unknown"
    limiter_key = f"{body.username.strip().lower()}:{client_ip}"

    allowed, retry_after = await auth_service.check_rate_limit(limiter_key)
    if not allowed:
        if retry_after is None:
            retry_after = settings.login_rate_limit_window_seconds
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
    except (AccountLockedError, AccountDisabledError, NHIPasswordLoginError, InvalidCredentialsError, PasswordLoginDisabledError):
        return _validation_error(
            message=GENERIC_LOGIN_FAILURE_MESSAGE,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    issue_session_cookie(response, result.session_token, result.session.expires_at)

    user_summary = UserSummary(
        id=result.user.id,
        username=result.user.username,
        role=result.user.role,
        status=result.user.status,
    )
    session_summary = SessionSummary(
        sessionId=result.session.id,
        expiresAt=result.session.expires_at,
    )

    return LoginResponse(
        user=user_summary,
        session=session_summary,
        mustChangePassword=result.user.must_change_password,
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

    metadata = _build_metadata(request)

    try:
        await auth_service.logout(
            db,
            session_token=session_token,
            metadata=metadata,
            reason=SessionRevokedReason.USER_LOGOUT,
        )
    except SessionNotFoundError:
        revoke_session_cookie(response)
        return _validation_error(
            message="Session is invalid or expired",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    revoke_session_cookie(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/passkeys/register/options", response_model=PasskeyBeginResponse)
async def begin_passkey_registration(
    request: Request,
    body: PasskeyBeginRegistrationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Begin WebAuthn registration for the authenticated human user."""
    try:
        login_result = await _require_human_session_user(request, db)
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

    return PasskeyBeginResponse(challenge=begin_result["challenge"], options=begin_result["options"])


@router.post("/passkeys/register/verify", response_model=PasskeyRead)
async def finish_passkey_registration(
    request: Request,
    body: PasskeyFinishRegistrationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify WebAuthn registration ceremony and persist passkey."""
    try:
        login_result = await _require_human_session_user(request, db)
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
    except Exception:
        return _validation_error(
            message="Unable to verify passkey registration.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return _to_passkey_read(passkey)


@router.post("/passkeys/authenticate/options", response_model=PasskeyBeginResponse)
async def begin_passkey_authentication(
    body: PasskeyBeginAuthenticationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Begin username-first WebAuthn authentication."""
    try:
        begin_result, _user = await passkey_service.begin_authentication(
            db,
            username=body.username,
        )
    except PasskeyCredentialNotFoundError:
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
    metadata = _build_metadata(request)

    try:
        auth_result = await passkey_service.finish_authentication(
            db,
            challenge=body.challenge,
            credential=body.credential,
        )
    except PasskeyChallengeNotFoundError:
        return _validation_error(
            message="Authentication challenge is invalid or expired.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except (PasskeyCredentialNotFoundError, PasskeyOwnershipError):
        return _validation_error(
            message="Passkey credential not found.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    except Exception:
        return _validation_error(
            message="Unable to verify passkey authentication.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    auth_login = await auth_service.create_session_for_user(
        db,
        user=auth_result.user,
        metadata=metadata,
    )
    auth_result.user.last_login_at = datetime.now(timezone.utc)

    issue_session_cookie(response, auth_login.session_token, auth_login.session.expires_at)

    return LoginResponse(
        user=UserSummary(
            id=auth_login.user.id,
            username=auth_login.user.username,
            role=auth_login.user.role,
            status=auth_login.user.status,
        ),
        session=SessionSummary(
            sessionId=auth_login.session.id,
            expiresAt=auth_login.session.expires_at,
        ),
        mustChangePassword=auth_login.user.must_change_password,
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
        login_result = await _require_human_session_user(request, db)
        passkey = await passkey_service.rename_passkey(
            db,
            user_id=login_result.user.id,
            passkey_id=passkey_id,
            name=body.name,
        )
    except SessionNotFoundError:
        return _validation_error(
            message="No active session",
            status_code=status.HTTP_401_UNAUTHORIZED,
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
        login_result = await _require_human_session_user(request, db)
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
        )
    except SessionNotFoundError:
        revoke_session_cookie(response)
        return _validation_error(
            message="Session is invalid or expired",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

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

    return LoginResponse(
        user=user_summary,
        session=session_summary,
        mustChangePassword=session_data.user.must_change_password,
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

    metadata = _build_metadata(request)

    try:
        await auth_service.change_password(
            db,
            session_token=session_token,
            current_password=body.currentPassword,
            new_password=body.newPassword,
            metadata=metadata,
        )
    except SessionNotFoundError:
        revoke_session_cookie(response)
        return _validation_error(
            message="Session is invalid or expired",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
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

    return Response(status_code=status.HTTP_204_NO_CONTENT)
