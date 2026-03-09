"""Admin authentication and user management routes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.route_utils import read_session_cookie
from app.core.database import get_db
from app.models.enums import AccountType, ResetDeliveryChannel, UserRole, UserStatus
from app.models.models import UserAccount, ApiKeyCreateResponse
from app.services.auth_service import (
    RequestMetadata,
    SessionNotFoundError,
    auth_service,
)
from app.services.api_key_service import (
    ApiKeyAuditService,
    ApiKeyExpiredError,
    ApiKeyNotFoundError,
    ApiKeyRevokedError,
    UserInactiveError,
    api_key_service,
)
from app.services.audit_service import AuditContext
from app.services.passkey_service import (
    PasskeyCredentialNotFoundError,
    PasskeyOwnershipError,
    passkey_service,
)


# ---------------------------------------------------------------------------
# Pydantic schemas (aligned with admin auth contract)
# ---------------------------------------------------------------------------


class AdminCreateUserRequest(BaseModel):
    """Request to create a new user account with temporary credentials."""

    username: str = Field(min_length=3, max_length=64, description="Unique username")
    email: EmailStr = Field(description="User email for notifications")
    role: UserRole = Field(description="User role (ANALYST, ADMIN, AUDITOR)")
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="User title or role description",
    )


class AdminCreateUserResponse(BaseModel):
    """Response after successful user creation."""

    userId: UUID = Field(description="ID of the created user")
    temporaryCredentialExpiresAt: datetime = Field(
        description="Expiration timestamp for temporary credential"
    )
    deliveryChannel: ResetDeliveryChannel = Field(
        description="Channel used to deliver temporary credential"
    )


class AdminUpdateStatusRequest(BaseModel):
    """Request to update user account status."""

    status: UserStatus = Field(description="New status (ACTIVE, DISABLED, LOCKED)")


class AdminResetPasswordRequest(BaseModel):
    """Request to issue an admin-initiated password reset."""

    userId: UUID = Field(description="Target user ID")
    deliveryChannel: ResetDeliveryChannel = Field(
        default=ResetDeliveryChannel.SECURE_EMAIL,
        description="Delivery channel for temporary credential",
    )


class AdminResetPasswordResponse(BaseModel):
    """Response after successful password reset issuance."""

    resetRequestId: UUID = Field(description="ID of the reset request")
    expiresAt: datetime = Field(description="Expiration timestamp for temporary credential")


class UserSummary(BaseModel):
    """Lightweight user summary for dropdowns and listings."""

    userId: UUID = Field(description="User ID")
    username: str = Field(description="Username")
    email: Optional[str] = Field(description="User email")
    role: UserRole = Field(description="User role")
    accountType: AccountType = Field(description="Account type (HUMAN, NHI)")
    oidcIssuer: Optional[str] = Field(default=None, description="OIDC issuer for linked SSO identities")
    oidcSubject: Optional[str] = Field(default=None, description="OIDC subject for linked SSO identities")



class ValidationField(BaseModel):
    field: str
    error: str


class ValidationErrorResponse(BaseModel):
    message: str
    fields: List[ValidationField] = []


class AdminCreateNHIRequest(BaseModel):
    """Request to create a Non-Human Identity (NHI) account."""

    username: str = Field(min_length=3, max_length=64, description="Unique username for the NHI account")
    role: UserRole = Field(description="User role (ANALYST, ADMIN, AUDITOR)")
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


def _build_audit_context(request: Request) -> AuditContext:
    """Build audit context from request metadata."""
    client_host: Optional[str] = None
    if request.client:
        client_host = request.client.host
    return AuditContext(
        ip_address=client_host,
        user_agent=request.headers.get("user-agent"),
        correlation_id=request.headers.get("x-request-id"),
    )


def _extract_api_key(request: Request) -> Optional[str]:
    """
    Extract API key from request headers.
    
    Supports:
    - Authorization: Bearer <key>
    - X-API-Key: <key>
    """
    # Check Authorization header first
    auth_header = request.headers.get("authorization")
    if auth_header:
        parts = auth_header.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
    
    # Fall back to X-API-Key header
    api_key = request.headers.get("x-api-key")
    if api_key:
        return api_key.strip()
    
    return None


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
    audit_context = _build_audit_context(request)
    
    # Try API key authentication first
    api_key = _extract_api_key(request)
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


async def require_admin_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserAccount:
    """
    Dependency that validates the current user has admin role.
    
    Supports both API key and session cookie authentication.
    
    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
    user = await _authenticate_from_request(request, db)
    
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ValidationErrorResponse(
                message="Admin role required for this operation",
                fields=[],
            ).model_dump(),
        )
    
    return user


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




