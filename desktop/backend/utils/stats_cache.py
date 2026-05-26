"""Small in-process TTL cache for dashboard statistics.

Statistics pages refresh on a minute cadence. Recomputing the same counters on
every request makes admin pages compete with collector writes, so hot stats
snapshots are cached for the same cadence.
"""
from __future__ import annotations

import copy
import time
from collections.abc import Callable, Hashable
from threading import RLock
from typing import Any

_CACHE: dict[tuple[str, Hashable], tuple[float, Any]] = {}
_LOCK = RLock()
_MAX_ENTRIES = 512


def get_or_compute(
    namespace: str,
    key: Hashable,
    compute: Callable[[], Any],
    *,
    ttl_seconds: float = 60.0,
) -> Any:
    """Return a cached snapshot, computing it at most once per TTL window."""
    cache_key = (namespace, key)
    now = time.monotonic()
    with _LOCK:
        entry = _CACHE.get(cache_key)
        if entry is not None:
            expires_at, value = entry
            if expires_at >= now:
                return copy.deepcopy(value)
            _CACHE.pop(cache_key, None)

        # Keep the compute inside the cache lock so concurrent dashboard polls
        # cannot stampede into the same expensive statistics query.
        value = compute()
        stored_value = copy.deepcopy(value)
        if len(_CACHE) >= _MAX_ENTRIES:
            stale = [item_key for item_key, (expires_at, _) in _CACHE.items() if expires_at < now]
            for item_key in stale:
                _CACHE.pop(item_key, None)
            if len(_CACHE) >= _MAX_ENTRIES:
                oldest = sorted(_CACHE.items(), key=lambda item: item[1][0])[: max(1, _MAX_ENTRIES // 10)]
                for item_key, _ in oldest:
                    _CACHE.pop(item_key, None)
        _CACHE[cache_key] = (time.monotonic() + ttl_seconds, stored_value)
        return copy.deepcopy(stored_value)


def refresh(
    namespace: str,
    key: Hashable,
    compute: Callable[[], Any],
    *,
    ttl_seconds: float = 120.0,
) -> Any:
    """Compute a fresh snapshot and atomically replace the cached value."""
    value = compute()
    stored_value = copy.deepcopy(value)
    with _LOCK:
        _CACHE[(namespace, key)] = (time.monotonic() + ttl_seconds, stored_value)
    return copy.deepcopy(stored_value)


def invalidate_namespace(namespace: str) -> None:
    with _LOCK:
        for cache_key in [cache_key for cache_key in _CACHE if cache_key[0] == namespace]:
            _CACHE.pop(cache_key, None)


def clear() -> None:
    with _LOCK:
        _CACHE.clear()
