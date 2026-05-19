"""
Remote X9 creator repository.

A thin HTTP client that talks to the remote X9 API at
    {settings.remote_api_url}/api/v1/data/{settings.remote_table}/...

Features:
- 60-second TTL cache for `list_all()` to keep UI responsive without
  hammering the network on every request.
- Automatic retry with exponential backoff on transient errors
  (connection refused, timeout) — 3 attempts.
- Stable error type `RemoteRepoError` for the router to catch and turn
  into a 502 if needed.
- Stdlib only (urllib + json), no extra deps.

The router uses this in place of `select(Creator)`. Filtering and sorting
that the remote API can't do (ilike / range / IN / multi-key sort) is
performed in Python on the cached row list — fine at 130 rows, will need
server-side support once data grows past ~5K (see ZHANG_API_ENHANCEMENTS.md).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any
from urllib import error, parse, request

from sqlalchemy import text

from ..config import settings
from ..database.connection import engine
from .departments import DEFAULT_DEPARTMENT

log = logging.getLogger("remote_creators")


class RemoteRepoError(RuntimeError):
    """Raised when the remote API call fails after retries."""


_CACHE_TTL_SECONDS = 60.0
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = (0.3, 0.8, 2.0)  # seconds
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_JSON_COLS = {
    "external_links_json",
    "fit_evidence_source_json",
    "matched_keywords_json",
    "evidence_text_json",
    "risk_tags_json",
    "positive_tags_json",
    "profile_snapshot_json",
    "tiktok_shop_json",
}


class _Cache:
    """Tiny TTL cache for list_all()."""

    def __init__(self) -> None:
        self._data: list[dict] | None = None
        self._fetched_at: float = 0.0
        self._lock = threading.Lock()

    def get(self) -> list[dict] | None:
        with self._lock:
            if self._data is not None and (time.time() - self._fetched_at) < _CACHE_TTL_SECONDS:
                return self._data
            return None

    def set(self, rows: list[dict]) -> None:
        with self._lock:
            self._data = rows
            self._fetched_at = time.time()

    def invalidate(self) -> None:
        with self._lock:
            self._data = None
            self._fetched_at = 0.0


_cache = _Cache()


def _direct_db_enabled() -> bool:
    return settings.db_url.startswith(("postgresql://", "postgresql+"))


def _safe_ident(value: str) -> str:
    if not _IDENT_RE.match(value):
        raise RemoteRepoError(f"unsafe SQL identifier: {value!r}")
    return value


def _direct_table() -> str:
    return _safe_ident(settings.remote_table)


def _decode_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    out["department_code"] = out.get("department_code") or DEFAULT_DEPARTMENT
    for col in _JSON_COLS:
        value = out.get(col)
        if isinstance(value, str) and value:
            try:
                out[col] = json.loads(value)
            except json.JSONDecodeError:
                pass
        elif col in out and not value:
            out[col] = []
    return out


def _normalize_handle_lookup(value: str | None) -> str:
    return str(value or "").strip().lstrip("@").lower()


def _direct_columns(conn) -> set[str]:
    table = _direct_table()
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
            """
        ),
        {"table": table},
    ).mappings()
    cols = {r["column_name"] for r in rows}
    if not cols:
        raise RemoteRepoError(f"PostgreSQL table not found: {table}")
    return cols


def _direct_list_all(force_refresh: bool = False) -> list[dict]:
    if not force_refresh:
        cached = _cache.get()
        if cached is not None:
            return cached
    table = _direct_table()
    with engine.connect() as conn:
        rows = [
            _decode_row(dict(row)) or {}
            for row in conn.execute(text(f"SELECT * FROM {table} ORDER BY id")).mappings().all()
        ]
    _cache.set(rows)
    return rows


def _direct_get_by_id(creator_id: int | str) -> dict | None:
    table = _direct_table()
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT * FROM {table} WHERE id = :id LIMIT 1"),
            {"id": creator_id},
        ).mappings().first()
    return _decode_row(dict(row)) if row else None


def _direct_get_by_handle(platform: str, handle: str) -> dict | None:
    table = _direct_table()
    platform_key = str(platform or "tiktok").strip().lower()
    handle_key = _normalize_handle_lookup(handle)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                f"""
                SELECT *
                FROM {table}
                WHERE lower(trim(platform)) = :platform
                  AND lower(trim(handle)) IN (:handle, :at_handle)
                LIMIT 1
                """
            ),
            {"platform": platform_key, "handle": handle_key, "at_handle": f"@{handle_key}"},
        ).mappings().first()
    return _decode_row(dict(row)) if row else None


