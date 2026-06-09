from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.youtube_lead import YoutubeImportRun, YoutubeLead, YoutubeLeadSource, YoutubeRawRow
from ..services.departments import current_department_code, department_where
from ..services.youtube_import_service import import_youtube_export
from ..youtube_database import YOUTUBE_DB_URL, get_youtube_db


router = APIRouter(prefix="/api/local/youtube", tags=["youtube-import"])


@router.post("/import")
async def import_youtube_rows(
    request: Request,
    filename: str = Query(default=""),
    dry_run: bool = Query(default=False),
    db: Session = Depends(get_youtube_db),
) -> dict:
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="empty YouTube export file")

    resolved_filename = filename or request.headers.get("X-Filename") or "youtube-export.json"
    try:
        return import_youtube_export(
            db,
            content,
            filename=resolved_filename,
            dry_run=dry_run,
            department_code=current_department_code(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/runs")
def list_youtube_runs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_youtube_db),
) -> dict:
    department = current_department_code(request)
    query = _department_query(db.query(YoutubeImportRun), YoutubeImportRun, department)
    total = query.count()
    runs = query.order_by(YoutubeImportRun.created_at.desc()).offset(offset).limit(limit).all()
    return {"ok": True, "total": total, "items": [_run_dict(run) for run in runs]}


@router.get("/stats")
def youtube_local_stats(
    request: Request,
    db: Session = Depends(get_youtube_db),
) -> dict:
    department = current_department_code(request)
    runs_query = _department_query(db.query(YoutubeImportRun), YoutubeImportRun, department)
    raw_query = _department_query(db.query(YoutubeRawRow), YoutubeRawRow, department)
    leads_query = _department_query(db.query(YoutubeLead), YoutubeLead, department)
    latest_run = runs_query.order_by(YoutubeImportRun.created_at.desc()).first()
    return {
        "ok": True,
        "local_mode": True,
        "db_status": "ok",
        "db_url": YOUTUBE_DB_URL,
        "runs": runs_query.count(),
        "today_runs": _today_count(runs_query),
        "raw_rows": raw_query.count(),
        "leads": leads_query.count(),
        "has_email": leads_query.filter(YoutubeLead.has_email == 1).count(),
        "manual_review": leads_query.filter(YoutubeLead.needs_manual_review == 1).count(),
        "dropped_no_contact": int(
            runs_query.with_entities(func.coalesce(func.sum(YoutubeImportRun.dropped_no_contact), 0)).scalar() or 0
        ),
        "latest_run": _run_dict(latest_run) if latest_run else None,
    }


@router.get("/actors")
def youtube_collection_actors(
    request: Request,
    db: Session = Depends(get_youtube_db),
) -> dict:
    department = current_department_code(request)
    runs_query = _department_query(db.query(YoutubeImportRun), YoutubeImportRun, department)
    raw_query = _department_query(db.query(YoutubeRawRow), YoutubeRawRow, department)
    leads_query = _department_query(db.query(YoutubeLead), YoutubeLead, department)
    latest_run = runs_query.order_by(YoutubeImportRun.created_at.desc()).first()
    raw_total = raw_query.count()
    lead_total = leads_query.count()
    email_total = leads_query.filter(YoutubeLead.has_email == 1).count()
    review_total = leads_query.filter(YoutubeLead.needs_manual_review == 1).count()
    today = _today_count(runs_query)
    actor = {
        "id": "youtube_local_collector",
        "username": "youtube_local_collector",
        "display_name": "本地 YouTube 插件",
        "email": "",
        "role": "collector",
        "department_code": department or "",
        "collection": {
            "scope": "local",
            "total": raw_total,
            "today": today,
            "lead_total": lead_total,
            "with_email": email_total,
            "manual_review": review_total,
            "last_collected_at": _dt(latest_run.finished_at or latest_run.created_at) if latest_run else "",
            "user_status": "online" if latest_run else "offline",
            "latest_run": _run_dict(latest_run) if latest_run else None,
        },
    }
    return {
        "ok": True,
        "scope": "admin",
        "items": [actor] if raw_total or lead_total or latest_run else [],
        "unassigned": {"total": 0, "today": 0, "sources": {}, "recent_workers": []},
    }


@router.get("/leads")
def list_youtube_leads(
    request: Request,
    has_email: bool | None = Query(default=None),
    needs_manual_review: bool | None = Query(default=None),
    keyword: str = Query(default=""),
    source_type: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_youtube_db),
) -> dict:
    department = current_department_code(request)
    query = _department_query(db.query(YoutubeLead), YoutubeLead, department)
    if has_email is not None:
        query = query.filter(YoutubeLead.has_email == (1 if has_email else 0))
    if needs_manual_review is not None:
        query = query.filter(YoutubeLead.needs_manual_review == (1 if needs_manual_review else 0))
    if keyword or source_type:
        query = query.join(YoutubeLeadSource, YoutubeLeadSource.lead_id == YoutubeLead.id)
        if keyword:
            query = query.filter(YoutubeLeadSource.keyword.ilike(f"%{keyword.strip()}%"))
        if source_type:
            query = query.filter(YoutubeLeadSource.source_type == source_type.strip())
        query = query.distinct()
    total = query.count()
    leads = query.order_by(YoutubeLead.updated_at.desc()).offset(offset).limit(limit).all()
    return {"ok": True, "total": total, "items": [_lead_dict(lead) for lead in leads]}


