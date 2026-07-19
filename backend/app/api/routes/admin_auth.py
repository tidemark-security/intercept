"""Admin authentication and user management routes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, NoReturn, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.error_schemas import ValidationErrorResponse
from app.api.request_metadata import build_audit_context
from app.api.route_utils import read_session_cookie
from app.core.csrf import API_KEY_AUTH_RESULT_SCOPE_KEY, extract_api_key
from app.core.database import get_db
from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import ApiKeyCreateResponse, ApiKeyRead, UserAccount
from app.services.admin_auth_service import (
    AdminAuthError,
    AdminAuthNotFoundError,
    admin_auth_service,
)
from app.services.api_key_service import (
    ApiKeyExpirationError,
    ApiKeyExpiredError,
    ApiKeyNotFoundError,
    ApiKeyRevokedError,
    UserInactiveError,
    api_key_service,
)
from app.services.audit_service import get_audit_service
from app.services.auth_service import SessionNotFoundError, auth_service
from app.services.passkey_service import (
    PasskeyCredentialNotFoundError,
    PasskeyOwnershipError,
    passkey_service,
)


# ---------------------------------------------------------------------------
# Pydantic schemas (aligned with admin auth contract)
# ---------------------------------------------------------------------------


class AdminCreateUserRequest(BaseModel):
    """Request to create a new user account with a password setup link."""

    username: str = Field(min_length=3, max_length=64, description="Unique username")
    email: Optional[EmailStr] = Field(default=None, description="Optional user email")
    role: UserRole = Field(description="User role (ANALYST, ADMIN, AUDITOR)")
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="User title or role description",
    )


class AdminCreateUserResponse(BaseModel):
    """Response after successful user creation."""

    userId: UUID = Field(description="ID of the created user")
    expiresAt: datetime = Field(description="Expiration timestamp for password setup token")
    resetToken: str = Field(description="One-time password setup token")


class AdminUpdateStatusRequest(BaseModel):
    """Request to update user account status."""

    status: UserStatus = Field(description="New status (ACTIVE, DISABLED, LOCKED)")


class AdminUpdateUserRequest(BaseModel):
    """Request to update editable user account fields."""

    username: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=64,
        description="Updated unique username",
    )
    email: Optional[EmailStr] = Field(
        default=None,
        description="Updated email for human accounts",
    )
    role: Optional[UserRole] = Field(
        default=None,
        description="Updated user role",
    )
    assignable: bool = Field(
        default=False,
        description="Whether an NHI account can be assigned task work",
    )
    override_timestamps: bool = Field(
        default=False,
        description="Whether an NHI account can override created_at timestamps during migration imports",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Updated user title or service account description",
    )

    @model_validator(mode="after")
    def validate_has_updates(self) -> "AdminUpdateUserRequest":
        if not self.model_fields_set.intersection({"username", "email", "role", "description", "assignable", "override_timestamps"}):
            raise ValueError("At least one editable field must be provided")
        return self


class AdminResetPasswordRequest(BaseModel):
    """Request to issue an admin-initiated password reset."""

    userId: UUID = Field(description="Target user ID")


class AdminResetPasswordResponse(BaseModel):
    """Response after successful password reset issuance."""

    resetRequestId: UUID = Field(description="ID of the reset request")
    expiresAt: datetime = Field(description="Expiration timestamp for password reset token")
    resetToken: str = Field(description="One-time password reset token")


class UserSummary(BaseModel):
    """Lightweight user summary for dropdowns and listings."""

    userId: UUID = Field(description="User ID")
    username: str = Field(description="Username")
    email: Optional[str] = Field(description="User email")
    role: UserRole = Field(description="User role")
    accountType: AccountType = Field(description="Account type (HUMAN, NHI)")
    assignable: bool = Field(default=False, description="Whether this account can be assigned work")
    overrideTimestamps: bool = Field(default=False, description="Whether this account can override timestamps")
    oidcIssuer: Optional[str] = Field(default=None, description="OIDC issuer for linked SSO identities")
    oidcSubject: Optional[str] = Field(default=None, description="OIDC subject for linked SSO identities")



class AdminCreateNHIRequest(BaseModel):
    """Request to create a Non-Human Identity (NHI) account."""

    username: str = Field(min_length=3, max_length=64, description="Unique username for the NHI account")
    role: UserRole = Field(description="User role (ANALYST, ADMIN, AUDITOR)")
    assignable: bool = Field(default=False, description="Whether this NHI can be assigned task work")
    override_timestamps: bool = Field(
        default=False,
        description="Whether this NHI can override created_at timestamps during migration imports",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Purpose or description of this NHI account",
    )
    initial_api_key_name: str = Field(
        min_length=1,
        max_length=100,
        description="Name for the initial API key",
    )
    initial_api_key_expires_at: datetime = Field(
        description="Expiration date for the initial API key (required)",
    )


class AdminCreateNHIResponse(BaseModel):
    """Response after successful NHI account creation."""

    userId: UUID = Field(description="ID of the created NHI account")
    username: str = Field(description="Username of the NHI account")
    role: UserRole = Field(description="Role assigned to the NHI account")
    apiKey: ApiKeyCreateResponse = Field(description="Initial API key (only shown once)")


class AdminPasskeyRead(BaseModel):
    id: UUID
    userId: UUID
    name: str
    createdAt: datetime
    lastUsedAt: Optional[datetime] = None
    revokedAt: Optional[datetime] = None
    transports: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dependency: Require admin role
# ---------------------------------------------------------------------------


async def _authenticate_from_request(
    request: Request,
    db: AsyncSession,
) -> UserAccount:
    """
    Authenticate a request using either API key or session cookie.
    
    Checks in order:
    1. Authorization: Bearer <api_key> header
    2. X-API-Key header
    3. Session cookie
    
    Returns the authenticated UserAccount.
    
    Raises:
        HTTPException: 401 if not authenticated
    """
    audit_context = build_audit_context(request)
    
    # Try API key authentication first
    cached_api_key_result = request.scope.get(API_KEY_AUTH_RESULT_SCOPE_KEY)
    if cached_api_key_result is not None:
        return cached_api_key_result.user

    api_key = extract_api_key(request.headers)
    if api_key:
        try:
            result = await api_key_service.validate_api_key(
                db,
                raw_key=api_key,
                context=audit_context,
            )
            return result.user
        except ApiKeyNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ValidationErrorResponse(
                    message="Invalid API key",
                ).model_dump(),
            )
        except ApiKeyExpiredError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ValidationErrorResponse(
                    message="API key has expired",
                ).model_dump(),
            )
        except ApiKeyRevokedError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ValidationErrorResponse(
                    message="API key has been revoked",
                ).model_dump(),
            )
        except UserInactiveError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ValidationErrorResponse(
                    message="User account is not active",
                ).model_dump(),
            )
    
    # Fall back to session cookie
    session_token = read_session_cookie(request)
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ValidationErrorResponse(
                message="Authentication required",
                fields=[],
            ).model_dump(),
        )
    
    try:
        login_result = await auth_service.validate_session(db, session_token=session_token)
        return login_result.user
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ValidationErrorResponse(
                message="Invalid or expired session",
            ).model_dump(),
        )


async def require_authenticated_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserAccount:
    """
    Dependency that validates the current user is authenticated.
    
    Supports both API key and session cookie authentication.
    
    Raises:
        HTTPException: 401 if not authenticated
    """
    return await _authenticate_from_request(request, db)


async def require_admin_user(
    user: UserAccount = Depends(require_authenticated_user),
) -> UserAccount:
    """
    Dependency that validates the current user has admin role.

    Supports both API key and session cookie authentication.

    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ValidationErrorResponse(
                message="Admin role required for this operation",
                fields=[],
            ).model_dump(),
        )
    
    return user


