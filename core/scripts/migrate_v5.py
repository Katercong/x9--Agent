"""Schema migration v5: multi-user RBAC for API keys.

Replaces the single shared `.api_key` model with proper user accounts + per-user
keys (hashed at rest via SHA-256). Roles: admin / user / readonly.

On first run:
  - creates api_user + api_key tables
  - migrates existing .api_key (if any) -> admin user '张' with that token
  - creates user '廖' (admin) with NO key — 张 must issue from UI
  - generates a fresh admin token if no .api_key exists, prints once

Idempotent.
"""
from __future__ import annotations
import hashlib
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"
LEGACY_KEY_FILE = ROOT / ".api_key"

CREATE_USER_SQL = """
CREATE TABLE IF NOT EXISTS api_user (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    display_name  TEXT,
    role          TEXT NOT NULL DEFAULT 'user'
                  CHECK (role IN ('admin','user','readonly')),
    active        INTEGER NOT NULL DEFAULT 1,
    notes         TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now'))
)
"""

CREATE_KEY_SQL = """
CREATE TABLE IF NOT EXISTS api_key (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES api_user(id) ON DELETE CASCADE,
    key_hash     TEXT UNIQUE NOT NULL,                  -- sha256 hex
    prefix       TEXT NOT NULL,                          -- first 8 chars (display)
    description  TEXT,
    last_used_at TEXT,
    expires_at   TEXT,
    revoked      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT DEFAULT (datetime('now'))
)
"""


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute(CREATE_USER_SQL)
    con.execute(CREATE_KEY_SQL)
    con.commit()

    n_users = con.execute("SELECT COUNT(*) FROM api_user").fetchone()[0]
    if n_users > 0:
        print(f"[migrate_v5] api_user already has {n_users} rows; skipping bootstrap")
        for u in con.execute("SELECT username, display_name, role, active FROM api_user"):
            print(f"   - {u['username']} ({u['display_name']}) role={u['role']} active={u['active']}")
        con.close()
        return

    # ----- Bootstrap 张 (admin) -----
    con.execute(
        "INSERT INTO api_user(username, display_name, role) VALUES('zhang', '张', 'admin')"
    )
    zhang_id = con.execute("SELECT id FROM api_user WHERE username='zhang'").fetchone()[0]

    # If legacy .api_key exists, migrate it to 张's first key (no plaintext leakage)
    legacy_used = False
    if LEGACY_KEY_FILE.exists():
        legacy_token = LEGACY_KEY_FILE.read_text(encoding="ascii").strip()
        if legacy_token:
            con.execute(
                "INSERT INTO api_key(user_id, key_hash, prefix, description) VALUES(?,?,?,?)",
                (zhang_id, sha256(legacy_token), legacy_token[:8],
                 "migrated from legacy .api_key on " + datetime.utcnow().strftime("%Y-%m-%d"))
            )
            legacy_used = True

    if not legacy_used:
        # Generate a brand-new admin token; print once
        token = secrets.token_urlsafe(32)
        con.execute(
            "INSERT INTO api_key(user_id, key_hash, prefix, description) VALUES(?,?,?,?)",
            (zhang_id, sha256(token), token[:8], "auto-generated bootstrap admin key")
        )
        # Persist printed-once notice to a file too, in case user missed the console
        bootstrap_note = ROOT / ".bootstrap_admin_key_FIRST_USE_ONLY.txt"
        bootstrap_note.write_text(
            f"BOOTSTRAP ADMIN KEY (user: 张)\n"
            f"=============================\n\n"
            f"{token}\n\n"
            f"⚠️ DELETE THIS FILE after you've copied the key into the front-end.\n"
            f"⚠️ Anyone with this file gets full admin access.\n",
            encoding="utf-8"
        )
        print(f"[migrate_v5] !!! NEW ADMIN KEY (also saved to {bootstrap_note.name}, delete after use):")
        print(f"            {token}")

    # ----- Bootstrap 廖 (admin, no key yet) -----
    con.execute(
        "INSERT INTO api_user(username, display_name, role, notes) "
        "VALUES('liao', '廖', 'admin', '由 张 在前台「设置→用户管理」处签发首把 Key')"
    )
    con.commit()

    print("[migrate_v5] users created:")
    for u in con.execute("SELECT u.id, u.username, u.display_name, u.role, "
                         "(SELECT COUNT(*) FROM api_key k WHERE k.user_id=u.id) AS keys "
                         "FROM api_user u"):
        print(f"   #{u['id']:2d} {u['username']:8s} {u['display_name']:6s} role={u['role']:8s} keys={u['keys']}")

    if legacy_used:
        print("[migrate_v5] 张's existing .api_key still works — log in with it.")
        print("[migrate_v5] for 廖: log in as 张, go to Settings → Users → 廖 → Issue New Key.")
    con.close()


if __name__ == "__main__":
    main()
