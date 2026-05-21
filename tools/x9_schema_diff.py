"""
Compare local creators.sqlite::creators schema vs a remote X9 resource.

Usage:
    python x9_schema_diff.py                      # diff against creator_leads
    python x9_schema_diff.py --remote some_name   # diff against any resource
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib import request, error

LOCAL_SQLITE = Path(
    r"F:\AI Agent\Auto boker grab\x9_creator_desktop_system\data\creators.sqlite"
)
LOCAL_TABLE = "creators"
REMOTE_BASE = "https://usx9.us"
TIMEOUT = 10


def http_get(path: str):
    req = request.Request(REMOTE_BASE + path, headers={"Accept": "application/json"})
    try:
        with request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"NETERR: {e}"


def map_type(t: str | None) -> str:
    t = (t or "TEXT").upper()
    base = t.split("(")[0]
    if "INT" in base:
        return "INTEGER"
    if "REAL" in base or "FLOA" in base or "DOUB" in base:
        return "REAL"
    if "BLOB" in base:
        return "BLOB"
    if "NUM" in base:
        return "NUMERIC"
    return "TEXT"


def read_local() -> dict[str, dict]:
    if not LOCAL_SQLITE.exists():
        sys.exit(f"FATAL: {LOCAL_SQLITE} not found")
    con = sqlite3.connect(LOCAL_SQLITE)
    rows = con.execute(f"PRAGMA table_info({LOCAL_TABLE})").fetchall()
    con.close()
    return {
        name: {"type": map_type(ctype), "notnull": bool(notnull), "pk": bool(pk),
               "default": dflt}
        for cid, name, ctype, notnull, dflt, pk in rows
    }


def read_remote(name: str) -> dict[str, dict] | None:
    s, b = http_get(f"/api/v1/resources/{name}")
    if s != 200:
        print(f"FATAL: cannot fetch remote resource `{name}` (HTTP {s})")
        print(b[:500])
        return None
    j = json.loads(b)
    out = {}
    for c in j.get("columns", []):
        out[c["name"]] = {
            "type": map_type(c.get("type")),
            "notnull": bool(c.get("notnull")),
            "pk": bool(c.get("pk")),
            "default": c.get("default"),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--remote", default="creator_leads")
    args = ap.parse_args()

    local = read_local()
    remote = read_remote(args.remote)
    if remote is None:
        return 1

    print(f"Local : creators.sqlite::{LOCAL_TABLE}    ({len(local)} cols)")
    print(f"Remote: /api/v1/resources/{args.remote}    ({len(remote)} cols)")
    print("=" * 80)

    only_local = [c for c in local if c not in remote]
    only_remote = [c for c in remote if c not in local]
    in_both = [c for c in local if c in remote]

    type_mismatches = []
    for c in in_both:
        if local[c]["type"] != remote[c]["type"]:
            type_mismatches.append((c, local[c]["type"], remote[c]["type"]))

    print(f"\n[+] Only on LOCAL  ({len(only_local)})  — would need to ADD on remote:")
    for c in only_local:
        print(f"    + {c:<35} {local[c]['type']}")

    print(f"\n[-] Only on REMOTE ({len(only_remote)})  — extra cols on remote (cannot drop via API):")
    for c in only_remote:
        print(f"    - {c:<35} {remote[c]['type']}")

    print(f"\n[!] Type mismatches ({len(type_mismatches)})  — cannot fix via API, would need DROP+RECREATE:")
    for c, lt, rt in type_mismatches:
        print(f"    ! {c:<35} local={lt}  remote={rt}")

    print(f"\n[=] Identical columns ({len(in_both) - len(type_mismatches)})")

    print("\n" + "=" * 80)
    if not only_remote and not type_mismatches:
        print(f"VERDICT: SAFE to MODIFY. Add {len(only_local)} columns via")
        print(f"         POST /api/v1/tables/{args.remote}/columns  (one call per missing col)")
    elif only_remote and not type_mismatches:
        print(f"VERDICT: PARTIALLY MIGRATABLE. Can add {len(only_local)} cols, but {len(only_remote)} extra")
        print(f"         cols on remote will linger (API has no DROP COLUMN). Consider rebuild.")
    else:
        print(f"VERDICT: REBUILD RECOMMENDED. {len(type_mismatches)} type mismatches cannot be fixed via API.")
        print(f"         Ask 张 to DROP the underlying physical table in SQLite, then recreate.")


if __name__ == "__main__":
    sys.exit(main() or 0)
