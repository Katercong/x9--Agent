from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import datetime
from typing import Any
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from .collector_service import ingest_observation
from ..utils.current_status import normalize_current_status


CREATOR_IMPORT_FIELDS = [
    "handle",
    "platform",
    "profile_url",
    "display_name",
    "bio",
    "country",
    "language",
    "followers",
    "tier",
    "engagement_rate",
    "avg_views",
    "email",
    "whatsapp",
    "instagram_handle",
    "category_tags",
    "source",
    "quality_score",
    "current_status",
    "store_assigned",
    "owner_bd",
    "search_keyword",
    "source_video_url",
    "source_video_title",
    "source_video_description",
    "collected_at",
]

HEADER_ALIASES = {
    "达人账号": "handle",
    "账号": "handle",
    "主页账号": "handle",
    "handle": "handle",
    "username": "handle",
    "user_name": "handle",
    "platform": "platform",
    "平台": "platform",
    "主页链接": "profile_url",
    "达人主页": "profile_url",
    "profile": "profile_url",
    "profile_url": "profile_url",
    "display_name": "display_name",
    "昵称": "display_name",
    "显示名称": "display_name",
    "bio": "bio",
    "简介": "bio",
    "达人简介": "bio",
    "个人描述": "bio",
    "country": "country",
    "国家": "country",
    "language": "language",
    "语言": "language",
    "followers": "followers",
    "followers_count": "followers",
    "粉丝": "followers",
    "粉丝数": "followers",
    "tier": "tier",
    "达人等级": "tier",
    "engagement_rate": "engagement_rate",
    "互动率": "engagement_rate",
    "avg_views": "avg_views",
    "平均播放": "avg_views",
    "email": "email",
    "邮箱": "email",
    "whatsapp": "whatsapp",
    "wa": "whatsapp",
    "WhatsApp": "whatsapp",
    "instagram": "instagram_handle",
    "instagram_handle": "instagram_handle",
    "ins": "instagram_handle",
    "ig": "instagram_handle",
    "category_tags": "category_tags",
    "标签": "category_tags",
    "内容标签": "category_tags",
    "source": "source",
    "来源": "source",
    "quality_score": "quality_score",
    "质量分": "quality_score",
    "current_status": "current_status",
    "当前状态": "current_status",
    "状态": "current_status",
    "达人状态": "current_status",
    "store_assigned": "store_assigned",
    "store": "store_assigned",
    "shop": "store_assigned",
    "店铺": "store_assigned",
    "分配店铺": "store_assigned",
    "店铺分配": "store_assigned",
    "owner_bd": "owner_bd",
    "bd_owner": "owner_bd",
    "bd": "owner_bd",
    "owner": "owner_bd",
    "对接人": "owner_bd",
    "负责人": "owner_bd",
    "bd负责人": "owner_bd",
    "search_keyword": "search_keyword",
    "关键词": "search_keyword",
    "source_video_url": "source_video_url",
    "来源视频": "source_video_url",
    "source_video_title": "source_video_title",
    "视频标题": "source_video_title",
    "source_video_description": "source_video_description",
    "视频描述": "source_video_description",
    "collected_at": "collected_at",
    "采集时间": "collected_at",
}


def import_creator_table(
    db: Session,
    content: bytes,
    *,
    filename: str = "",
    dry_run: bool = False,
    limit_errors: int = 50,
    department_code: str | None = None,
) -> dict[str, Any]:
    rows = parse_table(content, filename=filename)
    inserted = 0
    updated = 0
    failed = 0
    errors: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []

    for idx, row in enumerate(rows, start=2):
        normalized = normalize_row(row)
        handle = str(normalized.get("handle") or "").strip().lstrip("@")
        if not handle:
            failed += 1
            if len(errors) < limit_errors:
                errors.append({"row": idx, "detail": "handle is required"})
            continue

        payload = row_to_observation(normalized)
        if department_code:
            payload["department_code"] = department_code
        if dry_run:
            samples.append({"row": idx, "handle": handle, "payload": payload})
            continue

        try:
            result = ingest_observation(db, payload, auto_process=True)
            if result.get("action") == "inserted":
                inserted += 1
            else:
                updated += 1
            if len(samples) < 10:
                samples.append({
                    "row": idx,
                    "handle": handle,
                    "action": result.get("action"),
                    "pipeline": result.get("pipeline"),
                })
        except ValueError as exc:
            failed += 1
            if len(errors) < limit_errors:
                errors.append({"row": idx, "handle": handle, "detail": str(exc)})

    upserted = inserted + updated
    return {
        "ok": failed == 0,
        "filename": filename,
        "dry_run": dry_run,
        "total_rows": len(rows),
        "upserted": upserted,
        "updated": updated,
        "inserted": inserted,
        "failed": failed,
        "errors": errors,
        "items": samples,
    }