def _extract_request_metadata(request: Request) -> RequestMetadata:
    """Extract request metadata for audit logging."""
    return RequestMetadata(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        correlation_id=request.headers.get("x-correlation-id"),
    )


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
    Create a new user account with a temporary password.
    
    The temporary credential is sent via the specified delivery channel,
    and the user must change their password on first login.
    """
    # Import here to avoid circular dependency
    from app.services.admin_auth_service import admin_auth_service

    try:
        metadata = _extract_request_metadata(request)
        result = await admin_auth_service.create_user(
            admin_user_id=admin_user.id,
            username=payload.username,
            email=payload.email,
            role=payload.role,
            description=payload.description,
            delivery_channel=ResetDeliveryChannel.SECURE_EMAIL,
            request_metadata=metadata,
            db=db,
        )

        return AdminCreateUserResponse(
            userId=result.user_id,
            temporaryCredentialExpiresAt=result.temporary_credential_expires_at,
            deliveryChannel=result.delivery_channel,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ValidationErrorResponse(
                message=str(e),
                fields=[],
            ).model_dump(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ValidationErrorResponse(
                message="Internal server error",
                fields=[],
            ).model_dump(),
        )


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
    # Import here to avoid circular dependency
    from app.services.admin_auth_service import admin_auth_service

    try:
        metadata = _extract_request_metadata(request)
        await admin_auth_service.update_user_status(
            admin_user_id=admin_user.id,
            target_user_id=user_id,
            new_status=payload.status,
            request_metadata=metadata,
            db=db,
        )

    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ValidationErrorResponse(
                    message=str(e),
                    fields=[],
                ).model_dump(),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ValidationErrorResponse(
                message=str(e),
                fields=[],
            ).model_dump(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ValidationErrorResponse(
                message="Internal server error",
                fields=[],
            ).model_dump(),
        )


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
    
    This will:
    - Generate a temporary credential
    - Revoke all active sessions for the target user
    - Set must_change_password flag
    - Send credentials via specified delivery channel
    """
    # Import here to avoid circular dependency
    from app.services.admin_auth_service import admin_auth_service

    try:
        metadata = _extract_request_metadata(request)
        result = await admin_auth_service.issue_password_reset(
            admin_user_id=admin_user.id,
            target_user_id=payload.userId,
            delivery_channel=payload.deliveryChannel,
            request_metadata=metadata,
            db=db,
        )

        return AdminResetPasswordResponse(
            resetRequestId=result.reset_request_id,
            expiresAt=result.expires_at,
        )

    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ValidationErrorResponse(
                    message=str(e),
                    fields=[],
                ).model_dump(),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ValidationErrorResponse(
                message=str(e),
                fields=[],
            ).model_dump(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ValidationErrorResponse(
                message="Internal server error",
                fields=[],
            ).model_dump(),
        )


@authenticated_router.get(
    "/users/summary",
    response_model=List[UserSummary],
    summary="Get user list for dropdowns",
    description="Returns lightweight user summaries for assignee dropdowns and filtering. Available to all authenticated users.",
)
async def get_users_summary(
    user_status: Optional[UserStatus] = UserStatus.ACTIVE,
    role: Optional[UserRole] = None,
    account_type: Optional[AccountType] = AccountType.HUMAN,
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
    from app.services.admin_auth_service import admin_auth_service

    try:
        users = await admin_auth_service.get_users(
            db=db,
            status=user_status,
            role=role,
            account_type=account_type,
        )

        return [
            UserSummary(
                userId=user.id,
                username=user.username,
                email=user.email,
                role=user.role,
                accountType=user.account_type,
                oidcIssuer=user.oidc_issuer,
                oidcSubject=user.oidc_subject,
            )
            for user in users
        ]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ValidationErrorResponse(
                message="Failed to retrieve users",
                fields=[],
            ).model_dump(),
        )


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
            "oidcIssuer": user.oidc_issuer,
            "oidcSubject": user.oidc_subject,
            "accountType": user.account_type.value,
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
    
    audit_context = _build_audit_context(request)
    
    # Validate expiration is in the future
    now = datetime.now(timezone.utc)
    if payload.initial_api_key_expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ValidationErrorResponse(
                message="API key expiration date must be in the future",
            ).model_dump(),
        )
    
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
    api_key, raw_key = await api_key_service.create_api_key(
        db,
        user_id=nhi_account.id,
        name=payload.initial_api_key_name,
        expires_at=payload.initial_api_key_expires_at,
        created_by_user_id=admin_user.id,
        context=audit_context,
    )
    
    # Audit log for NHI creation
    api_key_audit = ApiKeyAuditService()
    api_key_audit.nhi_account_created(
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
            id=api_key.id,
            user_id=api_key.user_id,
            name=api_key.name,
            prefix=api_key.prefix,
            expires_at=api_key.expires_at,
            last_used_at=api_key.last_used_at,
            revoked_at=api_key.revoked_at,
            created_at=api_key.created_at,
            key=raw_key,
        ),
    )
