"""
Shared utilities for API routes.

This module contains common functionality used across multiple route modules,
including timeline item type discovery, human ID handling decorators, and
authentication session helpers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app.core.config import settings


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
# Authentication session helpers
# ---------------------------------------------------------------------------


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

    expiry = expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    else:
        expiry = expiry.astimezone(timezone.utc)

    kwargs = settings.cookie_kwargs(expires_at=expiry)
    response.set_cookie(value=session_token, **kwargs)


def revoke_session_cookie(response: Response) -> None:
    """Delete the session cookie from the client response."""

    if settings.session_cookie_domain:
        response.delete_cookie(
            key=settings.session_cookie_name,
            path=settings.session_cookie_path,
            domain=settings.session_cookie_domain,
        )
    else:
        response.delete_cookie(
            key=settings.session_cookie_name,
            path=settings.session_cookie_path,
        )


def read_session_cookie(request: Request) -> Optional[str]:
    """Return the session token from the incoming request, if present."""

    return request.cookies.get(settings.session_cookie_name)