def _direct_bulk_upsert(rows: list[dict]) -> dict:
    if not rows:
        return {"inserted": 0, "updated": 0, "skipped": 0, "errors": []}
    table = _direct_table()
    inserted = updated = 0
    errors: list[dict] = []
    with engine.begin() as conn:
        cols = _direct_columns(conn)
        for idx, raw in enumerate(rows):
            try:
                fields = {k: v for k, v in dict(raw).items() if k in cols}
                for col in _JSON_COLS:
                    if col in fields and not isinstance(fields[col], str):
                        fields[col] = json.dumps(fields[col] or [], ensure_ascii=False)
                if not fields:
                    errors.append({"idx": idx, "error": "no recognized columns"})
                    continue
                existing = None
                if fields.get("platform") and fields.get("handle"):
                    platform_key = str(fields["platform"]).strip().lower()
                    handle_key = _normalize_handle_lookup(fields["handle"])
                    existing = conn.execute(
                        text(
                            f"""
                            SELECT id
                            FROM {table}
                            WHERE lower(trim(platform)) = :platform
                              AND lower(trim(handle)) IN (:handle, :at_handle)
                            LIMIT 1
                            """
                        ),
                        {"platform": platform_key, "handle": handle_key, "at_handle": f"@{handle_key}"},
                    ).mappings().first()
                if existing:
                    update_cols = [c for c in fields if c not in {"platform", "handle", "id"}]
                    if update_cols:
                        sets = ", ".join([f"{_safe_ident(c)} = :{c}" for c in update_cols])
                        conn.execute(
                            text(f"UPDATE {table} SET {sets} WHERE id = :_id"),
                            {**fields, "_id": existing["id"]},
                        )
                    updated += 1
                    continue
                insert_cols = list(fields)
                placeholders = ", ".join([f":{c}" for c in insert_cols])
                conn.execute(
                    text(f"INSERT INTO {table}({', '.join(insert_cols)}) VALUES({placeholders})"),
                    fields,
                )
                inserted += 1
            except Exception as exc:
                errors.append({"idx": idx, "error": str(exc)})
    _cache.invalidate()
    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": len(rows) - inserted - updated,
        "errors": errors,
    }


def _direct_patch(creator_id: int | str, **fields: Any) -> dict:
    if not fields:
        return {"ok": True, "updated_fields": []}
    table = _direct_table()
    with engine.begin() as conn:
        cols = _direct_columns(conn)
        clean = {k: v for k, v in fields.items() if k in cols and k != "id"}
        for col in _JSON_COLS:
            if col in clean and not isinstance(clean[col], str):
                clean[col] = json.dumps(clean[col] or [], ensure_ascii=False)
        if not clean:
            return {"ok": True, "updated_fields": []}
        sets = ", ".join([f"{_safe_ident(c)} = :{c}" for c in clean])
        result = conn.execute(text(f"UPDATE {table} SET {sets} WHERE id = :_id"), {**clean, "_id": creator_id})
    _cache.invalidate()
    if result.rowcount == 0:
        raise RemoteRepoError(f"remote HTTP 404: creator #{creator_id} not found")
    return {"ok": True, "updated_fields": list(clean.keys())}


def _direct_delete(creator_id: int | str) -> dict:
    table = _direct_table()
    with engine.begin() as conn:
        result = conn.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": creator_id})
    _cache.invalidate()
    if result.rowcount == 0:
        raise RemoteRepoError(f"remote HTTP 404: creator #{creator_id} not found")
    return {"ok": True, "deleted": {"id": creator_id}}


