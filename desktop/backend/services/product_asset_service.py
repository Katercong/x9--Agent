"""Local product/SKU assets used by outreach script generation.

The store is intentionally file-backed so teams can test product images and
selling points without a database migration.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import DATA_DIR

ASSET_DIR = DATA_DIR / "outreach_product_assets"
IMAGE_DIR = ASSET_DIR / "images"
ASSET_FILE = ASSET_DIR / "assets.json"
MAX_IMAGE_BYTES = 8 * 1024 * 1024

_DATA_URL_RE = re.compile(r"^data:(image/(?:png|jpe?g|webp|gif));base64,(.+)$", re.I | re.S)

PRODUCT_LABELS_EN = {
    "feminine_care": "feminine care products",
    "adult_care": "adult care products",
    "pet_care": "pet care products",
    "baby_care": "baby care products",
    "all": "X9 care products",
}

PRODUCT_KEY_ALIASES = {
    "feminine_care": "feminine_care",
    "feminine_care_daily_liner": "feminine_care",
    "period_care_pad": "feminine_care",
    "period_products": "feminine_care",
    "sensitive_skin_care": "feminine_care",
    "women": "feminine_care",
    "female": "feminine_care",
    "sanitary": "feminine_care",
    "pad": "feminine_care",
    "liner": "feminine_care",
    "adult_care": "adult_care",
    "adult": "adult_care",
    "incontinence": "adult_care",
    "bladder": "adult_care",
    "pet_care": "pet_care",
    "pet": "pet_care",
    "dog": "pet_care",
    "cat": "pet_care",
    "baby_care": "baby_care",
    "baby": "baby_care",
    "mom_baby": "baby_care",
    "diaper": "baby_care",
    "infant": "baby_care",
}


def normalize_product_key(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return "all"
    if raw in PRODUCT_KEY_ALIASES:
        return PRODUCT_KEY_ALIASES[raw]
    for token, key in PRODUCT_KEY_ALIASES.items():
        if token in raw:
            return key
    return raw


def product_label(product_key: str | None) -> str:
    return PRODUCT_LABELS_EN.get(normalize_product_key(product_key), "X9 care products")


def list_assets(department_code: str | None = None, *, include_inactive: bool = False) -> list[dict[str, Any]]:
    rows = _read_assets()
    out: list[dict[str, Any]] = []
    for row in rows:
        if not include_inactive and not row.get("is_active", True):
            continue
        row_department = row.get("department_code")
        if department_code and row_department not in (None, "", department_code):
            continue
        out.append(_public_asset(row))
    return out


def get_asset(asset_id: str, department_code: str | None = None) -> dict[str, Any] | None:
    for row in list_assets(department_code, include_inactive=True):
        if row.get("id") == asset_id:
            return row
    return None


def save_asset(payload: dict[str, Any], department_code: str | None = None) -> dict[str, Any]:
    rows = _read_assets()
    now = _now()
    image_filename = _save_image_data_url(payload.get("image_data_url"))
    product_key = normalize_product_key(payload.get("product_key"))
    entry = {
        "id": f"sku_{uuid.uuid4().hex[:12]}",
        "department_code": department_code,
        "name": _clean_text(payload.get("name"), 120) or "X9 product",
        "sku_code": _clean_text(payload.get("sku_code"), 80),
        "product_key": product_key,
        "selling_points": _clean_list(payload.get("selling_points"), 8, 120),
        "target_creator_types": _clean_list(payload.get("target_creator_types"), 10, 80),
        "image_filename": image_filename,
        "is_active": bool(payload.get("is_active", True)),
        "created_at": now,
        "updated_at": now,
    }
    rows.append(entry)
    _write_assets(rows)
    return _public_asset(entry)


def update_asset(asset_id: str, payload: dict[str, Any], department_code: str | None = None) -> dict[str, Any] | None:
    rows = _read_assets()
    for row in rows:
        if row.get("id") != asset_id:
            continue
        row_department = row.get("department_code")
        if department_code and row_department not in (None, "", department_code):
            return None
        if "name" in payload:
            row["name"] = _clean_text(payload.get("name"), 120) or row.get("name") or "X9 product"
        if "sku_code" in payload:
            row["sku_code"] = _clean_text(payload.get("sku_code"), 80)
        if "product_key" in payload:
            row["product_key"] = normalize_product_key(payload.get("product_key"))
        if "selling_points" in payload:
            row["selling_points"] = _clean_list(payload.get("selling_points"), 8, 120)
        if "target_creator_types" in payload:
            row["target_creator_types"] = _clean_list(payload.get("target_creator_types"), 10, 80)
        if "is_active" in payload:
            row["is_active"] = bool(payload.get("is_active"))
        image_filename = _save_image_data_url(payload.get("image_data_url"))
        if image_filename:
            old = row.get("image_filename")
            row["image_filename"] = image_filename
            _remove_image(old)
        row["updated_at"] = _now()
        _write_assets(rows)
        return _public_asset(row)
    return None


def delete_asset(asset_id: str, department_code: str | None = None) -> bool:
    rows = _read_assets()
    next_rows: list[dict[str, Any]] = []
    deleted: dict[str, Any] | None = None
    for row in rows:
        if row.get("id") == asset_id:
            row_department = row.get("department_code")
            if department_code and row_department not in (None, "", department_code):
                next_rows.append(row)
                continue
            deleted = row
            continue
        next_rows.append(row)
    if deleted is None:
        return False
    _write_assets(next_rows)
    _remove_image(deleted.get("image_filename"))
    return True


def image_path(asset: dict[str, Any]) -> Path | None:
    filename = asset.get("image_filename")
    if not filename:
        return None
    candidate = (IMAGE_DIR / filename).resolve()
    root = IMAGE_DIR.resolve()
    if not candidate.is_file() or root not in candidate.parents:
        return None
    return candidate


def match_asset_for_creator(creator: Any, assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    active = [a for a in assets if a.get("is_active", True)]
    if not active:
        return None
    text = _creator_text(creator)
    creator_key = normalize_product_key(
        getattr(creator, "recommended_product_type", None)
        or getattr(creator, "primary_product_category", None)
    )
    scored: list[tuple[int, dict[str, Any]]] = []
    for asset in active:
        score = 0
        asset_key = normalize_product_key(asset.get("product_key"))
        if asset_key == creator_key and asset_key != "all":
            score += 80
        if asset_key != "all" and asset_key.replace("_", " ") in text:
            score += 30
        for target in asset.get("target_creator_types") or []:
            target_norm = str(target).strip().lower()
            if target_norm and target_norm in text:
                score += 20
        for point in asset.get("selling_points") or []:
            point_norm = str(point).strip().lower()
            if point_norm and point_norm in text:
                score += 8
        if asset_key == "all":
            score += 1
        scored.append((score, asset))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0 else active[0]


def asset_prompt_context(asset: dict[str, Any] | None) -> dict[str, Any]:
    if not asset:
        return {}
    points = [str(p).strip() for p in asset.get("selling_points") or [] if str(p).strip()]
    name = str(asset.get("name") or "").strip()
    sku_code = str(asset.get("sku_code") or "").strip()
    product_key = normalize_product_key(asset.get("product_key"))
    if points:
        point_text = ", ".join(points)
        product_para = f"{name} ({point_text})" if name else point_text
    else:
        product_para = name or product_label(product_key)
    return {
        "product_asset_id": asset.get("id", ""),
        "product_asset_name": name,
        "product_sku_code": sku_code,
        "product_key": product_key,
        "product_label": name or product_label(product_key),
        "product_para": product_para,
        "product_selling_points": ", ".join(points),
    }


def _read_assets() -> list[dict[str, Any]]:
    if not ASSET_FILE.exists():
        return []
    try:
        data = json.loads(ASSET_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _write_assets(rows: list[dict[str, Any]]) -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _public_asset(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["image_url"] = (
        f"/api/local/outreach/product-assets/{row.get('id')}/image"
        if row.get("image_filename")
        else None
    )
    out["product_label"] = product_label(row.get("product_key"))
    return out


def _save_image_data_url(value: str | None) -> str | None:
    if not value:
        return None
    match = _DATA_URL_RE.match(value.strip())
    if not match:
        raise ValueError("image_data_url must be a base64 image data URL")
    mime_type, encoded = match.groups()
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("image file is too large")
    ext = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }[mime_type.lower()]
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    (IMAGE_DIR / filename).write_bytes(raw)
    return filename


def _remove_image(filename: str | None) -> None:
    if not filename:
        return
    try:
        path = (IMAGE_DIR / filename).resolve()
        if IMAGE_DIR.resolve() in path.parents and path.exists():
            path.unlink()
    except OSError:
        pass


def _clean_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _clean_list(value: Any, max_items: int, limit: int) -> list[str]:
    if isinstance(value, str):
        parts = re.split(r"[,，\n]+", value)
    elif isinstance(value, list):
        parts = value
    else:
        parts = []
    out: list[str] = []
    for item in parts:
        text = _clean_text(item, limit)
        if text and text not in out:
            out.append(text)
        if len(out) >= max_items:
            break
    return out


def _creator_text(creator: Any) -> str:
    values: list[str] = []
    for key in (
        "recommended_product_type",
        "primary_product_category",
        "recommendation_reason",
        "bio",
        "source_video_title",
        "source_video_description",
        "search_keyword",
        "matched_keywords_json",
        "category_tags",
    ):
        raw = getattr(creator, key, None)
        if raw is None:
            continue
        if isinstance(raw, (list, tuple)):
            values.extend(str(v) for v in raw)
        else:
            values.append(str(raw))
    return " ".join(values).lower().replace("_", " ")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def guess_mime_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"
