"""Small process-local cache for validated OIDC discovery metadata."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import time
from typing import Awaitable, Callable


DiscoveryMetadata = dict[str, object]


@dataclass(frozen=True, slots=True)
class _DiscoveryEntry:
    metadata: DiscoveryMetadata | None
    error: Exception | None
    fresh_until: float


class OIDCDiscoveryCache:
    """Bound and coalesce discovery reads within one backend process."""

    def __init__(
        self,
        *,
        ttl_seconds: float = 300,
        failure_ttl_seconds: float = 15,
        max_entries: int = 8,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("OIDC discovery cache TTL must be positive")
        if failure_ttl_seconds <= 0:
            raise ValueError("OIDC discovery failure backoff must be positive")
        if max_entries <= 0:
            raise ValueError("OIDC discovery cache size must be positive")
        self._ttl_seconds = ttl_seconds
        self._failure_ttl_seconds = failure_ttl_seconds
        self._max_entries = max_entries
        self._monotonic = monotonic
        self._entries: OrderedDict[str, _DiscoveryEntry] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(
        self,
        discovery_url: str,
        loader: Callable[[], Awaitable[DiscoveryMetadata]],
    ) -> DiscoveryMetadata:
        """Return fresh validated metadata, loading it at most once concurrently."""

        cached = self._fresh_entry(discovery_url)
        if cached is not None:
            return self._resolve(cached)

        async with self._lock:
            cached = self._fresh_entry(discovery_url)
            if cached is not None:
                return self._resolve(cached)

            try:
                metadata = dict(await loader())
            except Exception as exc:
                # Discovery failures are short-lived cache entries. Keeping the
                # original exception preserves the service's existing typed
                # error contract while stopping an unauthenticated retry storm.
                exc.__traceback__ = None
                self._remember(
                    discovery_url,
                    _DiscoveryEntry(
                        metadata=None,
                        error=exc,
                        fresh_until=(
                            self._monotonic() + self._failure_ttl_seconds
                        ),
                    ),
                )
                raise

            self._remember(
                discovery_url,
                _DiscoveryEntry(
                    metadata=metadata,
                    error=None,
                    fresh_until=self._monotonic() + self._ttl_seconds,
                ),
            )
            return dict(metadata)

    def _remember(self, discovery_url: str, entry: _DiscoveryEntry) -> None:
        self._entries[discovery_url] = entry
        self._entries.move_to_end(discovery_url)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    @staticmethod
    def _resolve(entry: _DiscoveryEntry) -> DiscoveryMetadata:
        if entry.error is not None:
            raise entry.error
        if entry.metadata is None:  # pragma: no cover - internal invariant
            raise RuntimeError("OIDC discovery cache entry is incomplete")
        return dict(entry.metadata)

    def _fresh_entry(self, discovery_url: str) -> _DiscoveryEntry | None:
        entry = self._entries.get(discovery_url)
        if entry is None:
            return None
        if entry.fresh_until <= self._monotonic():
            return None
        self._entries.move_to_end(discovery_url)
        return entry


__all__ = ["DiscoveryMetadata", "OIDCDiscoveryCache"]
