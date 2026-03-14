"""Email notification service for user credential delivery."""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email notifications via SMTP.

    SMTP settings are hot-swappable — they are read fresh from the unified
    settings service on every send, so admin changes take effect immediately
    without a restart.
    """

    def __init__(self) -> None:
        # No settings cached at init — read per-send for hot-swap support
        pass

    async def _load_smtp_settings(self) -> dict:
        """Load SMTP settings through the unified precedence chain.

        Uses a one-off async session so that callers don't need to pass ``db``.
        """
        from app.core.database import async_session_factory
        from app.services.settings_service import SettingsService

        async with async_session_factory() as session:
            svc = SettingsService(session)  # type: ignore[arg-type]
            return {
                "host": await svc.get("smtp.host", default="localhost"),
                "port": await svc.get("smtp.port", default=1025),
                "username": await svc.get("smtp.username"),
                "password": await svc.get("smtp.password"),
                "use_tls": await svc.get("smtp.use_tls", default=False),
                "from_address": await svc.get(
                    "smtp.from_address", default="security-admin@example.com"
                ),
            }

    async def send_temporary_credential(
        self,
        *,
        recipient_email: str,
        username: str,
        temporary_password: str,
        expires_in_minutes: int = 30,
    ) -> str:
        """
        Send temporary credential to user via email.

        Args:
            recipient_email: Email address of the recipient
            username: Username for the account
            temporary_password: Temporary password to send
            expires_in_minutes: How long the credential is valid

        Returns:
            Message ID or delivery reference

        Raises:
            Exception: If email delivery fails
        """
        subject = "Your Temporary Intercept Credentials"
        
        body_text = f"""
Hello,

A temporary password has been issued for your Intercept account.

Username: {username}
Temporary Password: {temporary_password}

This password will expire in {expires_in_minutes} minutes.

You will be required to change your password upon first login.

If you did not request this credential reset, please contact your administrator immediately.

---
Intercept Security Platform
"""

        body_html = f"""
<html>
<body>
<p>Hello,</p>

<p>A temporary password has been issued for your Intercept account.</p>

<p>
<strong>Username:</strong> {username}<br>
<strong>Temporary Password:</strong> <code>{temporary_password}</code>
</p>

<p><em>This password will expire in {expires_in_minutes} minutes.</em></p>

<p>You will be required to change your password upon first login.</p>

<p><small>If you did not request this credential reset, please contact your administrator immediately.</small></p>

<hr>
<p><small>Intercept Security Platform</small></p>
</body>
</html>
"""

        return await self._send_email(
            recipient=recipient_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )

    async def _send_email(
        self,
        *,
        recipient: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> str:
        """
        Send an email via SMTP.

        Args:
            recipient: Email address of the recipient
            subject: Email subject line
            body_text: Plain text body
            body_html: Optional HTML body

        Returns:
            Message ID or delivery reference
        """
        smtp = await self._load_smtp_settings()
        smtp_host = smtp["host"]
        smtp_port = int(smtp["port"])
        smtp_username = smtp["username"]
        smtp_password = smtp["password"]
        smtp_use_tls = smtp["use_tls"]
        smtp_from_address = smtp["from_address"]

        # For development/testing, just log the email instead of sending
        if not smtp_host or smtp_host == "localhost":
            logger.info(
                f"[EMAIL STUB] Would send email to {recipient}:\n"
                f"Subject: {subject}\n"
                f"Body: {body_text[:200]}..."
            )
            return f"stub-message-id-{recipient}"

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["From"] = smtp_from_address
            msg["To"] = recipient
            msg["Subject"] = subject

            # Attach text and HTML parts
            part1 = MIMEText(body_text, "plain")
            msg.attach(part1)

            if body_html:
                part2 = MIMEText(body_html, "html")
                msg.attach(part2)

            # Send via SMTP — run blocking call in a thread to avoid blocking the event loop
            def _smtp_send() -> None:
                if smtp_use_tls:
                    server = smtplib.SMTP(smtp_host, smtp_port)
                    server.starttls()
                else:
                    server = smtplib.SMTP(smtp_host, smtp_port)

                if smtp_username and smtp_password:
                    server.login(smtp_username, smtp_password)

                server.send_message(msg)
                server.quit()

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _smtp_send)

            logger.info(f"Email sent successfully to {recipient}")
            return msg["Message-ID"] or f"sent-{recipient}"

        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {e}")
            raise


# Singleton instance
email_service = EmailService()
