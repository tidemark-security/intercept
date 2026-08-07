"""Security and canonicalization helpers for untrusted collector data."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlparse

from app.services.collectors.models import CollectorErrorCode

MAX_EXTERNAL_ID_LENGTH = 500
MAX_RAW_PAYLOAD_BYTES = 2_000_000
MAX_NORMALIZED_PAYLOAD_BYTES = 1_000_000
MAX_ERROR_SUMMARY_LENGTH = 500
REDACTED_ERROR_SUMMARIES: dict[CollectorErrorCode, str] = {
    CollectorErrorCode.AUTHENTICATION_FAILED: "Provider authentication failed",
    CollectorErrorCode.AUTHORIZATION_FAILED: "Provider authorization failed",
    CollectorErrorCode.RATE_LIMITED: "Provider rate limit reached",
    CollectorErrorCode.PROVIDER_UNAVAILABLE: "Provider is temporarily unavailable",
    CollectorErrorCode.INVALID_PROVIDER_RESPONSE: "Provider returned an invalid response",
    CollectorErrorCode.PAYLOAD_TOO_LARGE: "Provider payload exceeded the configured limit",
    CollectorErrorCode.NORMALIZATION_FAILED: "Provider event normalization failed",
    CollectorErrorCode.VALIDATION_REQUIRED: "External validation is required",
    CollectorErrorCode.VALIDATION_FAILED: "External validation failed",
    CollectorErrorCode.STALE_REVISION: "The event revision is no longer current",
    CollectorErrorCode.ALERT_INGESTION_FAILED: "Alert ingestion failed",
    CollectorErrorCode.CONFIGURATION_INVALID: "Collector configuration is invalid",
}


class CollectorSecurityError(ValueError):
    def __init__(self, code: CollectorErrorCode, summary: str | None = None) -> None:
        self.code = code
        self.summary = (summary or REDACTED_ERROR_SUMMARIES[code])[:MAX_ERROR_SUMMARY_LENGTH]
        super().__init__(self.summary)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    ).encode("utf-8")


def canonical_hash(value: Any, *, maximum_bytes: int = MAX_NORMALIZED_PAYLOAD_BYTES) -> str:
    encoded = canonical_json(value)
    if len(encoded) > maximum_bytes:
        raise CollectorSecurityError(CollectorErrorCode.PAYLOAD_TOO_LARGE)
    return hashlib.sha256(encoded).hexdigest()


def validate_external_event(external_id: str, raw_payload: Mapping[str, Any]) -> None:
    if not external_id or len(external_id) > MAX_EXTERNAL_ID_LENGTH:
        raise CollectorSecurityError(
            CollectorErrorCode.INVALID_PROVIDER_RESPONSE,
            "Provider event identity is missing or too long",
        )
    canonical_hash(raw_payload, maximum_bytes=MAX_RAW_PAYLOAD_BYTES)


def validate_allowed_url(url: str, allowed_hosts: Sequence[str]) -> str:
    """Require HTTPS and an exact, explicitly configured provider host."""

    parsed = urlparse(url)
    allowed = {host.strip().lower() for host in allowed_hosts if host.strip()}
    if parsed.scheme != "https" or not parsed.hostname or parsed.hostname.lower() not in allowed:
        raise CollectorSecurityError(
            CollectorErrorCode.CONFIGURATION_INVALID,
            "Provider URL is not on the configured HTTPS allowlist",
        )
    if parsed.username or parsed.password:
        raise CollectorSecurityError(
            CollectorErrorCode.CONFIGURATION_INVALID,
            "Provider URLs must not contain credentials",
        )
    return url


def redacted_error(code: CollectorErrorCode, _exc: BaseException | None = None) -> tuple[str, str]:
    """Return a stable code and a payload-safe operator summary."""

    return code.value, REDACTED_ERROR_SUMMARIES[code]


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"Unsupported value type: {type(value).__name__}")

