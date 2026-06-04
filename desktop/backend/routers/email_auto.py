from __future__ import annotations

import html
import json
import random
import time
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.creator import Creator
from ..models.creator_email_message import CreatorEmailMessage
from ..models.email_auto import EmailAutoCampaign, EmailAutoJob, GmailAccountQuota
from ..models.gmail_account import GmailAccount
from ..models.gmail_sync_state import GmailSyncState
from ..models.outreach_email import OutreachEmail
from ..services import gmail_service, product_asset_service
from ..services.departments import DEFAULT_DEPARTMENT, current_department_code, current_user, department_where, row_in_department
from ..services.post_processing import create_outreach_event
from ..services.tk_script_service import build_tk_context, build_tk_email_subject, generate_strategy_template
from ..utils.current_status import STATUS_CONTACTED, normalize_current_status
from ..utils.id_utils import new_id


router = APIRouter(prefix="/api/local/email-auto", tags=["email-auto"])


DEFAULT_FILTERS: dict[str, Any] = {
    "keyword": "",
    "source": "all",
    "priority": "all",
    "contact": "email",
    "score": "gte85",
    "product": "all",
    "collab": "all",
    "status": "all",
    "review": "clean",
    "owner": "all",
    "date": "30d",
    "sort": "recommended",
    "min_followers": None,
    "max_followers": None,
    "pause_on_failure": False,
}


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    status: str = Field(default="paused", pattern="^(running|paused|draft)$")
    schedule_type: str = Field(default="daily", pattern="^(daily|weekly|monthly)$")
    weekdays: list[str] = Field(default_factory=list)
    month_days: list[int] = Field(default_factory=list)
    start_time: str = "09:30"
    end_time: str = "18:00"
    daily_limit: int = Field(default=100, ge=1, le=100000)
    hourly_limit: int = Field(default=20, ge=1, le=500)
    interval_min_seconds: int = Field(default=90, ge=30, le=3600)
    interval_max_seconds: int = Field(default=240, ge=30, le=7200)
    mailbox_pool: str = "all"
    send_mode: str = Field(default="draft", pattern="^(draft|send)$")
    filters: dict[str, Any] = Field(default_factory=dict)
    generate_jobs: bool = True
    candidate_limit: int = Field(default=200, ge=1, le=1000)


class CampaignStatusIn(BaseModel):
    status: str = Field(pattern="^(running|paused|draft)$")


class MailboxQuotaPatch(BaseModel):
    enabled: bool | None = None
    daily_quota: int | None = Field(default=None, ge=1, le=2000)
    status: str | None = Field(default=None, pattern="^(normal|cooldown|limit|auth_expired|bounce_risk)$")


class MailboxHealthCheckIn(BaseModel):
    max_accounts: int = Field(default=20, ge=2, le=50)
    poll_seconds: int = Field(default=30, ge=5, le=90)


class ProcessJobsIn(BaseModel):
    limit: int = Field(default=5, ge=1, le=50)
    confirm_send: bool = False


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _health_step(action: str, label: str, status: str, detail: str = "") -> dict[str, Any]:
    return {
        "action": action,
        "label": label,
        "status": status,
        "detail": detail,
        "at": _iso(_now()),
    }


def _upsert_health_step(
    item: dict[str, Any],
    action: str,
    label: str,
    status: str,
    detail: str = "",
    *,
    current: bool = True,
) -> None:
    steps = item.setdefault("steps", [])
    for step in steps:
        if step.get("action") == action:
            step.update(_health_step(action, label, status, detail))
            break
    else:
        steps.append(_health_step(action, label, status, detail))
    if current:
        item["current_action"] = label
        item["current_action_status"] = status
    if detail:
        item["reason"] = detail


def _dept_for_write(request: Request) -> str:
    department_code = current_department_code(request)
    user = current_user(request)
    return department_code or user.get("department_code") or DEFAULT_DEPARTMENT


def _base_filters(department_code: str | None):
    filters: list[Any] = []
    where = department_where(Creator, department_code)
    if where is not None:
        filters.append(where)
    return filters


def _now() -> datetime:
    return datetime.now()


def _today_start() -> datetime:
    now = _now()
    return datetime(now.year, now.month, now.day)


def _quota_window_start() -> datetime:
    return _now() - timedelta(hours=24)


def _quota_window_start_text() -> str:
    return _quota_window_start().strftime("%Y-%m-%d %H:%M:%S.%f")


def _visible_gmail_accounts(db: Session, request: Request) -> list[GmailAccount]:
    user = current_user(request)
    department_code = current_department_code(request)
    q = select(GmailAccount).where(GmailAccount.is_active == 1)
    if department_code is not None:
        q = q.where(or_(GmailAccount.department_code == department_code, GmailAccount.department_code.is_(None), GmailAccount.user_id == str(user.get("id"))))
    return list(db.scalars(q.order_by(GmailAccount.is_default.desc(), GmailAccount.created_at.asc())).all())


def _sync_mailboxes(db: Session, request: Request) -> list[GmailAccountQuota]:
    now = _now()
    department_code = _dept_for_write(request)
    rows: list[GmailAccountQuota] = []
    accounts = _visible_gmail_accounts(db, request)
    for account in accounts:
        quota_id = f"gmq_{account.id}"
        row = db.get(GmailAccountQuota, quota_id)
        if row is None:
            row = GmailAccountQuota(
                id=quota_id,
                department_code=account.department_code or department_code,
                account_id=account.id,
                email=account.email,
                enabled=1,
                daily_quota=40,
                status="normal",
                last_synced_at=now,
            )
            db.add(row)
        else:
            row.email = account.email
            row.department_code = account.department_code or row.department_code or department_code
            row.last_synced_at = now
        row.synced_sent_today = 0
        row.synced_sent_date = None
        rows.append(row)
    db.commit()
    return rows


def _daily_auto_sent(db: Session, email: str, quota_row: GmailAccountQuota | None = None) -> int:
    window_start = _quota_window_start_text()
    return int(db.scalar(
        select(func.count())
        .select_from(OutreachEmail)
        .where(
            OutreachEmail.auto_send == 1,
            OutreachEmail.status == "sent",
            func.lower(OutreachEmail.from_email) == email.lower(),
            cast(OutreachEmail.sent_at, String) >= window_start,
        )
    ) or 0)


def _daily_direction_count(db: Session, email: str, direction: str) -> int:
    today = _today_start().isoformat()
    return int(db.scalar(
        select(func.count())
        .select_from(CreatorEmailMessage)
        .where(
            CreatorEmailMessage.direction == direction,
            func.lower(CreatorEmailMessage.gmail_account_email) == email.lower(),
            cast(CreatorEmailMessage.message_at, String) >= today,
        )
    ) or 0)


