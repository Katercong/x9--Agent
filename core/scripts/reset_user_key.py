"""Admin CLI: reset a user's API key.

Usage (run on the server machine, where database.db is):

    # Issue a new key for 廖, revoke all his existing ones
    python scripts/reset_user_key.py liao

    # Same but keep existing keys active (just add one more)
    python scripts/reset_user_key.py liao --add

    # Reset 张's key (emergency recovery if you've lost localStorage AND .api_key)
    python scripts/reset_user_key.py zhang

    # List users (show who's available)
    python scripts/reset_user_key.py --list

The new token is printed to stdout once. Save it immediately.

This is intentionally a CLI tool, not an API: it's the mechanism of last
resort when nobody can log into the web UI.
"""
from __future__ import annotations
import argparse
import hashlib
import secrets
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def list_users() -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT u.id, u.username, u.display_name, u.role, u.active, "
        "(SELECT COUNT(*) FROM api_key k WHERE k.user_id=u.id AND k.revoked=0) AS active_keys "
        "FROM api_user u ORDER BY u.id"
    ).fetchall()
    con.close()
    print(f"{'id':>3}  {'username':<12} {'display':<10} {'role':<10} active  active_keys")
    print("-" * 60)
    for r in rows:
        print(f"{r['id']:>3}  {r['username']:<12} {r['display_name']:<10} "
              f"{r['role']:<10} {'yes' if r['active'] else 'NO ':<6}  {r['active_keys']}")


def reset(username: str, *, add: bool = False) -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    user = con.execute(
        "SELECT id, username, display_name, role, active FROM api_user WHERE username=?",
        (username.lower(),)
    ).fetchone()
    if not user:
        print(f"[reset] user '{username}' not found. Available users:")
        con.close()
        list_users()
        sys.exit(1)

    if not user["active"]:
        print(f"[reset] WARN: user '{username}' is currently inactive — reactivating")
        con.execute("UPDATE api_user SET active=1 WHERE id=?", (user["id"],))

    if not add:
        n = con.execute(
            "UPDATE api_key SET revoked=1 WHERE user_id=? AND revoked=0",
            (user["id"],)
        ).rowcount
        if n > 0:
            print(f"[reset] revoked {n} existing key(s) for {username}")

    token = secrets.token_urlsafe(32)
    con.execute(
        "INSERT INTO api_key(user_id, key_hash, prefix, description) VALUES(?,?,?,?)",
        (user["id"], sha256(token), token[:8], "issued by reset_user_key.py CLI")
    )
    con.commit()
    con.close()

    print()
    print("=" * 70)
    print(f"  NEW API KEY for user '{username}' (role: {user['role']}, display: {user['display_name']})")
    print("=" * 70)
    print()
    print(f"  {token}")
    print()
    print("=" * 70)
    print("  ⚠ This is the ONLY time you'll see this token. Copy it now.")
    print("  ⚠ Server only stored its SHA-256 hash; cannot be recovered.")
    if not add:
        print(f"  ✓ All previous keys for '{username}' have been revoked.")
    else:
        print(f"  ✓ Previous keys for '{username}' remain active (--add mode).")
    print("=" * 70)


def main() -> None:
    p = argparse.ArgumentParser(description="Reset a user's API key (server-side admin tool)")
    p.add_argument("username", nargs="?", help="user to reset (or omit with --list)")
    p.add_argument("--add", action="store_true",
                   help="add a new key without revoking existing ones")
    p.add_argument("--list", action="store_true", help="list all users + key counts")
    args = p.parse_args()

    if args.list or not args.username:
        list_users()
        if not args.username:
            print()
            print("Usage: python scripts/reset_user_key.py <username> [--add]")
        return

    reset(args.username, add=args.add)


if __name__ == "__main__":
    main()
