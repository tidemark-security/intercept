"""
Shared utilities for API routes.

This module contains common functionality used across multiple route modules,
including timeline item type discovery, human ID handling decorators,
authentication session helpers, and attachment upload/download helpers.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings_registry import get_local

if TYPE_CHECKING:
    from app.models.models import (
        AttachmentStatusUpdate,
        PresignedDownloadResponse,
        PresignedUploadRequest,
        PresignedUploadResponse,
        UserAccount,
    )

logger = logging.getLogger(__name__)


def normalize_upload_status(status: Any, default: str = "COMPLETE") -> str:
    """Normalize stored attachment upload status values for route checks."""
    if status is None:
        return default

    if hasattr(status, "value"):
        status = status.value

    normalized = str(status).strip()
    if not normalized:
        return default

    return normalized.upper()


def get_timeline_item_types(union_type):
    """
    Dynamically extract timeline item types from a Union type.
    
    Args:
        union_type: A Union type containing timeline item classes
        
    Returns:
        Dict mapping JSON type strings to timeline item classes
    """
    import re
    
    timeline_types = {}
    
    # Get the union args from the provided union type
    if hasattr(union_type, '__args__'):
        for item_class in union_type.__args__:
            # Convert class name to JSON type string
            # e.g., AttachmentItem -> attachment, ForensicArtifactItem -> forensic_artifact, TTPItem -> ttp
            class_name = item_class.__name__
            if class_name.endswith('Item'):
                # Remove 'Item' suffix
                base_name = class_name[:-4]
                # Convert PascalCase to snake_case using regex
                # This handles both single capitals and consecutive capitals correctly
                json_type = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', base_name)
                json_type = re.sub('([a-z0-9])([A-Z])', r'\1_\2', json_type).lower()
                timeline_types[json_type] = item_class
    
    return timeline_types


def create_timeline_converter(timeline_item_types: Dict[str, Any]):
    """
    Create a timeline item converter function using the provided type mapping.
    
    Args:
        timeline_item_types: Dict mapping JSON type strings to timeline item classes
        
    Returns:
        Function that converts dict to appropriate timeline item type
    """
    from app.core.validation import validate_value
    
    def _validate_observable_item(timeline_item: dict) -> None:
        """Validate observable item fields."""
        obs_type = timeline_item.get("observable_type")
        obs_value = timeline_item.get("observable_value")
        
        if obs_type and obs_value:
            result = validate_value(f"observable.{obs_type}", obs_value)
            if not result.valid:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid observable value: {result.error}"
                )
    
    def _validate_network_item(timeline_item: dict) -> None:
        """Validate network traffic item fields."""
        validations = [
            ("network.src_ip", timeline_item.get("source_ip")),
            ("network.dst_ip", timeline_item.get("destination_ip")),
            ("network.src_port", timeline_item.get("source_port")),
            ("network.dst_port", timeline_item.get("destination_port")),
            ("network.protocol", timeline_item.get("protocol")),
        ]
        
        for key, value in validations:
            if value is not None:
                # Convert port numbers to strings for validation
                str_value = str(value) if isinstance(value, int) else value
                result = validate_value(key, str_value)
                if not result.valid:
                    field_name = key.split(".")[-1]
                    raise HTTPException(
                        status_code=422,
                        detail=f"Invalid {field_name}: {result.error}"
                    )
    
    def convert_timeline_item(timeline_item: dict):
        """Convert dict to appropriate timeline item type based on the 'type' field."""
        item_type = timeline_item.get("type")
        if item_type not in timeline_item_types:
            raise HTTPException(status_code=400, detail=f"Unsupported timeline item type: {item_type}")
        
        # Validate specific item types before conversion
        if item_type == "observable":
            _validate_observable_item(timeline_item)
        elif item_type == "network_traffic":
            _validate_network_item(timeline_item)
        
        item_class = timeline_item_types[item_type]
        return item_class(**timeline_item)
    
    return convert_timeline_item


def create_human_id_decorator(id_prefix: str, default_param_name: str = "id"):
    """
    Create a human ID decorator for the specified prefix and default parameter name.
    
    Args:
        id_prefix: The human ID prefix (e.g., "ALT-", "CAS-")
        default_param_name: Default parameter name to check for IDs
        
    Returns:
        Decorator function configured for the specified prefix
    """
    def handle_human_id(param_name: str = default_param_name):
        """
        Decorator to handle human ID redirects for endpoints.
        
        Args:
            param_name: The parameter name that contains the ID
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Get the ID value from kwargs
                id_value = kwargs.get(param_name)
                
                # Check if it's a human ID and redirect if so
                if isinstance(id_value, str) and id_value.startswith(id_prefix):
                    try:
                        numeric_id = int(id_value[len(id_prefix):])
                        
                        # Get the request object to build the redirect URL
                        request = kwargs.get('request')
                        if not request:
                            # Look for Request in args
                            for arg in args:
                                if isinstance(arg, Request):
                                    request = arg
                                    break
                        
                        if request:
                            # Replace the human ID in the URL path with numeric ID
                            original_path = str(request.url.path)
                            redirect_path = original_path.replace(id_value, str(numeric_id))
                            return RedirectResponse(url=redirect_path, status_code=308)
                        else:
                            raise HTTPException(status_code=500, detail="Request object not found for redirect")
                            
                    except ValueError:
                        raise HTTPException(status_code=400, detail=f"Invalid {id_prefix} ID format")
                
                # If we reach here, it means the ID is already numeric (redirect already happened)
                # Just ensure it's an integer if it's a string representation
                if isinstance(id_value, str) and id_value.isdigit():
                    kwargs[param_name] = int(id_value)
                
                # Call the original function
                return await func(*args, **kwargs)
            
            return wrapper
        return decorator
    
    return handle_human_id


