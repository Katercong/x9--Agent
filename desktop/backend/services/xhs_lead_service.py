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
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.social_lead import (
    XhsAiJudgment,
    XhsCollectionRun,
    XhsComment,
    XhsExtractedContact,
    XhsNoteMedia,
    XhsNote,
    XhsRawSnapshot,
    XhsUser,
    XhsUserHistoryPost,
    XhsUserSource,
)
from ..services.departments import DEFAULT_DEPARTMENT
from ..services.upload_queue_cleanup import attach_queue_cleanup
from ..utils.xhs_cleaning import (
    canonical_url,
    clean_text,
    data_quality_comment,
    data_quality_note,
    data_quality_user,
    extract_contacts,
    extract_douyin_post_id,
    extract_douyin_user_id,
    extract_platform_signals,
    extract_xhs_note_id,
    extract_xhs_user_id,
    parse_count_text,
    platform_prefixed_id,
    stable_hash,
)

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


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _keyword(payload: dict[str, Any], row: dict[str, Any] | None = None) -> str | None:
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    row = row or {}
    return clean_text(row.get("keyword") or settings.get("keyword") or payload.get("keyword"))


def _external_user_id(raw: dict[str, Any], platform: str) -> str | None:
    profile_url = canonical_url(raw.get("profile_url") or raw.get("canonical_profile_url"))
    if platform == "douyin":
        return clean_text(
            raw.get("external_user_id")
            or raw.get("user_id")
            or raw.get("sec_uid")
            or raw.get("unique_id")
            or raw.get("account")
        ) or extract_douyin_user_id(profile_url)
    return clean_text(
        raw.get("external_user_id")
        or raw.get("xhs_user_id")
        or raw.get("user_id")
        or raw.get("account")
    ) or extract_xhs_user_id(profile_url)


def _external_post_id(raw: dict[str, Any], platform: str) -> str | None:
    url = raw.get("url") or raw.get("post_url") or raw.get("note_url") or raw.get("search_result_url")
    if platform == "douyin":
        return clean_text(raw.get("external_post_id") or raw.get("post_id") or raw.get("video_id") or raw.get("aweme_id")) or extract_douyin_post_id(url)
    return clean_text(raw.get("external_post_id") or raw.get("xhs_note_id") or raw.get("note_id")) or extract_xhs_note_id(url)


def _external_comment_id(raw: dict[str, Any], platform: str) -> str | None:
    value = clean_text(raw.get("external_comment_id") or raw.get("xhs_comment_id") or raw.get("comment_id"))
    if value:
        return value
    return stable_hash([platform, raw.get("note_id") or raw.get("post_id"), raw.get("content"), raw.get("published_at_text"), raw.get("user", {})])[:32]


