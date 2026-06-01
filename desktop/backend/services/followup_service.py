from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.followup_task import FollowupTask
from ..models.outreach_email import OutreachEmail
from ..services.departments import DEFAULT_DEPARTMENT
from ..utils.id_utils import new_id
from ..utils.json_utils import dumps_json


OPEN_TASK_STATUSES = ("open", "pending")


def _owner_id(creator: Creator, actor_user_id: str | None = None) -> str | None:
    return actor_user_id or (creator.owner_bd or "").strip() or None


def create_followup_task_once(
    db: Session,
    *,
    creator: Creator,
    task_type: str,
    due_at: datetime | None,
    owner_user_id: str | None = None,
    priority: int = 50,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> FollowupTask:
    existing = db.scalars(
        select(FollowupTask)
        .where(FollowupTask.creator_id == creator.id)
        .where(FollowupTask.task_type == task_type)
        .where(FollowupTask.status.in_(OPEN_TASK_STATUSES))
        .limit(1)
    ).first()
    if existing is not None:
        if due_at is not None and existing.due_at is None:
            existing.due_at = due_at
        if owner_user_id and not existing.owner_user_id:
            existing.owner_user_id = owner_user_id
        existing.department_code = creator.department_code or existing.department_code or DEFAULT_DEPARTMENT
        db.flush()
        return existing

    task = FollowupTask(
        id=new_id("fup"),
        creator_id=creator.id,
        department_code=creator.department_code or DEFAULT_DEPARTMENT,
        owner_user_id=owner_user_id,
        task_type=task_type,
        status="open",
        due_at=due_at,
        priority=priority,
        reason=reason,
        metadata_json=dumps_json(metadata or {}) if metadata else None,
    )
    db.add(task)
    db.flush()
    return task


def close_creator_tasks(
    db: Session,
    *,
    creator_id: str,
    task_types: Iterable[str] | None = None,
    completed_at: datetime | None = None,
) -> int:
    query = (
        select(FollowupTask)
        .where(FollowupTask.creator_id == creator_id)
        .where(FollowupTask.status.in_(OPEN_TASK_STATUSES))
    )
    task_types_tuple = tuple(task_types or ())
    if task_types_tuple:
        query = query.where(FollowupTask.task_type.in_(task_types_tuple))
    count = 0
    now = completed_at or datetime.utcnow()
    for task in db.scalars(query).all():
        task.status = "completed"
        task.completed_at = now
        count += 1
    if count:
        db.flush()
    return count


def create_pending_reply_followup(
    db: Session,
    *,
    creator: Creator,
    email: OutreachEmail | None = None,
    actor_user_id: str | None = None,
) -> FollowupTask:
    now = datetime.utcnow()
    return create_followup_task_once(
        db,
        creator=creator,
        task_type="reply_followup_1",
        due_at=now,
        owner_user_id=_owner_id(creator, actor_user_id),
        priority=90,
        reason="Creator replied; follow up now.",
        metadata={
            "outreach_email_id": getattr(email, "id", None),
            "gmail_message_id": getattr(email, "gmail_message_id", None),
            "gmail_thread_id": getattr(email, "gmail_thread_id", None),
        },
    )


def apply_outreach_event_followups(
    db: Session,
    *,
    creator: Creator,
    event_type: str,
    actor_user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    metadata = metadata or {}
    if metadata.get("backfill"):
        return
    now = datetime.utcnow()
    normalized = str(event_type or "").strip().lower()
    owner_user_id = _owner_id(creator, actor_user_id)

    if normalized == "sent":
        close_creator_tasks(db, creator_id=creator.id, task_types=("reply_followup_1", "reply_followup_2"))
        create_followup_task_once(
            db,
            creator=creator,
            task_type="reply_followup_1",
            due_at=now + timedelta(days=3),
            owner_user_id=owner_user_id,
            priority=60,
            reason="No reply after outreach; first follow-up is due.",
            metadata=metadata,
        )
        return

    if normalized in {"pending_followup", "pending_reply", "replied"}:
        close_creator_tasks(db, creator_id=creator.id, task_types=("reply_followup_1", "reply_followup_2"))
        create_followup_task_once(
            db,
            creator=creator,
            task_type="reply_followup_1",
            due_at=now,
            owner_user_id=owner_user_id,
            priority=90,
            reason="Creator replied; follow up now.",
            metadata=metadata,
        )
        return

    if normalized in {"communicating", "contacted"}:
        close_creator_tasks(
            db,
            creator_id=creator.id,
            task_types=("reply_followup_1", "reply_followup_2", "reply_manual_review", "pending_reply_check"),
        )
        return

    if normalized == "confirmed":
        close_creator_tasks(
            db,
            creator_id=creator.id,
            task_types=("reply_followup_1", "reply_followup_2", "reply_manual_review", "pending_reply_check"),
        )
        create_followup_task_once(
            db,
            creator=creator,
            task_type="ship_sample",
            due_at=now,
            owner_user_id=owner_user_id,
            priority=70,
            reason="Cooperation confirmed; arrange sample shipment.",
            metadata=metadata,
        )
        return

    if normalized == "sample_shipped":
        create_followup_task_once(
            db,
            creator=creator,
            task_type="fill_tracking_info",
            due_at=now,
            owner_user_id=owner_user_id,
            priority=75,
            reason="\u5df2\u5bc4\u6837\uff0c\u8bf7\u586b\u5199\u7269\u6d41\u4fe1\u606f\u3002",
            metadata=metadata,
        )
        return

    if normalized == "sample_delivered":
        create_followup_task_once(
            db,
            creator=creator,
            task_type="confirm_video_plan",
            due_at=now + timedelta(days=3),
            owner_user_id=owner_user_id,
            priority=70,
            reason="Sample delivered; confirm the creator video plan.",
            metadata=metadata,
        )
        return

    if normalized == "video_published":
        create_followup_task_once(
            db,
            creator=creator,
            task_type="push_ad_authorization",
            due_at=now,
            owner_user_id=owner_user_id,
            priority=65,
            reason="Video published; move toward ad authorization.",
            metadata=metadata,
        )
        return

    if normalized in {"partnered", "ad_authorized"}:
        create_followup_task_once(
            db,
            creator=creator,
            task_type="start_ad_campaign",
            due_at=now,
            owner_user_id=owner_user_id,
            priority=65,
            reason="Ad authorization ready; prepare campaign launch.",
            metadata=metadata,
        )
