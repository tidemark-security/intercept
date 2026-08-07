"""Fail-closed checks for exposing the development Compose stack publicly."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit

from app.core.settings_registry import get_local


_INSECURE_DEV_CREDENTIALS: dict[str, frozenset[str]] = {
    "POSTGRES_PASSWORD": frozenset({"intercept_password"}),
    "LANGFLOW_DB_PASSWORD": frozenset({"langflow_password"}),
    "MINIO_ROOT_USER": frozenset({"minioadmin"}),
    "MINIO_ROOT_PASSWORD": frozenset({"minioadmin"}),
    "LANGFLOW_SUPERUSER_PASSWORD": frozenset({"admin"}),
    "LANGFLOW_SECRET_KEY": frozenset(
        {"3R1HFctPJZ_MDJg-GQe2Z_TaEyZyXQZtbcCR5l8S0E4="}
    ),
    "LANGFLOW_API_KEY": frozenset({"dev-langflow-api-key"}),
    "INITIAL_ADMIN_PASSWORD": frozenset({"Dev-initial-admin-password1!"}),
    "SECRET_KEY": frozenset(
        {
            "dev-secret-key-change-in-production",
            "your-super-secret-key-change-this-in-production",
        }
    ),
}


def _is_enabled(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def _is_loopback_host(hostname: str) -> bool:
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _external_origin_host(origin: str) -> str | None:
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("INTERCEPT_PUBLIC_ORIGIN must be a valid absolute URL") from exc

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or port == 0
    ):
        raise RuntimeError("INTERCEPT_PUBLIC_ORIGIN must be an origin-only HTTP(S) URL")

    if _is_loopback_host(parsed.hostname):
        return None
    if parsed.scheme != "https":
        raise RuntimeError("External INTERCEPT_PUBLIC_ORIGIN values must use HTTPS")
    return parsed.hostname.rstrip(".").lower()


def validate_dev_compose_public_exposure(
    *,
    environment: Mapping[str, str] | None = None,
    cookie_secure: bool | None = None,
    trusted_hosts: Sequence[str] | None = None,
) -> None:
    """Reject an externally exposed dev stack that still uses development defaults.

    The check is deliberately scoped to ``dev/docker-compose.yml`` through its
    marker variable. Local-only development keeps its convenient defaults, while
    setting a non-loopback public origin turns every bundled credential and the
    secure-cookie/trusted-host controls into mandatory startup requirements.
    """

    values = os.environ if environment is None else environment
    if not _is_enabled(values.get("INTERCEPT_DEV_COMPOSE")):
        return

    origin = (values.get("INTERCEPT_PUBLIC_ORIGIN") or "http://localhost:8080").strip()
    external_host = _external_origin_host(origin)
    if external_host is None:
        return

    insecure_names: list[str] = []
    for name, known_defaults in _INSECURE_DEV_CREDENTIALS.items():
        value = values.get(name, "").strip()
        if not value or value in known_defaults or (value.startswith("<") and value.endswith(">")):
            insecure_names.append(name)

    effective_cookie_secure = (
        bool(get_local("auth.session.cookie_secure"))
        if cookie_secure is None
        else cookie_secure
    )
    if not effective_cookie_secure:
        insecure_names.append("SESSION_COOKIE_SECURE")

    effective_trusted_hosts = (
        get_local("http.trusted_hosts") if trusted_hosts is None else trusted_hosts
    )
    normalized_hosts = {
        str(host).rstrip(".").lower()
        for host in effective_trusted_hosts
        if str(host).strip()
    }
    if external_host not in normalized_hosts:
        insecure_names.append("INTERCEPT_TRUSTED_HOSTS")

    if insecure_names:
        names = ", ".join(sorted(set(insecure_names)))
        raise RuntimeError(
            "Refusing to expose the development Compose stack with insecure or "
            f"missing configuration. Override: {names}"
        )
