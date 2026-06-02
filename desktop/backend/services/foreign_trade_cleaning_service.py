"""Foreign-trade lead cleaning and backfill helpers.

The normal ingest path already cleans new extension uploads. This service gives
the portal a safe way to re-run deterministic cleaning over existing database
rows: normalize text fields, refresh keyword scores, extract social contacts,
and mark raw social snapshots as cleaned once replayed.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from ..models.company_lead import CompanyLead
from ..models.social_lead import (
    XhsAiJudgment,
    XhsComment,
    XhsExtractedContact,
    XhsNoteMedia,
    XhsNote,
    XhsRawSnapshot,
    XhsUser,
    XhsUserHistoryPost,
    XhsUserSource,
)
from ..models.talent_lead import TalentLead
from ..services.departments import department_where
from ..services.xhs_lead_service import PROMPT_VERSION, ingest_snapshot, judge_users_with_gpt
from ..utils.job_exclusion import check_excluded
from ..utils.job_keyword_rules import score_company, score_talent_profile
from ..utils.xhs_cleaning import (
    canonical_url,
    clean_text,
    extract_contacts,
    extract_douyin_user_id,
    extract_xhs_user_id,
    platform_prefixed_id,
    parse_count_text,
    stable_hash,
)


def get_cleaning_status(db: Session, department_code: str | None = None) -> dict[str, Any]:
    company_total = _count(db, CompanyLead, department_code)
    talent_total = _count(db, TalentLead, department_code)
    social_total = _count(db, XhsUser, department_code)
    raw_total = _count(db, XhsRawSnapshot, department_code)
    raw_queued = _count(
        db,
        XhsRawSnapshot,
        department_code,
        or_(XhsRawSnapshot.clean_status.is_(None), XhsRawSnapshot.clean_status != "cleaned"),
    )
    contacts_total = _count(db, XhsExtractedContact, department_code)
    judgments_total = _count(db, XhsAiJudgment, department_code, XhsAiJudgment.prompt_version == PROMPT_VERSION)
    social_with_contact = _count(db, XhsUser, department_code, XhsUser.has_contact == 1)
    social_cleaned = _count(db, XhsUser, department_code, XhsUser.clean_status == "cleaned")
    company_scored = _count(db, CompanyLead, department_code, CompanyLead.score > 0)
    talent_scored = _count(db, TalentLead, department_code, TalentLead.score > 0)
    unjudged_with_contact = _unjudged_social_count(db, department_code)

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"type": "department" if department_code else "company", "department_code": department_code},
        "summary": {
            "company_total": company_total,
            "talent_total": talent_total,
            "social_total": social_total,
            "raw_snapshots": raw_total,
            "contacts_total": contacts_total,
            "judgments_total": judgments_total,
            "ready_total": company_scored + talent_scored + social_cleaned,
            "needs_cleaning": (company_total - company_scored) + (talent_total - talent_scored) + raw_queued,
            "unjudged_with_contact": unjudged_with_contact,
            "openai_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        },
        "channels": [
            {
                "key": "company",
                "name": "公司客户线索",
                "total": company_total,
                "cleaned": company_scored,
                "pending": max(company_total - company_scored, 0),
            },
            {
                "key": "talent",
                "name": "跨境人才线索",
                "total": talent_total,
                "cleaned": talent_scored,
                "pending": max(talent_total - talent_scored, 0),
            },
            {
                "key": "social",
                "name": "社媒线索",
                "total": social_total,
                "cleaned": social_cleaned,
                "pending": max(social_total - social_cleaned, 0) + raw_queued,
                "with_contact": social_with_contact,
                "unjudged_with_contact": unjudged_with_contact,
            },
        ],
        "raw": {
            "total": raw_total,
            "queued": raw_queued,
        },
    }


def run_cleaning(
    db: Session,
    department_code: str | None = None,
    *,
    include_gpt: bool = False,
    force_gpt: bool = False,
    gpt_limit: int | None = None,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    company = _clean_company_leads(db, department_code)
    talent = _clean_talent_leads(db, department_code)
    social = _clean_social_leads(db, department_code)
    db.commit()

    gpt: dict[str, Any] = {"enabled": False, "judged": 0}
    if include_gpt:
        limit = gpt_limit or max(_unjudged_social_count(db, department_code), 1)
        gpt = {"enabled": True, **judge_users_with_gpt(db, department_code=department_code, limit=limit, force=force_gpt)}

    finished_at = datetime.now(timezone.utc)
    return {
        "ok": True,
        "run_id": uuid.uuid4().hex,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
        "include_gpt": include_gpt,
        "company": company,
        "talent": talent,
        "social": social,
        "gpt": gpt,
        "status": get_cleaning_status(db, department_code),
    }


def _clean_company_leads(db: Session, department_code: str | None) -> dict[str, int]:
    processed = rescored = excluded = 0
    for lead in db.scalars(_scoped(select(CompanyLead), CompanyLead, department_code)).all():
        processed += 1
        _clean_attrs(
            lead,
            [
                "company_name",
                "industry",
                "size_range",
                "city",
                "province",
                "company_address",
                "company_description",
                "contact_name",
                "contact_title",
                "contact_email",
                "contact_phone",
                "hr_wechat",
                "search_keywords",
                "status",
                "notes",
            ],
        )
        jd_titles = _json_list(lead.raw_jd_titles)
        has_contact = bool(lead.contact_email or lead.contact_phone or lead.hr_wechat)
        hit, hit_kw = check_excluded(
            lead.company_name or "",
            lead.industry or "",
            lead.company_description or "",
            " ".join(jd_titles),
            "",
        )
        result = score_company(
            company_name=lead.company_name or "",
            industry=lead.industry or "",
            company_description=lead.company_description or "",
            size_range=lead.size_range or "",
            city=lead.city or "",
            jd_titles=jd_titles,
            jd_descriptions=[],
            has_contact=has_contact,
            risk=-35 if hit else 0,
        )
        lead.us_market_flag = 1 if result.get("us_market") else 0
        lead.raw_jd_keywords = _dump_json(result.get("matched_keywords") or [])
        _apply_deterministic_score(lead, result)
        if hit:
            lead.excluded = 1
            lead.excluded_reason = f"命中排除词: {hit_kw}"
            lead.tier = None
            lead.next_action = "drop"
            excluded += 1
        else:
            lead.excluded = 0
            lead.excluded_reason = None
        rescored += 1
    return {"processed": processed, "rescored": rescored, "excluded": excluded}


def _clean_talent_leads(db: Session, department_code: str | None) -> dict[str, int]:
    processed = rescored = 0
    for lead in db.scalars(_scoped(select(TalentLead), TalentLead, department_code)).all():
        processed += 1
        _clean_attrs(
            lead,
            [
                "name_masked",
                "desired_title",
                "city",
                "experience",
                "education",
                "major",
                "salary_expectation",
                "raw_summary",
                "contact_email",
                "contact_phone",
                "wechat",
                "search_keywords",
                "status",
                "notes",
            ],
        )
        data = {
            "name_masked": lead.name_masked,
            "desired_title": lead.desired_title,
            "city": lead.city,
            "experience": lead.experience,
            "education": lead.education,
            "major": lead.major,
            "salary_expectation": lead.salary_expectation,
            "raw_summary": lead.raw_summary,
            "contact_email": lead.contact_email,
            "contact_phone": lead.contact_phone,
            "wechat": lead.wechat,
            "notes": lead.notes,
        }
        _apply_deterministic_score(lead, score_talent_profile(data))
        rescored += 1
    return {"processed": processed, "rescored": rescored}


def _clean_social_leads(db: Session, department_code: str | None) -> dict[str, int]:
    replayed = replay_errors = 0
    for snapshot in db.scalars(
        _scoped(
            select(XhsRawSnapshot).where(
                or_(XhsRawSnapshot.clean_status.is_(None), XhsRawSnapshot.clean_status != "cleaned")
            ),
            XhsRawSnapshot,
            department_code,
        )
    ).all():
        if not snapshot.payload:
            snapshot.clean_status = "cleaned"
            continue
        try:
            payload = json.loads(snapshot.payload)
            if isinstance(payload, dict):
                ingest_snapshot(db, payload, platform=snapshot.platform, department_code=snapshot.department_code)
                replayed += 1
            snapshot.clean_status = "cleaned"
        except Exception as exc:  # noqa: BLE001 - keep the rest of the backfill moving
            snapshot.clean_status = "error"
            snapshot.external_id = (snapshot.external_id or "")[:160] or f"cleaning_error:{type(exc).__name__}"
            replay_errors += 1

    users = db.scalars(_scoped(select(XhsUser), XhsUser, department_code)).all()
    notes = db.scalars(_scoped(select(XhsNote), XhsNote, department_code)).all()
    comments = db.scalars(_scoped(select(XhsComment), XhsComment, department_code)).all()

    contacts_added = 0
    media_added = 0
    history_added = 0
    sources_added = 0
    for user in users:
        _clean_attrs(user, ["xhs_user_id", "username_clean", "account_clean", "bio_clean", "location_text"])
        profile_url = canonical_url(getattr(user, "canonical_profile_url", None) or getattr(user, "profile_url", None))
        if profile_url:
            user.canonical_profile_url = profile_url
        if not user.external_user_id:
            user.external_user_id = (
                extract_douyin_user_id(profile_url) if user.platform == "douyin" else extract_xhs_user_id(profile_url)
            )
        if not user.xhs_user_id:
            user.xhs_user_id = platform_prefixed_id(user.platform or "xhs", user.external_user_id or user.account_clean)
        if not user.follower_count and getattr(user, "followers_count", None):
            user.follower_count = user.followers_count
        user.clean_status = "cleaned"
        contacts_added += _add_platform_contact(db, dept=user.department_code, user=user)
        contacts_added += _add_contacts(
            db,
            dept=user.department_code,
            owner_type="user",
            owner_id=user.id,
            user_id=user.id,
            texts=[user.bio_clean, user.username_clean, user.account_clean],
        )
        history_added += _add_history_posts_from_user(db, user)

    for note in notes:
        _clean_attrs(note, ["xhs_note_id", "title_clean", "desc_clean", "publish_location"])
        note_raw = _json_object(getattr(note, "raw_json", None))
        note.canonical_note_url = canonical_url(note.canonical_note_url or getattr(note, "url", None) or note_raw.get("url") or note_raw.get("post_url")) or note.canonical_note_url
        note.search_result_url = canonical_url(getattr(note, "search_result_url", None) or note_raw.get("search_result_url")) or getattr(note, "search_result_url", None)
        note.cover_url = clean_text(getattr(note, "cover_url", None) or note_raw.get("cover_url")) or getattr(note, "cover_url", None)
        note.keyword = clean_text(getattr(note, "keyword", None) or note_raw.get("keyword")) or getattr(note, "keyword", None)
        user_id = note.author_user_id
        media_added += _add_note_media_from_row(db, note)
        if user_id:
            sources_added += _add_user_source(
                db,
                dept=note.department_code,
                platform=note.platform,
                user_id=user_id,
                note_id=note.id,
                comment_id=None,
                source_type="post_author",
                keyword=getattr(note, "keyword", None),
                evidence_text=note.title_clean or note.desc_clean,
                evidence_url=note.canonical_note_url,
                payload=_json_object(getattr(note, "raw_json", None)),
            )
        contacts_added += _add_contacts(
            db,
            dept=note.department_code,
            owner_type="note",
            owner_id=note.id,
            user_id=user_id,
            texts=[note.title_clean, note.desc_clean],
        )

    for comment in comments:
        _clean_attrs(comment, ["xhs_comment_id", "content_clean", "location_text"])
        comment_raw = _json_object(getattr(comment, "raw_json", None))
        comment.note_url = canonical_url(getattr(comment, "note_url", None) or comment_raw.get("note_url") or comment_raw.get("post_url")) or getattr(comment, "note_url", None)
        comment.keyword = clean_text(getattr(comment, "keyword", None) or comment_raw.get("keyword")) or getattr(comment, "keyword", None)
        comment.published_at_text = clean_text(getattr(comment, "published_at_text", None) or comment_raw.get("published_at_text")) or getattr(comment, "published_at_text", None)
        comment.location_text = clean_text(comment.location_text or getattr(comment, "location", None) or comment_raw.get("location")) or comment.location_text
        comment.like_count_text = clean_text(getattr(comment, "like_count_text", None) or comment_raw.get("like_count_text")) or getattr(comment, "like_count_text", None)
        if comment.user_id:
            sources_added += _add_user_source(
                db,
                dept=comment.department_code,
                platform=comment.platform,
                user_id=comment.user_id,
                note_id=comment.note_id,
                comment_id=comment.id,
                source_type="reply_author" if int(comment.depth or 0) > 0 else "comment_author",
                keyword=getattr(comment, "keyword", None),
                evidence_text=comment.content_clean,
                evidence_url=getattr(comment, "note_url", None),
                comment_depth=int(comment.depth or 0),
                payload=_json_object(getattr(comment, "raw_json", None)),
            )
        contacts_added += _add_contacts(
            db,
            dept=comment.department_code,
            owner_type="comment",
            owner_id=comment.id,
            user_id=comment.user_id,
            texts=[comment.content_clean],
        )

    db.flush()
    users_with_contact = 0
    for user in users:
        has_contact = bool(
            db.scalar(
                select(func.count())
                .select_from(XhsExtractedContact)
                .where(XhsExtractedContact.user_id == user.id)
            )
        )
        user.has_contact = 1 if has_contact else 0
        if has_contact:
            users_with_contact += 1

    return {
        "raw_replayed": replayed,
        "raw_errors": replay_errors,
        "users": len(users),
        "notes": len(notes),
        "comments": len(comments),
        "contacts_added": contacts_added,
        "users_with_contact": users_with_contact,
        "media_added": media_added,
        "history_added": history_added,
        "sources_added": sources_added,
    }


def _add_platform_contact(db: Session, *, dept: str, user: XhsUser) -> int:
    raw = clean_text(user.account_clean or user.xhs_user_id or user.username_clean)
    norm = clean_text(user.account_clean or user.xhs_user_id or user.external_user_id)
    if not raw or not norm:
        return 0
    contact_type = "douyin_handle" if (user.platform or "").lower() == "douyin" else "xhs_handle"
    exists = db.scalar(
        select(XhsExtractedContact).where(
            XhsExtractedContact.owner_type == "user",
            XhsExtractedContact.owner_id == user.id,
            XhsExtractedContact.contact_type.in_((contact_type, "platform_handle")),
            XhsExtractedContact.value_norm == norm.lower(),
        )
    )
    if exists:
        exists.contact_type = contact_type
        exists.rule_code = f"{user.platform or 'xhs'}_account"
        user.has_contact = 1
        return 0
    db.add(
        XhsExtractedContact(
            id=uuid.uuid4().hex,
            department_code=dept,
            owner_type="user",
            owner_id=user.id,
            user_id=user.id,
            contact_type=contact_type,
            value_raw=raw,
            value_norm=norm.lower(),
            source_field="account_clean" if user.account_clean else "xhs_user_id",
            rule_code=f"{user.platform or 'xhs'}_account",
        )
    )
    user.has_contact = 1
    return 1


def _add_note_media_from_row(db: Session, note: XhsNote) -> int:
    raw = _json_object(getattr(note, "raw_json", None))
    urls: list[tuple[str, str]] = []
    cover = clean_text(getattr(note, "cover_url", None) or raw.get("cover_url"))
    if cover:
        urls.append(("cover", cover))
    for value in _json_list(getattr(note, "images_json", None)) or _json_list(raw.get("image_urls")):
        url = clean_text(value)
        if url:
            urls.append(("image", url))
    added = 0
    seen: set[str] = set()
    for position, (media_type, url) in enumerate(urls):
        if url in seen:
            continue
        seen.add(url)
        exists = db.scalar(select(XhsNoteMedia.id).where(XhsNoteMedia.note_id == note.id, XhsNoteMedia.url == url))
        if exists:
            continue
        db.add(
            XhsNoteMedia(
                id=uuid.uuid4().hex,
                department_code=note.department_code,
                note_id=note.id,
                media_type=media_type,
                url=url,
                normalized_url=canonical_url(url),
                position=position,
            )
        )
        added += 1
    return added


def _add_history_posts_from_user(db: Session, user: XhsUser) -> int:
    posts = _json_list_any(getattr(user, "history_posts_json", None))
    if not posts:
        raw = _json_object(getattr(user, "raw_json", None))
        posts = _json_list_any(raw.get("history_posts"))
    added = 0
    for position, post in enumerate(posts):
        if not isinstance(post, dict):
            continue
        url = canonical_url(post.get("url") or post.get("post_url"))
        note_id = clean_text(post.get("note_id") or post.get("post_id"))
        xhs_note_id = platform_prefixed_id(user.platform or "xhs", note_id or url)
        if not xhs_note_id and not url:
            continue
        exists = db.scalar(
            select(XhsUserHistoryPost.id).where(
                XhsUserHistoryPost.user_id == user.id,
                XhsUserHistoryPost.xhs_note_id == xhs_note_id,
            )
        ) if xhs_note_id else None
        if exists:
            continue
        db.add(
            XhsUserHistoryPost(
                id=uuid.uuid4().hex,
                department_code=user.department_code,
                platform=user.platform or "xhs",
                user_id=user.id,
                xhs_note_id=xhs_note_id,
                canonical_note_url=url,
                title_raw=clean_text(post.get("title")),
                title_clean=clean_text(post.get("title")),
                cover_url=clean_text(post.get("cover_url")),
                like_count_text=clean_text(post.get("like_count_text")),
                like_count=parse_count_text(post.get("like_count") or post.get("like_count_text")),
                published_at_text=clean_text(post.get("published_at_text")),
                position=position,
            )
        )
        added += 1
    return added


def _add_user_source(
    db: Session,
    *,
    dept: str,
    platform: str,
    user_id: str,
    note_id: str | None,
    comment_id: str | None,
    source_type: str,
    keyword: str | None,
    evidence_text: Any,
    evidence_url: Any,
    payload: dict[str, Any] | None = None,
    comment_depth: int | None = None,
) -> int:
    record = {
        "user_id": user_id,
        "note_id": note_id,
        "comment_id": comment_id,
        "source_type": source_type,
        "keyword": keyword,
        "evidence_text": clean_text(evidence_text),
        "evidence_url": canonical_url(evidence_url),
    }
    digest = stable_hash(record)
    existing_row = None
    if comment_id:
        existing_row = db.scalar(
            select(XhsUserSource).where(
                XhsUserSource.user_id == user_id,
                XhsUserSource.comment_id == comment_id,
                XhsUserSource.source_type == source_type,
            )
        )
    elif note_id:
        existing_row = db.scalar(
            select(XhsUserSource).where(
                XhsUserSource.user_id == user_id,
                XhsUserSource.note_id == note_id,
                XhsUserSource.source_type == source_type,
            )
        )
    if existing_row is not None:
        existing_row.keyword = keyword or existing_row.keyword
        existing_row.evidence_text = record["evidence_text"] or existing_row.evidence_text
        existing_row.evidence_url = record["evidence_url"] or existing_row.evidence_url
        existing_row.source_payload = _dump_json(payload or {})
        return 0
    exists = db.scalar(select(XhsUserSource.id).where(XhsUserSource.source_hash == digest))
    if exists:
        return 0
    db.add(
        XhsUserSource(
            id=uuid.uuid4().hex,
            department_code=dept,
            platform=platform or "xhs",
            user_id=user_id,
            note_id=note_id,
            comment_id=comment_id,
            source_type=source_type,
            keyword=keyword,
            evidence_text=record["evidence_text"],
            evidence_url=record["evidence_url"],
            evidence_images="[]",
            comment_depth=comment_depth,
            source_payload=_dump_json(payload or {}),
            source_hash=digest,
        )
    )
    return 1


def _add_contacts(
    db: Session,
    *,
    dept: str,
    owner_type: str,
    owner_id: str,
    user_id: str | None,
    texts: list[Any],
) -> int:
    added = 0
    for contact in extract_contacts(texts):
        exists = db.scalar(
            select(XhsExtractedContact.id).where(
                XhsExtractedContact.owner_type == owner_type,
                XhsExtractedContact.owner_id == owner_id,
                XhsExtractedContact.contact_type == contact["contact_type"],
                XhsExtractedContact.value_norm == contact["value_norm"],
            )
        )
        if exists:
            continue
        db.add(
            XhsExtractedContact(
                id=uuid.uuid4().hex,
                department_code=dept,
                owner_type=owner_type,
                owner_id=owner_id,
                user_id=user_id,
                contact_type=contact["contact_type"],
                value_raw=contact["value_raw"],
                value_norm=contact["value_norm"],
                source_field="cleaning_backfill",
                rule_code=contact["rule_code"],
            )
        )
        added += 1
    return added


def _unjudged_social_count(db: Session, department_code: str | None) -> int:
    candidates = _scoped(
        select(func.count()).select_from(XhsUser).where(XhsUser.has_contact == 1),
        XhsUser,
        department_code,
    )
    judged = select(func.count(distinct(XhsAiJudgment.user_id))).where(
        XhsAiJudgment.prompt_version == PROMPT_VERSION
    )
    judged = _scoped(judged, XhsAiJudgment, department_code)
    return max(int(db.scalar(candidates) or 0) - int(db.scalar(judged) or 0), 0)


def _count(db: Session, model, department_code: str | None, *conditions) -> int:
    stmt = _scoped(select(func.count()).select_from(model), model, department_code)
    for cond in conditions:
        stmt = stmt.where(cond)
    return int(db.scalar(stmt) or 0)


def _scoped(stmt, model, department_code: str | None):
    where = department_where(model, department_code)
    return stmt.where(where) if where is not None else stmt


def _clean_attrs(row: Any, attrs: list[str]) -> None:
    for attr in attrs:
        value = getattr(row, attr, None)
        cleaned = clean_text(value)
        if cleaned is not None:
            setattr(row, attr, cleaned)


def _apply_deterministic_score(lead: Any, result: dict[str, Any]) -> None:
    lead.score = int(result.get("score") or 0)
    lead.tier = result.get("tier")
    lead.cooperation_type = result.get("cooperation_type")
    lead.lead_tags = _dump_json(result.get("lead_tags") or result.get("matched_keywords") or [])
    lead.score_breakdown = _dump_json({"source": "cleaning_backfill", "keyword": result.get("score_breakdown") or {}})
    lead.score_reason = result.get("score_reason")
    lead.data_quality = result.get("data_quality")
    lead.next_action = result.get("next_action")


def _json_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    try:
        parsed = json.loads(str(value))
    except Exception:
        return [str(value)]
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item or "").strip()]
    return [str(parsed)]


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list_any(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
