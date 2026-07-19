"""Shared extraction of request correlation metadata."""

from __future__ import annotations

from collections.abc import Mapping


def get_correlation_id(headers: Mapping[str, str]) -> str | None:
    """Prefer the canonical request ID while accepting the legacy header."""
    return headers.get("x-request-id") or headers.get("x-correlation-id")
