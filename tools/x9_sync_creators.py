"""
Sync local creators.sqlite -> remote X9 API.

Reads `creators` table from
  F:\\AI Agent\\Auto boker grab\\x9_creator_desktop_system\\data\\creators.sqlite
and pushes every row to a dynamic remote table called `tk_creators`,
upserting on (platform, handle).

Usage:
    # 1) Dry-run: just print what would happen, no writes
    python x9_sync_creators.py

    # 2) Inspect local schema only (no API calls)
    python x9_sync_creators.py --inspect

    # 3) Create the remote table if missing, then push everything
    python x9_sync_creators.py --commit

    # 4) Custom batch size, custom remote table name
    python x9_sync_creators.py --commit --batch 500 --remote-table my_table

Notes:
- Re-runnable: existing rows on remote are upserted by (platform, handle).
- JSON columns (those ending in _json) are stored as text on the remote.
- Datetime columns are serialized to ISO 8601 strings.
- The remote table will not be auto-deleted; ask 张 to drop manually if needed.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, date
from pathlib import Path
from urllib import request, error

# ----------------------------- Config ---------------------------------------

LOCAL_SQLITE = Path(
    r"F:\AI Agent\Auto boker grab\x9_creator_desktop_system\data\creators.sqlite"
)
LOCAL_TABLE = "creators"

REMOTE_BASE = "http://192.168.1.168:18765"
REMOTE_KEY = "TwXKU_xzfLt-kNj5b8IzSPxYi27KrcOyd-9DNppYPco"
DEFAULT_REMOTE_TABLE = "tk_creators"

UPSERT_KEYS = ["platform", "handle"]  # matches the local UNIQUE constraint
TIMEOUT = 20

# ---------------------------------------------------------------------------


def http(method: str, path: str, body: dict | None = None, auth: bool = False) -> tuple[int, str]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
    if auth:
        headers["X-API-Key"] = REMOTE_KEY
    req = request.Request(REMOTE_BASE + path, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"NETERR: {e}"


# --------------------- Local SQLite inspection ------------------------------


def inspect_local() -> list[dict]:
    """Return column metadata from the local table via PRAGMA table_info."""
    if not LOCAL_SQLITE.exists():
        sys.exit(f"FATAL: local sqlite not found: {LOCAL_SQLITE}")
    con = sqlite3.connect(LOCAL_SQLITE)
    try:
        rows = con.execute(f"PRAGMA table_info({LOCAL_TABLE})").fetchall()
    finally:
        con.close()
    if not rows:
        sys.exit(f"FATAL: table `{LOCAL_TABLE}` not found in {LOCAL_SQLITE}")
    cols = []
    for cid, name, ctype, notnull, dflt, pk in rows:
        cols.append({
            "cid": cid,
            "name": name,
            "type": (ctype or "TEXT").upper().split("(")[0],  # e.g. VARCHAR(120) -> VARCHAR
            "notnull": bool(notnull),
            "default": dflt,
            "pk": bool(pk),
        })
    return cols


def map_type_to_remote(local_type: str) -> str:
    """Map local SQLite/SQLAlchemy types to the X9 API's accepted types."""
    t = local_type.upper()
    if "INT" in t:
        return "INTEGER"
    if "REAL" in t or "FLOA" in t or "DOUB" in t:
        return "REAL"
    if "BLOB" in t:
        return "BLOB"
    # NUMERIC stays NUMERIC; everything else (VARCHAR, TEXT, DATETIME) becomes TEXT
    if "NUM" in t:
        return "NUMERIC"
    return "TEXT"


def build_remote_columns(local_cols: list[dict]) -> tuple[list[dict], list[str]]:
    """Convert local column list to the body expected by POST /api/v1/tables.

    Returns (remote_columns, json_col_names).
    Skips `id` (the API auto-adds an `id INTEGER PK` column).
    """
    remote_cols = []
    json_cols = []
    for c in local_cols:
        if c["name"] == "id":
            continue  # API adds its own id column
        # Skip created_at/updated_at — API adds created_at automatically. We'll
        # still pass updated_at as a regular TEXT column so we don't lose it.
        if c["name"] == "created_at":
            continue
        col = {"name": c["name"], "type": map_type_to_remote(c["type"])}
        if c["notnull"] and c["name"] not in ("platform",):  # platform has a default
            col["not_null"] = True
        if c["default"] is not None:
            col["default"] = c["default"]
        remote_cols.append(col)
        if c["name"].endswith("_json"):
            json_cols.append(c["name"])
    return remote_cols, json_cols


# --------------------- Remote table create/check ----------------------------


def remote_resource_exists(name: str) -> bool:
    s, b = http("GET", f"/api/v1/resources/{name}")
    return s == 200


def create_remote_table(name: str, columns: list[dict], json_cols: list[str]) -> tuple[int, str]:
    body = {
        "name": name,
        "description": "Mirror of local creators.sqlite::creators (Liao's recommendation list)",
        "columns": columns,
        "upsert_keys": UPSERT_KEYS,
        "json_cols": json_cols,
    }
    return http("POST", "/api/v1/tables", body=body, auth=True)


# --------------------- Row read + serialize --------------------------------