def _identity_key(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    key = text.strip().lstrip("@").replace(" ", "").lower()
    return key or None


def _normalized_identity_column(column):
    return func.replace(func.replace(func.lower(func.coalesce(column, "")), "@", ""), " ", "")


def _cache_identity_keys(platform: str, dept: str, values: list[Any]) -> list[str]:
    prefix = f"{dept}:{platform}:"
    keys: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _identity_key(value)
        if not key or key in seen:
            continue
        keys.append(prefix + key)
        seen.add(key)
    return keys


def _first_user_by_identity(
    db: Session,
    *,
    platform: str,
    dept: str,
    values: list[Any],
) -> XhsUser | None:
    """Find an existing cleaned user by stable account identifiers before insert."""
    columns = (
        XhsUser.account_clean,
        XhsUser.account,
        XhsUser.account_raw,
        XhsUser.user_id,
        XhsUser.xhs_user_id,
        XhsUser.external_user_id,
    )
    base_filters = [XhsUser.platform == platform, XhsUser.department_code == dept]
    seen: set[str] = set()
    for value in values:
        key = _identity_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        for column in columns:
            user = db.scalar(
                select(XhsUser)
                .where(*base_filters, _normalized_identity_column(column) == key)
                .order_by(XhsUser.created_at.asc())
                .limit(1)
            )
            if user is not None:
                return user
    return None


def _platform_handle_type(platform: str | None) -> str:
    return "douyin_handle" if (platform or "").lower() == "douyin" else "xhs_handle"


def _source_hash(payload: dict[str, Any]) -> str:
    return stable_hash(payload)


def _upsert_user(
    db: Session,
    cache: dict[str, XhsUser],
    *,
    platform: str,
    dept: str,
    raw: dict[str, Any],
    now: datetime,
    run_id: str | None = None,
    keyword: str | None = None,
) -> XhsUser | None:
    if not isinstance(raw, dict):
        return None
    ext = _external_user_id(raw, platform)
    profile_url = canonical_url(raw.get("profile_url") or raw.get("canonical_profile_url"))
    username = clean_text(raw.get("username") or raw.get("nickname"))
    account = clean_text(raw.get("account") or raw.get("account_raw") or raw.get("unique_id"))
    if not ext and not profile_url and not username and not account:
        return None
    xhs_user_id = platform_prefixed_id(platform, ext or raw.get("xhs_user_id") or profile_url or username or account)
    identity_values = [
        ext,
        xhs_user_id,
        raw.get("external_user_id"),
        raw.get("xhs_user_id"),
        raw.get("user_id"),
        raw.get("sec_uid"),
        raw.get("unique_id"),
        raw.get("account"),
        raw.get("account_raw"),
        account,
        profile_url,
    ]
    cache_keys = _cache_identity_keys(platform, dept, identity_values + [username])
    user = None
    for cache_key in cache_keys:
        user = cache.get(cache_key)
        if user is not None:
            break
    if user is None and ext:
        user = db.scalar(select(XhsUser).where(XhsUser.platform == platform, XhsUser.external_user_id == ext))
    if user is None and xhs_user_id:
        user = db.scalar(select(XhsUser).where(XhsUser.platform == platform, XhsUser.department_code == dept, XhsUser.xhs_user_id == xhs_user_id))
    if user is None and profile_url:
        user = db.scalar(select(XhsUser).where(XhsUser.platform == platform, XhsUser.department_code == dept, XhsUser.canonical_profile_url == profile_url))
    if user is None:
        user = _first_user_by_identity(db, platform=platform, dept=dept, values=identity_values)
    if user is None:
        user = XhsUser(id=_uid(), platform=platform, department_code=dept, external_user_id=ext, first_seen_at=now)
        db.add(user)
    # update fields (new value wins, keep old otherwise)
    user.department_code = dept or user.department_code
    user.external_user_id = ext or user.external_user_id
    user.xhs_user_id = xhs_user_id or user.xhs_user_id
    user.user_id = clean_text(raw.get("user_id")) or user.user_id
    user.username = username or user.username
    user.username_raw = username or user.username_raw
    user.username_clean = username or user.username_clean
    user.account = account or user.account
    user.account_raw = account or user.account_raw
    user.account_clean = account or user.account_clean
    user.profile_url = profile_url or user.profile_url
    user.canonical_profile_url = profile_url or user.canonical_profile_url
    user.avatar_url = clean_text(raw.get("avatar_url") or raw.get("avatar")) or user.avatar_url
    bio = clean_text(raw.get("bio") or raw.get("desc") or raw.get("signature"))
    user.bio = bio or user.bio
    user.bio_raw = bio or user.bio_raw
    user.bio_clean = bio or user.bio_clean
    user.location_text = clean_text(raw.get("location") or raw.get("location_text") or raw.get("ip_location")) or user.location_text
    user.gender_text = clean_text(raw.get("gender") or raw.get("gender_text")) or user.gender_text
    stats_text = " ".join(str(x) for x in _list(raw.get("stats_text")))
    follower_text = raw.get("follower_count") or raw.get("follower_count_text") or raw.get("fans") or raw.get("fans_count")
    following_text = raw.get("following_count") or raw.get("following_count_text")
    liked_text = raw.get("liked_collect_count") or raw.get("liked_collect_count_text")
    note_text = raw.get("note_count") or raw.get("note_count_text")
    if not follower_text and "粉丝" in stats_text:
        follower_text = stats_text
    if not following_text and "关注" in stats_text:
        following_text = stats_text
    if not liked_text and ("获赞" in stats_text or "喜欢" in stats_text):
        liked_text = stats_text
    fc = parse_count_text(follower_text)
    if fc is not None:
        user.follower_count = fc
        user.followers_count = fc
    if follower_text:
        user.follower_count_text = clean_text(follower_text) or user.follower_count_text
    following = parse_count_text(following_text)
    if following is not None:
        user.following_count = following
    if following_text:
        user.following_count_text = clean_text(following_text) or user.following_count_text
    liked = parse_count_text(liked_text)
    if liked is not None:
        user.liked_collect_count = liked
    if liked_text:
        user.liked_collect_count_text = clean_text(liked_text) or user.liked_collect_count_text
    note_count = parse_count_text(note_text)
    if note_count is not None:
        user.note_count = note_count
    if note_text:
        user.note_count_text = clean_text(note_text) or user.note_count_text
    if raw.get("history_posts") is not None:
        user.history_posts_json = _dump_json(_list(raw.get("history_posts")))
    if raw.get("sources") is not None:
        user.sources_json = _dump_json(_list(raw.get("sources")))
    user.raw_json = _dump_json(raw)
    user.last_keyword = keyword or user.last_keyword
    user.platform_signals = _dump_json(extract_platform_signals([username, account, bio, stats_text]))
    user.profile_quality = _dump_json(data_quality_user(raw))
    user.first_seen_run_id = run_id or user.first_seen_run_id
    user.profile_collected_at = _parse_dt(raw.get("profile_collected_at")) or user.profile_collected_at
    user.clean_status = "cleaned"
    user.last_seen_at = now
    db.flush()
    _add_platform_contact(db, dept=dept, user=user)
    for cache_key in cache_keys:
        cache[cache_key] = user
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


def _add_platform_contact(db: Session, *, dept: str, user: XhsUser) -> int:
    raw = clean_text(user.account_clean or user.xhs_user_id or user.username_clean)
    norm = clean_text(user.account_clean or user.xhs_user_id or user.external_user_id)
    if not raw or not norm:
        return 0
    contact_type = _platform_handle_type(user.platform)
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
            id=_uid(),
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


def _add_note_media(db: Session, *, dept: str, note: XhsNote, raw: dict[str, Any]) -> int:
    rows: list[tuple[str, str]] = []
    cover = clean_text(raw.get("cover_url"))
    if cover:
        rows.append(("cover", cover))
    for value in _list(raw.get("image_urls")):
        url = clean_text(value)
        if url:
            rows.append(("image", url))
    for value in _list(raw.get("media_urls")):
        url = clean_text(value)
        if url:
            rows.append(("video", url))
    media_url = clean_text(raw.get("media_url"))
    if media_url:
        rows.append(("video", media_url))
    added = 0
    seen: set[str] = set()
    for position, (media_type, url) in enumerate(rows):
        if url in seen:
            continue
        seen.add(url)
        exists = db.scalar(select(XhsNoteMedia.id).where(XhsNoteMedia.note_id == note.id, XhsNoteMedia.url == url))
        if exists:
            continue
        db.add(
            XhsNoteMedia(
                id=_uid(),
                department_code=dept,
                note_id=note.id,
                media_type=media_type,
                url=url,
                normalized_url=canonical_url(url),
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
    user: XhsUser,
    run_id: str | None,
    note_id: str | None,
    comment_id: str | None,
    source_type: str,
    keyword: str | None,
    evidence_text: Any,
    evidence_url: Any,
    evidence_images: list[Any] | None = None,
    comment_depth: int | None = None,
    payload: dict[str, Any] | None = None,
) -> int:
    record = {
        "user_id": user.id,
        "run_id": run_id,
        "note_id": note_id,
        "comment_id": comment_id,
        "source_type": source_type,
        "keyword": keyword,
        "evidence_text": clean_text(evidence_text),
        "evidence_url": canonical_url(evidence_url),
    }
    digest = _source_hash(record)
    exists = db.scalar(select(XhsUserSource.id).where(XhsUserSource.source_hash == digest))
    if exists:
        return 0
    db.add(
        XhsUserSource(
            id=_uid(),
            department_code=dept,
            platform=platform,
            user_id=user.id,
            run_id=run_id,
            note_id=note_id,
            comment_id=comment_id,
            source_type=source_type,
            keyword=keyword,
            evidence_text=record["evidence_text"],
            evidence_url=record["evidence_url"],
            evidence_images=_dump_json(evidence_images or []),
            comment_depth=comment_depth,
            source_payload=_dump_json(payload or {}),
            source_hash=digest,
        )
    )
    return 1


def _add_history_posts(db: Session, *, dept: str, platform: str, user: XhsUser, raw: dict[str, Any]) -> int:
    added = 0
    for position, post in enumerate(_list(raw.get("history_posts"))):
        if not isinstance(post, dict):
            continue
        url = canonical_url(post.get("url") or post.get("post_url"))
        post_id = _external_post_id(post, platform) or (stable_hash(url)[:24] if url else None)
        xhs_note_id = platform_prefixed_id(platform, post_id or url)
        exists = None
        if xhs_note_id:
            exists = db.scalar(
                select(XhsUserHistoryPost.id).where(
                    XhsUserHistoryPost.user_id == user.id,
                    XhsUserHistoryPost.xhs_note_id == xhs_note_id,
                )
            )
        if exists:
            continue
        db.add(
            XhsUserHistoryPost(
                id=_uid(),
                department_code=dept,
                platform=platform,
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


def ingest_snapshot(db: Session, payload: dict[str, Any], *, platform: str | None = None, department_code: str | None = None) -> dict[str, Any]:
    platform = (payload.get("platform") or platform or "xhs").strip().lower()
    dept = _dept(payload, department_code)
    now = datetime.utcnow()
    keyword = _keyword(payload)

    # collection run (upsert by run_key)
    run_key = clean_text(payload.get("run_id")) or stable_hash(payload)[:24]
    run = None
    if run_key:
        run = db.scalar(select(XhsCollectionRun).where(XhsCollectionRun.run_key == run_key))
    if run is None:
        run = XhsCollectionRun(id=_uid(), department_code=dept, platform=platform, run_key=run_key)
        db.add(run)
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    run.department_code = dept
    run.platform = platform
    run.keyword = keyword or run.keyword
    run.source_page_url = canonical_url(payload.get("source_page_url")) or run.source_page_url
    run.plugin_version = clean_text(payload.get("plugin_version")) or run.plugin_version
    run.collector_version = clean_text(payload.get("collector_version")) or run.collector_version
    run.raw_settings = _dump_json(settings)
    run.status = clean_text(payload.get("status")) or "done"
    run.started_at = _parse_dt(payload.get("started_at")) or run.started_at
    run.finished_at = _parse_dt(payload.get("finished_at")) or run.finished_at
    db.flush()

    # raw snapshot audit
    try:
        raw_json = json.dumps(payload, ensure_ascii=False, default=str)
        db.add(XhsRawSnapshot(
            id=_uid(), department_code=dept, platform=platform, run_id=run.id,
            snapshot_type="search", external_id=run_key, source_url=run.source_page_url,
            payload=raw_json, payload_hash=stable_hash(payload), clean_status="cleaned", observed_at=now,
        ))
    except Exception:  # noqa: BLE001 - audit row must never block ingest
        pass

    user_cache: dict[str, XhsUser] = {}
    note_cache: dict[str, XhsNote] = {}
    comment_cache: dict[str, XhsComment] = {}
    pending_parent_updates: list[tuple[XhsComment, str | None]] = []
    counts = {"notes": 0, "comments": 0, "users": 0, "contacts": 0, "media": 0, "history_posts": 0, "user_sources": 0}

    # top-level user profiles (rich: bio, followers)
    for raw in payload.get("users") or []:
        u = _upsert_user(db, user_cache, platform=platform, dept=dept, raw=raw, now=now, run_id=run.id, keyword=keyword)
        if u is not None:
            counts["users"] += 1
            counts["history_posts"] += _add_history_posts(db, dept=dept, platform=platform, user=u, raw=raw)
            counts["contacts"] += _add_contacts(
                db, dept=dept, owner_type="user", owner_id=u.id, user=u,
                texts=[u.bio_clean, u.username_clean, u.account_clean, raw.get("signature"), _dump_json(raw.get("stats_text") or [])],
            )
            for src in _list(raw.get("sources")):
                if not isinstance(src, dict):
                    continue
                source_type = clean_text(src.get("source_type")) or "manual"
                if source_type == "comment":
                    source_type = "reply_author" if int(src.get("comment_depth") or 0) > 0 else "comment_author"
                if source_type not in {"post_author", "comment_author", "reply_author", "mentioned_user", "profile_history", "manual"}:
                    source_type = "manual"
                counts["user_sources"] += _add_user_source(
                    db,
                    dept=dept,
                    platform=platform,
                    user=u,
                    run_id=run.id,
                    note_id=None,
                    comment_id=None,
                    source_type=source_type,
                    keyword=clean_text(src.get("keyword")) or keyword,
                    evidence_text=src.get("comment_content") or src.get("note_title") or src.get("post_title"),
                    evidence_url=src.get("note_url") or src.get("post_url"),
                    evidence_images=_list(src.get("note_images")),
                    comment_depth=int(src.get("comment_depth") or 0) if src.get("comment_depth") is not None else None,
                    payload=src,
                )

    # notes / posts
    notes = payload.get("notes") or payload.get("posts") or []
    for raw in notes:
        if not isinstance(raw, dict):
            continue
        row_keyword = _keyword(payload, raw)
        ext_post = _external_post_id(raw, platform)
        canonical_note_url = canonical_url(raw.get("url") or raw.get("canonical_note_url") or raw.get("post_url"))
        author = _upsert_user(db, user_cache, platform=platform, dept=dept, raw=raw.get("author") or {}, now=now, run_id=run.id, keyword=row_keyword)
        note = None
        if ext_post:
            note = db.scalar(select(XhsNote).where(XhsNote.platform == platform, XhsNote.external_post_id == ext_post))
        if note is None and canonical_note_url:
            note = db.scalar(select(XhsNote).where(XhsNote.platform == platform, XhsNote.canonical_note_url == canonical_note_url))
        if note is None:
            note = XhsNote(id=_uid(), platform=platform, department_code=dept, external_post_id=ext_post, first_seen_at=now)
            db.add(note)
        note.department_code = dept
        note.external_post_id = ext_post or note.external_post_id
        note.xhs_note_id = platform_prefixed_id(platform, ext_post or raw.get("xhs_note_id") or raw.get("aweme_id")) or note.xhs_note_id
        note.note_id = clean_text(raw.get("note_id") or raw.get("post_id")) or note.note_id
        note.content_type = "video" if (raw.get("aweme_id") or platform == "douyin") else "note"
        note.url = canonical_note_url or note.url
        note.canonical_note_url = canonical_note_url or note.canonical_note_url
        note.search_result_url = canonical_url(raw.get("search_result_url") or raw.get("source_page_url")) or note.search_result_url
        note.title = clean_text(raw.get("title")) or note.title
        note.title_raw = clean_text(raw.get("title")) or note.title_raw
        note.title_clean = clean_text(raw.get("title")) or note.title_clean
        note.content = clean_text(raw.get("content") or raw.get("desc")) or note.content
        note.desc_raw = clean_text(raw.get("desc")) or note.desc_raw
        note.desc_clean = clean_text(raw.get("desc")) or note.desc_clean
        note.published_at_text = clean_text(raw.get("published_at_text")) or note.published_at_text
        note.published_at = _parse_dt(raw.get("published_at")) or note.published_at
        note.publish_location = clean_text(raw.get("publish_location") or raw.get("location")) or note.publish_location
        note.like_count_text = clean_text(raw.get("like_count_text") or raw.get("like_count") or raw.get("digg_count")) or note.like_count_text
        note.like_count = parse_count_text(raw.get("like_count") or raw.get("like_count_text") or raw.get("digg_count")) if (raw.get("like_count") or raw.get("like_count_text") or raw.get("digg_count")) is not None else note.like_count
        note.collect_count_text = clean_text(raw.get("collect_count_text") or raw.get("collect_count")) or note.collect_count_text
        note.collect_count = parse_count_text(raw.get("collect_count") or raw.get("collect_count_text")) if (raw.get("collect_count") or raw.get("collect_count_text")) is not None else note.collect_count
        note.comment_count_text = clean_text(raw.get("comment_count_text") or raw.get("comment_count")) or note.comment_count_text
        note.comment_count = parse_count_text(raw.get("comment_count") or raw.get("comment_count_text")) if (raw.get("comment_count") or raw.get("comment_count_text")) is not None else note.comment_count
        note.author_user_id = author.id if author else note.author_user_id
        note.author_xhs_user_id_snapshot = author.xhs_user_id if author else note.author_xhs_user_id_snapshot
        note.author_username = author.username_clean if author else note.author_username
        note.author_username_snapshot = author.username_clean if author else note.author_username_snapshot
        note.cover_url = clean_text(raw.get("cover_url")) or note.cover_url
        note.images_json = _dump_json(_list(raw.get("image_urls"))) if raw.get("image_urls") is not None else note.images_json
        note.tags_json = _dump_json(_list(raw.get("tags"))) if raw.get("tags") is not None else note.tags_json
        note.keyword = row_keyword or note.keyword
        note.content_hash = stable_hash([note.title_clean, note.desc_clean, note.canonical_note_url])
        note.relevance_status = note.relevance_status or "unknown"
        note.data_quality = _dump_json(data_quality_note(raw))
        note.raw_json = json.dumps(raw, ensure_ascii=False, default=str)
        note.last_seen_at = now
        db.flush()
        counts["notes"] += 1
        counts["media"] += _add_note_media(db, dept=dept, note=note, raw=raw)
        if author is not None:
            counts["user_sources"] += _add_user_source(
                db,
                dept=dept,
                platform=platform,
                user=author,
                run_id=run.id,
                note_id=note.id,
                comment_id=None,
                source_type="post_author",
                keyword=row_keyword or keyword,
                evidence_text=note.title_clean or note.desc_clean,
                evidence_url=note.canonical_note_url,
                evidence_images=_list(raw.get("image_urls")),
                payload=raw,
            )
            counts["contacts"] += _add_contacts(
                db, dept=dept, owner_type="user", owner_id=author.id, user=author,
                texts=[author.bio_clean, author.username_clean, author.account_clean],
            )
        if ext_post:
            note_cache[ext_post] = note
        if note.xhs_note_id:
            note_cache[note.xhs_note_id] = note
        if canonical_note_url:
            note_cache[canonical_note_url] = note

    # comments (+ commenter users + contacts from comment text)
    for raw in payload.get("comments") or []:
        if not isinstance(raw, dict):
            continue
        row_keyword = _keyword(payload, raw)
        ext_comment = _external_comment_id(raw, platform)
        commenter = _upsert_user(db, user_cache, platform=platform, dept=dept, raw=raw.get("user") or {}, now=now, run_id=run.id, keyword=row_keyword)
        note_lookup = clean_text(raw.get("note_id") or raw.get("post_id")) or ""
        note_url = canonical_url(raw.get("note_url") or raw.get("post_url"))
        note = note_cache.get(note_lookup) or note_cache.get(note_url or "")
        comment = None
        if ext_comment:
            comment = db.scalar(select(XhsComment).where(XhsComment.platform == platform, XhsComment.external_comment_id == ext_comment))
        if comment is None:
            comment = XhsComment(id=_uid(), platform=platform, department_code=dept, external_comment_id=ext_comment, first_seen_at=now)
            db.add(comment)
        comment.department_code = dept
        comment.external_comment_id = ext_comment or comment.external_comment_id
        comment.xhs_comment_id = platform_prefixed_id(platform, ext_comment or raw.get("xhs_comment_id")) or comment.xhs_comment_id
        comment.comment_id = clean_text(raw.get("comment_id")) or comment.comment_id
        comment.note_id = note.id if note else comment.note_id
        comment.note_url = note_url or comment.note_url
        comment.root_comment_id = clean_text(raw.get("root_comment_id")) or comment.root_comment_id
        comment.root_comment_external_id = clean_text(raw.get("root_comment_id")) or comment.root_comment_external_id
        comment.parent_comment_external_id = clean_text(raw.get("parent_comment_id")) or comment.parent_comment_external_id
        comment.user_id = commenter.id if commenter else comment.user_id
        user_raw = raw.get("user") if isinstance(raw.get("user"), dict) else {}
        comment.user_xhs_id_snapshot = commenter.xhs_user_id if commenter else comment.user_xhs_id_snapshot
        comment.username = clean_text(user_raw.get("username") or user_raw.get("nickname")) or comment.username
        comment.username_snapshot = comment.username or (commenter.username_clean if commenter else comment.username_snapshot)
        comment.profile_url = canonical_url(user_raw.get("profile_url")) or comment.profile_url
        comment.profile_url_snapshot = comment.profile_url or comment.profile_url_snapshot
        comment.avatar_url = clean_text(user_raw.get("avatar_url") or user_raw.get("avatar")) or comment.avatar_url
        comment.avatar_url_snapshot = comment.avatar_url or comment.avatar_url_snapshot
        comment.content = clean_text(raw.get("content")) or comment.content
        comment.content_raw = clean_text(raw.get("content")) or comment.content_raw
        comment.content_clean = clean_text(raw.get("content")) or comment.content_clean
        comment.published_at_text = clean_text(raw.get("published_at_text")) or comment.published_at_text
        comment.published_at = _parse_dt(raw.get("published_at")) or comment.published_at
        comment.location = clean_text(raw.get("location")) or comment.location
        comment.location_text = clean_text(raw.get("location") or raw.get("location_text")) or comment.location_text
        comment.like_count_text = clean_text(raw.get("like_count_text") or raw.get("like_count")) or comment.like_count_text
        comment.like_count = parse_count_text(raw.get("like_count") or raw.get("like_count_text")) if (raw.get("like_count") or raw.get("like_count_text")) is not None else comment.like_count
        comment.reply_count = parse_count_text(raw.get("reply_count") or raw.get("reply_count_text")) if (raw.get("reply_count") or raw.get("reply_count_text")) is not None else comment.reply_count
        comment.is_author_reply = 1 if raw.get("is_author_reply") else comment.is_author_reply
        comment.keyword = row_keyword or comment.keyword
        comment.data_quality = _dump_json(data_quality_comment(raw))
        comment.raw_json = json.dumps(raw, ensure_ascii=False, default=str)
        comment.last_seen_at = now
        db.flush()
        counts["comments"] += 1
        if comment.external_comment_id:
            comment_cache[comment.external_comment_id] = comment
        pending_parent_updates.append((comment, clean_text(raw.get("parent_comment_id") or raw.get("root_comment_id"))))
        # contacts live mostly in comment text ("微信 xxx" / "vx: yyy")
        counts["contacts"] += _add_contacts(
            db, dept=dept, owner_type="comment", owner_id=comment.id, user=commenter,
            texts=[comment.content_clean],
        )
        if commenter is not None:
            counts["user_sources"] += _add_user_source(
                db,
                dept=dept,
                platform=platform,
                user=commenter,
                run_id=run.id,
                note_id=note.id if note else None,
                comment_id=comment.id,
                source_type="reply_author" if int(raw.get("depth") or 0) > 0 else "comment_author",
                keyword=row_keyword or keyword,
                evidence_text=comment.content_clean,
                evidence_url=comment.note_url,
                evidence_images=[],
                comment_depth=int(raw.get("depth") or 0),
                payload=raw,
            )

    for comment, parent_external_id in pending_parent_updates:
        parent = comment_cache.get(parent_external_id or "")
        if parent is not None and comment.parent_comment_id is None:
            comment.parent_comment_id = parent.id

    db.commit()
    auto_judgment = request_auto_judge_after_ingest(dept)
    return attach_queue_cleanup(
        {"ok": True, "platform": platform, "run_id": run.id, "counts": counts, "auto_judgment": auto_judgment},
        payload,
        entity="social_snapshot",
        platform=platform,
        run_id=run.id,
        counts=counts,
    )


def request_auto_judge_after_ingest(department_code: str | None = None) -> dict[str, Any]:
    try:
        from ..utils.foreign_trade_scoring_scheduler import request_auto_score

        request_auto_score(department_code)
        return {"queued": True, "department_code": department_code}
    except Exception as exc:  # noqa: BLE001 - auto scoring must never block ingest
        return {"queued": False, "error": str(exc)[:300], "department_code": department_code}


def count_unjudged_social_users(db: Session, department_code: str | None = None) -> int:
    stmt = _unjudged_social_user_stmt(department_code)
    return int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)


def auto_judge_unjudged_social(db: Session, *, department_code: str | None = None, limit: int | None = None) -> dict[str, Any]:
    raw_limit = os.getenv("X9_FT_AUTO_JUDGE_LIMIT", "10").strip()
    try:
        resolved_limit = int(raw_limit)
    except ValueError:
        resolved_limit = 10
    if limit is not None:
        resolved_limit = limit
    if resolved_limit <= 0:
        return {"enabled": False, "reason": "disabled", "pending": 0, "judged": 0}
    pending = count_unjudged_social_users(db, department_code)
    if pending <= 0:
        return {"enabled": True, "pending": 0, "judged": 0, "ok": True}
    result = judge_users_with_gpt(db, department_code=department_code, limit=min(resolved_limit, pending), force=False)
    return {"enabled": True, "pending": pending, "limit": resolved_limit, **result}


def _unjudged_social_user_stmt(department_code: str | None = None):
    judged_user_ids = select(XhsAiJudgment.user_id).where(XhsAiJudgment.prompt_version == PROMPT_VERSION)
    stmt = select(XhsUser).where(XhsUser.has_contact == 1, XhsUser.id.not_in(judged_user_ids))
    if department_code:
        stmt = stmt.where(XhsUser.department_code == department_code)
    return stmt


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

    stmt = select(XhsUser).where(XhsUser.has_contact == 1) if force else _unjudged_social_user_stmt(department_code)
    if department_code:
        stmt = stmt.where(XhsUser.department_code == department_code)
    candidates = list(db.scalars(stmt.order_by(XhsUser.created_at.desc()).limit(limit)).all())

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
