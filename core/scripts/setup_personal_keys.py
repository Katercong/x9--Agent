"""One-time bootstrap helper to set up personal keys for 张 and 廖.

Strategy (idempotent — safe to run twice):
  1. Take the existing .api_key (currently bound to zhang) and re-assign to 廖
     so 廖 keeps using the same token he was already given.
  2. Issue a brand-new admin key for 张.
  3. Save BOTH plaintext tokens to .local_keys_backup.txt as the local backup.
  4. Write/update .gitignore to make sure none of these files leak.

After running:
  - Tell 廖 nothing — his existing token now correctly authenticates as 廖.
  - Open .local_keys_backup.txt and copy 张's NEW token into the front-end login.
  - You can safely delete the original .api_key file (same value is in the backup).
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
BACKUP_FILE = ROOT / ".local_keys_backup.txt"
GITIGNORE = ROOT / ".gitignore"
SENSITIVE_FILES = [
    ".api_key",
    ".local_keys_backup.txt",
    ".bootstrap_admin_key_FIRST_USE_ONLY.txt",
    "database.db",
    "database.db-shm",
    "database.db-wal",
    "exports/",
    "__pycache__/",
    "app/__pycache__/",
]


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def update_gitignore() -> None:
    existing = set()
    if GITIGNORE.exists():
        existing = {ln.strip() for ln in GITIGNORE.read_text(encoding="utf-8").splitlines() if ln.strip()}
    merged = sorted(existing | set(SENSITIVE_FILES))
    GITIGNORE.write_text("# Sensitive: do not commit\n" + "\n".join(merged) + "\n", encoding="utf-8")


def main() -> None:
    if not LEGACY_KEY_FILE.exists():
        print(f"[setup] ERROR: {LEGACY_KEY_FILE.name} not found.")
        print(f"[setup] If you've already run this once, the swap is done — open {BACKUP_FILE.name} to read your tokens.")
        return

    legacy_token = LEGACY_KEY_FILE.read_text(encoding="ascii").strip()
    if not legacy_token:
        print(f"[setup] ERROR: {LEGACY_KEY_FILE.name} is empty.")
        return

    h = sha256(legacy_token)

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    legacy_row = con.execute("SELECT id, user_id FROM api_key WHERE key_hash=?", (h,)).fetchone()
    if not legacy_row:
        print("[setup] ERROR: the token in .api_key does not match any DB key.")
        print("[setup] Migration may have already happened differently. Use reset_key.bat instead.")
        con.close()
        return

    zhang_row = con.execute("SELECT id FROM api_user WHERE username='zhang'").fetchone()
    liao_row = con.execute("SELECT id FROM api_user WHERE username='liao'").fetchone()
    if not zhang_row or not liao_row:
        print("[setup] ERROR: expected users 'zhang' and 'liao' in api_user. Aborting.")
        con.close()
        return
    zhang_id, liao_id = zhang_row[0], liao_row[0]

    if legacy_row["user_id"] == liao_id:
        print(f"[setup] Already swapped — the legacy token is already 廖's.")
        print(f"[setup] If you need 张's token, open {BACKUP_FILE.name}.")
        print(f"[setup] If that file is missing, run: reset_key.bat zhang")
        con.close()
        return
    if legacy_row["user_id"] != zhang_id:
        print(f"[setup] ERROR: legacy key belongs to user_id={legacy_row['user_id']}, not zhang. Aborting.")
        con.close()
        return

    # ---- 1. Re-assign legacy key from zhang to liao ----
    con.execute(
        "UPDATE api_key SET user_id=?, description=? WHERE id=?",
        (liao_id, "原 .api_key 直接转给廖 (setup_personal_keys.py)", legacy_row["id"])
    )

    # ---- 2. Generate fresh admin key for zhang ----
    new_zhang_token = secrets.token_urlsafe(32)
    con.execute(
        "INSERT INTO api_key(user_id, key_hash, prefix, description) VALUES(?,?,?,?)",
        (zhang_id, sha256(new_zhang_token), new_zhang_token[:8],
         "张的新 admin key (setup_personal_keys.py)")
    )
    con.commit()
    con.close()

    # ---- 3. Save backup file ----
    BACKUP_FILE.write_text(
        f"X9 Database — local key backup\n"
        f"=================================\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"⚠ ALL KEYS BELOW ARE PLAINTEXT ADMIN CREDENTIALS\n"
        f"⚠ Anyone with this file has full database access\n"
        f"⚠ Already added to .gitignore — do NOT commit, share, screenshot, or paste in chat\n"
        f"⚠ Recommended: store these in 1Password / Bitwarden, then delete this file\n\n"
        f"=== 张 (zhang) — admin ===\n"
        f"{new_zhang_token}\n\n"
        f"=== 廖 (liao) — admin (= 之前 .api_key 那串，廖已收到) ===\n"
        f"{legacy_token}\n\n"
        f"--- Quick reference ---\n"
        f"Frontend login: paste your own token into the login overlay\n"
        f"Lost both tokens? Run: reset_key.bat <username>\n",
        encoding="utf-8"
    )

    # ---- 4. Update .gitignore ----
    update_gitignore()

    print("=" * 70)
    print("[OK] Done.")
    print()
    print("Final state:")
    print(f"  zhang : NEW admin token (saved to {BACKUP_FILE.name})")
    print(f"  liao  : keeps original .api_key token (no notification needed — he already has it)")
    print()
    print(f"Backup file written: {BACKUP_FILE}")
    print(f".gitignore updated to exclude all sensitive files")
    print()
    print("Next steps:")
    print(f"  1. Open  {BACKUP_FILE.name}  and copy 张's NEW token")
    print(f"  2. Restart run.bat, log in to the front-end with that token")
    print(f"  3. (Optional) Delete the old {LEGACY_KEY_FILE.name} file —")
    print(f"     same value is now in the backup; the file itself is no longer needed.")
    print(f"     You can also leave it as 廖's emergency-recovery copy.")
    print("=" * 70)


if __name__ == "__main__":
    main()
