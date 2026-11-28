"""
Shared utilities for API routes.

This module contains common functionality used across multiple route modules,
including timeline item type discovery, human ID handling decorators,
authentication session helpers, and attachment upload/download helpers.
"""
from __future__ import annotations

import inspect
import logging
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from math import ceil
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings_registry import get_local
from app.services.timeline_attachment_service import (
    expected_attachment_storage_prefix,
    find_attachment_item,
    normalize_upload_status,
    prepare_attachment_upload,
    sign_attachment_upload,
    validate_attachment_upload,
)

if TYPE_CHECKING:
    from app.models.models import (
        PresignedDownloadResponse,
        PresignedUploadRequest,
        PresignedUploadResponse,
        UserAccount,
    )

logger = logging.getLogger(__name__)


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

    CLIENT_WRITABLE_ATTACHMENT_FIELDS = {
        "id",
        "type",
        "description",
        "created_at",
        "timestamp",
        "created_by",
        "tags",
        "flagged",
        "highlighted",
        "parent_id",
        "replies",
        "audit",
    }
    
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

        if item_type == "attachment":
            timeline_item = {
                key: value
                for key, value in timeline_item.items()
                if key in CLIENT_WRITABLE_ATTACHMENT_FIELDS
            }
        
        item_class = timeline_item_types[item_type]
        try:
            return item_class(**timeline_item)
        except ValidationError as error:
            if item_type != "process_tree":
                raise
            issue = error.errors(include_url=False, include_context=False, include_input=False)[0]
            field = ".".join(str(part) for part in issue["loc"])
            raise HTTPException(status_code=422, detail=f"{field}: {issue['msg']}") from error
    
    return convert_timeline_item


def create_human_id_decorator(id_prefix: str, default_param_name: str = "id"):
    """
    Create a human ID decorator for the specified prefix and default parameter name.
    
    Args:
        id_prefix: The canonical human ID prefix (e.g., "ALT", "CAS"). A
            trailing hyphen is also accepted for compatibility.
        default_param_name: Default parameter name to check for IDs
        
    Returns:
        Decorator function configured for the specified prefix
    """
    prefix_marker = f"{id_prefix.rstrip('-')}-"

    def handle_human_id(param_name: str = default_param_name):
        """
        Decorator to handle human ID redirects for endpoints.
        
        Args:
            param_name: The parameter name that contains the ID
        """
        def decorator(func: Callable) -> Callable:
            endpoint_signature = inspect.signature(func, eval_str=True)

            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Get the ID value from kwargs
                id_value = kwargs.get(param_name)
                
                # Check if it's a human ID and redirect if so
                if isinstance(id_value, str) and id_value.startswith(prefix_marker):
                    try:
                        numeric_id = int(id_value[len(prefix_marker):])
                        
                        # Get the HTTP request object to build the redirect URL.
                        request = next(
                            (
                                argument
                                for argument in (*args, *kwargs.values())
                                if isinstance(argument, Request)
                            ),
                            None,
                        )

                        if request is not None:
                            # Replace the human ID in the URL path with numeric ID
                            original_path = str(request.url.path)
                            redirect_path = original_path.replace(id_value, str(numeric_id))
                            redirect_url = redirect_path
                            if request.url.query:
                                redirect_url = f"{redirect_path}?{request.url.query}"
                            return RedirectResponse(url=redirect_url, status_code=308)
                        else:
                            raise HTTPException(status_code=500, detail="Request object not found for redirect")
                            
                    except ValueError:
                        raise HTTPException(status_code=400, detail=f"Invalid {prefix_marker} ID format")
                
                # If we reach here, it means the ID is already numeric (redirect already happened)
                # Just ensure it's an integer if it's a string representation
                if isinstance(id_value, str) and id_value.isdigit():
                    kwargs[param_name] = int(id_value)
                
                # Call the original function
                return await func(*args, **kwargs)

            wrapper.__signature__ = endpoint_signature.replace(  # type: ignore[attr-defined]
                parameters=[
                    parameter.replace(annotation=int | str)
                    if parameter.name == param_name
                    else parameter
                    for parameter in endpoint_signature.parameters.values()
                ]
            )
            return wrapper
        return decorator
    
    return handle_human_id


# ---------------------------------------------------------------------------
# Attachment upload / download helpers
# ---------------------------------------------------------------------------