async def require_non_auditor_user(
    user: UserAccount = Depends(require_authenticated_user),
) -> UserAccount:
    """
    Dependency that validates the current user is authenticated and not an auditor.

    Supports both API key and session cookie authentication.

    Raises:
        HTTPException: 401 if not authenticated, 403 if auditor
    """
    if user.role == UserRole.AUDITOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ValidationErrorResponse(
                message="Auditor accounts have read-only access",
                fields=[],
            ).model_dump(),
        )

    return user


# Authenticated router for lightweight user-discovery endpoints.
authenticated_router = APIRouter(
    prefix="/admin/auth",
    tags=["admin"],
    dependencies=[Depends(require_authenticated_user)],
)


# Re-create router with admin authentication dependency
router = APIRouter(
    prefix="/admin/auth",
    tags=["admin"],
    dependencies=[Depends(require_admin_user)]
)


def _raise_admin_auth_http_error(error: AdminAuthError) -> NoReturn:
    """Translate an expected admin-auth failure at the HTTP seam."""
    status_code = (
        status.HTTP_404_NOT_FOUND
        if isinstance(error, AdminAuthNotFoundError)
        else status.HTTP_400_BAD_REQUEST
    )
    raise HTTPException(
        status_code=status_code,
        detail=ValidationErrorResponse(
            message=str(error),
            fields=[],
        ).model_dump(),
    ) from error


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/users",
    response_model=AdminCreateUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account",
    description="Admin endpoint to provision a new user with temporary credentials",
)
async def create_user(
    request: Request,
    payload: AdminCreateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: UserAccount = Depends(require_admin_user),
) -> AdminCreateUserResponse:
    """
    Create a new user account with a one-time password setup link.
    """
    try:
        metadata = build_audit_context(request)
        result = await admin_auth_service.create_user(
            admin_user_id=admin_user.id,
            username=payload.username,
            email=payload.email,
            role=payload.role,
            description=payload.description,
            request_metadata=metadata,
            db=db,
        )

        return AdminCreateUserResponse(
            userId=result.user_id,
            expiresAt=result.expires_at,
            resetToken=result.reset_token,
        )

    except AdminAuthError as error:
        _raise_admin_auth_http_error(error)


