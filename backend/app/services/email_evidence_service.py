from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import PurePath
from tempfile import NamedTemporaryFile
from typing import Any

from app.models.models import EmailItem


EMAIL_EVIDENCE_MIME_TYPES = {"message/rfc822", "application/vnd.ms-outlook"}
EMAIL_EVIDENCE_EXTENSIONS = {".eml", ".msg"}
MAX_EMAIL_BODY_CHARS = 20000
HTML_PREFIXES = ("<!doctype html", "<html", "<body", "<p", "<div", "<span", "<table")


class _BodyTextExtractor(HTMLParser):
    _BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "br", "div", "footer",
        "h1", "h2", "h3", "h4", "h5", "h6", "header", "li", "main", "p",
        "section", "table", "td", "th", "tr",
    }
    _SKIP_TAGS = {"head", "script", "style"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0
        self._href_stack: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return

        if self._skip_depth > 0:
            return

        if tag in self._BLOCK_TAGS:
            self.parts.append("\n\n" if tag != "br" else "\n")

        if tag == "a":
            attrs_by_name = {name.lower(): value for name, value in attrs}
            self._href_stack.append(attrs_by_name.get("href"))

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return

        if self._skip_depth > 0:
            return

        if tag == "a":
            href = self._href_stack.pop() if self._href_stack else None
            cleaned_href = _clean_link_url(href)
            if cleaned_href:
                self.parts.append(f" [{cleaned_href}]")

        if tag in self._BLOCK_TAGS:
            self.parts.append("\n\n" if tag != "br" else "\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        output: list[str] = []
        for line in lines:
            if line:
                output.append(line)
            elif output and output[-1]:
                output.append("")
        while output and not output[-1]:
            output.pop()
        return "\n".join(output)


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


def parse_email_evidence(
    data: bytes,
    filename: str | None,
    mime_type: str | None,
) -> ParsedEmailEvidence:
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
        raise EmailEvidenceParseError(
            "MSG email parsing requires the optional extract_msg package"
        ) from exc

    message: Any | None = None
    try:
        with NamedTemporaryFile(suffix=".msg") as tmp:
            tmp.write(data)
            tmp.flush()
            message = extract_msg.Message(tmp.name)
            recipient_headers = [
                _clean_header(getattr(message, "to", None)),
                _clean_header(getattr(message, "cc", None)),
                _clean_header(getattr(message, "bcc", None)),
            ]
            body = getattr(message, "body", None) or getattr(message, "htmlBody", None)
            parsed = ParsedEmailEvidence(
                sender=_clean_header(getattr(message, "sender", None)),
                recipient=", ".join(header for header in recipient_headers if header) or None,
                subject=_clean_header(getattr(message, "subject", None)),
                message_id=_clean_header(
                    getattr(message, "message_id", None)
                    or getattr(message, "messageId", None)
                ),
                body=_clean_body(body),
                timestamp=_parse_date(getattr(message, "date", None)),
            )
            return parsed
    except Exception as exc:  # pragma: no cover - optional parser exception type is broad
        raise EmailEvidenceParseError("Unable to parse MSG email file") from exc
    finally:
        close = getattr(message, "close", None)
        if close is not None:
            try:
                close()
            except Exception:
                # Parsing has already completed or raised a more useful error.
                pass


def _addresses_to_text(headers: list[str]) -> str | None:
    addresses = []
    for name, address in getaddresses(headers):
        display = f"{name} <{address}>" if name and address else address or name
        if display:
            addresses.append(display)
    return ", ".join(addresses) or None


def _clean_header(value: Any) -> str | None:
    cleaned = _coerce_text(value).replace("\x00", "").replace("\r", " ").replace("\n", " ")
    cleaned = " ".join(cleaned.split())
    return cleaned or None


def _clean_body(value: Any) -> str | None:
    cleaned = _coerce_text(value).replace("\x00", "")
    if _looks_like_html(cleaned):
        cleaned = _html_to_text(cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return None
    return cleaned[:MAX_EMAIL_BODY_CHARS]


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _looks_like_html(value: str) -> bool:
    normalized = value.lstrip().lower()
    return normalized.startswith(HTML_PREFIXES) or "<body" in normalized


def _html_to_text(value: str) -> str:
    parser = _BodyTextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        return value
    return unescape(parser.text())


def _clean_link_url(value: str | None) -> str | None:
    cleaned = _clean_header(value)
    if not cleaned or cleaned.lower().startswith(("javascript:", "data:")):
        return None
    return cleaned


def _parse_date(value: Any) -> Any | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return parsedate_to_datetime(str(value))
    except (TypeError, ValueError, IndexError, AttributeError):
        return None