# ---------------------------------------------------------------------------
# Attachment upload / download helpers
# ---------------------------------------------------------------------------


def find_attachment_item(
    timeline_items: Optional[List[Dict[str, Any]]], item_id: str
) -> Optional[Dict[str, Any]]:
    """Find an attachment timeline item by ID."""
    for item in timeline_items or []:
        if item.get("id") == item_id and item.get("type") == "attachment":
            return item
    return None


async def handle_generate_upload_url(
    *,
    entity_type: str,
    parent_id: int,
    request_data: "PresignedUploadRequest",
    current_user: "UserAccount",
    db: AsyncSession,
    service: Any,
) -> "PresignedUploadResponse":
    """Shared logic for generating a presigned upload URL and creating the attachment timeline item.

    ``service`` must expose ``add_timeline_item(db, parent_id, item, username)``.
    """
    from app.core.storage_config import storage_config
    from app.models.enums import UploadStatus
    from app.models.models import (
        AttachmentItem,
        PresignedUploadResponse,
    )
    from app.services.attachment_settings_service import get_attachment_limits
    from app.services.storage_service import storage_service

    parent_type = f"{entity_type}s"  # alert -> alerts

    try:
        attachment_limits = await get_attachment_limits(db)

        if request_data.file_size > attachment_limits.max_upload_size_bytes:
            max_size_mb = attachment_limits.max_upload_size_mb
            raise HTTPException(
                status_code=413,
                detail=f"File size {request_data.file_size} exceeds limit {max_size_mb}MB",
            )

        if request_data.mime_type and not storage_service.validate_file_type(request_data.mime_type):
            raise HTTPException(
                status_code=415,
                detail=f"File type {request_data.mime_type} not allowed",
            )

        sanitized_filename = storage_service.sanitize_filename(request_data.filename)

        item_id = str(uuid.uuid4())
        storage_key = storage_service.generate_storage_key(
            parent_id, item_id, sanitized_filename, parent_type=parent_type,
        )

        attachment_item = AttachmentItem(
            id=item_id,
            type="attachment",
            file_name=sanitized_filename,
            mime_type=request_data.mime_type,
            file_size=request_data.file_size,
            storage_key=storage_key,
            upload_status=UploadStatus.UPLOADING,
            uploaded_by=current_user.username,
            created_by=current_user.username,
            timestamp=datetime.now(timezone.utc),
        )

        await service.add_timeline_item(
            db, parent_id, attachment_item, current_user.username,
        )

        upload_url = await storage_service.generate_presigned_upload_url(
            storage_key, expires_minutes=storage_config.upload_timeout_minutes,
        )

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=storage_config.upload_timeout_minutes,
        )

        logger.info(
            "Generated presigned upload URL for %s %s, item %s, file %s, "
            "size %s bytes, user %s, expires %s",
            entity_type, parent_id, item_id, sanitized_filename,
            request_data.file_size, current_user.username, expires_at,
        )

        return PresignedUploadResponse(
            item_id=item_id,
            upload_url=upload_url,
            storage_key=storage_key,
            expires_at=expires_at,
            max_file_size=attachment_limits.max_upload_size_bytes,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error generating upload URL for %s %s: %s", entity_type, parent_id, e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate upload URL: {str(e)}",
        )


