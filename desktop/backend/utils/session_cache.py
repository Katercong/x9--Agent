"""Tiny in-process TTL cache for session_token → user dict.

Auth middleware runs on every request. Without caching, each request does a
DB roundtrip + (when remote) a network call to resolve the session token to a
user. Under concurrent load this saturates the connection pool first.

We cache up to ~5k tokens for ~60s. Eviction is opportunistic: stale entries
are dropped on read; size is capped to avoid unbounded growth from a flood of
unique tokens (e.g. attack/scanner traffic). Stamps are monotonic, so DST or
clock skew won't break the TTL.

This is intentionally a per-process cache — multi-worker setups will get up
to 60s of staleness per worker, which is acceptable for our roles (no
permission downgrades are time-critical; on logout we clear the entry).
"""
from __future__ import annotations

import time
from threading import RLock
from typing import Any

_CACHE: dict[str, tuple[float, Any]] = {}
_LOCK = RLock()
_TTL_SECONDS = 60.0
_MAX_ENTRIES = 5000


def get(token: str | None) -> Any | None:
    """Return cached user dict for `token`, or None if missing/expired."""
    if not token:
        return None
    now = time.monotonic()
    with _LOCK:
        entry = _CACHE.get(token)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < now:
            _CACHE.pop(token, None)
            return None
        return value


def put(token: str | None, value: Any) -> None:
    """Store `value` for `token` for ~60s."""
    if not token:
        return
    now = time.monotonic()
    with _LOCK:
        # Opportunistic eviction when we cross the cap. Drop the oldest 10%.
        if len(_CACHE) >= _MAX_ENTRIES:
            cutoff = sorted(_CACHE.items(), key=lambda kv: kv[1][0])[: _MAX_ENTRIES // 10]
            for key, _ in cutoff:
                _CACHE.pop(key, None)
        _CACHE[token] = (now + _TTL_SECONDS, value)


def invalidate(token: str | None) -> None:
    """Drop the cache entry for `token` (e.g. on logout/role change)."""
    if not token:
        return
    with _LOCK:
        _CACHE.pop(token, None)


def clear() -> None:
    """Drop everything. Used in tests."""
    with _LOCK:
        _CACHE.clear()
