"""Canonical conversion from HTTP requests to service-layer metadata."""

from fastapi import Request

from app.core.client_address import request_client_address
from app.core.request_context import get_correlation_id
from app.services.audit_service import AuditContext


def build_audit_context(request: Request) -> AuditContext:
    """Build the canonical service-layer context from an HTTP request."""
    return AuditContext(
        ip_address=request_client_address(request),
        user_agent=request.headers.get("user-agent"),
        correlation_id=get_correlation_id(request.headers),
    )


def build_request_metadata(request: Request) -> AuditContext:
    """Compatibility name for callers that still describe context as metadata."""
    return build_audit_context(request)
