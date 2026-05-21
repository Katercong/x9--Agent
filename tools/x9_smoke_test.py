"""
X9 API smoke test
-----------------
Run this against the live X9 API.

Usage:
    python x9_smoke_test.py

What it checks (all read-only / non-destructive):
    1.  GET /api/v1/                      service discovery
    2.  GET /api/v1/resources             list of resources
    3.  GET /api/v1/resources/creators    schema of one resource
    4.  GET /api/v1/queries               list of named queries
    5.  GET /api/v1/data/creators?limit=1 sample row (auth not required for GET)
    6.  GET /docs                         OpenAPI page is reachable
    7.  An auth probe: PATCH a non-existent id with the API key, just to
        confirm the key is accepted (we expect 404 for the row, not 401).

It prints a one-line PASS/FAIL per check and the response body (truncated).
"""
from __future__ import annotations

import json
import sys
import time
from urllib import request, error, parse

BASE = "https://usx9.us"
KEY  = "-PheaIjXfZLZIL4s_uK2FYUAqYZyWTSRYRm52u6jcm0"

TIMEOUT = 8  # seconds


def call(method: str, path: str, body: dict | None = None, auth: bool = False) -> tuple[int, str]:
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if auth:
        headers["X-API-Key"] = KEY
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except error.HTTPError as e:
        # HTTPError still has the body
        return e.code, e.read().decode("utf-8", "replace")
    except (error.URLError, TimeoutError, ConnectionError) as e:
        return 0, f"NETWORK ERROR: {e}"


def show(label: str, status: int, body: str, ok_codes: tuple[int, ...]) -> bool:
    ok = status in ok_codes
    tag = "PASS" if ok else "FAIL"
    snippet = body if len(body) <= 400 else body[:400] + "...<truncated>"
    print(f"[{tag}] {label}  -> HTTP {status}")
    print(f"       {snippet}")
    print()
    return ok


def main() -> int:
    print(f"X9 smoke test against {BASE}")
    print(f"Using key: {KEY[:8]}...{KEY[-4:]}")
    print("=" * 70)
    t0 = time.time()
    results: list[bool] = []

    s, b = call("GET", "/api/v1/")
    results.append(show("1. service discovery        GET /api/v1/", s, b, (200,)))

    s, b = call("GET", "/api/v1/resources")
    results.append(show("2. list resources           GET /api/v1/resources", s, b, (200,)))

    s, b = call("GET", "/api/v1/resources/creators")
    results.append(show("3. creators schema          GET /api/v1/resources/creators", s, b, (200,)))

    s, b = call("GET", "/api/v1/queries")
    results.append(show("4. list named queries       GET /api/v1/queries", s, b, (200,)))

    s, b = call("GET", "/api/v1/data/creators?limit=1")
    results.append(show("5. sample creator row       GET /api/v1/data/creators?limit=1", s, b, (200,)))

    s, b = call("GET", "/docs")
    results.append(show("6. OpenAPI docs page        GET /docs", s, b, (200,)))

    # Auth probe: PATCH a clearly-bogus id. Expected: 404 (row not found) if the key
    # is ACCEPTED; 401 if the key is rejected.
    s, b = call("PATCH", "/api/v1/data/creators/-1", body={"followers": 0}, auth=True)
    auth_ok = s in (200, 404, 400, 422)  # any of these means key wasn't rejected
    results.append(show("7. auth probe (PATCH bogus) PATCH /api/v1/data/creators/-1  (expect 404, NOT 401)", s, b, (200, 404, 400, 422)))

    print("=" * 70)
    passed = sum(results)
    total = len(results)
    elapsed = time.time() - t0
    print(f"Result: {passed}/{total} checks passed in {elapsed:.1f}s")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
