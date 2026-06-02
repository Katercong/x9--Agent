"""Recruitment lead ingest + scoring service (Phase 2).

Ported from CompanyLeads/backend/service.py and adapted to the X9 desktop
backend: writes into the x9db `company_leads` / `talent_leads` tables, carries a
`department_code` for multi-department scoping, and reuses the keyword + LLM
scoring modules under ``utils/job_*``. Scoring falls back to keyword-only when
no LLM is configured (``LLM_*`` env vars), so ingest never hard-fails on LLM.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models.company_lead import CompanyLead, CompanyObservation
from ..models.talent_lead import TalentLead
from ..services.departments import DEFAULT_DEPARTMENT
from ..utils.job_keyword_rules import _action, _tier, score_company, score_talent_profile
from ..utils.job_llm_scorer import PROMPT_VERSION, score_lead_with_llm
from ..utils.job_exclusion import check_excluded


def _uid() -> str:
    return uuid.uuid4().hex


def score_talent(data: dict[str, Any]) -> dict[str, Any]:
    return score_talent_profile(data)


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _extract_search_keywords(data: dict[str, Any]) -> str:
    raw = data.get("raw_data") if isinstance(data.get("raw_data"), dict) else {}
    candidates = [
        data.get("search_keywords"),
        data.get("search_keyword"),
        data.get("keyword"),
        raw.get("search_keywords"),
        raw.get("search_keyword"),
        raw.get("keyword"),
    ]
    notes = str(data.get("notes") or "")
    if "keyword=" in notes:
        candidates.append(notes.split("keyword=", 1)[1].split()[0].strip(" ,;"))
    return ", ".join(dict.fromkeys(str(v).strip() for v in candidates if str(v or "").strip()))


def _short_error(error: str) -> str:
    return (error or "")[:1200]


def _merge_llm_score(
    *,
    lead_type: str,
    search_keywords: str,
    llm_payload: dict[str, Any],
    fallback: dict[str, Any],
    has_contact: bool,
) -> dict[str, Any]:
    result = dict(fallback)
    result.setdefault("lead_tags", fallback.get("matched_keywords") or [])
    result.setdefault("score_breakdown", fallback.get("score_breakdown") or {})

    quality = fallback.get("data_quality") or "medium"
    risk = int((fallback.get("score_breakdown") or {}).get("risk") or 0)

    llm_result = score_lead_with_llm(
        lead_type=lead_type,
        search_keywords=search_keywords,
        lead=llm_payload,
    )

    llm_meta = {
        "source": "llm",
        "status": "scored" if llm_result.ok else "failed",
        "prompt_version": llm_result.prompt_version or PROMPT_VERSION,
        "model": llm_result.model,
    }

    if llm_result.ok and llm_result.score is not None:
        result["score"] = llm_result.score
        result["score_reason"] = llm_result.reason
        result["next_action"] = _action(llm_result.score, has_contact, quality, risk)
        result["llm_score_status"] = "scored"
        result["llm_score_reason"] = llm_result.reason
        result["llm_score_suggestion"] = llm_result.suggestion
        result["llm_score_error"] = None
    else:
        err = _short_error(llm_result.error)
        result["llm_score_status"] = "failed"
        result["llm_score_reason"] = None
        result["llm_score_suggestion"] = None
        result["llm_score_error"] = err
        base_reason = result.get("score_reason") or "Keyword fallback score retained"
        result["score_reason"] = f"{base_reason}; LLM scoring failed: {err}".strip()
        result["next_action"] = fallback.get("next_action") or _action(int(result.get("score") or 0), has_contact, quality, risk)
        llm_meta["error"] = err

    result["llm_score_model"] = llm_result.model
    result["llm_scored_at"] = datetime.utcnow()
    result["search_keywords"] = search_keywords
    result["score_breakdown"] = {
        "llm": llm_meta,
        "keyword_fallback": fallback.get("score_breakdown") or {},
    }
    final_score = int(result.get("score") or 0)
    tier = _tier(final_score)
    if final_score >= 80 and not has_contact:
        tier = "B"
    result["tier"] = tier
    return result


def _apply_score_metadata(lead: CompanyLead | TalentLead, result: dict[str, Any]) -> None:
    lead.score = result["score"]
    lead.tier = result.get("tier")
    lead.cooperation_type = result.get("cooperation_type")
    lead.lead_tags = _dump_json(result.get("lead_tags") or [])
    lead.score_breakdown = _dump_json(result.get("score_breakdown") or {})
    lead.score_reason = result.get("score_reason")
    lead.data_quality = result.get("data_quality")
    lead.next_action = result.get("next_action")
    lead.search_keywords = result.get("search_keywords") or lead.search_keywords
    lead.llm_score_status = result.get("llm_score_status")
    lead.llm_score_model = result.get("llm_score_model")
    lead.llm_score_reason = result.get("llm_score_reason")
    lead.llm_score_suggestion = result.get("llm_score_suggestion")
    lead.llm_score_error = result.get("llm_score_error")
    lead.llm_scored_at = result.get("llm_scored_at")


def is_search_or_listing_url(url: str | None) -> bool:
    if not url:
        return True
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    query = parsed.query.lower()
    if "we.51job.com" in host and "/pc/search" in path:
        return True
    if "sou.zhaopin.com" in host:
        return True
    if "search" in path and ("keyword" in query or "kw=" in query):
        return True
    return False


def is_detail_url(url: str | None) -> bool:
    if not url or is_search_or_listing_url(url):
        return False
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "jobs.51job.com" in host and _is_51job_detail_path(path):
        return True
    if "zhaopin.com" in host and any(token in path for token in ("company", "jobs", "jobdetail", "position")):
        return True
    if "qzrc.com" in host and any(token in path for token in ("/company/show/", "/job/show/")):
        return True
    return False


def _is_51job_detail_path(path: str) -> bool:
    return "/co" in path or path.endswith(".html")


_MALFORMED_NAME_PATTERNS = (
    "自我评价",
    "工作经历",
    "求职意向",
    "教育经历",
)


def _looks_like_company_name(name: str) -> tuple[bool, str]:
    name = (name or "").strip()
    if not name:
        return False, "empty"
    if len(name) > 80:
        return False, f"too long ({len(name)} chars)"
    if name.count("?") >= max(3, len(name) // 2):
        return False, "mojibake/question-marks"
    for token in _MALFORMED_NAME_PATTERNS:
        if name.startswith(token) or token in name[:10]:
            return False, f"resume-fragment ({token})"
    if "|" in name and ("Tel:" in name or "电话" in name):
        return False, "JD-ad/Tel"
    if name.startswith("[简历") or name.startswith("[求职者"):
        return False, "resume-marker (should go to talents)"
    return True, ""


def _dept(data: dict[str, Any], department_code: str | None) -> str:
    return (
        department_code
        or data.get("department_code")
        or DEFAULT_DEPARTMENT
    )


def ingest_company(db: Session, data: dict[str, Any], department_code: str | None = None) -> CompanyLead:
    platform = data.get("platform", "51job")
    platform_company_id = data.get("platform_company_id") or ""
    company_name = (data.get("company_name") or "").strip()
    ok, reason = _looks_like_company_name(company_name)
    if not ok:
        raise ValueError(f"malformed company_name: {reason}")

    dept = _dept(data, department_code)
    jd_titles = [t for t in [data.get("jd_title")] if t]
    jd_descriptions = [d for d in [data.get("jd_description")] if d]
    has_contact = bool(data.get("contact_email") or data.get("contact_phone") or data.get("hr_wechat"))
    hit, hit_kw = check_excluded(
        company_name,
        data.get("industry") or "",
        data.get("company_description") or "",
        " ".join(jd_titles),
        " ".join(jd_descriptions),
    )

    search_keywords = _extract_search_keywords(data)
    keyword_result = score_company(
        company_name=company_name,
        industry=data.get("industry", ""),
        company_description=data.get("company_description", ""),
        size_range=data.get("size_range", ""),
        city=data.get("city", ""),
        jd_titles=jd_titles,
        jd_descriptions=jd_descriptions,
        has_contact=has_contact,
        risk=-35 if hit else 0,
    )
    result = _merge_llm_score(
        lead_type="company",
        search_keywords=search_keywords,
        llm_payload={
            "platform": platform,
            "company_name": company_name,
            "industry": data.get("industry"),
            "size_range": data.get("size_range"),
            "city": data.get("city"),
            "province": data.get("province"),
            "company_address": data.get("company_address"),
            "company_description": data.get("company_description"),
            "jd_titles": jd_titles,
            "jd_descriptions": jd_descriptions,
            "contact_name": data.get("contact_name"),
            "contact_title": data.get("contact_title"),
            "contact_email": data.get("contact_email"),
            "contact_phone": data.get("contact_phone"),
            "hr_wechat": data.get("hr_wechat"),
            "source_url": data.get("source_url"),
            "raw_data": data.get("raw_data"),
        },
        fallback=keyword_result,
        has_contact=has_contact,
    )

    now = datetime.utcnow()

    lead: CompanyLead | None = None
    if platform_company_id:
        lead = db.query(CompanyLead).filter_by(
            platform=platform, platform_company_id=platform_company_id
        ).first()
    if lead is None:
        lead = db.query(CompanyLead).filter_by(
            platform=platform, company_name=company_name
        ).first()
    if lead is None and (data.get("contact_email") or data.get("contact_phone")):
        clauses = []
        if data.get("contact_email"):
            clauses.append(CompanyLead.contact_email == data.get("contact_email"))
        if data.get("contact_phone"):
            clauses.append(CompanyLead.contact_phone == data.get("contact_phone"))
        lead = db.query(CompanyLead).filter(or_(*clauses)).first() if clauses else None
    source_url = data.get("source_url")
    if lead is None and is_detail_url(source_url):
        obs = db.query(CompanyObservation).filter_by(source_url=data.get("source_url")).first()
        if obs:
            lead = db.query(CompanyLead).filter_by(id=obs.company_lead_id).first()
    if lead is None:
        lead = CompanyLead(
            id=_uid(), platform=platform, platform_company_id=platform_company_id or None,
            department_code=dept, first_seen_at=now,
        )
        db.add(lead)

    existing_name = (lead.company_name or "").strip()
    if existing_name and existing_name != company_name:
        old_ok, _ = _looks_like_company_name(existing_name)
        if old_ok:
            company_name = existing_name
    lead.company_name = company_name
    lead.platform_company_id = platform_company_id or lead.platform_company_id
    lead.industry = data.get("industry") or lead.industry
    lead.size_range = data.get("size_range") or lead.size_range
    lead.city = data.get("city") or lead.city
    lead.province = data.get("province") or lead.province
    lead.company_address = data.get("company_address") or lead.company_address
    lead.company_description = data.get("company_description") or lead.company_description
    lead.contact_name = data.get("contact_name") or lead.contact_name
    lead.contact_title = data.get("contact_title") or lead.contact_title
    lead.contact_email = data.get("contact_email") or lead.contact_email
    lead.contact_phone = data.get("contact_phone") or lead.contact_phone
    lead.hr_wechat = data.get("hr_wechat") or lead.hr_wechat
    lead.source_mode = data.get("source_mode", lead.source_mode or "job_seeker")
    lead.notes = data.get("notes") or lead.notes
    lead.last_seen_at = now

    existing_titles: list[str] = []
    try:
        existing_titles = json.loads(lead.raw_jd_titles or "[]")
    except Exception:
        pass
    for t in jd_titles:
        if t not in existing_titles:
            existing_titles.append(t)
    lead.raw_jd_titles = json.dumps(existing_titles, ensure_ascii=False)
    lead.search_keywords = search_keywords or lead.search_keywords

    lead.us_market_flag = 1 if result["us_market"] else 0
    lead.raw_jd_keywords = json.dumps(result["matched_keywords"], ensure_ascii=False)
    _apply_score_metadata(lead, result)

    if hit:
        lead.excluded = 1
        lead.excluded_reason = f"命中排除词: {hit_kw}"
        lead.tier = None
        lead.next_action = "drop"
        lead.score_reason = f"{lead.score_reason or ''}；命中排除词 {hit_kw}".strip("；")
    else:
        lead.excluded = 0
        lead.excluded_reason = None

    db.flush()

    obs = CompanyObservation(
        id=_uid(),
        company_lead_id=lead.id,
        department_code=dept,
        platform=platform,
        source_url=data.get("source_url"),
        raw_data=json.dumps(data.get("raw_data") or data, ensure_ascii=False, default=str),
        scraped_at=now,
    )
    db.add(obs)
    db.commit()
    db.refresh(lead)
    return lead


def ingest_talent(db: Session, data: dict[str, Any], department_code: str | None = None) -> TalentLead:
    platform = data.get("platform", "qzrc")
    resume_id = data.get("platform_resume_id") or data.get("platform_company_id") or ""
    name_masked = (data.get("name_masked") or data.get("name") or "").strip()
    desired_title = (data.get("desired_title") or data.get("jd_title") or "").strip()
    if not desired_title and not name_masked:
        raise ValueError("desired_title or name_masked is required")

    dept = _dept(data, department_code)
    search_keywords = _extract_search_keywords(data)
    keyword_result = score_talent(data)
    has_contact = bool(data.get("contact_email") or data.get("contact_phone") or data.get("wechat"))
    result = _merge_llm_score(
        lead_type="talent",
        search_keywords=search_keywords,
        llm_payload={
            "platform": platform,
            "name_masked": name_masked,
            "desired_title": desired_title,
            "city": data.get("city"),
            "experience": data.get("experience"),
            "education": data.get("education"),
            "major": data.get("major"),
            "salary_expectation": data.get("salary_expectation"),
            "raw_summary": data.get("raw_summary"),
            "contact_email": data.get("contact_email"),
            "contact_phone": data.get("contact_phone"),
            "wechat": data.get("wechat") or data.get("hr_wechat"),
            "source_url": data.get("source_url"),
            "raw_data": data.get("raw_data"),
        },
        fallback=keyword_result,
        has_contact=has_contact,
    )
    now = datetime.utcnow()

    lead: TalentLead | None = None
    if resume_id:
        lead = db.query(TalentLead).filter_by(platform=platform, platform_resume_id=resume_id).first()
    if lead is None and platform != "zhaopin_resume" and not resume_id and name_masked and desired_title:
        lead = db.query(TalentLead).filter_by(
            platform=platform, name_masked=name_masked, desired_title=desired_title
        ).first()
    if lead is None and (data.get("contact_email") or data.get("contact_phone") or data.get("wechat")):
        clauses = []
        if data.get("contact_email"):
            clauses.append(TalentLead.contact_email == data.get("contact_email"))
        if data.get("contact_phone"):
            clauses.append(TalentLead.contact_phone == data.get("contact_phone"))
        if data.get("wechat"):
            clauses.append(TalentLead.wechat == data.get("wechat"))
        lead = db.query(TalentLead).filter(or_(*clauses)).first() if clauses else None
    if lead is None:
        lead = TalentLead(
            id=_uid(), platform=platform, platform_resume_id=resume_id or None,
            department_code=dept, first_seen_at=now,
        )
        db.add(lead)

    lead.platform_resume_id = resume_id or lead.platform_resume_id
    lead.name_masked = name_masked or lead.name_masked
    lead.desired_title = desired_title or lead.desired_title
    lead.city = data.get("city") or lead.city
    lead.experience = data.get("experience") or lead.experience
    lead.education = data.get("education") or lead.education
    lead.major = data.get("major") or lead.major
    lead.salary_expectation = data.get("salary_expectation") or lead.salary_expectation
    lead.source_url = data.get("source_url") or lead.source_url
    lead.resume_download_url = data.get("resume_download_url") or lead.resume_download_url
    lead.raw_summary = data.get("raw_summary") or lead.raw_summary
    lead.contact_email = data.get("contact_email") or lead.contact_email
    lead.contact_phone = data.get("contact_phone") or lead.contact_phone
    lead.wechat = data.get("wechat") or data.get("hr_wechat") or lead.wechat
    lead.source_type = data.get("source_type") or lead.source_type
    lead.consent_status = data.get("consent_status") or lead.consent_status
    lead.permission_note = data.get("permission_note") or lead.permission_note
    lead.status = data.get("status") or lead.status
    lead.notes = data.get("notes") or lead.notes
    lead.search_keywords = search_keywords or lead.search_keywords
    lead.raw_data = json.dumps(data.get("raw_data") or data, ensure_ascii=False, default=str)
    _apply_score_metadata(lead, result)
    lead.last_seen_at = now

    db.commit()
    db.refresh(lead)
    return lead