def _http(method: str, path: str, body: dict | None = None, auth: bool = False) -> dict | list:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
    if auth:
        if not settings.remote_api_key:
            raise RemoteRepoError(
                "REMOTE_API_KEY is not set — write operations require an API key. "
                "Add REMOTE_API_KEY=... to your .env file."
            )
        headers["X-API-Key"] = settings.remote_api_key
    url = settings.remote_api_url.rstrip("/") + path
    last_err: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        req = request.Request(url, data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=settings.remote_timeout) as r:
                payload = r.read().decode("utf-8", "replace")
                try:
                    return json.loads(payload)
                except json.JSONDecodeError:
                    raise RemoteRepoError(f"non-JSON response from remote: {payload[:200]}")
        except error.HTTPError as e:
            body_text = e.read().decode("utf-8", "replace")
            # 4xx errors are not retryable — wrong key, bad request, missing row
            if 400 <= e.code < 500:
                raise RemoteRepoError(f"remote HTTP {e.code}: {body_text[:300]}") from e
            last_err = e
        except (error.URLError, TimeoutError) as e:
            last_err = e
        if attempt < _RETRY_ATTEMPTS - 1:
            sleep_for = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
            log.warning("remote call failed (attempt %d/%d): %s — retrying in %.1fs",
                        attempt + 1, _RETRY_ATTEMPTS, last_err, sleep_for)
            time.sleep(sleep_for)
    raise RemoteRepoError(f"remote call failed after {_RETRY_ATTEMPTS} attempts: {last_err}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_all(force_refresh: bool = False) -> list[dict]:
    """Fetch every row in tk_creators. Cached for 60s.

    The remote API caps `?limit=` at 1000, so for larger tables we'd need to
    paginate. Currently 130 rows so a single request is fine.
    """
    if _direct_db_enabled():
        return _direct_list_all(force_refresh=force_refresh)

    if not force_refresh:
        cached = _cache.get()
        if cached is not None:
            return cached

    # Walk pages of 1000 just in case the table grows.
    rows: list[dict] = []
    offset = 0
    page_size = 1000
    while True:
        result = _http(
            "GET",
            f"/api/v1/data/{settings.remote_table}?limit={page_size}&offset={offset}",
        )
        if not isinstance(result, dict):
            raise RemoteRepoError(f"unexpected response shape: {type(result).__name__}")
        items = result.get("items") or []
        rows.extend(items)
        total = result.get("total") or len(rows)
        if len(rows) >= total or not items:
            break
        offset += len(items)

    _cache.set(rows)
    return rows


def get_by_id(creator_id: int | str) -> dict | None:
    """Fetch one row by remote id."""
    if _direct_db_enabled():
        return _direct_get_by_id(creator_id)

    try:
        result = _http("GET", f"/api/v1/data/{settings.remote_table}/{creator_id}")
    except RemoteRepoError as e:
        if "404" in str(e):
            return None
        raise
    if isinstance(result, dict) and "items" in result:
        items = result["items"] or []
        return items[0] if items else None
    return result if isinstance(result, dict) else None


def get_by_handle(platform: str, handle: str) -> dict | None:
    """Fetch one row by (platform, handle). Convenient because remote ids
    differ from local ids."""
    if _direct_db_enabled():
        return _direct_get_by_handle(platform, handle)

    qs = parse.urlencode({"platform": platform, "handle": handle, "limit": 1})
    result = _http("GET", f"/api/v1/data/{settings.remote_table}?{qs}")
    if not isinstance(result, dict):
        return None
    items = result.get("items") or []
    return items[0] if items else None


def bulk_upsert(rows: list[dict]) -> dict:
    """Insert/update rows. Dedup is by (platform, handle) on the remote.
    Invalidates the cache so the next list_all() reads fresh data."""
    if _direct_db_enabled():
        return _direct_bulk_upsert(rows)

    if not rows:
        return {"inserted": 0, "updated": 0, "skipped": 0}
    result = _http(
        "POST",
        f"/api/v1/data/{settings.remote_table}/bulk",
        body={"items": rows},
        auth=True,
    )
    _cache.invalidate()
    return result if isinstance(result, dict) else {}


def patch(creator_id: int | str, **fields: Any) -> dict:
    """Partial update of one row by remote id."""
    if _direct_db_enabled():
        return _direct_patch(creator_id, **fields)

    if not fields:
        return {"ok": True, "updated_fields": []}
    result = _http(
        "PATCH",
        f"/api/v1/data/{settings.remote_table}/{creator_id}",
        body=fields,
        auth=True,
    )
    _cache.invalidate()
    return result if isinstance(result, dict) else {}


def delete(creator_id: int | str) -> dict:
    """Delete one row by remote id."""
    if _direct_db_enabled():
        return _direct_delete(creator_id)

    result = _http(
        "DELETE",
        f"/api/v1/data/{settings.remote_table}/{creator_id}",
        auth=True,
    )
    _cache.invalidate()
    return result if isinstance(result, dict) else {}


def invalidate_cache() -> None:
    """Force the next list_all() to hit the network."""
    _cache.invalidate()
