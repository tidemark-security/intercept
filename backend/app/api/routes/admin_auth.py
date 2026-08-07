"""Admin authentication and user management routes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, NoReturn, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.error_schemas import ValidationErrorResponse
from app.api.request_metadata import build_audit_context
from app.api.route_utils import read_session_cookie
from app.core.account_authentication import non_password_authentication_allowed
from app.core.csrf import API_KEY_AUTH_RESULT_SCOPE_KEY, extract_api_key
from app.core.authorization_lock import acquire_authorization_lock
from app.core.api_key_scopes import (
    API_ADMIN_SCOPE,
    API_READ_SCOPE,
    API_WRITE_SCOPE,
)
from app.core.database import get_db
from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import ApiKeyCreateResponse, ApiKeyRead, UserAccount
from app.services.admin_auth_service import (
    AdminAuthBusyError,
    AdminAuthError,
    AdminAuthNotFoundError,
    AdminAuthPolicyError,
    AdminAuthValidationError,
    admin_auth_service,
    validate_oidc_preprovisioning_issuer,
    validate_oidc_preprovisioning_subject,
)
from app.services.api_key_service import (
    ApiKeyExpirationError,
    ApiKeyExpiredError,
    ApiKeyNotFoundError,
    ApiKeyPolicyError,
    ApiKeyRevokedError,
    ApiKeyScopeError,
    ApiKeyScopeValidationError,
    UserInactiveError,
    api_key_service,
)
from app.services.audit_service import get_audit_service
from app.services.auth_service import (
    AuthenticationConcurrencyError,
    PasswordChangeRequiredError,
    SessionNotFoundError,
    auth_service,
)
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


class AdminCreateOIDCUserRequest(BaseModel):
    """Request to pre-provision an OIDC-only human account."""

    username: str = Field(min_length=3, max_length=64, description="Unique username")
    email: Optional[EmailStr] = Field(default=None, description="Optional user email")
    role: UserRole = Field(description="User role (ANALYST, ADMIN, AUDITOR)")
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="User title or role description",
    )
    oidc_issuer: str = Field(
        min_length=1,
        max_length=500,
        description="Exact case-sensitive OIDC issuer",
    )
    oidc_subject: str = Field(
        min_length=1,
        max_length=255,
        description="Exact case-sensitive OIDC subject",
    )

    @field_validator("oidc_issuer")
    @classmethod
    def validate_exact_issuer(cls, value: str) -> str:
        try:
            return validate_oidc_preprovisioning_issuer(value)
        except AdminAuthError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("oidc_subject")
    @classmethod
    def validate_exact_subject(cls, value: str) -> str:
        try:
            return validate_oidc_preprovisioning_subject(value)
        except AdminAuthError as exc:
            raise ValueError(str(exc)) from exc


class AdminCreateOIDCUserResponse(BaseModel):
    """Response after exact OIDC account pre-provisioning."""

    userId: UUID = Field(description="ID of the created user")


class AdminUpdateStatusRequest(BaseModel):
    """Request to update user account status."""

    status: UserStatus = Field(description="New status (ACTIVE, DISABLED, LOCKED)")


class AdminUpdateUserRequest(BaseModel):
    """Request to update editable user account fields."""

    model_config = ConfigDict(extra="forbid")

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
    initial_api_key_scopes: List[str] = Field(
        default_factory=lambda: [API_READ_SCOPE],
        min_length=1,
        description="Explicit scopes for the initial API key; defaults to read-only",
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
    
    required_api_key_scope = (
        API_READ_SCOPE
        if request.method.upper() in {"GET", "HEAD"}
        else API_WRITE_SCOPE
    )
    shared_auth_lock = request.method.upper() in {"GET", "HEAD"}

    # Try API key authentication first
    cached_api_key_result = request.scope.get(API_KEY_AUTH_RESULT_SCOPE_KEY)
    if cached_api_key_result is not None:
        if required_api_key_scope not in set(cached_api_key_result.api_key.scopes or []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ValidationErrorResponse(
                    message=f"API key lacks required scope: {required_api_key_scope}",
                ).model_dump(),
            )
        return cached_api_key_result.user

    api_key = extract_api_key(request.headers)
    if api_key:
        try:
            result = await api_key_service.validate_api_key(
                db,
                raw_key=api_key,
                required_scopes={required_api_key_scope},
                context=audit_context,
                skip_locked=True,
                shared_lock=shared_auth_lock,
            )
            request.scope[API_KEY_AUTH_RESULT_SCOPE_KEY] = result
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
        except ApiKeyScopeError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ValidationErrorResponse(message=str(exc)).model_dump(),
            )
        except ApiKeyPolicyError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ValidationErrorResponse(
                    message="Local API keys are disabled for this account",
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
        login_result = await auth_service.validate_session(
            db,
            session_token=session_token,
            allow_password_change_required=True,
            shared_lock=shared_auth_lock,
        )
        return login_result.user
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ValidationErrorResponse(
                message="Invalid or expired session",
            ).model_dump(),
        )


async def _reauthorize_admin_target_mutation(
    *,
    request: Request,
    db: AsyncSession,
    admin_user_id: UUID,
    target_user_id: UUID,
) -> None:
    """Revalidate an admin mutation with canonical actor/target row locking.

    The normal mutating-request dependency holds the acting user's row while
    the route runs. Reciprocal A→B/B→A operations would therefore deadlock if
    both then waited for the other target. Release that initial transaction,
    reacquire actor and target in UUID order, and revalidate the presented
    credential while those locks remain held. A queued target writer then also
    receives PostgreSQL lock-queue priority over later shared readers.
    """
    if admin_user_id == target_user_id:
        raise AdminAuthValidationError(
            "Cannot modify your own account through the admin panel"
        )

    raw_api_key = extract_api_key(request.headers)
    session_token = read_session_cookie(request)

    # Release locks acquired by the generic authentication dependency before
    # entering the canonical multi-user lock order below.
    await db.commit()

    locked_users: dict[UUID, UserAccount] = {}
    for user_id in sorted((admin_user_id, target_user_id), key=lambda value: value.int):
        await acquire_authorization_lock(
            db,
            user_id=user_id,
            shared=user_id == admin_user_id,
        )
        lock_options: bool | dict[str, bool]
        if user_id == admin_user_id:
            lock_options = {"read": True}
        else:
            lock_options = True
        user = await db.get(
            UserAccount,
            user_id,
            populate_existing=True,
            with_for_update=lock_options,
        )
        if user is None:
            if user_id == target_user_id:
                raise AdminAuthNotFoundError(
                    f"User with ID {target_user_id} not found"
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ValidationErrorResponse(
                    message="Authenticated administrator no longer exists",
                    fields=[],
                ).model_dump(),
            )
        locked_users[user_id] = user

    if raw_api_key:
        try:
            credential = await api_key_service.validate_api_key(
                db,
                raw_key=raw_api_key,
                required_scopes={API_WRITE_SCOPE, API_ADMIN_SCOPE},
                context=build_audit_context(request),
                audit_success=False,
                shared_lock=True,
            )
        except (ApiKeyExpiredError, ApiKeyNotFoundError, ApiKeyRevokedError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ValidationErrorResponse(
                    message="Administrative API key is no longer valid",
                    fields=[],
                ).model_dump(),
            ) from exc
        except (ApiKeyPolicyError, ApiKeyScopeError, UserInactiveError) as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ValidationErrorResponse(
                    message="Administrative API key is no longer authorized",
                    fields=[],
                ).model_dump(),
            ) from exc
        credential_user = credential.user
    elif session_token:
        try:
            credential = await auth_service.validate_session(
                db,
                session_token=session_token,
                shared_lock=True,
            )
        except AuthenticationConcurrencyError:
            raise
        except SessionNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ValidationErrorResponse(
                    message="Administrative session is no longer valid",
                    fields=[],
                ).model_dump(),
            ) from exc
        except PasswordChangeRequiredError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ValidationErrorResponse(
                    message="Password change required",
                    fields=[],
                ).model_dump(),
            ) from exc
        credential_user = credential.user
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ValidationErrorResponse(
                message="Administrative authentication is required",
                fields=[],
            ).model_dump(),
        )

    locked_admin = locked_users[admin_user_id]
    if (
        credential_user.id != locked_admin.id
        or not non_password_authentication_allowed(locked_admin)
        or locked_admin.role != UserRole.ADMIN
        or locked_admin.must_change_password
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ValidationErrorResponse(
                message="Administrator is no longer authorized",
                fields=[],
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
    user = await _authenticate_from_request(request, db)
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ValidationErrorResponse(
                message="Password change required before accessing this resource",
                fields=[],
            ).model_dump(),
        )
    return user


async def require_admin_user(
    request: Request,
    user: UserAccount = Depends(require_authenticated_user),
) -> UserAccount:
    """
    Dependency that validates the current user has admin role.

    Supports both API key and session cookie authentication.

    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
    require_api_key_admin_scope(request)

    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ValidationErrorResponse(
                message="Admin role required for this operation",
                fields=[],
            ).model_dump(),
        )
    
    return user


