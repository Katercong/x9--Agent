"""review_task_service.py — manual-review task lifecycle."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.review_task import ReviewTask
from ..utils.id_utils import new_id
from ..utils.json_utils import dumps_json, loads_json_list
from .departments import department_where, row_in_department


SEARCH_KEYWORD_REASON = (
    "Only matched by search keyword; bio/video evidence does not confirm "
    "feminine-care relevance. Manual review required."
)


def open_task_if_needed(db: Session, creator: Creator) -> ReviewTask | None:
    if not creator.review_required:
        stale_tasks = list(db.scalars(
            select(ReviewTask).where(and_(
                ReviewTask.creator_id == creator.id,
                ReviewTask.status.in_(["pending", "in_review"]),
            ))
        ).all())
        for task in stale_tasks:
            task.status = "skipped"
            task.reviewed_at = datetime.now(timezone.utc)
            task.reviewer_notes = "Auto-closed after rules re-routed this creator out of manual review."
        return None
    risks = loads_json_list(creator.risk_tags_json)
    risk_tag = "search_keyword_only_match" if "search_keyword_only_match" in risks else "manual_review_required"

    existing = db.scalar(
        select(ReviewTask).where(and_(
            ReviewTask.creator_id == creator.id,
            ReviewTask.status.in_(["pending", "in_review"]),
        ))
    )
    if existing:
        return existing

    task = ReviewTask(
        id=new_id("review"),
        department_code=creator.department_code,
        creator_id=creator.id,
        task_type="content_fit_review",
        status="pending",
        risk_tags_json=dumps_json(risks),
        reason=creator.recommendation_reason or SEARCH_KEYWORD_REASON,
    )
    db.add(task)
    return task


def list_tasks(
    db: Session,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
    department_code: str | None = None,
) -> list[ReviewTask]:
    q = select(ReviewTask)
    if status:
        q = q.where(ReviewTask.status == status)
    where_department = department_where(ReviewTask, department_code)
    if where_department is not None:
        q = q.where(where_department)
    q = q.order_by(ReviewTask.created_at.desc()).offset(offset).limit(limit)
    return list(db.scalars(q).all())


def update_task(
    db: Session,
    task_id: str,
    *,
    status: str | None = None,
    reviewer_notes: str | None = None,
    review_result: str | None = None,
    assigned_staff_id: str | None = None,
    change_product_type: str | None = None,
    change_collab_type: str | None = None,
    upgrade_priority: str | None = None,
    department_code: str | None = None,
) -> ReviewTask | None:
    """Approve/reject/hold + optional override of recommendation fields."""
    task = db.get(ReviewTask, task_id)
    if task is None:
        return None
    if not row_in_department(task, department_code):
        return None
    if status:
        task.status = status
        if status in {"approved", "rejected", "hold", "skipped"}:
            task.reviewed_at = datetime.now(timezone.utc)
    if reviewer_notes is not None:
        task.reviewer_notes = reviewer_notes
    if review_result is not None:
        task.review_result = review_result
    if assigned_staff_id is not None:
        task.assigned_staff_id = assigned_staff_id

    creator = db.get(Creator, task.creator_id)
    if creator is None:
        db.commit()
        return task

    # Apply human overrides
    if change_product_type:
        creator.recommended_product_type = change_product_type
    if change_collab_type:
        creator.recommended_collab_type = change_collab_type
    if upgrade_priority:
        creator.outreach_priority = upgrade_priority

    if status == "approved":
        # Drop blocking risk tags so the next pipeline run can route
        # the creator into a real outreach queue.
        risks = [r for r in loads_json_list(creator.risk_tags_json)
                 if r not in {"search_keyword_only_match", "manual_review_required"}]
        creator.risk_tags_json = dumps_json(risks)
        creator.review_required = 0
        creator.review_status = "approved"
        if creator.recommendation_status == "manual_review_before_outreach":
            creator.recommendation_status = "recommended_after_review"
        if creator.queue_type == "manual_review_queue":
            creator.queue_type = "feminine_warm_lead_queue" if (creator.feminine_care_fit or 0) >= 40 else "general_lifestyle_hold"
    elif status == "rejected":
        creator.review_required = 0
        creator.review_status = "rejected"
        creator.queue_type = "not_recommended_queue"
        creator.recommendation_status = "not_recommended_now"
        creator.recommended_collab_type = "do_not_contact_now"
    elif status == "hold":
        creator.review_required = 0
        creator.review_status = "hold"
        creator.queue_type = "general_lifestyle_hold"

    db.commit()
    return task