async def handle_update_attachment_status(
    *,
    entity: Any,
    entity_type: str,
    parent_id: int,
    item_id: str,
    update_data: "AttachmentStatusUpdate",
    current_user: "UserAccount",
    db: AsyncSession,
    service: Any,
) -> Any:
    """Shared logic for updating an attachment's upload status.

    ``entity`` must have a ``timeline_items`` attribute (list of dicts).
    ``service`` must expose ``update_timeline_item(db, parent_id, item_id, item, username)``.
    Returns the updated entity.
    """
    from app.models.enums import UploadStatus
    from app.models.models import AttachmentItem
    from app.services.storage_service import storage_service

    try:
        timeline_item = find_attachment_item(entity.timeline_items, item_id)
        if not timeline_item:
            raise HTTPException(
                status_code=404,
                detail=f"Attachment item {item_id} not found",
            )

        if timeline_item.get("uploaded_by") != current_user.username:
            raise HTTPException(
                status_code=403,
                detail="Only upload owner can update status",
            )

        current_status = normalize_upload_status(timeline_item.get("upload_status"))
        if current_status in [UploadStatus.COMPLETE.value, UploadStatus.FAILED.value]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from {current_status} to {update_data.status}",
            )

        if update_data.status == UploadStatus.COMPLETE:
            storage_key = timeline_item.get("storage_key")
            if not storage_key:
                raise HTTPException(
                    status_code=400,
                    detail="Attachment has no storage key",
                )
            file_exists = await storage_service.verify_file_exists(storage_key)
            if not file_exists:
                raise HTTPException(
                    status_code=409,
                    detail="File not found in storage",
                )

        timeline_item["upload_status"] = update_data.status.value
        if update_data.file_hash:
            timeline_item["file_hash"] = update_data.file_hash

        attachment_item = AttachmentItem(**timeline_item)

        updated = await service.update_timeline_item(
            db, parent_id, item_id, attachment_item, current_user.username,
        )

        logger.info(
            "Updated attachment status for %s %s, item %s, status %s, user %s",
            entity_type, parent_id, item_id, update_data.status, current_user.username,
        )

        return updated

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error updating attachment status for %s %s, item %s: %s",
            entity_type, parent_id, item_id, e,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update attachment status: {str(e)}",
        )


