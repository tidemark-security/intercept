"""Bounded FastMCP Client ID Metadata Document resolution."""

from __future__ import annotations

import time
from typing import Any

from fastmcp.server.auth.cimd import CIMDClientManager


def trim_cimd_cache(manager: Any, *, max_entries: int) -> None:
    """Enforce a hard FIFO bound on FastMCP's otherwise-unbounded cache."""

    fetcher = getattr(manager, "_fetcher", None)
    cache = getattr(fetcher, "_cache", None)
    if not isinstance(cache, dict):
        return
    while len(cache) > max_entries:
        cache.pop(next(iter(cache)))


def cimd_fetch_requires_network(manager: Any, client_id: str) -> bool:
    """Return whether resolving this client can perform outbound network I/O."""

    fetcher = getattr(manager, "_fetcher", None)
    cache = getattr(fetcher, "_cache", None)
    if not isinstance(cache, dict):
        return True
    entry = cache.get(client_id)
    if entry is None:
        return True
    try:
        expires_at = float(getattr(entry, "expires_at", 0))
    except (TypeError, ValueError):
        return True
    return bool(getattr(entry, "must_revalidate", False)) or time.time() >= expires_at


class BoundedCIMDClientManager(CIMDClientManager):
    """CIMD manager with a process-local hard bound on document cache entries."""

    def __init__(self, *, max_cache_entries: int, **kwargs: Any) -> None:
        if max_cache_entries <= 0:
            raise ValueError("CIMD cache capacity must be positive")
        super().__init__(**kwargs)
        self.max_cache_entries = max_cache_entries

    async def get_client(self, client_id_url: str):
        try:
            return await super().get_client(client_id_url)
        finally:
            trim_cimd_cache(self, max_entries=self.max_cache_entries)


__all__ = [
    "BoundedCIMDClientManager",
    "cimd_fetch_requires_network",
    "trim_cimd_cache",
]
