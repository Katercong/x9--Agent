from __future__ import annotations

import base64
import html
import json
import logging
import re
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database.connection import SessionLocal
from ..models.creator import Creator
from ..models.creator_email_message import CreatorEmailMessage
from ..models.gmail_account import GmailAccount
from ..models.gmail_sync_state import GmailSyncState
from ..models.outreach_email import OutreachEmail
from ..utils.id_utils import new_id
from . import gmail_service
from .post_processing import create_outreach_event


log = logging.getLogger(__name__)

SYNC_INTERVAL_MINUTES = 10
MAX_SENT_ROWS_PER_ACCOUNT = 2500
MAX_BODY_CHARS = 20_000
MAX_PREVIEW_CHARS = 1000

_BACKGROUND_RUN_LOCK = threading.Lock()
_BACKGROUND_STATE_LOCK = threading.Lock()
_BACKGROUND_STATUS: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "totals": None,
}

BOUNCE_FROM_MARKERS = (
    "mailer-daemon",
    "mail delivery subsystem",
    "postmaster",
)
BOUNCE_SUBJECT_MARKERS = (
    "delivery status notification",
    "delivery failure",
    "undeliverable",
    "returned mail",
    "message not delivered",
    "address not found",
    "recipient address rejected",
    "delivery incomplete",
)


def background_sync_status() -> dict[str, Any]:
    with _BACKGROUND_STATE_LOCK:
        return dict(_BACKGROUND_STATUS)


def start_background_sync(
    *,
    account_ids: Iterable[str] | None = None,
    department_code: str | None = None,
    limit_per_account: int = MAX_SENT_ROWS_PER_ACCOUNT,
) -> dict[str, Any]:
    """Start a reply sync in a background thread and return immediately."""

    if not _BACKGROUND_RUN_LOCK.acquire(blocking=False):
        return {"ok": True, "accepted": False, "running": True, "background": background_sync_status()}

    selected_ids = [str(value) for value in account_ids or [] if str(value or "").strip()]
    started_at = datetime.utcnow().isoformat()
    _set_background_status(
        running=True,
        started_at=started_at,
        finished_at=None,
        error=None,
        totals=None,
    )

    def _runner() -> None:
        try:
            with SessionLocal() as db:
                result = sync_all_authorized_mailboxes(
                    db,
                    account_ids=selected_ids,
                    department_code=department_code,
                    limit_per_account=limit_per_account,
                )
            _set_background_status(
                running=False,
                finished_at=datetime.utcnow().isoformat(),
                error=None,
                totals=result.get("totals"),
            )
        except Exception as exc:  # pragma: no cover - operational safety net
            log.warning("gmail_sync: background sync failed: %s", exc)
            _set_background_status(
                running=False,
                finished_at=datetime.utcnow().isoformat(),
                error=str(exc),
            )
        finally:
            _BACKGROUND_RUN_LOCK.release()

    thread = threading.Thread(target=_runner, daemon=True, name="gmail-reply-sync-manual")
    thread.start()
    return {"ok": True, "accepted": True, "running": True, "background": background_sync_status()}


def _set_background_status(**values: Any) -> None:
    with _BACKGROUND_STATE_LOCK:
        _BACKGROUND_STATUS.update(values)