def _serialize_campaign(db: Session, row: EmailAutoCampaign) -> dict[str, Any]:
    sent = int(db.scalar(
        select(func.count())
        .select_from(EmailAutoJob)
        .where(EmailAutoJob.campaign_id == row.id, EmailAutoJob.status.in_(["sent", "draft_created"]))
    ) or 0)
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "schedule_type": row.schedule_type,
        "weekdays": _json_loads(row.weekdays_json, []),
        "month_days": _json_loads(row.month_days_json, []),
        "schedule_label": _schedule_label(row),
        "time_window": f"{row.start_time}-{row.end_time}",
        "start_time": row.start_time,
        "end_time": row.end_time,
        "sent": sent,
        "daily_limit": row.daily_limit,
        "hourly_limit": row.hourly_limit,
        "interval_min_seconds": row.interval_min_seconds,
        "interval_max_seconds": row.interval_max_seconds,
        "interval": f"{row.interval_min_seconds}-{row.interval_max_seconds}s",
        "mailbox_pool": row.mailbox_pool,
        "send_mode": row.send_mode,
        "filters": _json_loads(row.filters_json, DEFAULT_FILTERS),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _schedule_label(row: EmailAutoCampaign) -> str:
    if row.schedule_type == "weekly":
        weekdays = _json_loads(row.weekdays_json, [])
        return "每周 " + "、".join(weekdays or ["周一", "周二", "周三", "周四", "周五"])
    if row.schedule_type == "monthly":
        days = _json_loads(row.month_days_json, [])
        return "每月 " + "、".join(str(day) for day in (days or [1])) + " 号"
    return "每天"


def _serialize_mailbox(db: Session, row: GmailAccountQuota) -> dict[str, Any]:
    auto_sent = _daily_auto_sent(db, row.email, row)
    replies = _daily_direction_count(db, row.email, "inbound")
    bounces = _daily_direction_count(db, row.email, "bounce")
    failures = int(db.scalar(
        select(func.count())
        .select_from(EmailAutoJob)
        .where(
            func.lower(EmailAutoJob.sender_email) == row.email.lower(),
            EmailAutoJob.status == "failed",
            EmailAutoJob.updated_at >= _today_start(),
        )
    ) or 0)
    status = row.status
    if auto_sent >= int(row.daily_quota or 0):
        status = "limit"
    if row.cooldown_until and row.cooldown_until > _now():
        status = "cooldown"
    return {
        "id": row.id,
        "account_id": row.account_id,
        "email": row.email,
        "owner": row.email.split("@", 1)[0],
        "status": status,
        "enabled": bool(row.enabled),
        "auto_sent": auto_sent,
        "quota": row.daily_quota,
        "remaining": max(0, int(row.daily_quota or 0) - auto_sent),
        "replies": replies,
        "bounces": bounces,
        "failures": failures,
        "next_send_at": _next_send_label(row, auto_sent),
        "last_sync_at": _iso(row.last_synced_at),
        "last_sent_at": _iso(row.last_sent_at),
    }


def _mailbox_send_capacity(db: Session, department_code: str | None) -> dict[str, int]:
    filters = [GmailAccountQuota.enabled == 1, GmailAccountQuota.status == "normal"]
    where = department_where(GmailAccountQuota, department_code)
    if where is not None:
        filters.append(where)
    rows = list(db.scalars(select(GmailAccountQuota).where(*filters)).all())
    total_quota = 0
    remaining_today = 0
    usable_count = 0
    now = _now()
    for row in rows:
        if row.cooldown_until and row.cooldown_until > now:
            continue
        quota = max(0, int(row.daily_quota or 0))
        sent = _daily_auto_sent(db, row.email, row)
        remaining = max(0, quota - sent)
        total_quota += quota
        remaining_today += remaining
        if remaining > 0:
            usable_count += 1
    return {"mailboxes": usable_count, "daily_capacity": total_quota, "remaining_today": remaining_today}


def _next_send_label(row: GmailAccountQuota, auto_sent: int) -> str:
    if not row.enabled:
        return "已停用"
    if row.status == "auth_expired":
        return "需重新授权"
    if auto_sent >= int(row.daily_quota or 0):
        return "今日达限"
    if row.cooldown_until and row.cooldown_until > _now():
        return row.cooldown_until.strftime("%m-%d %H:%M")
    if row.last_sent_at:
        return "等待间隔"
    return "可立即发送"


def _serialize_job(db: Session, row: EmailAutoJob) -> dict[str, Any]:
    creator = db.get(Creator, row.creator_id)
    campaign = db.get(EmailAutoCampaign, row.campaign_id)
    return {
        "id": row.id,
        "time": row.scheduled_at.strftime("%H:%M") if row.scheduled_at else "",
        "scheduled_at": _iso(row.scheduled_at),
        "sent_at": _iso(row.sent_at),
        "creator_id": row.creator_id,
        "creator": f"@{creator.handle}" if creator and creator.handle else row.creator_id,
        "recipient": row.recipient_email,
        "sender": row.sender_email or "待分配",
        "subject": row.subject,
        "body": row.body,
        "body_format": row.body_format,
        "product_asset_id": row.product_asset_id,
        "product": row.product_asset_id or "AI 自动匹配 SKU 图片",
        "plan": campaign.name if campaign else row.campaign_id,
        "campaign_id": row.campaign_id,
        "status": row.status,
        "reason": row.failure_reason or _job_reason(row.status),
        "filters": _json_loads(row.filters_json, []),
        "attempts": row.attempts,
        "outreach_email_id": row.outreach_email_id,
    }


def _job_reason(status: str) -> str:
    return {
        "pending": "等待调度",
        "sending": "正在发送",
        "sent": "已进入邮件跟踪",
        "draft_created": "已生成草稿",
        "failed": "发送失败",
        "skipped": "已跳过",
    }.get(status, status)


