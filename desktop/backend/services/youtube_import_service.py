from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, quote, urlparse, urlunparse

from sqlalchemy.orm import Session

from ..models.youtube_lead import YoutubeImportRun, YoutubeLead, YoutubeLeadSource, YoutubeRawRow
from ..services.departments import DEFAULT_DEPARTMENT, normalize_department_code
from ..utils.id_utils import content_hash


EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$", re.IGNORECASE)
MANUAL_REVIEW_KEYS = {"captcha_required", "hidden_email_button_present", "login_required"}
TRUTHY = {"1", "true", "yes", "y", "on", "required"}


def import_youtube_export(
    db: Session,
    content: bytes,
    *,
    filename: str = "",
    dry_run: bool = False,
    department_code: str | None = None,
) -> dict[str, Any]:
    department = normalize_department_code(department_code, default=DEFAULT_DEPARTMENT) or DEFAULT_DEPARTMENT
    rows, metadata = parse_youtube_export(content, filename=filename)
    cleaned_items = [_clean_row(row, idx, metadata) for idx, row in enumerate(rows)]

    total_rows = len(rows)
    kept_items = [item for item in cleaned_items if item.get("keep")]
    dropped_no_contact = sum(1 for item in cleaned_items if item.get("drop_reason") == "missing_email_or_review")
    errors = [item["error"] for item in cleaned_items if item.get("error")]
    manual_review = sum(1 for item in kept_items if item.get("review_reasons"))

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "filename": filename or metadata.get("filename") or "",
            "keyword": metadata.get("keyword") or "",
            "source_search_url": metadata.get("source_search_url") or "",
            "total_rows": total_rows,
            "kept": len(kept_items),
            "dropped_no_contact": dropped_no_contact,
            "inserted": 0,
            "updated": 0,
            "sources_added": 0,
            "manual_review": manual_review,
            "errors": errors,
            "samples": _samples(kept_items),
        }

    now = datetime.utcnow()
    clear_resolved_manual_review_leads(db, department)
    run = YoutubeImportRun(
        department_code=department,
        filename=(filename or metadata.get("filename") or "")[:300],
        keyword=_limit(metadata.get("keyword"), 300),
        source_search_url=metadata.get("source_search_url") or None,
        status="importing",
        total_rows=total_rows,
        started_at=now,
        raw_settings_json=_json_dumps(metadata.get("settings") or {}),
    )
    db.add(run)
    db.flush()

    inserted = 0
    updated = 0
    sources_added = 0
    kept = 0

    for item in cleaned_items:
        raw_json = _json_dumps(item.get("raw") if item.get("raw") is not None else {})
        raw_row = YoutubeRawRow(
            run_id=run.id,
            department_code=department,
            row_index=int(item.get("row_index") or 0),
            row_hash=content_hash(raw_json),
            source_type=item.get("source_type"),
            channel_key=item.get("channel_key"),
            channel_url=item.get("channel_url"),
            video_url=item.get("video_url"),
            raw_json=raw_json,
            clean_status="kept" if item.get("keep") else ("error" if item.get("error") else "dropped"),
            drop_reason=item.get("drop_reason") or item.get("error"),
            collected_at=item.get("collected_at"),
        )
        db.add(raw_row)
        db.flush()

        if not item.get("keep"):
            continue

        kept += 1
        lead = (
            db.query(YoutubeLead)
            .filter(YoutubeLead.department_code == department, YoutubeLead.channel_key == item["channel_key"])
            .one_or_none()
        )
        if lead is None:
            lead = _new_lead(item, department=department, now=now)
            db.add(lead)
            db.flush()
            inserted += 1
        else:
            _merge_lead(lead, item, now=now)
            updated += 1

        _enforce_email_priority(lead)
        raw_row.lead_id = lead.id
        source_key = _source_key(item)
        source = (
            db.query(YoutubeLeadSource)
            .filter(YoutubeLeadSource.lead_id == lead.id, YoutubeLeadSource.source_key == source_key)
            .one_or_none()
        )
        if source is None:
            db.add(_new_source(item, lead_id=lead.id, run_id=run.id, raw_row_id=raw_row.id, source_key=source_key, department=department))
            sources_added += 1
        else:
            source.updated_at = now
            source.raw_row_id = raw_row.id
            source.run_id = run.id

    clear_resolved_manual_review_leads(db, department)
    run.status = "imported"
    run.kept_rows = kept
    run.dropped_no_contact = dropped_no_contact
    run.inserted = inserted
    run.updated = updated
    run.sources_added = sources_added
    run.manual_review = manual_review
    run.errors_count = len(errors)
    run.finished_at = datetime.utcnow()
    db.commit()

    return {
        "ok": True,
        "dry_run": False,
        "run_id": run.id,
        "filename": run.filename,
        "keyword": run.keyword or "",
        "source_search_url": run.source_search_url or "",
        "total_rows": total_rows,
        "kept": kept,
        "dropped_no_contact": dropped_no_contact,
        "inserted": inserted,
        "updated": updated,
        "sources_added": sources_added,
        "manual_review": manual_review,
        "errors": errors,
        "samples": _samples(kept_items),
    }