def sync_all_authorized_mailboxes(
    db: Session,
    *,
    account_ids: Iterable[str] | None = None,
    department_code: str | None = None,
    limit_per_account: int = MAX_SENT_ROWS_PER_ACCOUNT,
) -> dict[str, Any]:
    """Fetch real Gmail replies for every selected authorized mailbox.

    The sync intentionally does not scan entire inboxes. It looks only at
    threads created by sent outreach rows for the same Gmail sender account,
    which keeps API reads bounded while still following the conversation that
    started from creator outreach.
    """

    filters = [GmailAccount.is_active == 1]
    selected_ids = [str(value) for value in account_ids or [] if str(value or "").strip()]
    if selected_ids:
        filters.append(GmailAccount.id.in_(selected_ids))
    if department_code:
        filters.append((GmailAccount.department_code == department_code) | (GmailAccount.department_code.is_(None)))
    accounts = list(
        db.scalars(
            select(GmailAccount)
            .where(*filters)
            .order_by(GmailAccount.is_default.desc(), GmailAccount.created_at.asc())
        ).all()
    )
    summaries: list[dict[str, Any]] = []
    for account in accounts:
        try:
            summary = sync_account_replies(
                db,
                account=account,
                department_code=department_code,
                limit_per_account=limit_per_account,
            )
        except Exception as exc:  # keep the other mailboxes moving
            log.warning("gmail_sync: account %s failed: %s", account.email, exc)
            summary = _account_summary(account)
            summary.update({"status": "error", "error": str(exc), "threads_checked": 0, "new_replies": 0, "new_bounces": 0})
            _touch_sync_state(db, account_id=account.id, status="error", error_message=str(exc))
        summaries.append(summary)
        db.commit()

    totals = {
        "accounts": len(summaries),
        "readable_accounts": sum(1 for item in summaries if item.get("has_readonly_scope")),
        "threads_checked": sum(int(item.get("threads_checked") or 0) for item in summaries),
        "messages_seen": sum(int(item.get("messages_seen") or 0) for item in summaries),
        "new_replies": sum(int(item.get("new_replies") or 0) for item in summaries),
        "new_bounces": sum(int(item.get("new_bounces") or 0) for item in summaries),
        "errors": sum(int(item.get("errors") or 0) for item in summaries),
        "needs_reauth": sum(1 for item in summaries if item.get("status") == "needs_reauth"),
    }
    return {"ok": True, "interval_minutes": SYNC_INTERVAL_MINUTES, "totals": totals, "accounts": summaries}


def sync_account_replies(
    db: Session,
    *,
    account: GmailAccount,
    department_code: str | None = None,
    limit_per_account: int = MAX_SENT_ROWS_PER_ACCOUNT,
) -> dict[str, Any]:
    summary = _account_summary(account)
    try:
        has_readonly_scope = gmail_service.account_has_readonly_scope(account)
    except Exception as exc:
        has_readonly_scope = False
        message = f"Gmail token cannot be read. Reconnect this mailbox. {exc}"
    else:
        message = "Gmail readonly scope missing. Reconnect this mailbox to enable reply sync."
    summary["has_readonly_scope"] = has_readonly_scope
    if not has_readonly_scope:
        summary.update({"status": "needs_reauth", "error": message})
        _touch_sync_state(db, account_id=account.id, status="needs_reauth", error_message=message)
        return summary

    sent_rows = _sent_rows_for_account(
        db,
        account=account,
        department_code=department_code,
        limit_per_account=limit_per_account,
    )
    summary["sent_rows"] = len(sent_rows)
    rows_by_thread: dict[str, list[OutreachEmail]] = defaultdict(list)
    for row in sent_rows:
        if row.gmail_thread_id:
            rows_by_thread[str(row.gmail_thread_id)].append(row)
    summary["tracked_threads"] = len(rows_by_thread)

    service = gmail_service.build_gmail_service_for_account(db, account)
    _touch_sync_state(db, account_id=account.id, status="running", error_message=None)

    for thread_id, thread_rows in rows_by_thread.items():
        try:
            thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
        except Exception as exc:
            summary["errors"] = int(summary.get("errors") or 0) + 1
            if _http_status(exc) in {401, 403}:
                message = f"Gmail read failed for {account.email}: {exc}"
                summary.update({"status": "needs_reauth", "error": message})
                _touch_sync_state(db, account_id=account.id, status="needs_reauth", error_message=message)
                return summary
            continue

        summary["threads_checked"] = int(summary.get("threads_checked") or 0) + 1
        for message in thread.get("messages") or []:
            summary["messages_seen"] = int(summary.get("messages_seen") or 0) + 1
            result = _record_message_from_gmail(db, account=account, sent_rows=thread_rows, message=message)
            if result == "inbound":
                summary["new_replies"] = int(summary.get("new_replies") or 0) + 1
            elif result == "bounce":
                summary["new_bounces"] = int(summary.get("new_bounces") or 0) + 1

    summary["status"] = "idle"
    _touch_sync_state(db, account_id=account.id, status="idle", error_message=None)
    return summary


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
    """Record a matched inbound Gmail reply that needs an operator follow-up."""

    creator = _creator_by_thread(db, gmail_thread_id) if gmail_thread_id else None
    if creator is None and from_email:
        creator = _creator_by_email(db, from_email)
    if creator is None:
        _touch_sync_state(db, account_id=account_id, status="idle")
        return {"ok": True, "matched": False, "creator_id": None}

    inbound_at = _naive_datetime(received_at or datetime.utcnow())
    latest_outbound = _latest_outbound_at(db, creator_id=creator.id, gmail_thread_id=gmail_thread_id)
    if latest_outbound is not None and latest_outbound > inbound_at:
        _touch_sync_state(db, account_id=account_id, status="idle")
        return {"ok": True, "matched": True, "creator_id": creator.id, "needs_followup": False}

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
        event_type="pending_followup",
        actor_user_id=account_id,
        owner_bd=creator.owner_bd,
        metadata=event_metadata,
        event_at=inbound_at,
    )
    _touch_sync_state(db, account_id=account_id, status="idle")
    return {"ok": True, "matched": True, "creator_id": creator.id, "needs_followup": True}


