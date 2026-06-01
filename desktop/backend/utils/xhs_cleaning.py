"""Xiaohongshu / Douyin cleaning + contact-extraction helpers (Phase 3).

Ported from x9_xhs_douyin .../backend/api/app/cleaning.py (regexes verbatim),
adapted to be storage-agnostic (returns plain dicts; the service layer writes to
the X9 xhs_* SQLAlchemy models).
"""

from __future__ import annotations

import re
from typing import Any

EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
URL_RE = re.compile(r"(?i)\bhttps?://[^\s<>'\"]+")
WECHAT_RE = re.compile(r"(?i)(?:微信|vx|v信|wechat)[:：\s]*([a-z][-_a-z0-9]{5,19})")

INTERNAL_URL_HOSTS = ("xiaohongshu.com", "xhslink.com", "douyin.com", "iesdouyin.com")


def clean_text(value: Any) -> str | None:
    if not value:
        return None
    text = CONTROL_RE.sub("", str(value))
    text = text.replace("​", "").strip()
    return text or None


def parse_count_text(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    multiplier = 1
    if text.endswith("万") or text.endswith("w"):
        multiplier = 10000
    elif text.endswith("千") or text.endswith("k"):
        multiplier = 1000
    digits = re.sub(r"[^\d.]", "", text)
    if not digits:
        return None
    try:
        return int(float(digits) * multiplier)
    except ValueError:
        return None


def normalize_url(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    lowered = text.lower()
    for host in INTERNAL_URL_HOSTS:
        if host in lowered:
            return None
    return text


def extract_contacts(texts: list[Any]) -> list[dict[str, str]]:
    """Pull email / phone / wechat / external-url contacts from free text.

    Returns deduped dicts: {contact_type, value_raw, value_norm, rule_code}.
    """
    joined = "\n".join(clean_text(t) or "" for t in texts if clean_text(t))
    if not joined:
        return []
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(contact_type: str, raw: str, norm: str, rule_code: str) -> None:
        norm = (norm or "").strip()
        if not norm:
            return
        key = (contact_type, norm.lower())
        if key in seen:
            return
        seen.add(key)
        out.append({"contact_type": contact_type, "value_raw": raw, "value_norm": norm, "rule_code": rule_code})

    for m in EMAIL_RE.findall(joined):
        add("email", m, m.lower(), "regex_email")
    for m in PHONE_RE.findall(joined):
        add("phone", m, re.sub(r"\D", "", m), "regex_phone")
    for m in WECHAT_RE.findall(joined):
        add("wechat", m, m.lower(), "regex_wechat_hint")
    for m in URL_RE.findall(joined):
        norm = normalize_url(m)
        if norm:
            add("url", m, norm.lower(), "regex_external_url")
    return out
