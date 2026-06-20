from __future__ import annotations

from app.services.email_evidence_service import (
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