def parse_youtube_export(content: bytes, *, filename: str = "") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    text = _decode_text(content)
    lower_name = (filename or "").lower()
    stripped = text.lstrip()
    if lower_name.endswith(".csv") or (stripped and stripped[0] not in "[{"):
        return _parse_csv(text), {"filename": filename}

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON/CSV export: {exc}") from exc

    rows, metadata = _extract_json_rows(payload)
    metadata["filename"] = filename
    return rows, metadata


def _parse_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV file has no header row")
    return [dict(row) for row in reader]


def _extract_json_rows(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if isinstance(payload, list):
        return [_safe_dict(row) for row in payload], {}
    if not isinstance(payload, dict):
        raise ValueError("JSON export must be an object or array")

    containers: list[dict[str, Any]] = [payload]
    for key in ("state", "result"):
        if isinstance(payload.get(key), dict):
            containers.append(payload[key])
    if isinstance(payload.get("state"), dict) and isinstance(payload["state"].get("result"), dict):
        containers.append(payload["state"]["result"])

    rows: list[dict[str, Any]] = []
    for container in containers:
        if isinstance(container.get("rows"), list):
            rows = [_safe_dict(row) for row in container["rows"]]
            break

    seen = {content_hash(_json_dumps(row)) for row in rows}
    for container in containers:
        manual_rows = container.get("manual_review_rows")
        if not isinstance(manual_rows, list):
            continue
        for row in manual_rows:
            row_dict = _safe_dict(row)
            row_hash = content_hash(_json_dumps(row_dict))
            if row_hash in seen:
                continue
            rows.append(row_dict)
            seen.add(row_hash)

    if not rows:
        raise ValueError("YouTube export does not contain rows")

    metadata = {
        "keyword": _first_text(*(container.get("keyword") for container in containers)),
        "source_search_url": _first_text(
            *(container.get("source_search_url") for container in containers),
            payload.get("page_url"),
        ),
        "settings": _first_mapping(*(container.get("settings") for container in containers)),
    }
    if not metadata["keyword"] and metadata["settings"]:
        metadata["keyword"] = _string(metadata["settings"].get("keyword"))
    return rows, metadata


def _clean_row(row: dict[str, Any], row_index: int, metadata: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"row_index": row_index, "raw": row, "keep": False, "error": "row is not an object"}

    source_type = _string(row.get("source_type")) or "creator_channel"
    email_values = _extract_emails(row)
    email = email_values[0] if email_values else ""
    review_reasons = [] if email else _review_reasons(row)
    channel_info = _channel_info(row, source_type)

    item: dict[str, Any] = {
        "row_index": row_index,
        "raw": row,
        "source_type": source_type,
        "keyword": _string(row.get("keyword")) or _string(metadata.get("keyword")),
        "video_id": _string(row.get("video_id")),
        "video_url": _normalize_video_url(_string(row.get("video_url"))),
        "video_title": _string(row.get("video_title")),
        "creator_channel_url": _normalize_channel_url(_string(row.get("creator_channel_url"))),
        "comment_author_name": _string(row.get("comment_author_name")),
        "comment_author_channel_url": _normalize_channel_url(_string(row.get("comment_author_channel_url"))),
        "email": email,
        "emails": email_values,
        "review_reasons": review_reasons,
        "review_reason": ",".join(review_reasons),
        "manual_review_url": _first_text(row.get("manual_review_url"), row.get("checked_about_url"), row.get("evidence_url")),
        "evidence_url": _first_text(row.get("evidence_url"), row.get("checked_about_url"), row.get("video_url")),
        "profile_text": _string(row.get("profile_text")),
        "collected_at": _parse_datetime(row.get("collected_at")),
        **channel_info,
    }
    if not item.get("channel_key") and email:
        item["channel_key"] = f"email:{email}"
    if not item.get("channel_url"):
        item["channel_url"] = item.get("manual_review_url") or item.get("evidence_url") or ""

    if not item.get("channel_key"):
        item["keep"] = False
        item["drop_reason"] = "missing_channel"
        return item

    item["keep"] = bool(email or review_reasons)
    if not item["keep"]:
        item["drop_reason"] = "missing_email_or_review"
    return item


def _new_lead(item: dict[str, Any], *, department: str, now: datetime) -> YoutubeLead:
    collected_at = item.get("collected_at") or now
    emails = item.get("emails") or []
    review_reasons = [] if emails else (item.get("review_reasons") or [])
    lead = YoutubeLead(
        department_code=department,
        platform="youtube",
        channel_key=item["channel_key"],
        channel_id=item.get("channel_id") or None,
        channel_handle=item.get("channel_handle") or None,
        channel_url=item.get("channel_url") or None,
        display_name=_display_name(item) or None,
        email=item.get("email") or None,
        emails_json=_json_dumps(emails),
        has_email=1 if item.get("email") else 0,
        needs_manual_review=1 if review_reasons else 0,
        review_reasons_json=_json_dumps(review_reasons),
        manual_review_url=(item.get("manual_review_url") if review_reasons else None) or None,
        profile_text=item.get("profile_text") or None,
        latest_source_type=item.get("source_type") or None,
        latest_video_id=item.get("video_id") or None,
        latest_video_url=item.get("video_url") or None,
        latest_video_title=item.get("video_title") or None,
        latest_keyword=item.get("keyword") or None,
        source_types_json=_json_dumps([item.get("source_type")] if item.get("source_type") else []),
        raw_json=_json_dumps(item.get("raw") or {}),
        first_seen_at=collected_at,
        last_seen_at=collected_at,
        collected_at=collected_at,
    )
    _enforce_email_priority(lead)
    return lead


def _merge_lead(lead: YoutubeLead, item: dict[str, Any], *, now: datetime) -> None:
    collected_at = item.get("collected_at") or now
    emails = _merge_unique(_json_load_list(lead.emails_json), item.get("emails") or [])
    reasons = [] if emails else _merge_unique(_json_load_list(lead.review_reasons_json), item.get("review_reasons") or [])
    source_types = _merge_unique(_json_load_list(lead.source_types_json), [item.get("source_type")] if item.get("source_type") else [])

    lead.channel_id = lead.channel_id or item.get("channel_id") or None
    lead.channel_handle = lead.channel_handle or item.get("channel_handle") or None
    lead.channel_url = lead.channel_url or item.get("channel_url") or None
    lead.display_name = lead.display_name or _display_name(item) or None
    lead.email = lead.email or item.get("email") or None
    lead.emails_json = _json_dumps(emails)
    lead.has_email = 1 if emails else 0
    lead.needs_manual_review = 1 if reasons else 0
    lead.review_reasons_json = _json_dumps(reasons)
    lead.manual_review_url = (lead.manual_review_url or item.get("manual_review_url") or None) if reasons else None
    if item.get("profile_text") and (not lead.profile_text or len(item["profile_text"]) > len(lead.profile_text)):
        lead.profile_text = item["profile_text"]
    lead.latest_source_type = item.get("source_type") or lead.latest_source_type
    lead.latest_video_id = item.get("video_id") or lead.latest_video_id
    lead.latest_video_url = item.get("video_url") or lead.latest_video_url
    lead.latest_video_title = item.get("video_title") or lead.latest_video_title
    lead.latest_keyword = item.get("keyword") or lead.latest_keyword
    lead.source_types_json = _json_dumps(source_types)
    lead.raw_json = _json_dumps(item.get("raw") or {})
    lead.last_seen_at = collected_at
    lead.collected_at = collected_at
    lead.updated_at = now
    _enforce_email_priority(lead)


def _enforce_email_priority(lead: YoutubeLead) -> None:
    emails = _merge_unique(_json_load_list(lead.emails_json), [lead.email] if lead.email else [])
    if not emails:
        return
    lead.email = lead.email or emails[0]
    lead.emails_json = _json_dumps(emails)
    lead.has_email = 1
    lead.needs_manual_review = 0
    lead.review_reasons_json = _json_dumps([])
    lead.manual_review_url = None


def clear_resolved_manual_review_leads(db: Session, department_code: str | None = None) -> int:
    query = db.query(YoutubeLead).filter(YoutubeLead.has_email == 1, YoutubeLead.needs_manual_review == 1)
    if department_code is not None:
        query = query.filter(YoutubeLead.department_code == department_code)
    now = datetime.utcnow()
    count = 0
    for lead in query.all():
        _enforce_email_priority(lead)
        lead.updated_at = now
        count += 1
    return count


def _new_source(
    item: dict[str, Any],
    *,
    lead_id: str,
    run_id: str,
    raw_row_id: str,
    source_key: str,
    department: str,
) -> YoutubeLeadSource:
    return YoutubeLeadSource(
        department_code=department,
        lead_id=lead_id,
        run_id=run_id,
        raw_row_id=raw_row_id,
        source_key=source_key,
        source_type=item.get("source_type") or None,
        keyword=item.get("keyword") or None,
        video_id=item.get("video_id") or None,
        video_url=item.get("video_url") or None,
        video_title=item.get("video_title") or None,
        evidence_url=item.get("evidence_url") or None,
        manual_review_url=item.get("manual_review_url") or None,
        email=item.get("email") or None,
        review_reason=item.get("review_reason") or None,
        raw_json=_json_dumps(item.get("raw") or {}),
        collected_at=item.get("collected_at"),
    )


def _source_key(item: dict[str, Any]) -> str:
    return content_hash(
        _json_dumps(
            [
                item.get("channel_key"),
                item.get("source_type"),
                item.get("video_url"),
                item.get("evidence_url"),
                item.get("manual_review_url"),
                item.get("email"),
            ]
        )
    )


def _channel_info(row: dict[str, Any], source_type: str) -> dict[str, str]:
    if source_type == "comment_author_channel":
        preferred = row.get("comment_author_channel_url")
    else:
        preferred = row.get("creator_channel_url")
    channel_url = _first_text(
        preferred,
        row.get("creator_channel_url"),
        row.get("comment_author_channel_url"),
        row.get("checked_about_url"),
        row.get("checked_profile_url"),
        row.get("manual_review_url"),
    )
    normalized = _normalize_channel_url(channel_url)
    channel_id = _string(row.get("channel_id"))
    handle = _string(row.get("channel_handle") or row.get("handle"))

    if normalized:
        parsed = urlparse(normalized)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "channel":
            channel_id = channel_id or parts[1]
        elif parts and parts[0].startswith("@"):
            handle = handle or parts[0]
        elif len(parts) >= 2 and parts[0] in {"user", "c"}:
            handle = handle or f"{parts[0]}:{parts[1]}"

    if channel_id:
        key = f"channel_id:{channel_id.lower()}"
    elif handle:
        key = f"handle:{handle.lower()}"
    elif normalized:
        key = f"url:{normalized.lower()}"
    else:
        key = ""

    return {
        "channel_key": key,
        "channel_id": channel_id,
        "channel_handle": handle,
        "channel_url": normalized,
    }


def _normalize_channel_url(value: str) -> str:
    value = _string(value)
    if not value:
        return ""
    if value.startswith("/"):
        value = "https://www.youtube.com" + value
    if not value.startswith(("http://", "https://")):
        if value.startswith("@"):
            value = "https://www.youtube.com/" + quote(value, safe="@._-")
        else:
            return value
    parsed = urlparse(value)
    host = parsed.netloc.lower().replace("m.youtube.com", "www.youtube.com")
    path_parts = [part for part in parsed.path.split("/") if part]
    if path_parts and path_parts[-1].lower() in {"about", "videos", "featured", "shorts", "streams", "community"}:
        path_parts = path_parts[:-1]
    path = "/" + "/".join(path_parts) if path_parts else ""
    return urlunparse(("https", host, path.rstrip("/"), "", "", ""))


def _normalize_video_url(value: str) -> str:
    value = _string(value)
    if not value:
        return ""
    if value.startswith("/"):
        value = "https://www.youtube.com" + value
    parsed = urlparse(value)
    if not parsed.netloc:
        return value
    host = parsed.netloc.lower().replace("m.youtube.com", "www.youtube.com")
    if parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
        query = f"v={video_id}" if video_id else ""
        return urlunparse(("https", host, "/watch", "", query, ""))
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "shorts":
        return urlunparse(("https", host, f"/shorts/{parts[1]}", "", "", ""))
    return urlunparse(("https", host, parsed.path.rstrip("/"), "", parsed.query, ""))


def _extract_emails(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    direct = _normalize_email(row.get("email"))
    if direct:
        values.append(direct)
    for raw in _json_load_list(row.get("emails_json")) + _json_load_list(row.get("emails")):
        email = _normalize_email(raw)
        if email:
            values.append(email)
    return _merge_unique([], values)


def _review_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for raw in _json_load_list(row.get("review_reason")):
        value = _string(raw)
        if value in MANUAL_REVIEW_KEYS:
            reasons.append(value)
    for key in MANUAL_REVIEW_KEYS:
        if _truthy(row.get(key)):
            reasons.append(key)
    return _merge_unique([], reasons)


def _normalize_email(value: Any) -> str:
    email = _string(value).lower().strip(" <>.,;:'\"")
    return email if EMAIL_RE.match(email) else ""


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _json_load_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                data = json.loads(stripped)
                return data if isinstance(data, list) else [data]
            except json.JSONDecodeError:
                pass
        return [part.strip() for part in re.split(r"[,;|]+", stripped) if part.strip()]
    return [value]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _merge_unique(existing: list[Any], incoming: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in [*existing, *incoming]:
        text = _string(value)
        key = text.lower()
        if not text or key in seen:
            continue
        out.append(text)
        seen.add(key)
    return out


def _parse_datetime(value: Any) -> datetime | None:
    text = _string(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return _string(value).lower() in TRUTHY


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _first_text(*values: Any) -> str:
    for value in values:
        text = _string(value)
        if text:
            return text
    return ""


def _first_mapping(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {"value": value}


def _display_name(item: dict[str, Any]) -> str:
    if item.get("source_type") == "comment_author_channel":
        return _string(item.get("comment_author_name"))
    handle = _string(item.get("channel_handle"))
    return handle.lstrip("@")


def _limit(value: Any, size: int) -> str | None:
    text = _string(value)
    return text[:size] if text else None


def _samples(items: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items[:limit]:
        out.append(
            {
                "source_type": item.get("source_type") or "",
                "channel_key": item.get("channel_key") or "",
                "channel_url": item.get("channel_url") or "",
                "email": item.get("email") or "",
                "review_reason": item.get("review_reason") or "",
                "video_url": item.get("video_url") or "",
            }
        )
    return out