@router.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    limit_jobs: int = Query(default=100, ge=1, le=500),
    job_status: str | None = Query(default=None),
    job_offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    current_user(request)
    _sync_mailboxes(db, request)
    department_code = current_department_code(request)
    campaign_filters = []
    job_filters = []
    quota_filters = []
    where_campaign = department_where(EmailAutoCampaign, department_code)
    where_job = department_where(EmailAutoJob, department_code)
    where_quota = department_where(GmailAccountQuota, department_code)
    if where_campaign is not None:
        campaign_filters.append(where_campaign)
    if where_job is not None:
        job_filters.append(where_job)
    if where_quota is not None:
        quota_filters.append(where_quota)

    campaign_rows = list(db.scalars(select(EmailAutoCampaign).where(*campaign_filters).order_by(EmailAutoCampaign.created_at.desc())).all())
    mailbox_rows = list(db.scalars(select(GmailAccountQuota).where(*quota_filters).order_by(GmailAccountQuota.email.asc())).all())
    job_status_counts = {
        str(status): int(count or 0)
        for status, count in db.execute(
            select(EmailAutoJob.status, func.count())
            .where(*job_filters)
            .group_by(EmailAutoJob.status)
        ).all()
    }
    job_list_filters = list(job_filters)
    if job_status and job_status != "all":
        job_list_filters.append(EmailAutoJob.status == job_status)
    jobs_total = int(db.scalar(select(func.count()).select_from(EmailAutoJob).where(*job_list_filters)) or 0)
    job_rows = list(db.scalars(
        select(EmailAutoJob)
        .where(*job_list_filters)
        .order_by(EmailAutoJob.created_at.desc())
        .offset(job_offset)
        .limit(limit_jobs)
    ).all())
    mailbox_items = [_serialize_mailbox(db, row) for row in mailbox_rows]
    sent_today = int(db.scalar(
        select(func.count())
        .select_from(EmailAutoJob)
        .where(*job_filters, EmailAutoJob.status.in_(["sent", "draft_created"]), EmailAutoJob.updated_at >= _today_start())
    ) or 0)
    queue_count = int(db.scalar(select(func.count()).select_from(EmailAutoJob).where(*job_filters, EmailAutoJob.status == "pending")) or 0)
    return {
        "ok": True,
        "dashboard": {
            "today_sent": sent_today,
            "today_target": sum(int(row.daily_limit or 0) for row in campaign_rows if row.status == "running"),
            "available_mailboxes": sum(1 for row in mailbox_items if row["enabled"] and row["status"] == "normal"),
            "mailbox_total": len(mailbox_items),
            "queue_count": queue_count,
            "reply_count": sum(int(row["replies"] or 0) for row in mailbox_items),
            "bounce_count": sum(int(row["bounces"] or 0) for row in mailbox_items),
            "risk_mailboxes": sum(1 for row in mailbox_items if row["status"] != "normal"),
        },
        "campaigns": [_serialize_campaign(db, row) for row in campaign_rows],
        "mailboxes": mailbox_items,
        "jobs": [_serialize_job(db, row) for row in job_rows],
        "jobs_total": jobs_total,
        "job_status_counts": job_status_counts,
    }


