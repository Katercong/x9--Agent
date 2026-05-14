"""User & API-key management endpoints (admin-gated)."""
from __future__ import annotations
import hashlib
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_admin, require_authenticated, sha256

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"

router = APIRouter()

ALLOWED_ROLES = {"admin", "user", "readonly"}


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# ==================== whoami ====================
@router.get("/api/v1/auth/whoami")
def whoami(user: dict = Depends(require_authenticated)) -> dict:
    """Returns the current logged-in user. Frontend uses this to gate UI."""
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "key_id": user["key_id"],
        "key_prefix": user["prefix"],
    }


# ==================== Users ====================
@router.get("/api/v1/auth/users", dependencies=[Depends(require_admin)])
def list_users() -> dict:
    con = _con()
    rows = con.execute(
        "SELECT u.id, u.username, u.display_name, u.role, u.active, u.notes, "
        "       u.created_at, u.updated_at, "
        "       (SELECT COUNT(*) FROM api_key k WHERE k.user_id=u.id AND k.revoked=0) AS active_keys, "
        "       (SELECT COUNT(*) FROM api_key k WHERE k.user_id=u.id) AS total_keys, "
        "       (SELECT MAX(k.last_used_at) FROM api_key k WHERE k.user_id=u.id) AS last_used_at "
        "FROM api_user u ORDER BY u.id"
    ).fetchall()
    con.close()
    return {"items": [dict(r) for r in rows]}


@router.post("/api/v1/auth/users", dependencies=[Depends(require_admin)])
async def create_user(payload: dict) -> dict:
    username = (payload.get("username") or "").strip().lower()
    if not username or not all(c.isalnum() or c == "_" for c in username):
        raise HTTPException(400, "username must be alphanumeric/underscore")
    role = payload.get("role", "user")
    if role not in ALLOWED_ROLES:
        raise HTTPException(400, f"role must be one of {sorted(ALLOWED_ROLES)}")
    con = _con()
    try:
        if con.execute("SELECT 1 FROM api_user WHERE username=?", (username,)).fetchone():
            raise HTTPException(409, f"user '{username}' already exists")
        con.execute(
            "INSERT INTO api_user(username, display_name, role, notes) VALUES(?,?,?,?)",
            (username, payload.get("display_name") or username, role, payload.get("notes"))
        )
        con.commit()
        uid = con.execute("SELECT id FROM api_user WHERE username=?", (username,)).fetchone()[0]
    finally:
        con.close()
    return {"ok": True, "user_id": uid, "username": username, "role": role}


@router.patch("/api/v1/auth/users/{user_id}", dependencies=[Depends(require_admin)])
async def update_user(user_id: int, payload: dict) -> dict:
    fields: dict[str, Any] = {}
    if "display_name" in payload: fields["display_name"] = payload["display_name"]
    if "role" in payload:
        if payload["role"] not in ALLOWED_ROLES:
            raise HTTPException(400, f"role must be one of {sorted(ALLOWED_ROLES)}")
        fields["role"] = payload["role"]
    if "active" in payload: fields["active"] = int(bool(payload["active"]))
    if "notes" in payload: fields["notes"] = payload["notes"]
    if not fields:
        raise HTTPException(400, "no editable fields")
    con = _con()
    try:
        if not con.execute("SELECT 1 FROM api_user WHERE id=?", (user_id,)).fetchone():
            raise HTTPException(404, "user not found")
        sets = ",".join([f"{k}=?" for k in fields]) + ", updated_at=datetime('now')"
        con.execute(f"UPDATE api_user SET {sets} WHERE id=?",
                    list(fields.values()) + [user_id])
        con.commit()
    finally:
        con.close()
    return {"ok": True, "user_id": user_id, "updated_fields": list(fields.keys())}


