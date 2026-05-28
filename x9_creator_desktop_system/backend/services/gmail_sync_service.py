from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.gmail_sync_state import GmailSyncState
from ..models.outreach_email import OutreachEmail
from .post_processing import create_outreach_event


def record_inbound_reply(
    db: Session,
    *,
    account_id: str,
    gmail_thread_id: str | None = None,
    from_email: str | None = None,
    gmail_message_id: str | None = None,
    received_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a matched inbound Gmail reply and advance the creator to communicating."""

    creator = _creator_by_thread(db, gmail_thread_id) if gmail_thread_id else None
    if creator is None and from_email:
        creator = _creator_by_email(db, from_email)
    if creator is None:
        _touch_sync_state(db, account_id=account_id, status="idle")
        return {"ok": True, "matched": False, "creator_id": None}

    event_metadata = {
        "source": "gmail_sync",
        "account_id": account_id,
        "gmail_thread_id": gmail_thread_id,
        "gmail_message_id": gmail_message_id,
        **(metadata or {}),
    }
    create_outreach_event(
        db,
        creator,
        event_type="communicating",
        actor_user_id=account_id,
        owner_bd=creator.owner_bd,
        metadata=event_metadata,
        event_at=received_at or datetime.utcnow(),
    )
    _touch_sync_state(db, account_id=account_id, status="idle")
    return {"ok": True, "matched": True, "creator_id": creator.id}


def _creator_by_thread(db: Session, gmail_thread_id: str | None) -> Creator | None:
    if not gmail_thread_id:
        return None
    email = db.scalars(
        select(OutreachEmail)
        .where(OutreachEmail.gmail_thread_id == gmail_thread_id)
        .order_by(OutreachEmail.sent_at.desc(), OutreachEmail.created_at.desc())
        .limit(1)
    ).first()
    if email is None:
        return None
    return db.get(Creator, email.creator_id)


def _creator_by_email(db: Session, email: str) -> Creator | None:
    normalized = email.strip().lower()
    if not normalized:
        return None
    return db.scalars(
        select(Creator)
        .where(func.lower(func.trim(Creator.email)) == normalized)
        .limit(1)
    ).first()


def _touch_sync_state(db: Session, *, account_id: str, status: str) -> GmailSyncState:
    now = datetime.utcnow()
    state = db.get(GmailSyncState, account_id)
    if state is None:
        state = GmailSyncState(account_id=account_id, interval_minutes=30, status=status)
        db.add(state)
    state.status = status
    state.last_sync_at = now
    state.next_sync_at = now + timedelta(minutes=int(state.interval_minutes or 30))
    db.flush()
    return state
