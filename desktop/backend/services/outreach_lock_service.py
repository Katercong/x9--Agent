from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.creator_outreach_lock import CreatorOutreachLock
from ..utils.id_utils import new_id
from .departments import DEFAULT_DEPARTMENT


ADMIN_ROLES = {"department_admin", "company_admin", "super_admin"}
DEFAULT_LOCK_TTL_SECONDS = 15 * 60
MAX_LOCK_TTL_SECONDS = 60 * 60


def utcnow() -> datetime:
    return datetime.utcnow()


def actor_id(user: dict[str, Any] | None) -> str:
    user = user or {}
    return str(user.get("id") or user.get("identity") or user.get("username") or user.get("email") or "").strip()


def actor_label(user: dict[str, Any] | None) -> str:
    user = user or {}
    return str(
        user.get("display_name")
        or user.get("email")
        or user.get("username")
        or user.get("identity")
        or user.get("id")
        or ""
    ).strip()


def is_admin_user(user: dict[str, Any] | None) -> bool:
    user = user or {}
    return user.get("role") in ADMIN_ROLES


def _ttl(seconds: int | None) -> int:
    value = int(seconds or DEFAULT_LOCK_TTL_SECONDS)
    return max(60, min(value, MAX_LOCK_TTL_SECONDS))


def _active_lock_stmt(creator_id: str, now: datetime | None = None):
    now = now or utcnow()
    return (
        select(CreatorOutreachLock)
        .where(CreatorOutreachLock.creator_id == str(creator_id))
        .where(CreatorOutreachLock.released_at.is_(None))
        .where(CreatorOutreachLock.expires_at > now)
        .order_by(CreatorOutreachLock.expires_at.desc())
    )


def active_lock_for_creator(db: Session, creator_id: str, now: datetime | None = None) -> CreatorOutreachLock | None:
    return db.scalars(_active_lock_stmt(str(creator_id), now).limit(1)).first()


def lock_owner_matches(lock: CreatorOutreachLock, user: dict[str, Any] | None) -> bool:
    owner = actor_id(user)
    return bool(owner and str(lock.owner_user_id) == owner)


def serialize_lock(lock: CreatorOutreachLock, user: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": lock.id,
        "department_code": lock.department_code,
        "creator_id": lock.creator_id,
        "owner_user_id": lock.owner_user_id,
        "owner_label": lock.owner_label,
        "owner_email": lock.owner_email,
        "expires_at": _utc_iso(lock.expires_at),
        "released_at": _utc_iso(lock.released_at),
        "heartbeat_count": int(lock.heartbeat_count or 0),
        "is_mine": lock_owner_matches(lock, user),
        "can_release": lock_owner_matches(lock, user) or is_admin_user(user),
    }


def _utc_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def active_lock_summaries(
    db: Session,
    creator_ids: Iterable[Any],
    user: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    ids = [str(creator_id) for creator_id in creator_ids if creator_id]
    if not ids:
        return {}
    rows = list(db.scalars(
        select(CreatorOutreachLock)
        .where(CreatorOutreachLock.creator_id.in_(ids))
        .where(CreatorOutreachLock.released_at.is_(None))
        .where(CreatorOutreachLock.expires_at > utcnow())
        .order_by(CreatorOutreachLock.creator_id.asc(), CreatorOutreachLock.expires_at.desc())
    ).all())
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.creator_id)
        if key not in out:
            out[key] = serialize_lock(row, user)
    return out