def require_api_key_admin_scope(request: Request) -> None:
    """Require explicit administrative scope when this request uses an API key."""

    api_key_result = request.scope.get(API_KEY_AUTH_RESULT_SCOPE_KEY)
    if api_key_result is None or API_ADMIN_SCOPE in set(
        api_key_result.api_key.scopes or []
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=ValidationErrorResponse(
            message=f"API key lacks required scope: {API_ADMIN_SCOPE}",
            fields=[],
        ).model_dump(),
    )


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
    status_code = status.HTTP_400_BAD_REQUEST
    if isinstance(error, AdminAuthNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, AdminAuthBusyError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(error, AdminAuthPolicyError):
        status_code = status.HTTP_403_FORBIDDEN
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


@router.post(
    "/users/oidc",
    response_model=AdminCreateOIDCUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Pre-provision an OIDC user account",
    description="Admin endpoint to provision a human account bound to an exact OIDC identity",
)
async def create_oidc_user(
    request: Request,
    payload: AdminCreateOIDCUserRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: UserAccount = Depends(require_admin_user),
) -> AdminCreateOIDCUserResponse:
    try:
        result = await admin_auth_service.create_oidc_user(
            admin_user_id=admin_user.id,
            username=payload.username,
            email=str(payload.email) if payload.email is not None else None,
            role=payload.role,
            description=payload.description,
            oidc_issuer=payload.oidc_issuer,
            oidc_subject=payload.oidc_subject,
            request_metadata=build_audit_context(request),
            db=db,
        )
        return AdminCreateOIDCUserResponse(userId=result.user_id)
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
        await _reauthorize_admin_target_mutation(
            request=request,
            db=db,
            admin_user_id=admin_user.id,
            target_user_id=user_id,
        )
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
        await _reauthorize_admin_target_mutation(
            request=request,
            db=db,
            admin_user_id=admin_user.id,
            target_user_id=user_id,
        )
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
    request: Request,
    admin_user: UserAccount = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await _reauthorize_admin_target_mutation(
            request=request,
            db=db,
            admin_user_id=admin_user.id,
            target_user_id=user_id,
        )
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
        await _reauthorize_admin_target_mutation(
            request=request,
            db=db,
            admin_user_id=admin_user.id,
            target_user_id=payload.userId,
        )
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
            scopes=payload.initial_api_key_scopes,
            created_by_user_id=admin_user.id,
            context=audit_context,
        )
    except ApiKeyExpirationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ValidationErrorResponse(
                message=str(exc),
            ).model_dump(),
        ) from exc
    except ApiKeyScopeValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ValidationErrorResponse(message=str(exc)).model_dump(),
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
