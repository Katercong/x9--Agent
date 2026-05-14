"""
X9 API key permission compare
-----------------------------
Run side-by-side write probes with two API keys and print a comparison table.

Side effects on the live DB:
  - Creates 1-2 small dynamic tables named `liao_keytest_<timestamp>_a/_b`
  - Inserts/updates/deletes a few test rows in those tables
  - Adds a few test columns to those tables
  - Does NOT touch any built-in resource data; only attempts an `add column`
    on a built-in resource as a negative control (expected 403)

Cleanup: API has no DROP TABLE endpoint. Ask 张 to drop the leftover
`liao_keytest_*` tables in SQLite after review.

Usage:
    python x9_key_permissions.py

Keys: set X9_KEY_A / X9_KEY_B env vars to override the defaults.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from urllib import request, error

BASE = "http://192.168.1.168:18765"

# Set X9_KEY_A / X9_KEY_B env vars to override — do NOT commit real keys.
KEYS = {
    "A_TwXKU": os.environ.get("X9_KEY_A", "TwXKU_xzfLt-kNj5b8IzSPxYi27KrcOyd-9DNppYPco"),
    "B_PheaI": os.environ.get("X9_KEY_B", "-PheaIjXfZLZIL4s_uK2FYUAqYZyWTSRYRm52u6jcm0"),
}

TIMEOUT = 10


def call(method: str, path: str, body: dict | None = None, key: str | None = None) -> tuple[int, str]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if key:
        headers["X-API-Key"] = key
    req = request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"NETERR: {e}"


def short(s: str, n: int = 180) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[:n] + "...<trunc>"


def get_row_id(table: str, label_value: str) -> int | None:
    """Look up row id by `label` column."""
    s, b = call("GET", f"/api/v1/data/{table}?label={label_value}&limit=1")
    if s != 200:
        return None
    try:
        items = json.loads(b).get("items", [])
        return items[0]["id"] if items else None
    except Exception:
        return None


def run_step(method: str, path_fn, body_fn=None) -> dict[str, tuple[int, str]]:
    """Call `method path` for every key; return {label: (status, body)}."""
    return {
        label: call(method, path_fn(label), body_fn(label) if body_fn else None, key)
        for label, key in KEYS.items()
    }


def main() -> int:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    probe_base = f"liao_keytest_{ts}"

    print(f"X9 key permission comparison")
    print(f"BASE = {BASE}")
    for label, key in KEYS.items():
        print(f"  key {label}: {key[:8]}...{key[-4:]}")
    print("=" * 90)

    rows: list[tuple[str, dict[str, tuple[int, str]]]] = []

    # ---------- Step 1: each key tries to create its own probe table ----------
    print("\n[Step 1] Creating probe tables...")
    create_outcome: dict[str, tuple[int, str, str | None]] = {}
    for label, key in KEYS.items():
        sub = f"{probe_base}_{label.split('_')[0].lower()}"
        body = {
            "name": sub,
            "description": "key permission probe (safe to drop after review)",
            "columns": [
                {"name": "label", "type": "TEXT", "unique": True, "not_null": True},
                {"name": "n", "type": "INTEGER", "default": 0},
            ],
            "upsert_keys": ["label"],
        }
        s, b = call("POST", "/api/v1/tables", body=body, key=key)
        create_outcome[label] = (s, b, sub if s == 200 else None)

    rows.append((
        "1. POST /api/v1/tables   (create dynamic table)",
        {l: (s, b) for l, (s, b, _) in create_outcome.items()},
    ))

    # Pick the first successfully-created probe to use for downstream data ops
    probe_for_data = next((t for s, b, t in create_outcome.values() if t), None)
    if probe_for_data is None:
        print("\nFATAL: neither key could create a probe table. Cannot run further steps.")
        for label, (s, b, _) in create_outcome.items():
            print(f"  {label}: HTTP {s}  {short(b)}")
        return 1

    print(f"Using probe table for data ops: {probe_for_data}")

    # ---------- Step 2: bulk insert ----------
    print("\n[Step 2] Bulk inserting rows...")
    bulk_outcome = run_step(
        "POST",
        lambda _: f"/api/v1/data/{probe_for_data}/bulk",
        lambda label: {"items": [{"label": f"row_from_{label}", "n": 1}]},
    )
    rows.append((f"2. POST /data/{probe_for_data}/bulk   (insert one row)", bulk_outcome))

    # ---------- Step 3: PATCH own row ----------
    print("\n[Step 3] Patching own rows...")
    patch_outcome: dict[str, tuple[int, str]] = {}
    rid_cache: dict[str, int | None] = {}
    for label, key in KEYS.items():
        rid = get_row_id(probe_for_data, f"row_from_{label}")
        rid_cache[label] = rid
        if rid is None:
            patch_outcome[label] = (0, f"no row to patch (bulk returned HTTP {bulk_outcome[label][0]})")
            continue
        patch_outcome[label] = call("PATCH", f"/api/v1/data/{probe_for_data}/{rid}",
                                    body={"n": 999}, key=key)
    rows.append((f"3. PATCH /data/{probe_for_data}/<own row>   (update n=999)", patch_outcome))

    # ---------- Step 4: DELETE own row (reuse cached rid from Step 3) ----------
    print("\n[Step 4] Deleting own rows...")
    delete_outcome: dict[str, tuple[int, str]] = {}
    for label, key in KEYS.items():
        rid = rid_cache[label]
        if rid is None:
            delete_outcome[label] = (0, "no row to delete")
            continue
        delete_outcome[label] = call("DELETE", f"/api/v1/data/{probe_for_data}/{rid}", key=key)
    rows.append((f"4. DELETE /data/{probe_for_data}/<own row>", delete_outcome))

    # ---------- Step 5: add a column to the dynamic probe (should work) ----------
    print("\n[Step 5] Adding column to dynamic probe table...")
    addcol_outcome = run_step(
        "POST",
        lambda _: f"/api/v1/tables/{probe_for_data}/columns",
        lambda label: {"name": f"probe_col_{label.split('_')[0].lower()}", "type": "TEXT"},
    )
    rows.append((f"5. POST /tables/{probe_for_data}/columns   (add col on dynamic)", addcol_outcome))

    # ---------- Step 6: try to add a column to BUILT-IN `creators` (expect 403 both) ----------
    print("\n[Step 6] Probing built-in table (expect 403)...")
    ts_col = int(time.time())
    builtin_outcome = run_step(
        "POST",
        lambda _: "/api/v1/tables/creators/columns",
        lambda label: {"name": f"probe_x_{label.split('_')[0].lower()}_{ts_col}", "type": "TEXT"},
    )
    rows.append(("6. POST /tables/creators/columns   (built-in, expect 403)", builtin_outcome))

    # ---------- Print comparison ----------
    print()
    label_keys = list(KEYS.keys())
    col_w = max(len(l) for l in label_keys) + 2
    for title, kv in rows:
        print(title)
        for label in label_keys:
            s, b = kv[label]
            print(f"  {label:<{col_w}} HTTP {s:<4} {short(b)}")
        print()

    # ---------- Summary verdict ----------
    print("=" * 90)
    verdict_lines = []
    for label in label_keys:
        s_create = create_outcome[label][0]
        s_bulk = bulk_outcome[label][0]
        s_patch = patch_outcome[label][0]
        s_del = delete_outcome[label][0]
        s_addcol = addcol_outcome[label][0]
        s_builtin = builtin_outcome[label][0]
        flags = []
        if s_create == 200: flags.append("create-table")
        if s_bulk == 200: flags.append("bulk-write")
        if s_patch == 200: flags.append("patch")
        if s_del == 200: flags.append("delete")
        if s_addcol == 200: flags.append("add-col")
        verdict_lines.append(f"  {label}: " + (", ".join(flags) if flags else "<no write perms>"))
        if s_builtin == 200:
            verdict_lines.append(f"    !! {label} ALSO got 200 on built-in add-column — schema lock may be off")
    print("Permissions detected:")
    for line in verdict_lines:
        print(line)

    print()
    print("Probe tables left behind (ask 张 to drop in SQLite):")
    for label, (s, _, name) in create_outcome.items():
        if name:
            print(f"  - {name}   (created by {label}, HTTP {s})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