@router.post("/mailboxes/sync")
def sync_mailboxes(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    current_user(request)
    rows = _sync_mailboxes(db, request)
    return {"ok": True, "items": [_serialize_mailbox(db, row) for row in rows], "total": len(rows)}


@router.post("/mailboxes/health-check")
def health_check_mailboxes(request: Request, body: MailboxHealthCheckIn | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    current_user(request)
    payload = body or MailboxHealthCheckIn()
    started_at = _now()
    marker = new_id("ehc")
    _sync_mailboxes(db, request)
    department_code = current_department_code(request)
    filters = [GmailAccountQuota.enabled == 1]
    where = department_where(GmailAccountQuota, department_code)
    if where is not None:
        filters.append(where)
    quota_rows = list(db.scalars(select(GmailAccountQuota).where(*filters).order_by(GmailAccountQuota.email.asc()).limit(payload.max_accounts)).all())
    pairs: list[tuple[GmailAccountQuota, GmailAccount]] = []
    for quota in quota_rows:
        account = db.get(GmailAccount, quota.account_id)
        if account is not None and int(account.is_active or 0) == 1:
            pairs.append((quota, account))

    if len(pairs) < 2:
        return {
            "ok": True,
            "marker": marker,
            "started_at": _iso(started_at),
            "completed_at": _iso(_now()),
            "total": len(pairs),
            "passed": 0,
            "failed": len(pairs),
            "items": [
                {
                    "sender_email": quota.email,
                    "recipient_email": None,
                    "status": "failed",
                    "reason": "至少需要 2 个启用的内部邮箱才能互发健康检查",
                }
                for quota, _account in pairs
            ],
        }

    now = _now()
    checks: list[dict[str, Any]] = []
    for idx, (sender_quota, sender_account) in enumerate(pairs):
        recipient_quota, recipient_account = pairs[(idx + 1) % len(pairs)]
        subject = f"X9 mailbox health check {marker}-{idx + 1}"
        item = {
            "check_id": f"{marker}-{idx + 1}",
            "sender_id": sender_quota.id,
            "sender_account_id": sender_account.id,
            "sender_email": sender_quota.email,
            "recipient_id": recipient_quota.id,
            "recipient_account_id": recipient_account.id,
            "recipient_email": recipient_quota.email,
            "subject": subject,
            "send_ok": False,
            "read_ok": False,
            "status": "pending",
            "reason": "",
            "message_id": None,
            "thread_id": None,
            "found_message_id": None,
            "current_action": "准备互发配对",
            "current_action_status": "passed",
            "started_at": _iso(now),
            "completed_at": None,
            "steps": [
                _health_step(
                    "prepare_pair",
                    "准备互发配对",
                    "passed",
                    f"{sender_quota.email} -> {recipient_quota.email}",
                ),
                _health_step("send_test_email", "发送测试邮件", "running", "正在调用 Gmail 发送内部健康检查邮件"),
                _health_step("wait_for_delivery", "等待邮件入箱", "pending", "发送成功后开始等待收件箱可读取"),
                _health_step("read_recipient_mailbox", "读取收件箱确认", "pending", "等待 Gmail readonly 读取测试邮件"),
                _health_step("update_mailbox_status", "更新邮箱状态", "pending", "等待检查结果"),
            ],
        }
        try:
            result = gmail_service.send_email(
                to_email=recipient_quota.email,
                subject=subject,
                body=(
                    "X9 internal mailbox health check.\n\n"
                    f"Marker: {marker}\n"
                    f"Sender: {sender_quota.email}\n"
                    f"Recipient: {recipient_quota.email}\n"
                    f"Time: {now.isoformat()}\n"
                ),
                body_format="plain",
                from_account_id=sender_account.id,
                user_id=sender_account.user_id,
                department_code=sender_account.department_code or sender_quota.department_code,
                include_shared=True,
            )
            item.update(
                {
                    "send_ok": True,
                    "message_id": result.get("message_id"),
                    "thread_id": result.get("thread_id"),
                    "status": "sent",
                    "reason": "已发送，等待收件邮箱读取确认",
                }
            )
            _upsert_health_step(item, "send_test_email", "发送测试邮件", "passed", f"Gmail 已返回 message_id={result.get('message_id') or 'unknown'}")
            _upsert_health_step(item, "wait_for_delivery", "等待邮件入箱", "running", "已发送，正在等待收件邮箱同步到测试邮件")
        except Exception as exc:
            status = _mailbox_failure_status(exc)
            sender_quota.status = status
            sender_quota.last_synced_at = now
            item.update({"status": "failed", "reason": f"发送失败: {exc}"})
        if item["status"] == "failed" and not item["send_ok"]:
            _upsert_health_step(item, "send_test_email", "发送测试邮件", "failed", str(item.get("reason") or "发送失败"))
            _upsert_health_step(item, "wait_for_delivery", "等待邮件入箱", "skipped", "发送失败，跳过收件确认", current=False)
            _upsert_health_step(item, "read_recipient_mailbox", "读取收件箱确认", "skipped", "发送失败，跳过读取", current=False)
            _upsert_health_step(item, "update_mailbox_status", "更新邮箱状态", "failed", f"发件邮箱状态标记为 {sender_quota.status}")
        checks.append(item)

    db.commit()

    deadline = time.monotonic() + payload.poll_seconds
    while time.monotonic() < deadline and any(item["send_ok"] and not item["read_ok"] for item in checks):
        for item in checks:
            if not item["send_ok"] or item["read_ok"]:
                continue
            recipient_quota = db.get(GmailAccountQuota, item["recipient_id"])
            recipient_account = db.get(GmailAccount, item["recipient_account_id"])
            if recipient_quota is None or recipient_account is None:
                _upsert_health_step(item, "wait_for_delivery", "等待邮件入箱", "failed", "收件邮箱授权记录不存在")
                _upsert_health_step(item, "read_recipient_mailbox", "读取收件箱确认", "failed", "收件邮箱授权记录不存在")
                _upsert_health_step(item, "update_mailbox_status", "更新邮箱状态", "failed", "无法更新收件邮箱状态")
                item.update({"status": "failed", "reason": "收件邮箱授权记录不存在"})
                continue
            _upsert_health_step(item, "read_recipient_mailbox", "读取收件箱确认", "running", f"正在读取 {recipient_quota.email} 的收件箱")
            try:
                found_id = _find_health_check_message(
                    db,
                    recipient_account,
                    sender_email=str(item["sender_email"]),
                    subject=str(item["subject"]),
                )
            except Exception as exc:
                status = _mailbox_failure_status(exc)
                recipient_quota.status = status
                recipient_quota.last_synced_at = _now()
                _upsert_health_step(item, "read_recipient_mailbox", "读取收件箱确认", "failed", f"读取失败: {exc}")
                _upsert_health_step(item, "update_mailbox_status", "更新邮箱状态", "failed", f"收件邮箱状态标记为 {status}")
                item.update({"status": "failed", "reason": f"读取失败: {exc}"})
                continue
            if found_id:
                _upsert_health_step(item, "wait_for_delivery", "等待邮件入箱", "passed", "收件箱已出现测试邮件", current=False)
                _upsert_health_step(item, "read_recipient_mailbox", "读取收件箱确认", "passed", f"已读取到 message_id={found_id}")
                item.update({"read_ok": True, "found_message_id": found_id, "status": "passed", "reason": "发送和读取均通过"})
                sender_quota = db.get(GmailAccountQuota, item["sender_id"])
                if sender_quota is not None:
                    sender_quota.status = "normal"
                    sender_quota.last_synced_at = _now()
                recipient_quota.status = "normal"
                recipient_quota.last_synced_at = _now()
                _upsert_health_step(item, "update_mailbox_status", "更新邮箱状态", "passed", "发件和收件邮箱均标记为正常")
        db.commit()
        if any(item["send_ok"] and not item["read_ok"] for item in checks):
            time.sleep(3)

    for item in checks:
        if item["send_ok"] and not item["read_ok"] and item["status"] not in {"failed", "passed"}:
            recipient_quota = db.get(GmailAccountQuota, item["recipient_id"])
            if recipient_quota is not None:
                recipient_quota.status = "bounce_risk"
                recipient_quota.last_synced_at = _now()
            _upsert_health_step(item, "wait_for_delivery", "等待邮件入箱", "failed", f"{payload.poll_seconds} 秒内未读取到测试邮件")
            _upsert_health_step(item, "read_recipient_mailbox", "读取收件箱确认", "failed", "收件箱查询未命中健康检查邮件")
            _upsert_health_step(item, "update_mailbox_status", "更新邮箱状态", "failed", "收件邮箱标记为 bounce_risk")
            item.update({"status": "failed", "reason": "已发送但收件邮箱未在等待时间内读取到检查邮件"})
    db.commit()

    completed_at = _now()
    for item in checks:
        item["completed_at"] = _iso(completed_at)

    public_items = [
        {
            key: value
            for key, value in item.items()
            if key
            in {
                "sender_email",
                "recipient_email",
                "send_ok",
                "read_ok",
                "status",
                "reason",
                "message_id",
                "thread_id",
                "found_message_id",
                "check_id",
                "subject",
                "current_action",
                "current_action_status",
                "started_at",
                "completed_at",
                "steps",
            }
        }
        for item in checks
    ]
    passed = sum(1 for item in public_items if item["status"] == "passed")
    return {
        "ok": True,
        "marker": marker,
        "started_at": _iso(started_at),
        "completed_at": _iso(completed_at),
        "total": len(public_items),
        "passed": passed,
        "failed": len(public_items) - passed,
        "items": public_items,
    }


def _mailbox_failure_status(exc: Exception) -> str:
    text = str(exc).lower()
    if "401" in text or "403" in text or "auth" in text or "scope" in text or "permission" in text:
        return "auth_expired"
    if "429" in text or "rate" in text or "quota" in text or "limit" in text:
        return "cooldown"
    return "bounce_risk"


def _find_health_check_message(db: Session, account: GmailAccount, *, sender_email: str, subject: str) -> str | None:
    if not gmail_service.account_has_readonly_scope(account):
        raise RuntimeError("Gmail readonly scope missing. Reconnect this mailbox.")

    service = gmail_service.build_gmail_service_for_account(db, account)
    query = f'from:{sender_email} subject:"{subject}" newer_than:1d'
    response = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=5,
        includeSpamTrash=True,
    ).execute()
    messages = response.get("messages") or []
    if not messages:
        return None
    return str(messages[0].get("id") or "") or None


@router.patch("/mailboxes/{quota_id}")
def update_mailbox(quota_id: str, body: MailboxQuotaPatch, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    department_code = current_department_code(request)
    row = db.get(GmailAccountQuota, quota_id)
    if row is None or not row_in_department(row, department_code):
        raise HTTPException(status_code=404, detail="mailbox quota not found")
    payload = body.model_dump(exclude_unset=True)
    if "enabled" in payload and payload["enabled"] is not None:
        row.enabled = 1 if payload["enabled"] else 0
    if payload.get("daily_quota") is not None:
        row.daily_quota = int(payload["daily_quota"])
    if payload.get("status"):
        row.status = str(payload["status"])
    db.commit()
    db.refresh(row)
    return {"ok": True, "item": _serialize_mailbox(db, row)}


@router.delete("/mailboxes/{quota_id}")
def remove_mailbox(quota_id: str, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    current_user(request)
    department_code = current_department_code(request)
    row = db.get(GmailAccountQuota, quota_id)
    if row is None or not row_in_department(row, department_code):
        raise HTTPException(status_code=404, detail="mailbox quota not found")

    account_id = row.account_id
    email = row.email
    account = db.get(GmailAccount, account_id)
    sync_state = db.get(GmailSyncState, account_id)

    if sync_state is not None:
        db.delete(sync_state)
    db.delete(row)

    promoted_default_id: str | None = None
    if account is not None:
        was_default = bool(account.is_default)
        owner_id = account.user_id
        account_department_code = account.department_code
        db.delete(account)
        db.flush()

        if was_default:
            q = select(GmailAccount).where(GmailAccount.is_active == 1)
            if owner_id:
                q = q.where(GmailAccount.user_id == owner_id)
            elif account_department_code:
                q = q.where(GmailAccount.department_code == account_department_code)
            replacement = db.scalar(q.order_by(GmailAccount.created_at.asc()))
            if replacement is not None:
                replacement.is_default = 1
                promoted_default_id = replacement.id

    db.commit()
    return {"ok": True, "removed": True, "account_id": account_id, "email": email, "promoted_default_id": promoted_default_id}


@router.post("/campaigns")
def create_campaign(body: CampaignIn, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = current_user(request)
    department_code = _dept_for_write(request)
    _sync_mailboxes(db, request)
    capacity = _mailbox_send_capacity(db, department_code)
    daily_limit = int(body.daily_limit)
    if capacity["daily_capacity"] > 0:
        daily_limit = min(daily_limit, capacity["daily_capacity"])
    hourly_limit = min(int(body.hourly_limit), daily_limit)
    candidate_limit = min(int(body.candidate_limit), daily_limit)
    filters = {**DEFAULT_FILTERS, **(body.filters or {})}
    interval_min = min(body.interval_min_seconds, body.interval_max_seconds)
    interval_max = max(body.interval_min_seconds, body.interval_max_seconds)
    row = EmailAutoCampaign(
        id=new_id("eac"),
        department_code=department_code,
        name=body.name.strip(),
        status=body.status,
        schedule_type=body.schedule_type,
        weekdays_json=_json_dumps(body.weekdays),
        month_days_json=_json_dumps(body.month_days),
        start_time=body.start_time,
        end_time=body.end_time,
        daily_limit=daily_limit,
        hourly_limit=hourly_limit,
        interval_min_seconds=interval_min,
        interval_max_seconds=interval_max,
        mailbox_pool=body.mailbox_pool,
        send_mode=body.send_mode,
        filters_json=_json_dumps(filters),
        created_by=str(user.get("id") or user.get("identity") or ""),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    created_jobs = _generate_jobs_for_campaign(db, row, candidate_limit=candidate_limit) if body.generate_jobs else 0
    return {"ok": True, "item": _serialize_campaign(db, row), "created_jobs": created_jobs}


@router.patch("/campaigns/{campaign_id}")
def update_campaign(campaign_id: str, body: CampaignIn, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    current_user(request)
    department_code = _dept_for_write(request)
    _sync_mailboxes(db, request)
    row = db.get(EmailAutoCampaign, campaign_id)
    if row is None or not row_in_department(row, department_code):
        raise HTTPException(status_code=404, detail="campaign not found")
    capacity = _mailbox_send_capacity(db, department_code)
    daily_limit = int(body.daily_limit)
    if capacity["daily_capacity"] > 0:
        daily_limit = min(daily_limit, capacity["daily_capacity"])
    hourly_limit = min(int(body.hourly_limit), daily_limit)
    candidate_limit = min(int(body.candidate_limit), daily_limit)
    filters = {**DEFAULT_FILTERS, **(body.filters or {})}
    interval_min = min(body.interval_min_seconds, body.interval_max_seconds)
    interval_max = max(body.interval_min_seconds, body.interval_max_seconds)
    row.name = body.name.strip()
    row.status = body.status
    row.schedule_type = body.schedule_type
    row.weekdays_json = _json_dumps(body.weekdays)
    row.month_days_json = _json_dumps(body.month_days)
    row.start_time = body.start_time
    row.end_time = body.end_time
    row.daily_limit = daily_limit
    row.hourly_limit = hourly_limit
    row.interval_min_seconds = interval_min
    row.interval_max_seconds = interval_max
    row.mailbox_pool = body.mailbox_pool
    row.send_mode = body.send_mode
    row.filters_json = _json_dumps(filters)
    db.commit()
    db.refresh(row)
    created_jobs = _generate_jobs_for_campaign(db, row, candidate_limit=candidate_limit) if body.generate_jobs else 0
    return {"ok": True, "item": _serialize_campaign(db, row), "created_jobs": created_jobs}


@router.post("/campaigns/preview")
def preview_campaign(body: CampaignIn, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    current_user(request)
    department_code = _dept_for_write(request)
    filters = {**DEFAULT_FILTERS, **(body.filters or {})}
    query_filters = _base_filters(department_code)
    query_filters.append(Creator.email.is_not(None))
    query_filters.append(Creator.email.like("%@%"))
    _apply_creator_filters(query_filters, filters)
    rows = list(db.scalars(select(Creator).where(*query_filters).order_by(*_sort_clauses(filters)).limit(body.candidate_limit)).all())
    if not rows:
        raise HTTPException(status_code=404, detail="no matching creator found")
    assets = product_asset_service.list_assets(department_code)
    creator = next((row for row in rows if not _creator_already_contacted(db, row.id)), rows[0])
    asset = product_asset_service.match_asset_for_creator(creator, assets)
    ctx = build_tk_context(creator, commission=20, product_asset=asset)
    subject = build_tk_email_subject(ctx)
    plain = generate_strategy_template(ctx)
    body_html = _email_html(plain, asset)
    return {
        "ok": True,
        "item": {
            "id": "preview",
            "time": _now().strftime("%H:%M"),
            "scheduled_at": _iso(_now()),
            "sent_at": None,
            "creator_id": creator.id,
            "creator": f"@{creator.handle}" if creator.handle else creator.id,
            "recipient": str(creator.email),
            "sender": "待分配",
            "subject": subject,
            "body": body_html,
            "body_format": "html",
            "product_asset_id": (asset or {}).get("id") if asset else None,
            "product": (asset or {}).get("name") or "AI 自动匹配 SKU 图片",
            "plan": body.name.strip(),
            "campaign_id": "preview",
            "status": "pending",
            "reason": "真实筛选预览，不写入队列",
            "filters": _job_filter_tags(filters, creator),
            "attempts": 0,
            "outreach_email_id": None,
        },
    }


@router.patch("/campaigns/{campaign_id}/status")
def update_campaign_status(campaign_id: str, body: CampaignStatusIn, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.get(EmailAutoCampaign, campaign_id)
    if row is None or not row_in_department(row, current_department_code(request)):
        raise HTTPException(status_code=404, detail="campaign not found")
    row.status = body.status
    db.commit()
    db.refresh(row)
    return {"ok": True, "item": _serialize_campaign(db, row)}


@router.post("/campaigns/pause-all")
def pause_all_campaigns(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    department_code = current_department_code(request)
    filters = []
    where = department_where(EmailAutoCampaign, department_code)
    if where is not None:
        filters.append(where)
    rows = list(db.scalars(select(EmailAutoCampaign).where(*filters)).all())
    for row in rows:
        row.status = "paused"
    db.commit()
    return {"ok": True, "updated": len(rows)}


@router.post("/campaigns/{campaign_id}/generate-jobs")
def generate_jobs(campaign_id: str, request: Request, db: Session = Depends(get_db), limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
    row = db.get(EmailAutoCampaign, campaign_id)
    if row is None or not row_in_department(row, current_department_code(request)):
        raise HTTPException(status_code=404, detail="campaign not found")
    created = _generate_jobs_for_campaign(db, row, candidate_limit=limit)
    return {"ok": True, "created_jobs": created}


def _generate_jobs_for_campaign(db: Session, campaign: EmailAutoCampaign, *, candidate_limit: int) -> int:
    filters = _json_loads(campaign.filters_json, DEFAULT_FILTERS)
    query_filters = _base_filters(campaign.department_code)
    query_filters.append(Creator.email.is_not(None))
    query_filters.append(Creator.email.like("%@%"))
    _apply_creator_filters(query_filters, filters)
    rows = list(db.scalars(select(Creator).where(*query_filters).order_by(*_sort_clauses(filters)).limit(candidate_limit)).all())
    assets = product_asset_service.list_assets(campaign.department_code)
    created = 0
    now = _now()
    capacity = _mailbox_send_capacity(db, campaign.department_code)
    mailbox_count = max(1, int(capacity.get("mailboxes") or 0))
    interval_min = max(30, int(campaign.interval_min_seconds or 90))
    interval_max = max(interval_min, int(campaign.interval_max_seconds or interval_min))
    slot_offsets = [0 for _ in range(mailbox_count)]
    for creator in rows:
        if _creator_already_contacted(db, creator.id):
            continue
        if _job_exists(db, campaign.id, creator.id):
            continue
        asset = product_asset_service.match_asset_for_creator(creator, assets)
        ctx = build_tk_context(creator, commission=20, product_asset=asset)
        subject = build_tk_email_subject(ctx)
        plain = generate_strategy_template(ctx)
        body = _email_html(plain, asset)
        slot_index = created % mailbox_count
        scheduled_at = now + timedelta(seconds=slot_offsets[slot_index])
        slot_offsets[slot_index] += random.randint(interval_min, interval_max)
        job = EmailAutoJob(
            id=new_id("eaj"),
            department_code=campaign.department_code,
            campaign_id=campaign.id,
            creator_id=creator.id,
            recipient_email=str(creator.email),
            subject=subject,
            body=body,
            body_format="html",
            product_asset_id=(asset or {}).get("id") if asset else None,
            status="pending",
            scheduled_at=scheduled_at,
            filters_json=_json_dumps(_job_filter_tags(filters, creator)),
        )
        db.add(job)
        created += 1
    db.commit()
    return created


def _apply_creator_filters(query_filters: list[Any], filters: dict[str, Any]) -> None:
    keyword = str(filters.get("keyword") or filters.get("q") or "").strip().lower()
    if keyword:
        pattern = f"%{keyword}%"
        query_filters.append(or_(
            func.lower(func.coalesce(Creator.handle, "")).like(pattern),
            func.lower(func.coalesce(Creator.email, "")).like(pattern),
            func.lower(func.coalesce(Creator.display_name, "")).like(pattern),
            func.lower(func.coalesce(Creator.primary_product_category, "")).like(pattern),
            func.lower(func.coalesce(Creator.recommended_product_type, "")).like(pattern),
            func.lower(func.coalesce(Creator.recommendation_reason, "")).like(pattern),
        ))
    source = str(filters.get("source") or "all")
    if source == "other":
        query_filters.append(or_(Creator.source.is_(None), ~Creator.source.in_(["tiktok_shop", "x9_leads", "table_import"])))
    elif source != "all":
        query_filters.append(or_(Creator.source == source, Creator.platform == source))
    priority = str(filters.get("priority") or "all")
    if priority != "all":
        query_filters.append(or_(Creator.outreach_priority == priority, Creator.priority_level == priority))
    contact = str(filters.get("contact") or "email")
    if contact == "contactable":
        query_filters.append(or_(Creator.has_email == 1, Creator.contactability_score > 0))
    score = str(filters.get("score") or "all")
    if score == "gte85":
        query_filters.append(Creator.recommendation_score >= 85)
    elif score == "70_84":
        query_filters.append(and_(Creator.recommendation_score >= 70, Creator.recommendation_score <= 84))
    elif score == "50_69":
        query_filters.append(and_(Creator.recommendation_score >= 50, Creator.recommendation_score <= 69))
    elif score == "lt50":
        query_filters.append(Creator.recommendation_score < 50)
    product = str(filters.get("product") or "all")
    if product != "all":
        query_filters.append(or_(Creator.recommended_product_type == product, Creator.primary_product_category == product))
    collab = str(filters.get("collab") or "all")
    if collab != "all":
        query_filters.append(Creator.recommended_collab_type == collab)
    status = str(filters.get("status") or "all")
    if status != "all":
        query_filters.append(or_(Creator.current_status == status, Creator.recommendation_status == status))
    review = str(filters.get("review") or "all")
    if review == "clean":
        query_filters.append(or_(Creator.review_required == 0, Creator.review_required.is_(None)))
        query_filters.append(or_(Creator.risk_summary.is_(None), Creator.risk_summary == ""))
    elif review == "need_review":
        query_filters.append(Creator.review_required == 1)
    elif review == "has_risk":
        query_filters.append(Creator.risk_summary.is_not(None))
    owner = str(filters.get("owner") or "all")
    if owner == "assigned":
        query_filters.append(Creator.owner_bd.is_not(None))
    elif owner == "unassigned":
        query_filters.append(or_(Creator.owner_bd.is_(None), Creator.owner_bd == ""))
    min_followers = filters.get("min_followers")
    max_followers = filters.get("max_followers")
    if min_followers not in {None, ""}:
        query_filters.append(Creator.followers_count >= int(min_followers))
    if max_followers not in {None, ""}:
        query_filters.append(Creator.followers_count <= int(max_followers))
    date_filter = str(filters.get("date") or "all")
    if date_filter in {"1d", "7d", "30d"}:
        days = {"1d": 1, "7d": 7, "30d": 30}[date_filter]
        cutoff = _now() - timedelta(days=days)
        query_filters.append(or_(Creator.recommended_at >= cutoff, Creator.collected_at >= cutoff, Creator.created_at >= cutoff))


def _priority_rank_clause():
    return case(
        (Creator.outreach_priority == "P1", 1),
        (Creator.outreach_priority == "P2", 2),
        (Creator.outreach_priority == "P3", 3),
        (Creator.outreach_priority == "P4", 4),
        else_=9,
    )


def _sort_clauses(filters: dict[str, Any]) -> list[Any]:
    sort = str(filters.get("sort") or "recommended")
    recent = Creator.collected_at.desc().nullslast()
    created = Creator.created_at.desc().nullslast()
    followers_desc = Creator.followers_count.desc().nullslast()
    followers_asc = Creator.followers_count.asc().nullslast()
    score_desc = Creator.recommendation_score.desc()
    fit_desc = Creator.primary_product_fit_score.desc()
    priority_rank = _priority_rank_clause().asc()
    if sort == "score":
        return [score_desc, fit_desc, followers_desc, recent, created]
    if sort == "followers":
        return [followers_desc, score_desc, fit_desc, recent, created]
    if sort == "fit":
        return [fit_desc, score_desc, followers_desc, recent, created]
    if sort == "priority":
        return [priority_rank, score_desc, fit_desc, recent, created]
    if sort in {"recent", "collected_at"}:
        return [recent, created, score_desc, followers_desc]
    if sort == "contactable":
        return [Creator.has_email.desc(), Creator.contactability_score.desc(), priority_rank, score_desc, recent, created]
    if sort == "micro":
        return [followers_asc, score_desc, fit_desc, recent, created]
    return [priority_rank, score_desc, fit_desc, followers_desc, recent, created]


def _creator_already_contacted(db: Session, creator_id: str) -> bool:
    total = int(db.scalar(
        select(func.count())
        .select_from(OutreachEmail)
        .where(OutreachEmail.creator_id == creator_id, OutreachEmail.status.in_(["queued", "sent", "draft"]))
    ) or 0)
    return total > 0


def _job_exists(db: Session, campaign_id: str, creator_id: str) -> bool:
    total = int(db.scalar(
        select(func.count())
        .select_from(EmailAutoJob)
        .where(EmailAutoJob.campaign_id == campaign_id, EmailAutoJob.creator_id == creator_id, EmailAutoJob.status.in_(["pending", "sending", "sent", "draft_created"]))
    ) or 0)
    return total > 0


def _job_filter_tags(filters: dict[str, Any], creator: Creator) -> list[str]:
    tags = ["客户推荐库", "有邮箱"]
    for key in ("keyword", "priority", "score", "product", "collab", "status", "review", "owner", "date", "sort"):
        value = filters.get(key)
        if value and value != "all":
            tags.append(str(value))
    if creator.fit_level:
        tags.append(f"Fit {creator.fit_level}")
    if creator.primary_product_category:
        tags.append(str(creator.primary_product_category))
    return tags[:8]


def _email_html(plain_body: str, asset: dict[str, Any] | None) -> str:
    paragraphs = [part.strip() for part in plain_body.split("\n\n") if part.strip()]
    paragraph_style = "margin:0 0 16px;font-size:14px;line-height:1.7;color:#111827;"
    body = "".join(
        f'<p style="{paragraph_style}">{html.escape(part).replace(chr(10), "<br>")}</p>'
        for part in paragraphs
    )
    if asset and asset.get("id") and asset.get("image_url"):
        image = (
            f'<p style="margin:0 0 18px;"><img src="/api/local/outreach/product-assets/{html.escape(str(asset["id"]))}/image" '
            f'alt="{html.escape(str(asset.get("name") or "X9 product image"))}" '
            'style="display:block;max-width:560px;width:100%;height:auto;border:1px solid #e5e7eb;border-radius:10px;" /></p>'
        )
        body = image + body
    return body


def _parse_hhmm(value: str | None, default: str) -> tuple[int, int]:
    raw = (value or default).strip()
    try:
        hour, minute = raw.split(":", 1)
        h = max(0, min(23, int(hour)))
        m = max(0, min(59, int(minute)))
        return h, m
    except Exception:
        fallback_hour, fallback_minute = default.split(":", 1)
        return int(fallback_hour), int(fallback_minute)


def _campaign_matches_calendar(campaign: EmailAutoCampaign, now: datetime) -> bool:
    if campaign.schedule_type == "weekly":
        weekdays = _json_loads(campaign.weekdays_json, []) or ["周一", "周二", "周三", "周四", "周五"]
        weekday_label = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
        return weekday_label in weekdays
    if campaign.schedule_type == "monthly":
        days = _json_loads(campaign.month_days_json, []) or [now.day]
        return now.day in {int(day) for day in days if str(day).isdigit()}
    return True


def _campaign_in_time_window(campaign: EmailAutoCampaign, now: datetime) -> bool:
    start_h, start_m = _parse_hhmm(campaign.start_time, "09:30")
    end_h, end_m = _parse_hhmm(campaign.end_time, "18:00")
    current = now.hour * 60 + now.minute
    start = start_h * 60 + start_m
    end = end_h * 60 + end_m
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def _campaign_is_due(campaign: EmailAutoCampaign, now: datetime) -> bool:
    return _campaign_matches_calendar(campaign, now) and _campaign_in_time_window(campaign, now)


def _campaign_sent_count(db: Session, campaign: EmailAutoCampaign, since: datetime) -> int:
    return int(db.scalar(
        select(func.count())
        .select_from(EmailAutoJob)
        .where(
            EmailAutoJob.campaign_id == campaign.id,
            EmailAutoJob.status.in_(["sent", "draft_created"]),
            EmailAutoJob.updated_at >= since,
        )
    ) or 0)


def _campaign_pause_on_failure(campaign: EmailAutoCampaign) -> bool:
    filters = _json_loads(campaign.filters_json, DEFAULT_FILTERS)
    value = filters.get("pause_on_failure")
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


@router.post("/jobs/process")
def process_jobs(body: ProcessJobsIn, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = current_user(request)
    if not body.confirm_send:
        raise HTTPException(status_code=400, detail="confirm_send must be true")
    results = process_due_email_auto_jobs(db, limit=body.limit, department_code=current_department_code(request), user=user)
    return {"ok": True, "processed": len(results), "results": results}


def process_due_email_auto_jobs(
    db: Session,
    *,
    limit: int = 5,
    department_code: str | None = None,
    user: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    now = _now()
    filters = [EmailAutoJob.status == "pending", or_(EmailAutoJob.scheduled_at.is_(None), EmailAutoJob.scheduled_at <= now)]
    where = department_where(EmailAutoJob, department_code)
    if where is not None:
        filters.append(where)
    rows = list(db.scalars(select(EmailAutoJob).where(*filters).order_by(EmailAutoJob.scheduled_at.asc(), EmailAutoJob.created_at.asc()).limit(limit)).all())
    actor = user or {"id": "email_auto_scheduler", "identity": "email_auto_scheduler"}
    results: list[dict[str, Any]] = []
    for job in rows:
        results.append(_process_one_job(db, job, actor))
    return results


def _process_one_job(db: Session, job: EmailAutoJob, user: dict[str, Any]) -> dict[str, Any]:
    campaign = db.get(EmailAutoCampaign, job.campaign_id)
    if campaign is None or campaign.status != "running":
        job.failure_reason = "计划未运行"
        db.commit()
        return {"job_id": job.id, "status": job.status, "reason": job.failure_reason}
    now = _now()
    if not _campaign_is_due(campaign, now):
        job.failure_reason = "不在计划发送窗口"
        db.commit()
        return {"job_id": job.id, "status": job.status, "reason": job.failure_reason}
    if _campaign_sent_count(db, campaign, _today_start()) >= int(campaign.daily_limit or 0):
        job.failure_reason = "计划今日发送量已达上限"
        db.commit()
        return {"job_id": job.id, "status": job.status, "reason": job.failure_reason}
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    if _campaign_sent_count(db, campaign, hour_start) >= int(campaign.hourly_limit or 0):
        job.failure_reason = "计划本小时发送量已达上限"
        db.commit()
        return {"job_id": job.id, "status": job.status, "reason": job.failure_reason}

    quota = _pick_mailbox_for_job(db, campaign)
    if quota is None:
        job.failure_reason = "没有可用邮箱额度"
        db.commit()
        return {"job_id": job.id, "status": job.status, "reason": job.failure_reason}

    job.status = "sending"
    job.gmail_account_id = quota.account_id
    job.sender_email = quota.email
    job.attempts = int(job.attempts or 0) + 1
    db.commit()

    email = OutreachEmail(
        id=new_id("oem"),
        department_code=job.department_code,
        creator_id=job.creator_id,
        to_email=job.recipient_email,
        from_email=quota.email,
        subject=job.subject,
        body=job.body,
        body_format=job.body_format,
        status="queued",
        review_required=0,
        auto_send=1,
        context_json=_json_dumps({"email_auto_job_id": job.id, "campaign_id": job.campaign_id}),
        created_by=str(user.get("id") or user.get("identity") or "email_auto"),
    )
    db.add(email)
    db.commit()
    job.outreach_email_id = email.id

    if campaign.send_mode == "draft":
        email.status = "draft"
        job.status = "draft_created"
        job.failure_reason = None
        db.commit()
        return {"job_id": job.id, "status": job.status, "outreach_email_id": email.id}

    account = db.get(GmailAccount, quota.account_id)
    try:
        result = gmail_service.send_email(
            to_email=job.recipient_email,
            subject=job.subject,
            body=job.body,
            body_format=job.body_format,
            from_account_id=quota.account_id,
            user_id=account.user_id if account else None,
            department_code=account.department_code if account else job.department_code,
            include_shared=True,
        )
    except Exception as exc:
        email.status = "failed"
        email.error_message = str(exc)
        job.status = "failed"
        job.failure_reason = str(exc)
        quota.status = "cooldown" if "429" in str(exc) or "limit" in str(exc).lower() else quota.status
        quota.cooldown_until = _now() + timedelta(hours=24) if quota.status == "cooldown" else quota.cooldown_until
        paused = False
        if _campaign_pause_on_failure(campaign):
            campaign.status = "paused"
            paused = True
            job.failure_reason = f"{job.failure_reason}；计划已因发送失败自动暂停"
        db.commit()
        return {"job_id": job.id, "status": job.status, "reason": job.failure_reason, "campaign_paused": paused}

    email.status = "sent"
    email.sent_at = _now()
    email.gmail_message_id = result.get("message_id")
    email.gmail_thread_id = result.get("thread_id")
    email.from_email = result.get("from_email") or quota.email
    email.error_message = None
    job.status = "sent"
    job.sent_at = email.sent_at
    job.failure_reason = None
    quota.last_sent_at = email.sent_at
    _mark_creator_sent(db, job.creator_id, email, user)
    db.commit()
    return {"job_id": job.id, "status": job.status, "outreach_email_id": email.id}


def _pick_mailbox_for_job(db: Session, campaign: EmailAutoCampaign) -> GmailAccountQuota | None:
    rows = list(db.scalars(
        select(GmailAccountQuota)
        .where(
            GmailAccountQuota.department_code == campaign.department_code,
            GmailAccountQuota.enabled == 1,
            GmailAccountQuota.status == "normal",
        )
        .order_by(GmailAccountQuota.last_sent_at.asc().nullsfirst(), GmailAccountQuota.email.asc())
    ).all())
    random.shuffle(rows)
    rows.sort(key=lambda row: _daily_auto_sent(db, row.email, row))
    for row in rows:
        if _daily_auto_sent(db, row.email, row) >= int(row.daily_quota or 0):
            continue
        if row.cooldown_until and row.cooldown_until > _now():
            continue
        if row.last_sent_at:
            elapsed = (_now() - row.last_sent_at).total_seconds()
            if elapsed < int(campaign.interval_min_seconds or 90):
                continue
        return row
    return None


def _mark_creator_sent(db: Session, creator_id: str, email: OutreachEmail, user: dict[str, Any]) -> None:
    creator = db.get(Creator, creator_id)
    if creator is None:
        return
    actor_user_id = str(user.get("id") or user.get("identity") or "email_auto")
    create_outreach_event(
        db,
        creator,
        event_type="sent",
        actor_user_id=actor_user_id,
        owner_bd=creator.owner_bd,
        metadata={
            "outreach_email_id": email.id,
            "gmail_message_id": email.gmail_message_id,
            "gmail_thread_id": email.gmail_thread_id,
            "source": "email_auto",
        },
    )
    if normalize_current_status(creator.current_status) in {None, "", "待建联"}:
        creator.current_status = STATUS_CONTACTED


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.get(EmailAutoJob, job_id)
    if row is None or not row_in_department(row, current_department_code(request)):
        raise HTTPException(status_code=404, detail="job not found")
    if row.status not in {"failed", "skipped"}:
        raise HTTPException(status_code=400, detail="only failed or skipped jobs can be retried")
    row.status = "pending"
    row.failure_reason = None
    row.scheduled_at = _now()
    db.commit()
    return {"ok": True, "item": _serialize_job(db, row)}


@router.post("/jobs/retry-failed")
def retry_failed_jobs(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    department_code = current_department_code(request)
    filters = [EmailAutoJob.status == "failed"]
    where = department_where(EmailAutoJob, department_code)
    if where is not None:
        filters.append(where)
    rows = list(db.scalars(select(EmailAutoJob).where(*filters)).all())
    for row in rows:
        row.status = "pending"
        row.failure_reason = None
        row.scheduled_at = _now()
    db.commit()
    return {"ok": True, "updated": len(rows)}


@router.post("/jobs/{job_id}/skip")
def skip_job(job_id: str, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.get(EmailAutoJob, job_id)
    if row is None or not row_in_department(row, current_department_code(request)):
        raise HTTPException(status_code=404, detail="job not found")
    if row.status not in {"pending", "failed"}:
        raise HTTPException(status_code=400, detail="only pending or failed jobs can be skipped")
    row.status = "skipped"
    row.failure_reason = "手动跳过"
    db.commit()
    return {"ok": True, "item": _serialize_job(db, row)}