async def handle_generate_download_url(
    *,
    entity: Any,
    entity_type: str,
    parent_id: int,
    item_id: str,
    as_download: bool,
    current_user: "UserAccount",
) -> "PresignedDownloadResponse":
    """Shared logic for generating a presigned download URL for an attachment.

    ``entity`` must have a ``timeline_items`` attribute (list of dicts).
    """
    from app.core.storage_config import storage_config
    from app.models.enums import UploadStatus
    from app.models.models import PresignedDownloadResponse
    from app.services.storage_service import storage_service

    try:
        timeline_item = find_attachment_item(entity.timeline_items, item_id)
        if not timeline_item:
            raise HTTPException(
                status_code=404,
                detail=f"Attachment item {item_id} not found",
            )

        upload_status = normalize_upload_status(timeline_item.get("upload_status"))
        if upload_status != UploadStatus.COMPLETE.value:
            raise HTTPException(
                status_code=400,
                detail=f"Attachment upload still in progress (status: {upload_status})",
            )

        storage_key = timeline_item.get("storage_key")
        if not storage_key:
            raise HTTPException(
                status_code=400,
                detail="Attachment has no storage key",
            )

        file_exists = await storage_service.verify_file_exists(storage_key)
        if not file_exists:
            raise HTTPException(
                status_code=410,
                detail="File no longer available in storage",
            )

        download_url = await storage_service.generate_presigned_download_url(
            storage_key,
            expires_minutes=storage_config.download_timeout_minutes,
            filename=timeline_item.get("file_name"),
            as_attachment=as_download,
        )

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=storage_config.download_timeout_minutes,
        )

        logger.info(
            "Generated presigned download URL for %s %s, item %s, file %s, "
            "user %s, expires %s",
            entity_type, parent_id, item_id, timeline_item.get("file_name"),
            current_user.username, expires_at,
        )

        return PresignedDownloadResponse(
            download_url=download_url,
            filename=timeline_item.get("file_name") or "attachment",
            mime_type=timeline_item.get("mime_type") or "application/octet-stream",
            file_size=timeline_item.get("file_size") or 0,
            expires_at=expires_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error generating download URL for %s %s, item %s: %s",
            entity_type, parent_id, item_id, e,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate download URL: {str(e)}",
        )


# ---------------------------------------------------------------------------
# Authentication session helpers
# ---------------------------------------------------------------------------


def _normalize_cookie_expiry(expires_at: Optional[datetime]) -> Optional[datetime]:
    if isinstance(expires_at, datetime):
        if expires_at.tzinfo is None:
            return expires_at.replace(tzinfo=timezone.utc)
        return expires_at.astimezone(timezone.utc)
    return expires_at


def _cookie_kwargs(
    *,
    key: str,
    path: str,
    expires_at: Optional[datetime] = None,
    max_age: Optional[int] = None,
    httponly: Optional[bool] = None,
    samesite: Optional[str] = None,
) -> dict:
    """Build keyword arguments for ``Response.set_cookie`` from the settings registry."""
    kwargs: dict[str, object] = {
        "key": key,
        "httponly": get_local("auth.session.cookie_http_only") if httponly is None else httponly,
        "secure": get_local("auth.session.cookie_secure"),
        "samesite": get_local("auth.session.cookie_same_site") if samesite is None else samesite,
        "path": path,
    }

    domain = get_local("auth.session.cookie_domain")
    if domain:
        kwargs["domain"] = domain

    expiry = _normalize_cookie_expiry(expires_at)
    if isinstance(expiry, datetime):
        kwargs["expires"] = expiry
    elif expiry is not None:
        kwargs["expires"] = expiry

    if max_age is None:
        idle_hours = get_local("auth.session.idle_timeout_hours")
        max_age = int(idle_hours * 3600)
    kwargs["max_age"] = max_age

    return kwargs


def _delete_cookie(response: Response, *, key: str, path: str) -> None:
    cookie_domain = get_local("auth.session.cookie_domain")

    if cookie_domain:
        response.delete_cookie(key=key, path=path, domain=cookie_domain)
    else:
        response.delete_cookie(key=key, path=path)