def parse_table(content: bytes, *, filename: str = "") -> list[dict[str, Any]]:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "xlsx" or content[:2] == b"PK":
        return parse_xlsx(content)
    if suffix not in {"", "csv", "txt"} and not content[:2] == b"PK":
        raise ValueError("only .csv and .xlsx files are supported")
    return parse_csv(content)


def parse_csv(content: bytes) -> list[dict[str, Any]]:
    text = _decode_text(content)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return [
        {str(k or "").strip(): _cell(v) for k, v in row.items()}
        for row in reader
        if any(_cell(v) for v in row.values())
    ]


def parse_xlsx(content: bytes) -> list[dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        shared = _xlsx_shared_strings(zf)
        sheet_name = _first_sheet_path(zf)
        root = ET.fromstring(zf.read(sheet_name))

    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows: list[list[str]] = []
    for row in root.findall(".//a:sheetData/a:row", ns):
        values: list[str] = []
        for cell in row.findall("a:c", ns):
            ref = cell.attrib.get("r", "")
            col_idx = _column_index(ref)
            while len(values) < col_idx:
                values.append("")
            values.append(_xlsx_cell_value(cell, shared, ns))
        rows.append(values)

    if not rows:
        return []
    headers = [str(x).strip() for x in rows[0]]
    out: list[dict[str, Any]] = []
    for values in rows[1:]:
        if not any(_cell(v) for v in values):
            continue
        out.append({headers[i] if i < len(headers) else f"column_{i + 1}": _cell(v) for i, v in enumerate(values)})
    return out


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw_key, value in row.items():
        key = _norm_header(raw_key)
        mapped = HEADER_ALIASES.get(key) or HEADER_ALIASES.get(str(raw_key).strip()) or key
        if mapped:
            out[mapped] = _cell(value)
    if not out.get("handle") and out.get("profile_url"):
        out["handle"] = _handle_from_url(str(out["profile_url"]))
    return out


def row_to_observation(row: dict[str, Any]) -> dict[str, Any]:
    handle = str(row.get("handle") or "").strip().lstrip("@")
    platform = (str(row.get("platform") or "tiktok").strip() or "tiktok").lower()
    bio = _bio_with_contacts(str(row.get("bio") or ""), row)
    followers = _int_or_none(row.get("followers"))
    # The channel source is fixed so table imports always classify into the
    # table_import dashboard bucket; a free-text CSV "source" column is kept
    # as origin_source metadata instead of shadowing the channel.
    csv_origin_source = str(row.get("source") or "").strip() or None
    collected_at = str(row.get("collected_at") or "").strip() or datetime.now().isoformat(timespec="seconds")

    external_links = []
    instagram = _instagram_handle(row.get("instagram_handle"))
    if instagram:
        external_links.append(f"https://www.instagram.com/{instagram.lstrip('@')}")
    whatsapp = str(row.get("whatsapp") or "").strip()
    if whatsapp:
        digits = re.sub(r"\D", "", whatsapp)
        if digits:
            external_links.append(f"https://wa.me/{digits}")

    return {
        "event_type": "creator_observation",
        "platform": platform,
        "source": "creator_table_import",
        "search_keyword": row.get("search_keyword") or None,
        "creator": {
            "handle": handle,
            "display_name": row.get("display_name") or handle,
            "profile_url": row.get("profile_url") or f"https://www.tiktok.com/@{handle}",
            "bio": bio or None,
            "followers_raw": row.get("followers_raw") or None,
            "followers_count": followers,
            "current_status": normalize_current_status(row.get("current_status")),
            "store_assigned": row.get("store_assigned") or None,
            "owner_bd": row.get("owner_bd") or None,
            "email": row.get("email") or None,
            "external_links": external_links,
        },
        "source_video": {
            "video_url": row.get("source_video_url") or None,
            "title": row.get("source_video_title") or None,
            "description": row.get("source_video_description") or None,
            "hashtags": [],
        },
        "import_row": row,
        "category_tags": _category_tags(row.get("category_tags")),
        "import_meta": {
            "country": row.get("country") or None,
            "language": row.get("language") or None,
            "tier": row.get("tier") or None,
            "engagement_rate": _float_or_none(row.get("engagement_rate")),
            "avg_views": _int_or_none(row.get("avg_views")),
            "quality_score": _float_or_none(row.get("quality_score")),
            "origin_source": csv_origin_source,
        },
        "collected_at": collected_at,
    }


def template_csv_bytes() -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CREATOR_IMPORT_FIELDS)
    writer.writeheader()
    writer.writerow({
        "handle": "test_creator_001",
        "platform": "tiktok",
        "profile_url": "https://www.tiktok.com/@test_creator_001",
        "display_name": "Test Creator",
        "bio": "UGC creator. WhatsApp +1 555 123 4567. IG @test_creator_ig",
        "followers": "50000",
        "email": "test@example.com",
        "whatsapp": "+1 555 123 4567",
        "instagram_handle": "@test_creator_ig",
        "category_tags": '["lifestyle"]',
        "source": "table_import",
        "quality_score": "0.85",
        "current_status": "已建联",
        "store_assigned": "X9x9 Shop 01",
        "owner_bd": "Mercy",
    })
    return out.getvalue().encode("utf-8-sig")


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall("a:si", ns):
        strings.append("".join(t.text or "" for t in item.findall(".//a:t", ns)))
    return strings