def _record_message_from_gmail(
    db: Session,
    *,
    account: GmailAccount,
    sent_rows: list[OutreachEmail],
    message: dict[str, Any],
) -> str | None:
    gmail_message_id = str(message.get("id") or "").strip()
    if not gmail_message_id:
        return None
    if _message_already_recorded(db, account_id=account.id, gmail_message_id=gmail_message_id):
        return None

    payload = message.get("payload") or {}
    headers = payload.get("headers") or []
    from_header = _header(headers, "From")
    to_header = _header(headers, "To")
    subject = _header(headers, "Subject") or "(no subject)"
    from_email = _normalized_email(from_header)
    account_email = (account.email or "").strip().lower()
    labels = {str(value).upper() for value in (message.get("labelIds") or [])}
    if "SENT" in labels or from_email == account_email:
        return None

    message_at = _message_datetime(message, headers)
    outreach = _matching_outreach_row(sent_rows, message_at)
    if outreach is None:
        return None
    sent_at = _as_naive_datetime(outreach.sent_at or outreach.created_at)
    if sent_at is not None and message_at is not None and message_at < sent_at - timedelta(minutes=5):
        return None

    direction = "bounce" if _is_bounce(from_header, subject) else "inbound"
    body, body_format = _extract_body(payload)
    snippet = html.unescape(str(message.get("snippet") or "")).strip()
    preview = _preview(body, body_format=body_format, fallback=snippet)
    metadata = {
        "labels": sorted(labels),
        "history_id": message.get("historyId"),
        "rfc_message_id": _header(headers, "Message-ID"),
        "gmail_internal_date": message.get("internalDate"),
        "source": "gmail_sync",
    }
    row = CreatorEmailMessage(
        id=new_id("cem"),
        department_code=outreach.department_code,
        creator_id=str(outreach.creator_id),
        outreach_email_id=outreach.id,
        gmail_account_id=account.id,
        gmail_account_email=account.email,
        gmail_thread_id=message.get("threadId") or outreach.gmail_thread_id,
        gmail_message_id=gmail_message_id,
        direction=direction,
        from_email=from_email or from_header,
        to_email=to_header,
        subject=subject,
        snippet=snippet,
        body_preview=preview,
        body=(body or snippet)[:MAX_BODY_CHARS],
        body_format=body_format or "plain",
        message_at=message_at,
        metadata_json=json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        return None

    if direction == "inbound":
        record_inbound_reply(
            db,
            account_id=account.id,
            gmail_thread_id=row.gmail_thread_id,
            from_email=row.from_email,
            gmail_message_id=row.gmail_message_id,
            received_at=message_at,
            metadata={
                "subject": subject,
                "snippet": snippet,
                "preview": preview,
                "from_email": row.from_email,
                "to_email": row.to_email,
                "gmail_account_email": account.email,
                "outreach_email_id": outreach.id,
                "creator_email": outreach.to_email,
                "direction": direction,
            },
        )
    return direction


def _sent_rows_for_account(
    db: Session,
    *,
    account: GmailAccount,
    department_code: str | None,
    limit_per_account: int,
) -> list[OutreachEmail]:
    filters = [
        OutreachEmail.status == "sent",
        OutreachEmail.gmail_thread_id.is_not(None),
        func.lower(func.trim(OutreachEmail.from_email)) == (account.email or "").strip().lower(),
    ]
    if department_code:
        filters.append((OutreachEmail.department_code == department_code) | (OutreachEmail.department_code.is_(None)))
    sent_at = func.coalesce(OutreachEmail.sent_at, OutreachEmail.created_at)
    q = select(OutreachEmail).where(*filters).order_by(sent_at.desc(), OutreachEmail.created_at.desc())
    if limit_per_account > 0:
        q = q.limit(limit_per_account)
    return list(db.scalars(q).all())


def _matching_outreach_row(sent_rows: list[OutreachEmail], message_at: datetime | None) -> OutreachEmail | None:
    if not sent_rows:
        return None
    rows = sorted(sent_rows, key=lambda row: _timestamp(row.sent_at or row.created_at), reverse=True)
    if message_at is None:
        return rows[0]
    for row in rows:
        sent_at = _as_naive_datetime(row.sent_at or row.created_at)
        if sent_at is not None and sent_at <= message_at + timedelta(minutes=5):
            return row
    return rows[-1]


def _message_already_recorded(db: Session, *, account_id: str, gmail_message_id: str) -> bool:
    return bool(
        db.scalar(
            select(CreatorEmailMessage.id)
            .where(
                CreatorEmailMessage.gmail_account_id == account_id,
                CreatorEmailMessage.gmail_message_id == gmail_message_id,
            )
            .limit(1)
        )
    )


def _header(headers: list[dict[str, Any]], name: str) -> str | None:
    target = name.lower()
    for item in headers:
        if str(item.get("name") or "").lower() == target:
            return str(item.get("value") or "").strip() or None
    return None


def _normalized_email(value: str | None) -> str | None:
    if not value:
        return None
    parsed = getaddresses([value])
    if not parsed:
        return value.strip().lower()
    email = (parsed[0][1] or parsed[0][0] or "").strip().lower()
    return email or None


def _message_datetime(message: dict[str, Any], headers: list[dict[str, Any]]) -> datetime | None:
    internal = message.get("internalDate")
    if internal is not None:
        try:
            return datetime.fromtimestamp(int(internal) / 1000, tz=timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError, OSError):
            pass
    date_header = _header(headers, "Date")
    if date_header:
        try:
            return _naive_datetime(parsedate_to_datetime(date_header))
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
    return None


def _extract_body(payload: dict[str, Any]) -> tuple[str, str]:
    plain_chunks: list[str] = []
    html_chunks: list[str] = []
    for part in _walk_payload(payload):
        mime_type = str(part.get("mimeType") or "").lower()
        filename = str(part.get("filename") or "")
        if filename:
            continue
        text = _decode_part_body(part)
        if not text:
            continue
        if mime_type == "text/plain":
            plain_chunks.append(text)
        elif mime_type == "text/html":
            html_chunks.append(text)
    if plain_chunks:
        return "\n\n".join(plain_chunks).strip(), "plain"
    if html_chunks:
        return "\n\n".join(html_chunks).strip(), "html"
    text = _decode_part_body(payload)
    return text.strip(), "plain"


def _walk_payload(payload: dict[str, Any]):
    yield payload
    for part in payload.get("parts") or []:
        if isinstance(part, dict):
            yield from _walk_payload(part)


def _decode_part_body(part: dict[str, Any]) -> str:
    data = ((part.get("body") or {}).get("data") or "").strip()
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    try:
        raw = base64.urlsafe_b64decode((data + padding).encode("ascii"))
    except Exception:
        return ""
    for encoding in ("utf-8", "latin-1"):
        try:
            return raw.decode(encoding, errors="replace")
        except Exception:
            continue
    return ""


def _preview(body: str | None, *, body_format: str | None, fallback: str | None = None) -> str:
    text = body or fallback or ""
    if (body_format or "").lower() == "html":
        text = re.sub(r"<(br|/p|/div|/li)\b[^>]*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_PREVIEW_CHARS] + ("..." if len(text) > MAX_PREVIEW_CHARS else "")


def _is_bounce(from_header: str | None, subject: str | None) -> bool:
    sender = (from_header or "").lower()
    title = (subject or "").lower()
    return any(marker in sender for marker in BOUNCE_FROM_MARKERS) or any(
        marker in title for marker in BOUNCE_SUBJECT_MARKERS
    )


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


def _naive_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _as_naive_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _naive_datetime(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return _naive_datetime(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def _latest_outbound_at(db: Session, *, creator_id: str, gmail_thread_id: str | None = None) -> datetime | None:
    q = select(OutreachEmail).where(OutreachEmail.creator_id == creator_id).where(OutreachEmail.status == "sent")
    if gmail_thread_id:
        q = q.where(OutreachEmail.gmail_thread_id == gmail_thread_id)
    email = db.scalars(
        q.order_by(
            OutreachEmail.sent_at.desc(),
            OutreachEmail.created_at.desc(),
        ).limit(1)
    ).first()
    if email is None:
        return None
    return _as_naive_datetime(email.sent_at or email.created_at)


def _touch_sync_state(
    db: Session,
    *,
    account_id: str,
    status: str,
    error_message: str | None = None,
) -> GmailSyncState:
    now = datetime.utcnow()
    state = db.get(GmailSyncState, account_id)
    if state is None:
        state = GmailSyncState(account_id=account_id, interval_minutes=SYNC_INTERVAL_MINUTES, status=status)
        db.add(state)
    state.status = status
    state.interval_minutes = SYNC_INTERVAL_MINUTES
    state.last_sync_at = now
    state.next_sync_at = now + timedelta(minutes=SYNC_INTERVAL_MINUTES)
    state.error_message = error_message
    db.flush()
    return state


def _account_summary(account: GmailAccount) -> dict[str, Any]:
    return {
        "account_id": account.id,
        "email": account.email,
        "user_id": account.user_id,
        "department_code": account.department_code,
        "has_readonly_scope": _safe_has_readonly_scope(account),
        "status": "idle",
        "sent_rows": 0,
        "tracked_threads": 0,
        "threads_checked": 0,
        "messages_seen": 0,
        "new_replies": 0,
        "new_bounces": 0,
        "errors": 0,
        "error": None,
    }


def _safe_has_readonly_scope(account: GmailAccount) -> bool:
    try:
        return gmail_service.account_has_readonly_scope(account)
    except Exception:
        return False


def _timestamp(value: Any) -> float:
    parsed = _as_naive_datetime(value)
    return parsed.timestamp() if parsed is not None else 0.0


def _http_status(exc: Exception) -> int | None:
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None
