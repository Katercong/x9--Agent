"""Recruitment lead API (Phase 2): ingest + list + patch for company leads and
cross-border talent leads. Department-scoped; ingest stamps the actor's
department_code. Scrapers / the browser extension POST to the ingest endpoints.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.company_lead import CompanyLead, CompanyObservation
from ..models.talent_lead import TalentLead
from ..services.company_lead_service import ingest_company, ingest_talent
from ..services.departments import current_department_code, department_where
from ..services.upload_queue_cleanup import attach_queue_cleanup

router = APIRouter(prefix="/api/local", tags=["company-leads"])


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _company_dict(lead: CompanyLead) -> dict[str, Any]:
    return {
        "id": lead.id,
        "platform": lead.platform,
        "company_name": lead.company_name,
        "industry": lead.industry,
        "size_range": lead.size_range,
        "city": lead.city,
        "province": lead.province,
        "company_address": lead.company_address,
        "company_description": lead.company_description,
        "tier": lead.tier,
        "score": lead.score,
        "cooperation_type": lead.cooperation_type,
        "data_quality": lead.data_quality,
        "next_action": lead.next_action,
        "us_market": int(lead.us_market_flag or 0),
        "excluded": int(lead.excluded or 0),
        "excluded_reason": lead.excluded_reason,
        "lead_tags": _json_list(lead.lead_tags),
        "raw_jd_titles": _json_list(lead.raw_jd_titles),
        "search_keywords": lead.search_keywords,
        "score_reason": lead.score_reason,
        "llm_score_status": lead.llm_score_status,
        "llm_score_reason": lead.llm_score_reason,
        "llm_score_suggestion": lead.llm_score_suggestion,
        "contact_name": lead.contact_name,
        "contact_title": lead.contact_title,
        "contact_email": lead.contact_email,
        "contact_phone": lead.contact_phone,
        "hr_wechat": lead.hr_wechat,
        "contact_source": lead.contact_source,
        "status": lead.status,
        "owner_bd": lead.owner_bd,
        "notes": lead.notes,
        "created_at": _iso(lead.created_at),
    }


def _talent_dict(lead: TalentLead) -> dict[str, Any]:
    return {
        "id": lead.id,
        "platform": lead.platform,
        "name_masked": lead.name_masked,
        "desired_title": lead.desired_title,
        "city": lead.city,
        "experience": lead.experience,
        "education": lead.education,
        "major": lead.major,
        "salary_expectation": lead.salary_expectation,
        "tier": lead.tier,
        "score": lead.score,
        "cooperation_type": lead.cooperation_type,
        "next_action": lead.next_action,
        "lead_tags": _json_list(lead.lead_tags),
        "score_reason": lead.score_reason,
        "llm_score_suggestion": lead.llm_score_suggestion,
        "raw_summary": lead.raw_summary,
        "source_url": lead.source_url,
        "resume_download_url": lead.resume_download_url,
        "contact_email": lead.contact_email,
        "contact_phone": lead.contact_phone,
        "wechat": lead.wechat,
        "status": lead.status,
        "notes": lead.notes,
        "created_at": _iso(lead.created_at),
    }


def _company_source_urls(db: Session, lead_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Source page URLs (51job / zhaopin / qzrc) captured for this company,
    newest first. These are the clickable links shown in the detail panel."""
    rows = db.execute(
        select(CompanyObservation.source_url, CompanyObservation.platform, CompanyObservation.scraped_at)
        .where(CompanyObservation.company_lead_id == lead_id, CompanyObservation.source_url.isnot(None))
        .order_by(CompanyObservation.scraped_at.desc())
        .limit(limit)
    ).all()
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for url, platform, scraped_at in rows:
        if not url or url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "platform": platform, "scraped_at": _iso(scraped_at)})
    return out


# ---------------- ingest (scraper / extension) ----------------

