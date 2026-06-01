"""Xiaohongshu / Douyin social-lead ingest + GPT purchase-intent judge (Phase 3).

Ports the standalone xhs_cleaning pipeline into the X9 desktop backend: accepts
the browser extension's collection snapshot, cleans + dedups + extracts contacts,
and writes into the x9db `xhs_*` tables (SQLAlchemy models) with a
`department_code`. The GPT judge (prompt_version xhs-b2b-us-dropship-fit-v5)
classifies users as US dropship/sourcing customers; it no-ops without
`OPENAI_API_KEY` so ingest never depends on it.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.social_lead import (
    XhsAiJudgment,
    XhsCollectionRun,
    XhsComment,
    XhsExtractedContact,
    XhsNote,
    XhsRawSnapshot,
    XhsUser,
)
from ..services.departments import DEFAULT_DEPARTMENT
from ..utils.xhs_cleaning import clean_text, extract_contacts, parse_count_text

PROMPT_VERSION = "xhs-b2b-us-dropship-fit-v5"


def _uid() -> str:
    return uuid.uuid4().hex


def _parse_dt(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.replace("Z", "+00:00") if text.endswith("Z") else text
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.fromisoformat(text) if fmt is None else datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _dept(payload: dict[str, Any], department_code: str | None) -> str:
    return department_code or payload.get("department_code") or DEFAULT_DEPARTMENT


def _external_user_id(raw: dict[str, Any]) -> str | None:
    return clean_text(raw.get("xhs_user_id") or raw.get("account") or raw.get("external_user_id"))


def _upsert_user(db: Session, cache: dict[str, XhsUser], *, platform: str, dept: str, raw: dict[str, Any], now: datetime) -> XhsUser | None:
    if not isinstance(raw, dict):
        return None
    ext = _external_user_id(raw)
    profile_url = clean_text(raw.get("profile_url") or raw.get("canonical_profile_url"))
    if not ext and not profile_url:
        return None
    cache_key = ext or profile_url or ""
    user = cache.get(cache_key)
    if user is None and ext:
        user = db.scalar(select(XhsUser).where(XhsUser.platform == platform, XhsUser.external_user_id == ext))
    if user is None:
        user = XhsUser(id=_uid(), platform=platform, department_code=dept, external_user_id=ext, first_seen_at=now)
        db.add(user)
    # update fields (new value wins, keep old otherwise)
    user.xhs_user_id = clean_text(raw.get("xhs_user_id") or raw.get("account")) or user.xhs_user_id
    user.username_clean = clean_text(raw.get("username") or raw.get("nickname")) or user.username_clean
    user.account_clean = clean_text(raw.get("account")) or user.account_clean
    user.canonical_profile_url = profile_url or user.canonical_profile_url
    user.avatar_url = clean_text(raw.get("avatar_url") or raw.get("avatar")) or user.avatar_url
    bio = clean_text(raw.get("bio") or raw.get("desc") or raw.get("signature"))
    user.bio_clean = bio or user.bio_clean
    user.location_text = clean_text(raw.get("location") or raw.get("location_text") or raw.get("ip_location")) or user.location_text
    fc = parse_count_text(raw.get("follower_count") or raw.get("follower_count_text") or raw.get("fans") or raw.get("fans_count"))
    if fc is not None:
        user.follower_count = fc
    user.last_seen_at = now
    db.flush()
    cache[cache_key] = user
    if ext:
        cache[ext] = user
    if profile_url:
        cache[profile_url] = user
    return user


def _add_contacts(db: Session, *, dept: str, owner_type: str, owner_id: str, user: XhsUser | None, texts: list[Any]) -> int:
    contacts = extract_contacts(texts)
    if not contacts:
        return 0
    added = 0
    for c in contacts:
        exists = db.scalar(
            select(XhsExtractedContact.id).where(
                XhsExtractedContact.owner_type == owner_type,
                XhsExtractedContact.owner_id == owner_id,
                XhsExtractedContact.contact_type == c["contact_type"],
                XhsExtractedContact.value_norm == c["value_norm"],
            )
        )
        if exists:
            continue
        db.add(XhsExtractedContact(
            id=_uid(), department_code=dept, owner_type=owner_type, owner_id=owner_id,
            user_id=user.id if user else None,
            contact_type=c["contact_type"], value_raw=c["value_raw"], value_norm=c["value_norm"],
            source_field=owner_type, rule_code=c["rule_code"],
        ))
        added += 1
    if added and user is not None:
        user.has_contact = 1
    return added


def ingest_snapshot(db: Session, payload: dict[str, Any], *, platform: str | None = None, department_code: str | None = None) -> dict[str, Any]:
    platform = (payload.get("platform") or platform or "xhs").strip().lower()
    dept = _dept(payload, department_code)
    now = datetime.utcnow()

    # collection run (upsert by run_key)
    run_key = clean_text(payload.get("run_id"))
    run = None
    if run_key:
        run = db.scalar(select(XhsCollectionRun).where(XhsCollectionRun.run_key == run_key))
    if run is None:
        run = XhsCollectionRun(id=_uid(), department_code=dept, platform=platform, run_key=run_key)
        db.add(run)
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    run.keyword = clean_text(settings.get("keyword")) or run.keyword
    run.source_page_url = clean_text(payload.get("source_page_url")) or run.source_page_url
    run.plugin_version = clean_text(payload.get("plugin_version")) or run.plugin_version
    run.collector_version = clean_text(payload.get("collector_version")) or run.collector_version
    run.status = clean_text(payload.get("status")) or "done"
    run.started_at = _parse_dt(payload.get("started_at")) or run.started_at
    run.finished_at = _parse_dt(payload.get("finished_at")) or run.finished_at
    db.flush()

    # raw snapshot audit
    try:
        raw_json = json.dumps(payload, ensure_ascii=False, default=str)
        db.add(XhsRawSnapshot(
            id=_uid(), department_code=dept, platform=platform, run_id=run.id,
            snapshot_type="search", payload=raw_json, clean_status="cleaned", observed_at=now,
        ))
    except Exception:  # noqa: BLE001 - audit row must never block ingest
        pass

    user_cache: dict[str, XhsUser] = {}
    note_cache: dict[str, XhsNote] = {}
    counts = {"notes": 0, "comments": 0, "users": 0, "contacts": 0}

    # top-level user profiles (rich: bio, followers)
    for raw in payload.get("users") or []:
        u = _upsert_user(db, user_cache, platform=platform, dept=dept, raw=raw, now=now)
        if u is not None:
            counts["users"] += 1
            counts["contacts"] += _add_contacts(
                db, dept=dept, owner_type="user", owner_id=u.id, user=u,
                texts=[u.bio_clean, u.username_clean, raw.get("signature")],
            )

    # notes / posts
    notes = payload.get("notes") or payload.get("posts") or []
    for raw in notes:
        if not isinstance(raw, dict):
            continue
        ext_post = clean_text(raw.get("xhs_note_id") or raw.get("aweme_id") or raw.get("note_id") or raw.get("external_post_id"))
        author = _upsert_user(db, user_cache, platform=platform, dept=dept, raw=raw.get("author") or {}, now=now)
        note = None
        if ext_post:
            note = db.scalar(select(XhsNote).where(XhsNote.platform == platform, XhsNote.external_post_id == ext_post))
        if note is None:
            note = XhsNote(id=_uid(), platform=platform, department_code=dept, external_post_id=ext_post, first_seen_at=now)
            db.add(note)
        note.xhs_note_id = clean_text(raw.get("xhs_note_id") or raw.get("aweme_id")) or note.xhs_note_id
        note.content_type = "video" if (raw.get("aweme_id") or platform == "douyin") else "note"
        note.canonical_note_url = clean_text(raw.get("url") or raw.get("canonical_note_url")) or note.canonical_note_url
        note.title_clean = clean_text(raw.get("title")) or note.title_clean
        note.desc_clean = clean_text(raw.get("desc")) or note.desc_clean
        note.published_at = _parse_dt(raw.get("published_at")) or note.published_at
        note.publish_location = clean_text(raw.get("publish_location") or raw.get("location")) or note.publish_location
        note.like_count = parse_count_text(raw.get("like_count") or raw.get("digg_count")) if (raw.get("like_count") or raw.get("digg_count")) is not None else note.like_count
        note.collect_count = parse_count_text(raw.get("collect_count")) if raw.get("collect_count") is not None else note.collect_count
        note.comment_count = parse_count_text(raw.get("comment_count")) if raw.get("comment_count") is not None else note.comment_count
        note.author_user_id = author.id if author else note.author_user_id
        note.raw_json = json.dumps(raw, ensure_ascii=False, default=str)
        db.flush()
        counts["notes"] += 1
        if ext_post:
            note_cache[ext_post] = note

    # comments (+ commenter users + contacts from comment text)
    for raw in payload.get("comments") or []:
        if not isinstance(raw, dict):
            continue
        ext_comment = clean_text(raw.get("xhs_comment_id") or raw.get("external_comment_id") or raw.get("comment_id"))
        commenter = _upsert_user(db, user_cache, platform=platform, dept=dept, raw=raw.get("user") or {}, now=now)
        note = note_cache.get(clean_text(raw.get("note_id")) or "")
        comment = None
        if ext_comment:
            comment = db.scalar(select(XhsComment).where(XhsComment.platform == platform, XhsComment.external_comment_id == ext_comment))
        if comment is None:
            comment = XhsComment(id=_uid(), platform=platform, department_code=dept, external_comment_id=ext_comment, first_seen_at=now)
            db.add(comment)
        comment.xhs_comment_id = clean_text(raw.get("xhs_comment_id")) or comment.xhs_comment_id
        comment.note_id = note.id if note else comment.note_id
        comment.user_id = commenter.id if commenter else comment.user_id
        comment.content_clean = clean_text(raw.get("content")) or comment.content_clean
        comment.published_at = _parse_dt(raw.get("published_at")) or comment.published_at
        comment.location_text = clean_text(raw.get("location")) or comment.location_text
        comment.like_count = parse_count_text(raw.get("like_count")) if raw.get("like_count") is not None else comment.like_count
        comment.raw_json = json.dumps(raw, ensure_ascii=False, default=str)
        db.flush()
        counts["comments"] += 1
        # contacts live mostly in comment text ("微信 xxx" / "vx: yyy")
        counts["contacts"] += _add_contacts(
            db, dept=dept, owner_type="comment", owner_id=comment.id, user=commenter,
            texts=[comment.content_clean],
        )

    db.commit()
    return {"ok": True, "platform": platform, "run_id": run.id, "counts": counts}


# ---------------- GPT purchase-intent judge ----------------

def _openai_cfg() -> dict[str, str] | None:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return None
    return {
        "key": key,
        "base": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/"),
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
    }


_JUDGE_SYSTEM = (
    "你是跨境电商 B2B 选品/供应链 BD 助手。我们要找的是【有美区一件代发 / 跨境采购需求】的人："
    "跨境电商卖家（亚马逊 / TikTok Shop / Temu / Shopify / 独立站，尤其美区）、明确有货源采购/供应链/一件代发需求、"
    "在小红书/抖音主动找货源或做美区电商的人。降分/排除：纯消费者、平台官方/大牌旗舰店、同行供应商、"
    "纯内容创作者/网红、招聘/求职/培训/中介。\n"
    "只返回 JSON，字段：fit_score(0-100)、fit_level(high/medium/low)、decision(target_customer/potential/irrelevant)、"
    "intent_type(sourcing/dropship/cross_border_ecom/consumer/peer_supplier/other)、evidence、suggestion。"
    "evidence 与 suggestion 用简体中文。档位：80-100 high=明确美区跨境卖家且明确找货源/代发；60-79 medium=有背景或意向但信息不全；"
    "40-59 low=有一点相关性需确认；0-39 irrelevant=消费者/同行/无关。"
)


def _judge_one(cfg: dict[str, str], user: XhsUser, texts: list[str]) -> dict[str, Any] | None:
    payload = {
        "model": cfg["model"],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": json.dumps({
                "prompt_version": PROMPT_VERSION,
                "username": user.username_clean,
                "bio": user.bio_clean,
                "follower_count": user.follower_count,
                "location": user.location_text,
                "evidence_texts": [t for t in texts if t][:20],
            }, ensure_ascii=False)},
        ],
    }
    with httpx.Client(timeout=float(os.getenv("OPENAI_TIMEOUT", "30"))) as client:
        resp = client.post(
            f"{cfg['base']}/chat/completions",
            headers={"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    parsed = json.loads(content)
    return {"parsed": parsed, "raw": content}


def judge_users_with_gpt(db: Session, *, department_code: str | None = None, limit: int = 10, force: bool = False) -> dict[str, Any]:
    cfg = _openai_cfg()
    if cfg is None:
        return {"ok": False, "error": "OPENAI_API_KEY not configured", "judged": 0}

    stmt = select(XhsUser).where(XhsUser.has_contact == 1)
    if department_code:
        stmt = stmt.where(XhsUser.department_code == department_code)
    candidates = list(db.scalars(stmt.order_by(XhsUser.created_at.desc()).limit(limit * 3)).all())

    judged = 0
    for user in candidates:
        if judged >= limit:
            break
        if not force:
            existing = db.scalar(select(XhsAiJudgment.id).where(XhsAiJudgment.user_id == user.id, XhsAiJudgment.prompt_version == PROMPT_VERSION))
            if existing:
                continue
        comment_texts = [
            row for row in db.scalars(
                select(XhsComment.content_clean).where(XhsComment.user_id == user.id).limit(20)
            ).all() if row
        ]
        try:
            result = _judge_one(cfg, user, [user.bio_clean or "", *comment_texts])
        except Exception as exc:  # noqa: BLE001
            db.add(XhsAiJudgment(
                id=_uid(), department_code=user.department_code, platform=user.platform, user_id=user.id,
                model=cfg["model"], prompt_version=PROMPT_VERSION, decision="error",
                judgment=None, raw_response=str(exc)[:1000],
            ))
            db.commit()
            continue
        p = result["parsed"] if result else {}
        try:
            fit_score = int(round(float(p.get("fit_score")))) if p.get("fit_score") is not None else None
        except (TypeError, ValueError):
            fit_score = None
        db.add(XhsAiJudgment(
            id=_uid(), department_code=user.department_code, platform=user.platform, user_id=user.id,
            model=cfg["model"], prompt_version=PROMPT_VERSION,
            fit_score=fit_score,
            fit_level=clean_text(p.get("fit_level")),
            decision=clean_text(p.get("decision")),
            intent_type=clean_text(p.get("intent_type")),
            judgment=json.dumps(p, ensure_ascii=False),
            raw_response=(result["raw"] if result else None),
        ))
        db.commit()
        judged += 1
    return {"ok": True, "judged": judged}