@router.patch(
    "/users/{user_id}/status",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update user account status",
    description="Admin endpoint to enable or disable a user account",
    response_model=None,
)
async def update_user_status(
    user_id: UUID,
    request: Request,
    payload: AdminUpdateStatusRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: UserAccount = Depends(require_admin_user),
) -> None:
    """
    Update the status of a user account.
    
    Disabling a user will revoke all their active sessions.
    """
    try:
        metadata = build_audit_context(request)
        await admin_auth_service.update_user_status(
            admin_user_id=admin_user.id,
            target_user_id=user_id,
            new_status=payload.status,
            request_metadata=metadata,
            db=db,
        )

    except AdminAuthError as error:
        _raise_admin_auth_http_error(error)


@router.patch(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update editable user account fields",
    description="Admin endpoint to edit a user's username, role, email, or description",
    response_model=None,
)
async def update_user(
    user_id: UUID,
    request: Request,
    payload: AdminUpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: UserAccount = Depends(require_admin_user),
) -> None:
    try:
        metadata = build_audit_context(request)
        await admin_auth_service.update_user(
            admin_user_id=admin_user.id,
            target_user_id=user_id,
            username=payload.username,
            email=payload.email,
            email_provided="email" in payload.model_fields_set,
            role=payload.role,
            assignable=payload.assignable if "assignable" in payload.model_fields_set else None,
            override_timestamps=payload.override_timestamps if "override_timestamps" in payload.model_fields_set else None,
            description=payload.description,
            request_metadata=metadata,
            db=db,
        )

    except AdminAuthError as error:
        _raise_admin_auth_http_error(error)


