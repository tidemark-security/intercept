"""Shared IP-address eligibility policy for enrichment providers."""

from __future__ import annotations

import ipaddress


def normalize_public_ip_address(value: str) -> str | None:
    """Return an eligible address in canonical form, or ``None``.

    Eligibility deliberately uses the providers' existing deny-list rather
    than ``is_global``: multicast is rejected, while shared CGNAT space is
    accepted.
    """
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return None
    if (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
    ):
        return None
    return str(parsed)


__all__ = ["normalize_public_ip_address"]