def filter_rows_visible_by_lock(
    db: Session,
    rows: list[dict[str, Any]],
    user: dict[str, Any] | None,
    *,
    id_getter: Callable[[dict[str, Any]], Any] = lambda row: row.get("id"),
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    locks = active_lock_summaries(db, [id_getter(row) for row in rows], user)
    if not locks:
        return rows, {}
    admin = is_admin_user(user)
    visible: list[dict[str, Any]] = []
    visible_locks: dict[str, dict[str, Any]] = {}
    for row in rows:
        creator_id = str(id_getter(row) or "")
        lock = locks.get(creator_id)
        if lock and not lock.get("is_mine") and not admin:
            continue
        visible.append(row)
        if lock:
            visible_locks[creator_id] = lock
    return visible, visible_locks


def acquire_creator_lock(
    db: Session,
    *,
    creator_id: str,
    department_code: str | None,
    user: dict[str, Any] | None,
    ttl_seconds: int | None = None,
    force: bool = False,
) -> CreatorOutreachLock:
    owner = actor_id(user)
    if not owner:
        raise HTTPException(status_code=401, detail="login required")

    now = utcnow()
    active = active_lock_for_creator(db, str(creator_id), now)
    if active is not None and not lock_owner_matches(active, user):
        if not (force and is_admin_user(user)):
            label = active.owner_label or active.owner_email or "another user"
            raise HTTPException(status_code=409, detail=f"creator outreach is locked by {label}")
        active.released_at = now
        active.release_reason = "force_replaced"
        db.flush()

    expires_at = now + timedelta(seconds=_ttl(ttl_seconds))
    if active is not None and lock_owner_matches(active, user):
        active.expires_at = expires_at
        active.owner_label = actor_label(user) or active.owner_label
        active.owner_email = (user or {}).get("email") or active.owner_email
        db.commit()
        db.refresh(active)
        return active

    lock = CreatorOutreachLock(
        id=new_id("olk"),
        department_code=department_code or DEFAULT_DEPARTMENT,
        creator_id=str(creator_id),
        owner_user_id=owner,
        owner_label=actor_label(user) or owner,
        owner_email=(user or {}).get("email"),
        heartbeat_count=0,
        expires_at=expires_at,
    )
    db.add(lock)
    db.commit()
    db.refresh(lock)
    return lock


def require_creator_lock(
    db: Session,
    *,
    creator_id: str,
    user: dict[str, Any] | None,
) -> CreatorOutreachLock | None:
    lock = active_lock_for_creator(db, str(creator_id))
    if lock is None:
        return None
    if lock_owner_matches(lock, user) or is_admin_user(user):
        return lock
    label = lock.owner_label or lock.owner_email or "another user"
    raise HTTPException(status_code=409, detail=f"creator outreach is locked by {label}")


def heartbeat_lock(
    db: Session,
    *,
    lock_id: str,
    user: dict[str, Any] | None,
    ttl_seconds: int | None = None,
) -> CreatorOutreachLock:
    lock = db.get(CreatorOutreachLock, lock_id)
    if lock is None or lock.released_at is not None:
        raise HTTPException(status_code=404, detail="outreach lock not found")
    if not lock_owner_matches(lock, user):
        raise HTTPException(status_code=403, detail="outreach lock owned by another user")
    now = utcnow()
    if lock.expires_at <= now:
        raise HTTPException(status_code=409, detail="outreach lock expired")
    lock.expires_at = now + timedelta(seconds=_ttl(ttl_seconds))
    lock.heartbeat_count = int(lock.heartbeat_count or 0) + 1
    db.commit()
    db.refresh(lock)
    return lock


def release_lock(
    db: Session,
    *,
    lock_id: str,
    user: dict[str, Any] | None,
    force: bool = False,
    reason: str | None = None,
) -> CreatorOutreachLock:
    lock = db.get(CreatorOutreachLock, lock_id)
    if lock is None:
        raise HTTPException(status_code=404, detail="outreach lock not found")
    if lock.released_at is not None:
        return lock
    if not lock_owner_matches(lock, user):
        if not (force and is_admin_user(user)):
            raise HTTPException(status_code=403, detail="outreach lock owned by another user")
    lock.released_at = utcnow()
    lock.release_reason = reason or ("force_release" if force else "release")
    db.commit()
    db.refresh(lock)
    return lock


def release_creator_lock_if_owned(
    db: Session,
    *,
    creator_id: str,
    user: dict[str, Any] | None,
    reason: str | None = None,
) -> None:
    lock = active_lock_for_creator(db, str(creator_id))
    if lock is None or not lock_owner_matches(lock, user):
        return
    lock.released_at = utcnow()
    lock.release_reason = reason or "release"
    db.flush()