@router.get(
    "/users/{user_id}/passkeys",
    response_model=List[AdminPasskeyRead],
    summary="List passkeys for a user",
)
async def list_user_passkeys(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> List[AdminPasskeyRead]:
    user = await db.get(UserAccount, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ValidationErrorResponse(
                message="User not found",
                fields=[],
            ).model_dump(),
        )

    passkeys = await passkey_service.list_user_passkeys(db, user_id=user_id, include_revoked=True)
    return [
        AdminPasskeyRead(
            id=item.id,
            userId=item.user_id,
            name=item.name,
            createdAt=item.created_at,
            lastUsedAt=item.last_used_at,
            revokedAt=item.revoked_at,
            transports=item.transports,
        )
        for item in passkeys
    ]


@router.delete(
    "/users/{user_id}/passkeys/{passkey_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke user passkey",
    response_model=None,
)
async def revoke_user_passkey(
    user_id: UUID,
    passkey_id: UUID,
    admin_user: UserAccount = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await passkey_service.revoke_passkey(
            db,
            passkey_id=passkey_id,
            user_id=user_id,
            revoked_by_admin_id=admin_user.id,
        )
    except (PasskeyCredentialNotFoundError, PasskeyOwnershipError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ValidationErrorResponse(
                message="Passkey not found",
                fields=[],
            ).model_dump(),
        )

    return None


@router.post(
    "/password-resets",
    response_model=AdminResetPasswordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue an admin-initiated password reset",
    description="Admin endpoint to force password reset for a user",
)
async def issue_password_reset(
    request: Request,
    payload: AdminResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: UserAccount = Depends(require_admin_user),
) -> AdminResetPasswordResponse:
    """
    Issue an admin-initiated password reset for a user.
    """
    try:
        metadata = build_audit_context(request)
        result = await admin_auth_service.issue_password_reset(
            admin_user_id=admin_user.id,
            target_user_id=payload.userId,
            request_metadata=metadata,
            db=db,
        )

        return AdminResetPasswordResponse(
            resetRequestId=result.reset_request_id,
            expiresAt=result.expires_at,
            resetToken=result.reset_token,
        )

    except AdminAuthError as error:
        _raise_admin_auth_http_error(error)


@authenticated_router.get(
    "/users/summary",
    response_model=List[UserSummary],
    summary="Get user list for dropdowns",
    description="Returns lightweight user summaries for assignee dropdowns and filtering. Available to all authenticated users.",
)
async def get_users_summary(
    user_status: Optional[UserStatus] = UserStatus.ACTIVE,
    role: Optional[UserRole] = None,
    account_type: Optional[AccountType] = None,
    db: AsyncSession = Depends(get_db),
    _current_user: UserAccount = Depends(require_authenticated_user),
) -> List[UserSummary]:
    """
    Get list of users for dropdowns and filtering.
    
    Query Parameters:
    - user_status: Filter by user status (default: ACTIVE)
    - role: Optional filter by user role
    
    Returns lightweight user summaries without sensitive information.
    """
    users = await admin_auth_service.get_users(
        db=db,
        status=user_status,
        role=role,
        account_type=account_type,
    )
    users = [
        user for user in users
        if user.account_type == AccountType.HUMAN or user.assignable
    ]

    return [
        UserSummary(
            userId=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            accountType=user.account_type,
            assignable=user.assignable,
            overrideTimestamps=user.override_timestamps,
            oidcIssuer=user.oidc_issuer,
            oidcSubject=user.oidc_subject,
        )
        for user in users
    ]


@router.get(
    "/users",
    summary="List all user accounts",
    description="Admin endpoint to retrieve all user accounts",
)
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin_user: UserAccount = Depends(require_admin_user),
) -> List[dict]:
    """
    List all user accounts with their current status.
    
    Returns basic user information without sensitive fields.
    """
    from sqlmodel import select
    
    result = await db.execute(select(UserAccount))
    users = result.scalars().all()
    
    return [
        {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "description": user.description,
            "oidcIssuer": user.oidc_issuer,
            "oidcSubject": user.oidc_subject,
            "accountType": user.account_type.value,
            "assignable": user.assignable,
            "overrideTimestamps": user.override_timestamps,
            "role": user.role.value,
            "status": user.status.value,
            "mustChangePassword": user.must_change_password,
            "lastLoginAt": user.last_login_at.isoformat() if user.last_login_at else None,
            "createdAt": user.created_at.isoformat(),
        }
        for user in users
    ]


@router.post(
    "/users/nhi",
    response_model=AdminCreateNHIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Non-Human Identity (NHI) account",
    description="Admin endpoint to create an NHI account with an initial API key",
)
async def create_nhi_account(
    request: Request,
    payload: AdminCreateNHIRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: UserAccount = Depends(require_admin_user),
) -> AdminCreateNHIResponse:
    """
    Create a Non-Human Identity (NHI) account for programmatic access.
    
    NHI accounts:
    - Have no email or password
    - Authenticate exclusively via API keys
    - Cannot use the login endpoint
    
    **IMPORTANT**: The initial API key is only shown in this response.
    Store it securely - it cannot be retrieved again.
    
    The NHI account inherits the permissions of the assigned role.
    """
    from uuid import uuid4
    from sqlmodel import select
    
    audit_context = build_audit_context(request)
    
    now = datetime.now(timezone.utc)

    # Check username uniqueness
    normalized_username = payload.username.strip().lower()
    result = await db.execute(
        select(UserAccount).where(UserAccount.username == normalized_username)
    )
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ValidationErrorResponse(
                message=f"Username '{normalized_username}' is already taken",
            ).model_dump(),
        )
    
    # Create the NHI account
    nhi_account = UserAccount(
        id=uuid4(),
        username=normalized_username,
        account_type=AccountType.NHI,
        role=payload.role,
        assignable=payload.assignable,
        override_timestamps=payload.override_timestamps,
        description=payload.description,
        email=None,
        password_hash=None,
        status=UserStatus.ACTIVE,
        must_change_password=False,
        created_by_admin_id=admin_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(nhi_account)
    await db.flush()
    
    # Create the initial API key
    try:
        api_key, raw_key = await api_key_service.create_api_key(
            db,
            user_id=nhi_account.id,
            name=payload.initial_api_key_name,
            expires_at=payload.initial_api_key_expires_at,
            created_by_user_id=admin_user.id,
            context=audit_context,
        )
    except ApiKeyExpirationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ValidationErrorResponse(
                message="API key expiration date must be in the future",
            ).model_dump(),
        ) from exc
    
    # Audit log for NHI creation
    await get_audit_service(db).nhi_account_created(
        admin_user_id=admin_user.id,
        admin_username=admin_user.username,
        nhi_user_id=nhi_account.id,
        nhi_username=nhi_account.username,
        role=nhi_account.role.value,
        initial_api_key_id=api_key.id,
        initial_api_key_prefix=api_key.prefix,
        context=audit_context,
    )
    
    return AdminCreateNHIResponse(
        userId=nhi_account.id,
        username=nhi_account.username,
        role=nhi_account.role,
        apiKey=ApiKeyCreateResponse(
            **ApiKeyRead.model_validate(api_key).model_dump(),
            key=raw_key,
        ),
    )