@router.post("/company-leads/ingest")
def company_ingest(request: Request, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        lead = ingest_company(db, payload, department_code=current_department_code(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return attach_queue_cleanup(
        {"ok": True, "id": lead.id, "tier": lead.tier, "score": lead.score, "llm_score_status": lead.llm_score_status},
        payload,
        entity="company_lead",
        lead_id=lead.id,
    )


@router.post("/talents/ingest")
def talent_ingest(request: Request, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        lead = ingest_talent(db, payload, department_code=current_department_code(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return attach_queue_cleanup(
        {"ok": True, "id": lead.id, "tier": lead.tier, "score": lead.score, "llm_score_status": lead.llm_score_status},
        payload,
        entity="talent_lead",
        lead_id=lead.id,
    )


# ---------------- list ----------------

def _scope(stmt, model, request: Request):
    where = department_where(model, current_department_code(request))
    if where is not None:
        stmt = stmt.where(where)
    return stmt


@router.get("/company-leads")
def list_company_leads(
    request: Request,
    tier: str | None = Query(default=None),
    status: str | None = Query(default=None),
    cooperation_type: str | None = Query(default=None),
    us_market: int | None = Query(default=None),
    include_excluded: int = Query(default=0),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    base = _scope(select(CompanyLead), CompanyLead, request)
    if not include_excluded:
        base = base.where(func.coalesce(CompanyLead.excluded, 0) == 0)
    if tier:
        base = base.where(CompanyLead.tier == tier)
    if status:
        base = base.where(CompanyLead.status == status)
    if cooperation_type:
        base = base.where(CompanyLead.cooperation_type == cooperation_type)
    if us_market is not None:
        base = base.where(CompanyLead.us_market_flag == us_market)
    if q:
        like = f"%{q.strip()}%"
        base = base.where(or_(
            CompanyLead.company_name.ilike(like),
            CompanyLead.industry.ilike(like),
            CompanyLead.city.ilike(like),
        ))
    total = int(db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0)
    rows = db.scalars(
        base.order_by(CompanyLead.score.desc(), CompanyLead.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {"ok": True, "total": total, "limit": limit, "offset": offset, "items": [_company_dict(r) for r in rows]}


@router.get("/talents")
def list_talents(
    request: Request,
    tier: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    base = _scope(select(TalentLead), TalentLead, request)
    if tier:
        base = base.where(TalentLead.tier == tier)
    if status:
        base = base.where(TalentLead.status == status)
    if q:
        like = f"%{q.strip()}%"
        base = base.where(or_(
            TalentLead.desired_title.ilike(like),
            TalentLead.city.ilike(like),
            TalentLead.major.ilike(like),
        ))
    total = int(db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0)
    rows = db.scalars(
        base.order_by(TalentLead.score.desc(), TalentLead.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {"ok": True, "total": total, "limit": limit, "offset": offset, "items": [_talent_dict(r) for r in rows]}


# ---------------- patch (CRM status / notes / owner) ----------------

_COMPANY_PATCH_FIELDS = {"status", "owner_bd", "notes", "contact_email", "contact_phone", "hr_wechat"}
_TALENT_PATCH_FIELDS = {"status", "notes", "contact_email", "contact_phone", "wechat"}


# ---------------- detail (click a row) ----------------

@router.get("/company-leads/{lead_id}")
def get_company_lead(lead_id: str, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    lead = db.get(CompanyLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="not found")
    item = _company_dict(lead)
    item["source_urls"] = _company_source_urls(db, lead.id)
    return {"ok": True, "item": item}


@router.get("/talents/{lead_id}")
def get_talent(lead_id: str, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    lead = db.get(TalentLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True, "item": _talent_dict(lead)}


@router.patch("/company-leads/{lead_id}")
def patch_company_lead(lead_id: str, request: Request, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    lead = db.get(CompanyLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="not found")
    for key, value in payload.items():
        if key in _COMPANY_PATCH_FIELDS:
            setattr(lead, key, value)
    db.commit()
    db.refresh(lead)
    return {"ok": True, "item": _company_dict(lead)}


@router.patch("/talents/{lead_id}")
def patch_talent(lead_id: str, request: Request, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    lead = db.get(TalentLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="not found")
    for key, value in payload.items():
        if key in _TALENT_PATCH_FIELDS:
            setattr(lead, key, value)
    db.commit()
    db.refresh(lead)
    return {"ok": True, "item": _talent_dict(lead)}