def issue_session_cookie(response: Response, session_token: str, expires_at: datetime) -> None:
    """Attach the secure session cookie to the response.

    Args:
        response: FastAPI/Starlette response object to mutate.
        session_token: Opaque session token value to be stored in the cookie.
        expires_at: Absolute session expiry timestamp (UTC recommended).
    """

    if not isinstance(session_token, str) or not session_token:
        raise ValueError("session_token must be a non-empty string")

    if not isinstance(expires_at, datetime):
        raise TypeError("expires_at must be a datetime instance")

    expiry = _normalize_cookie_expiry(expires_at)
    kwargs = _cookie_kwargs(
        key=get_local("auth.session.cookie_name"),
        path=get_local("auth.session.cookie_path"),
        expires_at=expiry,
    )
    response.set_cookie(value=session_token, **kwargs)


def generate_csrf_token() -> str:
    """Return a new opaque CSRF token."""

    return secrets.token_urlsafe(32)


def issue_csrf_cookie(response: Response, csrf_token: str, expires_at: datetime) -> None:
    """Attach the readable CSRF cookie to the response."""

    if not isinstance(csrf_token, str) or not csrf_token:
        raise ValueError("csrf_token must be a non-empty string")

    expiry = _normalize_cookie_expiry(expires_at)
    kwargs = _cookie_kwargs(
        key=get_local("auth.csrf.cookie_name"),
        path=get_local("auth.session.cookie_path"),
        expires_at=expiry,
        httponly=False,
    )
    response.set_cookie(value=csrf_token, **kwargs)


def issue_authenticated_session_cookies(response: Response, session_token: str, expires_at: datetime) -> str:
    """Issue both the session cookie and the readable CSRF cookie."""

    issue_session_cookie(response, session_token, expires_at)
    csrf_token = generate_csrf_token()
    issue_csrf_cookie(response, csrf_token, expires_at)
    return csrf_token


def revoke_session_cookie(response: Response) -> None:
    """Delete the session cookie from the client response."""

    _delete_cookie(
        response,
        key=get_local("auth.session.cookie_name"),
        path=get_local("auth.session.cookie_path"),
    )


def revoke_csrf_cookie(response: Response) -> None:
    """Delete the readable CSRF cookie from the client response."""

    _delete_cookie(
        response,
        key=get_local("auth.csrf.cookie_name"),
        path=get_local("auth.session.cookie_path"),
    )


def revoke_authenticated_session_cookies(response: Response) -> None:
    """Delete both session and CSRF cookies from the client response."""

    revoke_session_cookie(response)
    revoke_csrf_cookie(response)


def read_session_cookie(request: Request) -> Optional[str]:
    """Return the session token from the incoming request, if present."""

    return request.cookies.get(get_local("auth.session.cookie_name"))


def read_csrf_cookie(request: Request) -> Optional[str]:
    """Return the CSRF token from the incoming request, if present."""

    return request.cookies.get(get_local("auth.csrf.cookie_name"))


def issue_oidc_browser_binding_cookie(response: Response, browser_binding_token: str, expires_at: datetime) -> None:
    """Attach the short-lived OIDC browser-binding cookie to the response."""

    if not isinstance(browser_binding_token, str) or not browser_binding_token:
        raise ValueError("browser_binding_token must be a non-empty string")

    expiry = _normalize_cookie_expiry(expires_at)
    now = datetime.now(timezone.utc)
    max_age = max(1, int((expiry - now).total_seconds())) if isinstance(expiry, datetime) else 300
    kwargs = _cookie_kwargs(
        key=get_local("oidc.browser_binding.cookie_name"),
        path="/api/v1/auth/oidc",
        expires_at=expiry,
        max_age=max_age,
        httponly=True,
    )
    response.set_cookie(value=browser_binding_token, **kwargs)


def revoke_oidc_browser_binding_cookie(response: Response) -> None:
    """Delete the OIDC browser-binding cookie from the client response."""

    _delete_cookie(
        response,
        key=get_local("oidc.browser_binding.cookie_name"),
        path="/api/v1/auth/oidc",
    )


def read_oidc_browser_binding_cookie(request: Request) -> Optional[str]:
    """Return the OIDC browser-binding token from the incoming request, if present."""

    return request.cookies.get(get_local("oidc.browser_binding.cookie_name"))