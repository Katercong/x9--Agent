from __future__ import annotations

import hashlib
import re
import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def slugify(value: str, fallback: str = "item") -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value or fallback


def content_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def creator_id_for(platform: str, handle: str) -> str:
    """Stable creator id derived from (platform, handle) — lets us upsert
    cleanly without needing to read the row first."""
    norm = f"{(platform or 'tiktok').lower()}:{(handle or '').lower().strip()}"
    return f"creator_{hashlib.sha1(norm.encode('utf-8')).hexdigest()[:16]}"