@router.delete("/api/v1/auth/users/{user_id}", dependencies=[Depends(require_admin)])
async def delete_user(user_id: int, current: dict = Depends(require_admin)) -> dict:
    if user_id == current["user_id"]:
        raise HTTPException(400, "you cannot delete your own user")
    con = _con()
    try:
        if not con.execute("SELECT 1 FROM api_user WHERE id=?", (user_id,)).fetchone():
            raise HTTPException(404, "user not found")
        # ensure at least 1 admin remains
        admins = con.execute("SELECT COUNT(*) FROM api_user WHERE role='admin' AND active=1").fetchone()[0]
        target_role = con.execute("SELECT role FROM api_user WHERE id=?", (user_id,)).fetchone()[0]
        if admins <= 1 and target_role == "admin":
            raise HTTPException(400, "cannot delete the last admin")
        con.execute("DELETE FROM api_user WHERE id=?", (user_id,))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "deleted": user_id}


# ==================== Keys ====================
@router.get("/api/v1/auth/users/{user_id}/keys", dependencies=[Depends(require_admin)])
def list_user_keys(user_id: int) -> dict:
    con = _con()
    rows = con.execute(
        "SELECT id, user_id, prefix, description, last_used_at, expires_at, revoked, scopes, created_at "
        "FROM api_key WHERE user_id=? ORDER BY id DESC", (user_id,)
    ).fetchall()
    con.close()
    return {"items": [dict(r) for r in rows]}


@router.post("/api/v1/auth/users/{user_id}/keys", dependencies=[Depends(require_admin)])
async def issue_key(user_id: int, payload: dict | None = None) -> dict:
    """Create a fresh API key for a user. The plaintext token is returned ONCE
    in the response — server stores only the SHA-256 hash."""
    payload = payload or {}
    con = _con()
    try:
        if not con.execute("SELECT 1 FROM api_user WHERE id=?", (user_id,)).fetchone():
            raise HTTPException(404, "user not found")
        token = secrets.token_urlsafe(32)
        con.execute(
            "INSERT INTO api_key(user_id, key_hash, prefix, description, expires_at) "
            "VALUES(?,?,?,?,?)",
            (user_id, sha256(token), token[:8],
             payload.get("description") or "", payload.get("expires_at"))
        )
        kid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.commit()
    finally:
        con.close()
    return {
        "ok": True, "key_id": kid, "user_id": user_id,
        "token": token,                    # PLAINTEXT — shown ONCE
        "prefix": token[:8],
        "warning": "Save this token now. It will NOT be shown again.",
    }


@router.patch("/api/v1/auth/keys/{key_id}/scopes", dependencies=[Depends(require_admin)])
async def set_key_scopes(key_id: int, payload: dict) -> dict:
    """Set scopes on a key. Admin only.

    body: {"scopes": ["write:tk_*", "read:*"]}  — list of scope strings
    body: {"scopes": null}                       — clear scopes (revert to role)

    Scope syntax (see auth.py): 'admin' | 'admin:<pat>' | 'write:<pat>' | 'read:<pat>'
    """
    import json as _j
    scopes_val = payload.get("scopes")
    if scopes_val is not None:
        if not isinstance(scopes_val, list) or not all(isinstance(s, str) for s in scopes_val):
            raise HTTPException(400, "scopes must be null or list of strings")
        scopes_json = _j.dumps(scopes_val)
    else:
        scopes_json = None
    con = _con()
    try:
        existing = con.execute("SELECT id FROM api_key WHERE id=?", (key_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "key not found")
        con.execute("UPDATE api_key SET scopes=? WHERE id=?", (scopes_json, key_id))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "key_id": key_id, "scopes": scopes_val}


@router.delete("/api/v1/auth/keys/{key_id}", dependencies=[Depends(require_admin)])
async def revoke_key(key_id: int, current: dict = Depends(require_admin)) -> dict:
    con = _con()
    try:
        row = con.execute("SELECT user_id FROM api_key WHERE id=?", (key_id,)).fetchone()
        if not row:
            raise HTTPException(404, "key not found")
        # safety: cannot revoke the key you're currently using
        if key_id == current["key_id"]:
            raise HTTPException(400, "cannot revoke the key you're currently authenticated with — use a different admin key first")
        con.execute("UPDATE api_key SET revoked=1 WHERE id=?", (key_id,))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "revoked_key_id": key_id}
