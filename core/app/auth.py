"""Multi-user RBAC authentication.

Replaces the single-key model with proper user accounts. Tokens are stored
hashed (SHA-256) in api_key; only the prefix is shown.

Usage in routes:
    from fastapi import Depends
    from app.auth import require_authenticated, require_admin

    @router.post("/api/v1/data/...")
    def write(_user = Depends(require_authenticated)):
        ...

    @router.post("/api/v1/tables")
    def schema_change(_user = Depends(require_admin)):
        ...

Callers send `X-API-Key: <token>` header.
"""
from __future__ import annotations
import fnmatch
import hashlib
import ipaddress
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Header, HTTPException, Request, status, Depends

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"
_TRUTHY = {"1", "true", "yes", "on", "local", "loopback"}
# Explicit strict opt-out: require a valid X-API-Key even for loopback.
_STRICT = {"0", "false", "no", "off", "none", "strict", "require"}


def _env_core_auth_disabled() -> str:
    return (
        os.environ.get("X9_CORE_API_AUTH_DISABLED")
        or os.environ.get("X9_API_AUTH_DISABLED")
        or ""
    ).strip().lower()


def _is_loopback_request(request: Request | None) -> bool:
    host = getattr(getattr(request, "client", None), "host", None)
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    host = host.split("%", 1)[0]
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _core_auth_bypass_enabled(request: Request | None) -> bool:
    """Local requests are auth-free by default ("后端本地免鉴权").

    - mode == "all": bypass unconditionally (incl. public traffic).
    - explicit strict opt-out (0/false/off/strict/...): always require key.
    - default (env unset) OR any truthy value: bypass only for
      loopback/same-machine requests. The desktop backend reverse-proxies
      /api/v1/* to core over 127.0.0.1, so this makes those proxied calls
      work without a key while public traffic (via the cloudflared tunnel,
      never loopback) still needs a valid X-API-Key.
    """
    mode = _env_core_auth_disabled()
    if mode == "all":
        return True
    if mode in _STRICT:
        return False
    return _is_loopback_request(request)


def _local_admin_user() -> dict[str, Any]:
    return {
        "user_id": 0,
        "username": "local_api",
        "display_name": "Local API",
        "role": "admin",
        "active": 1,
        "key_id": 0,
        "prefix": "local",
        "revoked": 0,
        "expires_at": None,
        "scopes": None,
    }


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _open() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def get_user_from_key(api_key: str | None) -> dict | None:
    """Resolve token -> user. Returns None if invalid/revoked/expired/inactive."""
    if not api_key:
        return None
    h = sha256(api_key.strip())
    con = _open()
    try:
        row = con.execute(
            "SELECT u.id AS user_id, u.username, u.display_name, u.role, u.active, "
            "       k.id AS key_id, k.prefix, k.revoked, k.expires_at, k.scopes "
            "FROM api_key k JOIN api_user u ON u.id = k.user_id "
            "WHERE k.key_hash = ?",
            (h,)
        ).fetchone()
        if not row:
            return None
        if row["revoked"] or not row["active"]:
            return None
        if row["expires_at"]:
            try:
                if datetime.fromisoformat(row["expires_at"]) <= datetime.utcnow():
                    return None
            except ValueError:
                pass
        # update last_used_at (best-effort)
        try:
            con.execute("UPDATE api_key SET last_used_at=datetime('now') WHERE id=?",
                        (row["key_id"],))
            con.commit()
        except Exception:
            pass
        return dict(row)
    finally:
        con.close()


def require_authenticated(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    """Any authenticated user (admin / user / readonly)."""
    user = get_user_from_key(x_api_key)
    if not user and _core_auth_bypass_enabled(request):
        return _local_admin_user()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid X-API-Key (have you logged in via Settings?)",
        )
    return user


def _parse_scopes(user: dict) -> list[str] | None:
    """Returns scope list, or None if user has no scopes (use role)."""
    raw = user.get("scopes")
    if not raw:
        return None
    try:
        v = json.loads(raw) if isinstance(raw, str) else raw
        return [s for s in v if isinstance(s, str)] if isinstance(v, list) else None
    except Exception:
        return None


_ACTION_RANK = {"read": 1, "write": 2, "admin": 3}


def _scope_grants(scopes: list[str], action: str, resource: str | None) -> bool:
    """Check if scope list grants `action` on `resource`.

    Higher action implies lower (admin grants write+read, write grants read).
    'admin' bare = all-resources. 'admin:pat' = pattern-restricted admin.
    Pattern uses fnmatch: '*' = any, 'tk_*' = prefix.
    """
    needed = _ACTION_RANK.get(action, 0)
    for sc in scopes:
        if sc == "admin":
            return True  # bare admin = all
        if ":" not in sc:
            continue
        sc_action, sc_pattern = sc.split(":", 1)
        if _ACTION_RANK.get(sc_action, 0) < needed:
            continue
        if resource is None or fnmatch.fnmatch(resource, sc_pattern):
            return True
    return False


def assert_can(user: dict, action: str, resource: str | None = None) -> None:
    """Resource-level permission gate. Call inside handlers after auth dep.

    If user has scopes set, scopes are authoritative (resource pattern enforced).
    Otherwise falls back to role check (admin > user > readonly).
    Raises 403 on deny.
    """
    scopes = _parse_scopes(user)
    if scopes is not None:
        if _scope_grants(scopes, action, resource):
            return
        raise HTTPException(
            403,
            f"scope check failed: need '{action}' on '{resource}'. "
            f"Your scopes: {scopes}"
        )
    # legacy role-based
    role = user.get("role")
    if action == "admin":
        if role != "admin":
            raise HTTPException(403, "admin role required for this operation")
    elif action == "write":
        if role == "readonly":
            raise HTTPException(403, "readonly account cannot perform writes")


def require_user_or_above(user: dict = Depends(require_authenticated)) -> dict:
    """Entry-level guard for write endpoints.

    Scoped key: must have ANY write/admin scope. Resource-level check happens
    inside handlers via assert_can(user, 'write', resource).
    Legacy key: blocks readonly role.
    """
    scopes = _parse_scopes(user)
    if scopes is not None:
        if any(s == "admin" or s.startswith("admin:") or s.startswith("write:")
               for s in scopes):
            return user
        raise HTTPException(403, f"key scopes lack write capability: {scopes}")
    if user.get("role") == "readonly":
        raise HTTPException(403, "readonly account cannot perform writes")
    return user


def require_admin(user: dict = Depends(require_authenticated)) -> dict:
    """Entry-level guard for admin endpoints (DDL/user mgmt/etc).

    Scoped key: must have any admin scope.
    Legacy key: must have admin role.
    """
    scopes = _parse_scopes(user)
    if scopes is not None:
        if any(s == "admin" or s.startswith("admin:") for s in scopes):
            return user
        raise HTTPException(403, f"key scopes lack admin capability: {scopes}")
    if user.get("role") != "admin":
        raise HTTPException(403, "admin role required for this operation")
    return user


# Backward-compat alias for any existing callers (deprecated path)
def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    return require_authenticated(request, x_api_key)


def audit(con: sqlite3.Connection, *, user: dict | None, table: str,
          record_id: int | None, action: str, changes: Any | None = None) -> None:
    """Write to audit_log with the resolved username (or 'anonymous')."""
    import json
    op = (user or {}).get("username") or "anonymous"
    con.execute(
        "INSERT INTO audit_log(table_name, record_id, action, changes, operator) "
        "VALUES(?,?,?,?,?)",
        (table, record_id, action,
         json.dumps(changes, ensure_ascii=False) if changes is not None else None,
         op)
    )
