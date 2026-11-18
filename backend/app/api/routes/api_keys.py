"""API key management routes."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.error_schemas import ValidationErrorResponse
from app.api.request_metadata import build_audit_context
from app.api.routes.admin_auth import (
    require_authenticated_user,
    require_api_key_admin_scope,
)
from app.core.csrf import extract_api_key
from app.core.database import get_db
from app.core.api_key_scopes import API_READ_SCOPE
from app.models.models import ApiKeyCreateResponse, ApiKeyRead, UserAccount
from app.models.enums import AccountType
from app.services.api_key_service import (
    ApiKeyExpirationError,
    ApiKeyNotFoundError,
    ApiKeyPolicyError,
    ApiKeyRevokedError,
    ApiKeyScopeValidationError,
    ApiKeyUserNotFoundError,
    api_key_service,
)


router = APIRouter(
    prefix="/api-keys",
    tags=["api-keys"],
    dependencies=[Depends(require_authenticated_user)],
)


# ---------------------------------------------------------------------------
# Request/Response schemas
# ---------------------------------------------------------------------------


class CreateApiKeyRequest(BaseModel):
    """Request to create a new API key."""
    name: str = Field(min_length=1, max_length=100, description="User-defined name for this API key")
    expires_at: datetime = Field(description="Expiration date (required)")
    scopes: List[str] = Field(
        default_factory=lambda: [API_READ_SCOPE],
        min_length=1,
        description="Explicit permissions granted to the API key",
    )
    
    # Optional: for admins creating keys for other users
    user_id: Optional[UUID] = Field(
        default=None,
        description="Target user ID (admin-only, defaults to current user)",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: Request,
    body: CreateApiKeyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Create a new API key.
    
    **IMPORTANT**: The full API key is only returned in this response.
    Store it securely - it cannot be retrieved again.
    
    Regular users can only create keys for themselves.
    Admins can create keys for other users only when the target account is NHI.
    
    **Authentication**: Session cookie or API key
    
    **Returns**: The created API key with the full key value (one-time only)
    """
    audit_context = build_audit_context(request)
    if extract_api_key(request.headers):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ValidationErrorResponse(
                message="API keys cannot be used to create additional API keys",
            ).model_dump(),
        )
    
    # Determine target user
    target_user_id = body.user_id or current_user.id
    
    # If creating for another user, require admin and target must be NHI
    if target_user_id != current_user.id:
        if current_user.role.value != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ValidationErrorResponse(
                    message="Admin role required to create API keys for other users",
                ).model_dump(),
            )
        require_api_key_admin_scope(request)

        target_user = await db.get(UserAccount, target_user_id)
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ValidationErrorResponse(
                    message="Target user not found",
                ).model_dump(),
            )

        if target_user.account_type != AccountType.NHI:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ValidationErrorResponse(
                    message="Admins can only create API keys for NHI accounts",
                ).model_dump(),
            )
    
    try:
        api_key, raw_key = await api_key_service.create_api_key(
            db,
            user_id=target_user_id,
            name=body.name,
            expires_at=body.expires_at,
            scopes=body.scopes,
            created_by_user_id=current_user.id,
            context=audit_context,
        )
    except ApiKeyUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ValidationErrorResponse(message=str(exc)).model_dump(),
        ) from exc
    except ApiKeyExpirationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ValidationErrorResponse(message=str(exc)).model_dump(),
        ) from exc
    except ApiKeyScopeValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ValidationErrorResponse(message=str(exc)).model_dump(),
        ) from exc
    except ApiKeyPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ValidationErrorResponse(message=str(exc)).model_dump(),
        ) from exc
    
    return ApiKeyCreateResponse(
        **ApiKeyRead.model_validate(api_key).model_dump(),
        key=raw_key,
    )


@router.get("", response_model=List[ApiKeyRead])
async def list_api_keys(
    request: Request,
    include_revoked: bool = False,
    user_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    List API keys.
    
    Regular users can only list their own keys.
    Admins can list any user's keys by specifying `user_id`.
    
    **Authentication**: Session cookie or API key
    
    **Query Parameters**:
    - `include_revoked`: Include revoked keys (default: false)
    - `user_id`: Target user ID (admin-only, defaults to current user)
    
    **Returns**: List of API key metadata (never includes the actual key value)
    """
    # Determine target user
    target_user_id = user_id or current_user.id
    
    # If listing for another user, require admin
    if target_user_id != current_user.id:
        if current_user.role.value != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ValidationErrorResponse(
                    message="Admin role required to list API keys for other users",
                ).model_dump(),
            )
        require_api_key_admin_scope(request)
    
    keys = await api_key_service.list_user_api_keys(
        db,
        user_id=target_user_id,
        include_revoked=include_revoked,
    )
    
    return [ApiKeyRead.model_validate(key) for key in keys]


@router.get("/{api_key_id}", response_model=ApiKeyRead)
async def get_api_key(
    request: Request,
    api_key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Get details of a specific API key.
    
    Regular users can only view their own keys.
    Admins can view any key.
    
    **Authentication**: Session cookie or API key
    
    **Returns**: API key metadata (never includes the actual key value)
    """
    api_key = await api_key_service.get_api_key(db, api_key_id=api_key_id)
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ValidationErrorResponse(message="API key not found").model_dump(),
        )
    
    # Check permissions
    if api_key.user_id != current_user.id:
        if current_user.role.value != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ValidationErrorResponse(
                    message="You can only view your own API keys",
                ).model_dump(),
            )
        require_api_key_admin_scope(request)
    
    return ApiKeyRead.model_validate(api_key)


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    request: Request,
    api_key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Revoke an API key.
    
    Once revoked, an API key cannot be used for authentication.
    This action cannot be undone.
    
    Regular users can only revoke their own keys.
    Admins can revoke any key.
    
    **Authentication**: Session cookie or API key
    """
    audit_context = build_audit_context(request)
    
    # First check if key exists and get ownership info
    api_key = await api_key_service.get_api_key(db, api_key_id=api_key_id)
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ValidationErrorResponse(message="API key not found").model_dump(),
        )
    
    # Check permissions
    if api_key.user_id != current_user.id:
        if current_user.role.value != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ValidationErrorResponse(
                    message="You can only revoke your own API keys",
                ).model_dump(),
            )
        require_api_key_admin_scope(request)
    
    try:
        await api_key_service.revoke_api_key(
            db,
            api_key_id=api_key_id,
            revoked_by_user_id=current_user.id,
            context=audit_context,
        )
    except ApiKeyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ValidationErrorResponse(message="API key not found").model_dump(),
        )
    except ApiKeyRevokedError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ValidationErrorResponse(message="API key is already revoked").model_dump(),
        )