def _first_sheet_path(zf: zipfile.ZipFile) -> str:
    names = zf.namelist()
    preferred = "xl/worksheets/sheet1.xml"
    if preferred in names:
        return preferred
    for name in names:
        if name.startswith("xl/worksheets/") and name.endswith(".xml"):
            return name
    raise ValueError("xlsx has no worksheet")


def _xlsx_cell_value(cell: ET.Element, shared: list[str], ns: dict[str, str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(t.text or "" for t in cell.findall(".//a:t", ns)).strip()
    raw = cell.findtext("a:v", default="", namespaces=ns)
    if cell_type == "s":
        idx = _int_or_none(raw)
        return shared[idx] if idx is not None and 0 <= idx < len(shared) else ""
    return str(raw or "").strip()


def _column_index(ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", ref.upper())
    if not letters:
        return 0
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return index - 1


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _norm_header(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"none", "null", "nan"} else text


def _int_or_none(value: Any) -> int | None:
    text = _cell(value).replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _float_or_none(value: Any) -> float | None:
    text = _cell(value).replace("%", "")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number / 100 if "%" in _cell(value) else number


def _handle_from_url(value: str) -> str:
    match = re.search(r"/@([^/?#]+)", value or "")
    return match.group(1).strip() if match else ""


def _instagram_handle(value: Any) -> str:
    text = _cell(value).lstrip("@")
    if not text:
        return ""
    match = re.search(r"instagram\.com/([^/?#]+)", text, re.IGNORECASE)
    if match:
        text = match.group(1)
    return text.strip().strip("/")


def _bio_with_contacts(bio: str, row: dict[str, Any]) -> str:
    parts = [bio.strip()] if bio.strip() else []
    whatsapp = _cell(row.get("whatsapp"))
    instagram = _instagram_handle(row.get("instagram_handle"))
    if whatsapp and "whatsapp" not in bio.lower():
        parts.append(f"WhatsApp: {whatsapp}")
    if instagram and not any(term in bio.lower() for term in ("instagram", "insta", "ig @", "ig:")):
        parts.append(f"IG @{instagram}")
    return " ".join(parts).strip()


def _category_tags(value: Any) -> list[str]:
    text = _cell(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = [x.strip() for x in re.split(r"[,;，；]", text) if x.strip()]
    return [str(x).strip() for x in parsed if str(x).strip()] if isinstance(parsed, list) else []
