"""Notification services for email and other channels."""

from app.services.notifications.email_service import EmailService, email_service

__all__ = [
    "EmailService",
    "email_service",
]
