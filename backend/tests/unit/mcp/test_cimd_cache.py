"""Bounds around FastMCP's process-local CIMD document cache."""

import time
from types import SimpleNamespace

from app.mcp.cimd import cimd_fetch_requires_network, trim_cimd_cache


def test_cimd_cache_trimming_evicts_oldest_entries() -> None:
    cache = {"first": object(), "second": object(), "third": object()}
    manager = SimpleNamespace(_fetcher=SimpleNamespace(_cache=cache))

    trim_cimd_cache(manager, max_entries=2)

    assert list(cache) == ["second", "third"]


def test_cimd_network_admission_skips_only_fresh_cached_documents() -> None:
    fresh = SimpleNamespace(must_revalidate=False, expires_at=time.time() + 60)
    stale = SimpleNamespace(must_revalidate=False, expires_at=time.time() - 1)
    manager = SimpleNamespace(
        _fetcher=SimpleNamespace(_cache={"fresh": fresh, "stale": stale})
    )

    assert cimd_fetch_requires_network(manager, "fresh") is False
    assert cimd_fetch_requires_network(manager, "stale") is True
    assert cimd_fetch_requires_network(manager, "missing") is True
