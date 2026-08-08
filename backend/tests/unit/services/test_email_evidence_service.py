from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.email_evidence_service import (
    EmailEvidenceParseError,
    build_email_timeline_item,
    is_email_evidence_file,
    parse_email_evidence,
)


def test_is_email_evidence_file_matches_extension_or_mime_type() -> None:
    assert is_email_evidence_file("message.eml", "application/octet-stream")
    assert is_email_evidence_file("message.bin", "message/rfc822")
    assert is_email_evidence_file("message.msg", "application/octet-stream")
    assert is_email_evidence_file("message.bin", "application/vnd.ms-outlook")
    assert not is_email_evidence_file("report.txt", "text/plain")


def test_parse_eml_extracts_email_timeline_fields() -> None:
    data = (
        b"From: Attacker <attacker@evil.example>\r\n"
        b"To: Victim <victim@corp.example>\r\n"
        b"Cc: SOC <soc@corp.example>\r\n"
        b"Subject: Urgent reset\r\n"
        b"Message-ID: <abc123@evil.example>\r\n"
        b"Date: Fri, 20 Jun 2026 10:15:00 +0000\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Click the link immediately.\r\n"
    )

    parsed = parse_email_evidence(data, "message.eml", "message/rfc822")
    item = build_email_timeline_item(parsed, created_by="analyst")

    assert item.type == "email"
    assert item.sender == "Attacker <attacker@evil.example>"
    assert item.recipient == "Victim <victim@corp.example>, SOC <soc@corp.example>"
    assert item.subject == "Urgent reset"
    assert item.message_id == "<abc123@evil.example>"
    assert item.description == "Click the link immediately."
    assert item.created_by == "analyst"
    assert item.timestamp.year == 2026


def test_parse_msg_extracts_email_timeline_fields(monkeypatch) -> None:
    closed = []

    class FakeMessage:
        def __init__(self, path: str) -> None:
            assert Path(path).read_bytes() == b"msg bytes"
            self.sender = "Attacker <attacker@evil.example>"
            self.to = "Victim <victim@corp.example>"
            self.cc = "SOC <soc@corp.example>"
            self.subject = "Urgent reset\x00"
            self.messageId = "<abc123@evil.example>"
            self.date = datetime(2026, 6, 20, 10, 15, tzinfo=timezone.utc)
            self.body = None
            self.htmlBody = (
                b"<p>Click <a href=\"https://evil.example/reset\">"
                b"the link</a> immediately.</p>\x00"
                b"<p>Then report it.</p>"
            )

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setitem(sys.modules, "extract_msg", SimpleNamespace(Message=FakeMessage))

    parsed = parse_email_evidence(
        b"msg bytes",
        "message.msg",
        "application/vnd.ms-outlook",
    )
    item = build_email_timeline_item(parsed, created_by="analyst")

    assert item.type == "email"
    assert item.sender == "Attacker <attacker@evil.example>"
    assert item.recipient == "Victim <victim@corp.example>, SOC <soc@corp.example>"
    assert item.subject == "Urgent reset"
    assert item.message_id == "<abc123@evil.example>"
    assert item.description == (
        "Click the link [https://evil.example/reset] immediately.\n\n"
        "Then report it."
    )
    assert item.created_by == "analyst"
    assert item.timestamp.year == 2026
    assert closed == [True]


def test_parse_msg_closes_message_when_field_extraction_fails(monkeypatch) -> None:
    closed: list[bool] = []

    class BrokenMessage:
        sender = "sender@example.com"
        to = "recipient@example.com"
        cc = None
        bcc = None
        subject = "Broken message"
        message_id = None
        messageId = None
        date = None

        def __init__(self, _path: str) -> None:
            pass

        @property
        def body(self) -> str:
            raise RuntimeError("body extraction failed")

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setitem(
        sys.modules,
        "extract_msg",
        SimpleNamespace(Message=BrokenMessage),
    )

    with pytest.raises(EmailEvidenceParseError, match="Unable to parse MSG"):
        parse_email_evidence(
            b"broken msg bytes",
            "message.msg",
            "application/vnd.ms-outlook",
        )

    assert closed == [True]
