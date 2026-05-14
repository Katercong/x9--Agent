"""
Read-side smoke test for tk_creators on the remote X9 API.

Exercises the typical query shapes:
  1. Count total rows
  2. Fetch one sample row (full payload)
  3. Filter + sort + limit  (e.g. top 5 by recommendation_score, US only)
  4. Pagination (offset)
  5. Full-text search via ?q=
  6. Equality filters on multiple columns
  7. JSON column round-trip check

Usage:
    python x9_read_tk_creators.py
"""
from __future__ import annotations

import json
import sys
from urllib import request, parse, error

BASE = "http://192.168.1.168:18765"
RESOURCE = "tk_creators"
TIMEOUT = 10


def get(path: str, params: dict | None = None) -> tuple[int, dict | str]:
    if params:
        path = path + "?" + parse.urlencode(params)
    req = request.Request(BASE + path, headers={"Accept": "application/json"})
    try:
        with request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(body)
            except json.JSONDecodeError:
                return r.status, body
    except error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"NETERR: {e}"


def banner(t: str) -> None:
    print("\n" + t)
    print("-" * len(t))


def show_row(row: dict, fields: list[str]) -> None:
    for f in fields:
        v = row.get(f)
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        if isinstance(v, str) and len(v) > 80:
            v = v[:80] + "..."
        print(f"    {f:<28} {v}")


def main() -> int:
    print(f"Reading from {BASE}/api/v1/data/{RESOURCE}")
    print("=" * 80)

    # ---- 1. Total count ----
    banner("1. Total rows in tk_creators")
    s, j = get(f"/api/v1/data/{RESOURCE}", {"limit": 1})
    if s != 200 or not isinstance(j, dict):
        print(f"   FAIL  HTTP {s}  {j}")
        return 1
    print(f"   total = {j.get('total')}")

    # ---- 2. Sample row (full payload) ----
    banner("2. One sample row — all fields")
    s, j = get(f"/api/v1/data/{RESOURCE}", {"limit": 1})
    if j.get("items"):
        row = j["items"][0]
        print(f"   row keys ({len(row)} total):")
        keys = list(row.keys())
        for i in range(0, len(keys), 4):
            print("     " + "  ".join(f"{k:<24}" for k in keys[i:i+4]))
        print(f"\n   pretty payload of first row:")
        print(json.dumps(row, ensure_ascii=False, indent=2)[:2000])

    # ---- 3. Top 5 by recommendation_score, US only ----
    banner("3. Top 5 by recommendation_score (US only)")
    s, j = get(f"/api/v1/data/{RESOURCE}", {
        "order_by": "recommendation_score",
        "desc": "true",
        "limit": 5,
    })
    if isinstance(j, dict):
        for r in j.get("items", []):
            show_row(r, ["handle", "platform", "display_name", "followers_count",
                         "recommendation_score", "recommendation_status",
                         "primary_product_category"])
            print()

    # ---- 4. Pagination check ----
    banner("4. Pagination — page 2 (offset=5, limit=5)")
    s, j = get(f"/api/v1/data/{RESOURCE}", {"limit": 5, "offset": 5,
                                            "order_by": "id", "desc": "false"})
    if isinstance(j, dict):
        print(f"   returned {len(j.get('items', []))} rows, "
              f"offset={j.get('offset')}, total={j.get('total')}")
        for r in j.get("items", []):
            print(f"     id={r['id']:<5} handle={r.get('handle'):<25} "
                  f"platform={r.get('platform')}")

    # ---- 5. Full-text search ----
    banner("5. Full-text search (q=feminine)")
    s, j = get(f"/api/v1/data/{RESOURCE}", {"q": "feminine", "limit": 3})
    if isinstance(j, dict):
        print(f"   matched {j.get('total')} rows; first 3:")
        for r in j.get("items", []):
            print(f"     id={r['id']:<5} handle={r.get('handle'):<25} "
                  f"keyword={r.get('search_keyword')}")

    # ---- 6. Equality filter combo ----
    banner("6. Equality filters: platform=tiktok & has_email=1")
    s, j = get(f"/api/v1/data/{RESOURCE}", {"platform": "tiktok", "has_email": 1, "limit": 3})
    if isinstance(j, dict):
        print(f"   matched {j.get('total')} rows; sample 3:")
        for r in j.get("items", []):
            show_row(r, ["handle", "email", "followers_count", "fit_level"])
            print()

    # ---- 7. JSON column round-trip ----
    banner("7. JSON column shape (matched_keywords_json on first row that has any)")
    s, j = get(f"/api/v1/data/{RESOURCE}", {"limit": 50})
    found = False
    for r in j.get("items", []):
        v = r.get("matched_keywords_json")
        if v not in (None, "", "[]", "null"):
            found = True
            print(f"   row id={r['id']} handle={r.get('handle')}")
            print(f"   raw type        : {type(v).__name__}")
            print(f"   raw value       : {repr(v)[:300]}")
            if isinstance(v, str):
                try:
                    parsed = json.loads(v)
                    print(f"   parses to       : {type(parsed).__name__}  {repr(parsed)[:200]}")
                    print(f"   note: API returned a string — json_cols decoding may not be active "
                          f"on read path (you'd json.loads() in your client)")
                except Exception:
                    print(f"   (not valid JSON)")
            else:
                print(f"   note: API decoded it for you ({type(v).__name__})")
            break
    if not found:
        print("   no row in first 50 had a populated matched_keywords_json")

    print("\n" + "=" * 80)
    print("Read smoke test done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
