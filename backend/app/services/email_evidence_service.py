from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import PurePath
from tempfile import NamedTemporaryFile
from typing import Any

from app.models.models import EmailItem


EMAIL_EVIDENCE_MIME_TYPES = {"message/rfc822", "application/vnd.ms-outlook"}
EMAIL_EVIDENCE_EXTENSIONS = {".eml", ".msg"}
MAX_EMAIL_BODY_CHARS = 20000


@dataclass(frozen=True)
class ParsedEmailEvidence:
    sender: str | None
    recipient: str | None
    subject: str | None
    message_id: str | None
    body: str | None
    timestamp: Any | None = None


class EmailEvidenceParseError(ValueError):
    """Raised when an uploaded email evidence file cannot be parsed."""


def is_email_evidence_file(filename: str | None, mime_type: str | None) -> bool:
    extension = PurePath(filename or "").suffix.lower()
    normalized_mime = (mime_type or "").strip().lower()
    return extension in EMAIL_EVIDENCE_EXTENSIONS or normalized_mime in EMAIL_EVIDENCE_MIME_TYPES


def parse_email_evidence(data: bytes, filename: str | None, mime_type: str | None) -> ParsedEmailEvidence:
    extension = PurePath(filename or "").suffix.lower()
    normalized_mime = (mime_type or "").strip().lower()

    if extension == ".msg" or normalized_mime == "application/vnd.ms-outlook":
        return _parse_msg(data)
    return _parse_eml(data)


def build_email_timeline_item(parsed: ParsedEmailEvidence, *, created_by: str) -> EmailItem:
    item_data = {
        "type": "email",
        "sender": parsed.sender,
        "recipient": parsed.recipient,
        "subject": parsed.subject,
        "message_id": parsed.message_id,
        "description": parsed.body,
        "created_by": created_by,
    }
    if parsed.timestamp is not None:
        item_data["timestamp"] = parsed.timestamp
    return EmailItem(**item_data)


def _parse_eml(data: bytes) -> ParsedEmailEvidence:
    try:
        message = BytesParser(policy=policy.default).parsebytes(data)
    except Exception as exc:  # pragma: no cover - parser exception type is broad
        raise EmailEvidenceParseError("Unable to parse EML email file") from exc

    body_part = message.get_body(preferencelist=("plain", "html"))
    body = body_part.get_content() if body_part else None
    return ParsedEmailEvidence(
        sender=_addresses_to_text(message.get_all("from", [])),
        recipient=_addresses_to_text(
            [
                *(message.get_all("to", []) or []),
                *(message.get_all("cc", []) or []),
                *(message.get_all("bcc", []) or []),
            ]
        ),
        subject=str(message.get("subject") or "").strip() or None,
        message_id=str(message.get("message-id") or "").strip() or None,
        body=_clean_body(body),
        timestamp=_parse_date(message.get("date")),
    )


def _parse_msg(data: bytes) -> ParsedEmailEvidence:
    try:
        import extract_msg  # type: ignore[import-not-found]
    except ImportError as exc:
        raise EmailEvidenceParseError("MSG email parsing requires the optional extract_msg package") from exc

    try:
        with NamedTemporaryFile(suffix=".msg") as tmp:
            tmp.write(data)
            tmp.flush()
            message = extract_msg.Message(tmp.name)
            parsed = ParsedEmailEvidence(
                sender=_clean_header(getattr(message, "sender", None)),
                recipient=_clean_header(getattr(message, "to", None)),
                subject=_clean_header(getattr(message, "subject", None)),
                message_id=_clean_header(getattr(message, "message_id", None)),
                body=_clean_body(getattr(message, "body", None)),
                timestamp=_parse_date(getattr(message, "date", None)),
            )
            close = getattr(message, "close", None)
            if close:
                close()
            return parsed
    except Exception as exc:  # pragma: no cover - optional parser exception type is broad
        raise EmailEvidenceParseError("Unable to parse MSG email file") from exc


def _addresses_to_text(headers: list[str]) -> str | None:
    addresses = []
    for name, address in getaddresses(headers):
        display = f"{name} <{address}>" if name and address else address or name
        if display:
            addresses.append(display)
    return ", ".join(addresses) or None


def _clean_header(value: Any) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _clean_body(value: Any) -> str | None:
    cleaned = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return None
    return cleaned[:MAX_EMAIL_BODY_CHARS]


def _parse_date(value: Any) -> Any | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(str(value))
    except (TypeError, ValueError, IndexError, AttributeError):
        return None