async def handle_generate_upload_url(
    *,
    entity_type: str,
    parent_id: int,
    request_data: "PresignedUploadRequest",
    current_user: "UserAccount",
    db: AsyncSession,
    service: Any,
) -> "PresignedUploadResponse":
    """Create an attachment timeline item and return a staging PUT URL."""
    try:
        max_file_size = await validate_attachment_upload(request_data, db)
        attachment_item = prepare_attachment_upload(
            entity_type=entity_type,
            parent_id=parent_id,
            request_data=request_data,
            current_user=current_user,
        )
        response = await sign_attachment_upload(
            attachment_item.id, attachment_item.upload_storage_key, max_file_size,
        )
        await service.add_timeline_item(db, parent_id, attachment_item, current_user.username)

        logger.info(
            "Generated presigned upload URL for %s %s, item %s, file %s, "
            "size %s bytes, user %s, expires %s",
            entity_type, parent_id, attachment_item.id, attachment_item.file_name,
            request_data.file_size, current_user.username, response.expires_at,
        )
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error generating upload URL for %s %s", entity_type, parent_id)
        raise HTTPException(status_code=500, detail="Failed to generate upload URL")


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
        if not str(storage_key).startswith(expected_attachment_storage_prefix(entity_type, parent_id, item_id)):
            raise HTTPException(
                status_code=403,
                detail="Attachment storage key does not belong to this entity",
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
    except Exception:
        logger.exception(
            "Error generating download URL for %s %s, item %s",
            entity_type,
            parent_id,
            item_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to generate download URL",
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
    secure: Optional[bool] = None,
    include_configured_domain: bool = True,
) -> dict:
    """Build cookie attributes, aligning ``Max-Age`` with an absolute expiry."""
    kwargs: dict[str, object] = {
        "key": key,
        "httponly": get_local("auth.session.cookie_http_only") if httponly is None else httponly,
        "secure": get_local("auth.session.cookie_secure") if secure is None else secure,
        "samesite": get_local("auth.session.cookie_same_site") if samesite is None else samesite,
        "path": path,
    }

    if include_configured_domain:
        domain = get_local("auth.session.cookie_domain")
        if domain:
            kwargs["domain"] = domain

    expiry = _normalize_cookie_expiry(expires_at)
    if isinstance(expiry, datetime):
        kwargs["expires"] = expiry
    elif expiry is not None:
        kwargs["expires"] = expiry

    if max_age is None:
        if isinstance(expiry, datetime):
            max_age = max(
                0,
                ceil((expiry - datetime.now(timezone.utc)).total_seconds()),
            )
        else:
            idle_hours = get_local("auth.session.idle_timeout_hours")
            max_age = int(idle_hours * 3600)
    kwargs["max_age"] = max_age

    return kwargs


def _delete_cookie(
    response: Response,
    *,
    key: str,
    path: str,
    secure: bool = False,
    include_configured_domain: bool = True,
) -> None:
    cookie_domain = (
        get_local("auth.session.cookie_domain")
        if include_configured_domain
        else None
    )

    if cookie_domain:
        response.delete_cookie(
            key=key,
            path=path,
            domain=cookie_domain,
            secure=secure,
        )
    else:
        response.delete_cookie(key=key, path=path, secure=secure)


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


def _oidc_browser_binding_cookie_secure() -> bool:
    return urlsplit(str(get_local("oidc.redirect_uri"))).scheme.lower() == "https"


def _oidc_browser_binding_cookie_name() -> str:
    """Return a cookie-tossing-resistant name for secure deployments."""

    configured_name = str(get_local("oidc.browser_binding.cookie_name"))
    if _oidc_browser_binding_cookie_secure():
        if configured_name.startswith("__Host-"):
            return configured_name
        return f"__Host-{configured_name}"
    # __Host- cookies require Secure. Preserve loopback HTTP development flows
    # when an operator carries a production-prefixed name into local settings.
    return configured_name.removeprefix("__Host-")


def issue_oidc_browser_binding_cookie(response: Response, browser_binding_token: str, expires_at: datetime) -> None:
    """Attach the short-lived OIDC browser-binding cookie to the response."""

    if not isinstance(browser_binding_token, str) or not browser_binding_token:
        raise ValueError("browser_binding_token must be a non-empty string")

    expiry = _normalize_cookie_expiry(expires_at)
    kwargs = _cookie_kwargs(
        key=_oidc_browser_binding_cookie_name(),
        # __Host- cookies require Path=/ and prohibit Domain. The broader path
        # does not expose the HttpOnly value to script and the five-minute
        # lifetime bounds its use.
        path="/",
        expires_at=expiry,
        httponly=True,
        # The authorization response is a top-level cross-site navigation
        # from the IdP. A Strict transaction cookie would suppress the PKCE
        # verifier and make every otherwise-valid callback fail.
        samesite="lax",
        secure=_oidc_browser_binding_cookie_secure(),
        include_configured_domain=False,
    )
    response.set_cookie(value=browser_binding_token, **kwargs)


def revoke_oidc_browser_binding_cookie(response: Response) -> None:
    """Delete the OIDC browser-binding cookie from the client response."""

    _delete_cookie(
        response,
        key=_oidc_browser_binding_cookie_name(),
        path="/",
        secure=_oidc_browser_binding_cookie_secure(),
        include_configured_domain=False,
    )


def read_oidc_browser_binding_cookie(request: Request) -> Optional[str]:
    """Return the OIDC browser-binding token from the incoming request, if present."""

    return request.cookies.get(_oidc_browser_binding_cookie_name())