def serialize_value(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def read_local_rows() -> tuple[list[str], list[dict]]:
    con = sqlite3.connect(LOCAL_SQLITE)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(f"SELECT * FROM {LOCAL_TABLE}").fetchall()
    finally:
        con.close()
    if not rows:
        return [], []
    cols = list(rows[0].keys())
    out = []
    for r in rows:
        d = {}
        for c in cols:
            if c in ("id", "created_at"):  # let remote auto-assign
                continue
            d[c] = serialize_value(r[c])
        out.append(d)
    return [c for c in cols if c not in ("id", "created_at")], out


# --------------------- Push -------------------------------------------------


def push_rows(remote_table: str, rows: list[dict], batch: int, commit: bool) -> dict:
    total = len(rows)
    inserted = updated = skipped = errors = 0
    error_samples = []
    for i in range(0, total, batch):
        chunk = rows[i:i + batch]
        body = {"items": chunk}
        if not commit:
            print(f"  [DRY-RUN] would POST /api/v1/data/{remote_table}/bulk  with {len(chunk)} rows "
                  f"(rows {i+1}-{i+len(chunk)})")
            continue
        s, b = http("POST", f"/api/v1/data/{remote_table}/bulk", body=body, auth=True)
        if s != 200:
            errors += len(chunk)
            error_samples.append(f"HTTP {s}: {b[:300]}")
            print(f"  batch {i+1}-{i+len(chunk)}: HTTP {s}  {b[:200]}")
            continue
        try:
            j = json.loads(b)
            inserted += j.get("inserted", 0)
            updated += j.get("updated", 0)
            skipped += j.get("skipped", 0)
            if j.get("errors"):
                error_samples.append(f"row errors: {json.dumps(j['errors'])[:300]}")
        except Exception:
            pass
        print(f"  batch {i+1}-{i+len(chunk)}: HTTP {s}  inserted={j.get('inserted')} "
              f"updated={j.get('updated')} skipped={j.get('skipped')}")
    return {
        "total": total, "inserted": inserted, "updated": updated, "skipped": skipped,
        "errors": errors, "error_samples": error_samples,
    }


# --------------------- Main -------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", action="store_true", help="dump local schema and exit")
    ap.add_argument("--commit", action="store_true", help="actually write to remote")
    ap.add_argument("--batch", type=int, default=200)
    ap.add_argument("--remote-table", default=DEFAULT_REMOTE_TABLE)
    args = ap.parse_args()

    print(f"Local : {LOCAL_SQLITE}::{LOCAL_TABLE}")
    print(f"Remote: {REMOTE_BASE} -> resource `{args.remote_table}`")
    print(f"Mode  : {'COMMIT (will write)' if args.commit else 'DRY-RUN (no writes)'}")
    print("=" * 80)

    local_cols = inspect_local()
    print(f"\n[1] Local schema: {len(local_cols)} columns")
    for c in local_cols[:5]:
        print(f"    {c['name']}  {c['type']}  notnull={c['notnull']}  pk={c['pk']}")
    if len(local_cols) > 5:
        print(f"    ... and {len(local_cols)-5} more")

    if args.inspect:
        print("\n--- full local schema ---")
        for c in local_cols:
            print(f"  {c['name']:<35} {c['type']:<12} notnull={c['notnull']} pk={c['pk']}  default={c['default']}")
        return

    remote_cols, json_cols = build_remote_columns(local_cols)
    print(f"\n[2] Remote table plan: {len(remote_cols)} columns, {len(json_cols)} json cols")
    print(f"    upsert_keys = {UPSERT_KEYS}")

    print(f"\n[3] Checking if remote table `{args.remote_table}` exists...")
    if remote_resource_exists(args.remote_table):
        print(f"    EXISTS — will upsert into it")
    else:
        print(f"    MISSING — will create it")
        if args.commit:
            s, b = create_remote_table(args.remote_table, remote_cols, json_cols)
            if s != 200:
                print(f"    !!! create failed HTTP {s}: {b[:400]}")
                return 1
            print(f"    OK created (HTTP {s})")
        else:
            print(f"    [DRY-RUN] would POST /api/v1/tables  body={{name:{args.remote_table}, "
                  f"{len(remote_cols)} columns, json_cols={json_cols}, upsert_keys={UPSERT_KEYS}}}")

    print(f"\n[4] Reading local rows...")
    cols, rows = read_local_rows()
    print(f"    {len(rows)} rows, {len(cols)} columns each")
    if not rows:
        print("    nothing to push.")
        return

    print(f"\n[5] Pushing in batches of {args.batch}...")
    t0 = time.time()
    summary = push_rows(args.remote_table, rows, args.batch, args.commit)
    dt = time.time() - t0

    print("\n" + "=" * 80)
    if args.commit:
        print(f"DONE in {dt:.1f}s — total={summary['total']} inserted={summary['inserted']} "
              f"updated={summary['updated']} skipped={summary['skipped']} errors={summary['errors']}")
        for s in summary["error_samples"][:5]:
            print(f"  err: {s}")
    else:
        print(f"DRY-RUN complete. Re-run with --commit to actually write.")


if __name__ == "__main__":
    sys.exit(main() or 0)
