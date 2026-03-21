"""Shared payload builders for all timeline item types.

Each ``make_*`` function returns a JSON-serialisable dict that the
``POST /{entity_id}/timeline`` endpoint accepts.  The functions are
intentionally stateless — every call produces a fresh, isolated payload
so tests can safely parametrise over them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.models.enums import ObservableType, Protocol, SystemType


# ---------------------------------------------------------------------------
# Base helper
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_item(item_id: str, item_type: str, **overrides: Any) -> dict[str, Any]:
    now = _now_iso()
    base: dict[str, Any] = {
        "id": item_id,
        "type": item_type,
        "description": overrides.pop("description", f"Test {item_type} item"),
        "created_at": now,
        "timestamp": now,
        "created_by": overrides.pop("created_by", "test-user"),
        "tags": [],
        "flagged": False,
        "highlighted": False,
        "enrichments": {},
        "replies": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Simple (non-variant) item builders
# ---------------------------------------------------------------------------

def make_note(item_id: str = "note-1") -> dict[str, Any]:
    return _base_item(item_id, "note", description="Investigation notes from analyst")


def make_attachment(item_id: str = "attachment-1") -> dict[str, Any]:
    return _base_item(
        item_id,
        "attachment",
        file_name="evidence.pcap",
        mime_type="application/vnd.tcpdump.pcap",
        file_size=102400,
        upload_status="COMPLETE",
        url="https://storage.example.com/evidence.pcap",
    )


def make_ttp(item_id: str = "ttp-1") -> dict[str, Any]:
    return _base_item(
        item_id,
        "ttp",
        mitre_id="T1059",
        title="Command and Scripting Interpreter",
        tactic="Execution",
        technique="PowerShell",
    )


def make_link(item_id: str = "link-1") -> dict[str, Any]:
    return _base_item(
        item_id,
        "link",
        url="https://reference.example.com/article",
    )


def make_email_item(item_id: str = "email-1") -> dict[str, Any]:
    return _base_item(
        item_id,
        "email",
        sender="attacker@evil.example.com",
        recipient="victim@corp.example.com",
        subject="Urgent: Password reset required",
        message_id="<abc123@evil.example.com>",
    )


def make_process(item_id: str = "process-1") -> dict[str, Any]:
    return _base_item(
        item_id,
        "process",
        process_name="powershell.exe",
        process_id=4832,
        parent_process_id=1024,
        command_line="powershell.exe -enc SQBFAFgA",
        user_account="CORP\\admin",
        duration=12,
        exit_code=0,
    )


def make_forensic_artifact(item_id: str = "forensic-1") -> dict[str, Any]:
    return _base_item(
        item_id,
        "forensic_artifact",
        hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        hash_type="sha256",
        url="https://evidence.example.com/artifact/disk-image.dd",
    )


# ---------------------------------------------------------------------------
# Reference-type builders (need pre-created entity IDs)
# ---------------------------------------------------------------------------

def make_case_ref(case_id: int, item_id: str = "case-ref-1") -> dict[str, Any]:
    return _base_item(item_id, "case", case_id=case_id)


def make_alert_ref(alert_id: int, item_id: str = "alert-ref-1") -> dict[str, Any]:
    return _base_item(item_id, "alert", alert_id=alert_id)


def make_task_ref(item_id: str = "task-ref-1") -> dict[str, Any]:
    return _base_item(
        item_id,
        "task",
        title="Follow-up investigation task",
        status="TODO",
        priority="MEDIUM",
    )


# ---------------------------------------------------------------------------
# Variant builders — observable
# ---------------------------------------------------------------------------

def make_observable(
    observable_type: str,
    observable_value: str,
    item_id: str = "observable-1",
) -> dict[str, Any]:
    return _base_item(
        item_id,
        "observable",
        observable_type=observable_type,
        observable_value=observable_value,
    )


_OBSERVABLE_SAMPLE_VALUES: dict[str, str] = {
    "IP": "192.168.1.1",
    "DOMAIN": "example.com",
    "HASH": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "FILENAME": "malware.exe",
    "URL": "https://evil.example.com/payload",
    "EMAIL": "user@example.com",
    "REGISTRY_KEY": r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    "PROCESS_NAME": "cmd.exe",
}

OBSERVABLE_VARIANTS = [
    pytest.param(t.value, _OBSERVABLE_SAMPLE_VALUES[t.value], id=f"observable-{t.value.lower()}")
    for t in ObservableType
]


# ---------------------------------------------------------------------------
# Variant builders — system
# ---------------------------------------------------------------------------

def make_system(system_type: str, item_id: str = "system-1") -> dict[str, Any]:
    return _base_item(
        item_id,
        "system",
        hostname="srv-prod-01.corp.local",
        ip_address="10.0.1.42",
        system_type=system_type,
    )


SYSTEM_TYPE_VARIANTS = [
    pytest.param(t.value, id=f"system-{t.value.lower()}")
    for t in SystemType
]


# ---------------------------------------------------------------------------
# Variant builders — actors
# ---------------------------------------------------------------------------

def make_internal_actor(
    *,
    item_id: str = "internal-actor-1",
    **kwargs: Any,
) -> dict[str, Any]:
    payload = _base_item(item_id, "internal_actor")
    payload.update(kwargs)
    return payload


INTERNAL_ACTOR_VARIANTS = [
    pytest.param(
        {"user_id": "alice@example.com"},
        id="internal-actor-by-user-id",
    ),
    pytest.param(
        {"user_id": "bob", "name": "Bob Smith", "is_privileged": True},
        id="internal-actor-privileged",
    ),
]


def make_external_actor(
    *,
    item_id: str = "external-actor-1",
    **kwargs: Any,
) -> dict[str, Any]:
    payload = _base_item(item_id, "external_actor")
    payload.update(kwargs)
    return payload


EXTERNAL_ACTOR_VARIANTS = [
    pytest.param({"name": "Vendor Corp"}, id="external-actor-by-name"),
    pytest.param(
        {"name": "Partner Inc", "org": "Technology Partners", "contact_email": "sec@partner.com"},
        id="external-actor-with-details",
    ),
]


def make_threat_actor(
    *,
    item_id: str = "threat-actor-1",
    **kwargs: Any,
) -> dict[str, Any]:
    payload = _base_item(item_id, "threat_actor")
    payload.update(kwargs)
    return payload


THREAT_ACTOR_VARIANTS = [
    pytest.param(
        {"name": "APT28", "confidence": 85},
        id="threat-actor-by-name",
    ),
    pytest.param(
        {"tag_id": "TA0001", "name": "Fancy Bear"},
        id="threat-actor-by-tag-id",
    ),
    pytest.param(
        {"name": "Lazarus Group", "org": "DPRK-linked", "confidence": 60},
        id="threat-actor-with-org",
    ),
]


# ---------------------------------------------------------------------------
# Variant builders — network traffic
# ---------------------------------------------------------------------------

def make_network_traffic(protocol: str, item_id: str = "nettraffic-1") -> dict[str, Any]:
    return _base_item(
        item_id,
        "network_traffic",
        source_ip="10.0.1.100",
        destination_ip="203.0.113.50",
        source_port=49152,
        destination_port=443,
        protocol=protocol,
        bytes_sent=1024,
        bytes_received=4096,
        duration=3,
    )


PROTOCOL_VARIANTS = [
    pytest.param(t.value, id=f"network-{t.value.lower()}")
    for t in Protocol
]


# ---------------------------------------------------------------------------
# Variant builders — registry change
# ---------------------------------------------------------------------------

def make_registry_change(operation: str, item_id: str = "regchange-1") -> dict[str, Any]:
    return _base_item(
        item_id,
        "registry_change",
        registry_key=r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        registry_value="MalwarePayload",
        old_data="" if operation != "CREATE" else None,
        new_data="C:\\malware.exe" if operation != "DELETE" else None,
        operation=operation,
        user_account="CORP\\admin",
    )


REGISTRY_OP_VARIANTS = [
    pytest.param("CREATE", id="registry-create"),
    pytest.param("MODIFY", id="registry-modify"),
    pytest.param("DELETE", id="registry-delete"),
]
