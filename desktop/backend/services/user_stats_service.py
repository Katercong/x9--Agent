"""Per-user statistics for the admin "user detail" page.

The dashboard already aggregates company- and department-level KPIs (see
`routers/dashboard.py`). This module zooms in on a single user — what they
collected, who they're contacting, and how their outreach is converting —
for the new /a/users/:id detail page.

Three deliverables:
  * `get_user_detail(db, user_id)` — total + today KPIs (collection / creators
    / outreach), reusing the existing aggregator from `auth_service`.
  * `get_user_trend(db, user_id, days)` — daily series for the last N days,
    suitable for a line chart.
  * `get_user_funnel(db, user_id)` — sent → replied → deal-closed funnel.
    Reply and deal-closed are placeholder approximations until we add
    explicit columns (see _CAVEATS_ below).

Data scoping rules (matches the memory note `仪表盘统计须按三个采集来源汇总`):
  * Raw collection counts come from `raw_observations` filtered to the user's
    department (or company-wide for super/company admins).
  * Creator ownership is matched by `_user_aliases()` against `owner_bd`,
    consistent with `_user_activity_stats` in auth_service.py.
  * Outreach emails attribute by `created_by` alias OR by owning the creator.

Caveats / placeholders (call out in UI tooltip):
  * `replied` count uses `gmail_thread_id IS NOT NULL` as a proxy for "got a
    reply." Once we add `outreach_emails.replied_at`, swap this to the real
    timestamp.
  * `deal_closed` uses `creator.current_status` containing one of the
    terminal-success markers (e.g. 视频已发布). Once we add an explicit deal
    column, swap this too.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.app_user import AppUser
from ..models.creator import Creator
from ..models.outreach_email import OutreachEmail
from ..models.raw_observation import RawObservation
from ..services.auth_service import (
    _empty_user_stats,
    _matches_user_alias,
    _user_activity_stats,
    _user_aliases,
)
from ..services.departments import DEFAULT_DEPARTMENT, normalize_department_code


# These status strings count as a "deal" for funnel purposes. Conservative on
# purpose — anything less terminal stays out of the numerator so the deal
# rate doesn't look inflated.
_DEAL_CLOSED_STATUSES = {
    "成交",
    "已签约",
    "视频已发布",
    "已发布视频",
    "video_published",
    "ad_running",
    "广告投放中",
}


def _load_user(db: Session, user_id: str) -> AppUser | None:
    return db.execute(select(AppUser).where(AppUser.id == user_id)).scalar_one_or_none()


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if hasattr(value, "date"):
        try:
            return value.date()
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def get_user_detail(db: Session, user_id: str) -> dict[str, Any]:
    """High-level KPIs for one user. Reuses the same aggregator the user
    list view uses, so totals stay consistent between /a/users and
    /a/users/:id."""
    user = _load_user(db, user_id)
    if user is None:
        return {"ok": False, "detail": "user not found"}
    stats_map = _user_activity_stats(db, [user])
    return {
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name or user.username,
            "email": user.email,
            "role": user.role,
            "department_code": user.department_code,
            "is_active": bool(user.is_active),
            "approval_status": user.approval_status,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "stats": stats_map.get(user.id, _empty_user_stats()),
    }


def get_user_trend(db: Session, user_id: str, days: int = 30) -> dict[str, Any]:
    """Per-day series for the last `days` days. Returns a list aligned to the
    last N calendar dates so the chart never has gaps.

    Includes:
      * collected — raw_observations created on that day, scoped to the user's
        department (or all if company-wide).
      * sent — outreach_emails sent on that day owned by the user.
      * replied — outreach_emails sent on that day with gmail_thread_id set
        (placeholder, see module docstring).
    """
    user = _load_user(db, user_id)
    if user is None:
        return {"ok": False, "detail": "user not found"}

    days = max(1, min(days, 90))
    today = datetime.now().date()
    window_start = today - timedelta(days=days - 1)
    # Pre-seed every date so the response shape is stable for the chart.
    buckets: dict[date, dict[str, int]] = {
        window_start + timedelta(days=i): {"collected": 0, "sent": 0, "replied": 0}
        for i in range(days)
    }

    aliases = _user_aliases(user)
    dept = normalize_department_code(user.department_code, default=DEFAULT_DEPARTMENT) or DEFAULT_DEPARTMENT
    company_wide = user.role in {"super_admin", "company_admin"} and not user.department_code

    # --- Collection (raw_observations) ---
    obs_q = select(RawObservation.department_code, RawObservation.created_at, RawObservation.collected_at)
    for department_code, created_at, collected_at in db.execute(obs_q).all():
        day = _as_date(collected_at) or _as_date(created_at)
        if day is None or day not in buckets:
            continue
        row_dept = normalize_department_code(department_code, default=DEFAULT_DEPARTMENT) or DEFAULT_DEPARTMENT
        if not company_wide and row_dept != dept:
            continue
        buckets[day]["collected"] += 1

    # --- Outreach ---
    owned_creator_ids = {
        c.id for c in db.scalars(select(Creator)).all() if _matches_user_alias(c.owner_bd, aliases)
    }
    for email in db.scalars(select(OutreachEmail)).all():
        send_day = _as_date(email.sent_at) or _as_date(email.created_at)
        if send_day is None or send_day not in buckets:
            continue
        is_user_email = _matches_user_alias(email.created_by, aliases) or (
            not email.created_by and email.creator_id in owned_creator_ids
        )
        if not is_user_email:
            continue
        # We treat anything past draft/queued as a "sent" effort for the chart;
        # the funnel below is stricter.
        status = (email.status or "").lower()
        if status in {"sent", "delivered", "queued"}:
            buckets[send_day]["sent"] += 1
        # Placeholder reply signal — see module docstring.
        if getattr(email, "gmail_thread_id", None):
            buckets[send_day]["replied"] += 1

    series = [
        {
            "date": day.isoformat(),
            "collected": values["collected"],
            "sent": values["sent"],
            "replied": values["replied"],
        }
        for day, values in sorted(buckets.items())
    ]
    return {
        "ok": True,
        "days": days,
        "series": series,
        "caveats": {
            "replied": "占位口径：使用 gmail_thread_id 非空作为已回复近似估算。",
        },
    }


def get_user_funnel(db: Session, user_id: str) -> dict[str, Any]:
    """Outreach funnel: sent → replied → deal_closed.

    Numbers come from the same alias-based ownership match used everywhere
    else, so the funnel matches the trend chart and the user-list `stats`."""
    user = _load_user(db, user_id)
    if user is None:
        return {"ok": False, "detail": "user not found"}

    aliases = _user_aliases(user)
    creators = list(db.scalars(select(Creator)).all())
    owned_creators = [c for c in creators if _matches_user_alias(c.owner_bd, aliases)]
    owned_ids = {c.id for c in owned_creators}

    sent = replied = 0
    for email in db.scalars(select(OutreachEmail)).all():
        is_user_email = _matches_user_alias(email.created_by, aliases) or (
            not email.created_by and email.creator_id in owned_ids
        )
        if not is_user_email:
            continue
        status = (email.status or "").lower()
        if status in {"sent", "delivered"}:
            sent += 1
        if getattr(email, "gmail_thread_id", None):
            replied += 1

    deal_closed = sum(
        1 for c in owned_creators if str(c.current_status or "").strip() in _DEAL_CLOSED_STATUSES
    )

    def _rate(top: int, bottom: int) -> float:
        return round(top / bottom * 100, 1) if bottom else 0.0

    return {
        "ok": True,
        "funnel": {
            "sent": sent,
            "replied": replied,
            "deal_closed": deal_closed,
        },
        "rates": {
            "reply_rate": _rate(replied, sent),
            "deal_rate_of_replied": _rate(deal_closed, replied),
            "deal_rate_of_sent": _rate(deal_closed, sent),
        },
        "caveats": {
            "replied": "占位口径：使用 gmail_thread_id 非空。后续接入 replied_at 字段。",
            "deal_closed": "占位口径：根据 creator.current_status 反推。",
        },
    }