@router.get("/manual-review")
def list_youtube_manual_review(
    request: Request,
    keyword: str = Query(default=""),
    source_type: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_youtube_db),
) -> dict:
    department = current_department_code(request)
    query = _department_query(db.query(YoutubeLead), YoutubeLead, department).filter(YoutubeLead.needs_manual_review == 1)
    if keyword or source_type:
        query = query.join(YoutubeLeadSource, YoutubeLeadSource.lead_id == YoutubeLead.id)
        if keyword:
            query = query.filter(YoutubeLeadSource.keyword.ilike(f"%{keyword.strip()}%"))
        if source_type:
            query = query.filter(YoutubeLeadSource.source_type == source_type.strip())
        query = query.distinct()
    total = query.count()
    leads = query.order_by(YoutubeLead.updated_at.desc()).offset(offset).limit(limit).all()
    return {"ok": True, "total": total, "items": [_lead_dict(lead) for lead in leads]}


@router.get("/sources")
def list_youtube_sources(
    request: Request,
    lead_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_youtube_db),
) -> dict:
    department = current_department_code(request)
    lead = _department_query(db.query(YoutubeLead), YoutubeLead, department).filter(YoutubeLead.id == lead_id).one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="YouTube lead not found")
    query = _department_query(db.query(YoutubeLeadSource), YoutubeLeadSource, department).filter(
        YoutubeLeadSource.lead_id == lead_id
    )
    total = query.count()
    sources = query.order_by(YoutubeLeadSource.created_at.desc()).offset(offset).limit(limit).all()
    return {"ok": True, "total": total, "lead": _lead_dict(lead), "items": [_source_dict(source) for source in sources]}


def _run_dict(run: YoutubeImportRun) -> dict:
    return {
        "id": run.id,
        "filename": run.filename,
        "keyword": run.keyword or "",
        "source_search_url": run.source_search_url or "",
        "status": run.status,
        "total_rows": run.total_rows,
        "kept_rows": run.kept_rows,
        "dropped_no_contact": run.dropped_no_contact,
        "inserted": run.inserted,
        "updated": run.updated,
        "sources_added": run.sources_added,
        "manual_review": run.manual_review,
        "errors_count": run.errors_count,
        "started_at": _dt(run.started_at),
        "finished_at": _dt(run.finished_at),
        "created_at": _dt(run.created_at),
        "updated_at": _dt(run.updated_at),
    }


def _department_query(query, model, department: str | None):
    clause = department_where(model, department)
    return query.filter(clause) if clause is not None else query


def _lead_dict(lead: YoutubeLead) -> dict:
    return {
        "id": lead.id,
        "platform": lead.platform,
        "channel_key": lead.channel_key,
        "channel_id": lead.channel_id or "",
        "channel_handle": lead.channel_handle or "",
        "channel_url": lead.channel_url or "",
        "display_name": lead.display_name or "",
        "email": lead.email or "",
        "emails": _json_list(lead.emails_json),
        "has_email": bool(lead.has_email),
        "needs_manual_review": bool(lead.needs_manual_review),
        "review_reasons": _json_list(lead.review_reasons_json),
        "manual_review_url": lead.manual_review_url or "",
        "latest_source_type": lead.latest_source_type or "",
        "latest_video_id": lead.latest_video_id or "",
        "latest_video_url": lead.latest_video_url or "",
        "latest_video_title": lead.latest_video_title or "",
        "latest_keyword": lead.latest_keyword or "",
        "source_types": _json_list(lead.source_types_json),
        "first_seen_at": _dt(lead.first_seen_at),
        "last_seen_at": _dt(lead.last_seen_at),
        "created_at": _dt(lead.created_at),
        "updated_at": _dt(lead.updated_at),
    }


def _source_dict(source: YoutubeLeadSource) -> dict:
    return {
        "id": source.id,
        "lead_id": source.lead_id,
        "run_id": source.run_id or "",
        "source_type": source.source_type or "",
        "keyword": source.keyword or "",
        "video_id": source.video_id or "",
        "video_url": source.video_url or "",
        "video_title": source.video_title or "",
        "evidence_url": source.evidence_url or "",
        "manual_review_url": source.manual_review_url or "",
        "email": source.email or "",
        "review_reason": source.review_reason or "",
        "collected_at": _dt(source.collected_at),
        "created_at": _dt(source.created_at),
        "updated_at": _dt(source.updated_at),
    }


def _json_list(value: str | None) -> list:
    if not value:
        return []
    try:
        import json

        parsed = json.loads(value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _dt(value) -> str:
    return value.isoformat() if value else ""


def _today_count(query) -> int:
    from datetime import datetime, time

    start = datetime.combine(datetime.utcnow().date(), time.min)
    return query.filter(YoutubeImportRun.created_at >= start).count()
