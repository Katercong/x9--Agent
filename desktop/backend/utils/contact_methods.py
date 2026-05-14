from __future__ import annotations

import json
import re
from typing import Any


EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
PHONE_RE = re.compile(r"(?:(?:\+|00)\d[\d\s().-]{7,}\d)")
CHANNEL_PHONE_RE = re.compile(r"(?:(?:\+|00)?\d[\d\s().-]{7,}\d)")
WHATSAPP_RE = re.compile(
    r"(?:whats\s*app|whatsapp|\bwa\b)\s*[:：/|\-]?\s*(?P<phone>(?:\+|00)?\d[\d\s().-]{7,}\d)",
    re.IGNORECASE,
)
INSTAGRAM_LABEL_RE = re.compile(
    r"(?:^|[\s,;|/])(?:instagram|insta|ig)\b\s*[:：/@\-]?\s*@?(?P<handle>[A-Za-z0-9][A-Za-z0-9._]{1,28}[A-Za-z0-9])",
    re.IGNORECASE,
)
INSTAGRAM_REVERSE_RE = re.compile(
    r"@(?P<handle>[A-Za-z0-9][A-Za-z0-9._]{1,28}[A-Za-z0-9])\s+(?:on\s+)?(?:ig|insta|instagram)\b",
    re.IGNORECASE,
)
URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>'\"，。；;]+|"
    r"(?:wa\.me|api\.whatsapp\.com|chat\.whatsapp\.com|t\.me|telegram\.me|"
    r"instagram\.com|linktr\.ee|beacons\.ai|bio\.site|taplink\.cc|stan\.store|"
    r"line\.me|lin\.ee|m\.me|facebook\.com)/[^\s<>'\"，。；;]+",
    re.IGNORECASE,
)

CONTACT_CHANNEL_LABELS = {
    "email": "Email",
    "whatsapp": "WhatsApp",
    "instagram": "Instagram",
    "link": "Link",
    "telegram": "Telegram",
    "line": "LINE",
    "phone": "Phone",
    "facebook": "Facebook",
    "dm": "DM",
}

CONTACT_CHANNEL_TERMS = {
    "whatsapp": ("whatsapp", "whats app", "wa.me", "api.whatsapp.com", "chat.whatsapp.com", "wa:"),
    "instagram": ("instagram", "instagram.com", "insta", "ig:", "ig @"),
    "link": ("linktr.ee", "beacons.ai", "bio.site", "taplink", "stan.store", "link in bio"),
    "telegram": ("telegram", "t.me/", "telegram.me"),
    "line": ("line.me", "lin.ee", "line id", "line:"),
    "facebook": ("facebook.com", "fb.me", "m.me/"),
    "dm": ("dm me", "dm for", "direct message", "message me"),
    "phone": ("phone", "tel:", "call me", "text me"),
}

DIRECT_CONTACT_TYPES = {"email", "whatsapp", "instagram", "telegram", "line", "phone", "facebook", "dm"}


def extract_contact_methods(
    email: str | None = None,
    bio: str | None = None,
    external_links: Any | None = None,
) -> list[dict[str, str]]:
    """Extract contact channels from the creator bio/description only.

    The stored email is included because it is normally parsed from that
    same profile description by the collector. External links are
    deliberately ignored here.
    """
    methods: list[dict[str, str]] = []
    bio_text = str(bio or "")

    def add(kind: str, value: str, href: str | None = None, source: str = "bio") -> None:
        value = _clean_value(value)
        if not value:
            return
        if any(m["type"] == kind for m in methods) and not href:
            return
        key = (kind, value.lower())
        if any((m["type"], m["value"].lower()) == key for m in methods):
            return
        method = {
            "type": kind,
            "label": CONTACT_CHANNEL_LABELS.get(kind, kind.title()),
            "value": value,
            "source": source,
        }
        if href:
            method["href"] = href
        methods.append(method)

    if email:
        clean_email = str(email).strip().lower()
        if EMAIL_RE.fullmatch(clean_email):
            add("email", clean_email, f"mailto:{clean_email}", source="email")

    for match in EMAIL_RE.finditer(bio_text):
        clean_email = match.group(0).lower()
        add("email", clean_email, f"mailto:{clean_email}")

    for match in URL_RE.finditer(bio_text):
        raw_url = _clean_value(match.group(0))
        kind = _classify_url(raw_url)
        if kind:
            add(kind, _url_display_value(kind, raw_url), _normal_url(raw_url))

    for raw_url in _iter_external_link_values(external_links):
        kind = _classify_url(raw_url)
        if kind:
            add(kind, _url_display_value(kind, raw_url), _normal_url(raw_url), source="external_link")

    for match in PHONE_RE.finditer(bio_text):
        phone = _clean_value(match.group(0))
        dial = _tel_digits(phone)
        add("phone", phone, f"tel:{dial}" if dial else None)

    for match in WHATSAPP_RE.finditer(bio_text):
        phone = _clean_value(match.group("phone"))
        add("whatsapp", phone, _whatsapp_href(phone))

    for regex in (INSTAGRAM_LABEL_RE, INSTAGRAM_REVERSE_RE):
        for match in regex.finditer(bio_text):
            handle = _clean_instagram_handle(match.group("handle"))
            if handle:
                add("instagram", f"@{handle}", f"https://www.instagram.com/{handle}")

    lower_bio = bio_text.lower()
    for kind, terms in CONTACT_CHANNEL_TERMS.items():
        if kind == "phone" and any(m["type"] == "phone" for m in methods):
            continue
        if kind == "instagram" and any(m["type"] == "instagram" for m in methods):
            continue
        for term in terms:
            idx = lower_bio.find(term.lower())
            if idx >= 0:
                nearby_phone = _nearby_phone(bio_text, idx)
                if kind == "whatsapp" and nearby_phone:
                    add(kind, nearby_phone, _whatsapp_href(nearby_phone))
                    break
                if kind == "phone" and nearby_phone:
                    dial = _tel_digits(nearby_phone)
                    add(kind, nearby_phone, f"tel:{dial}" if dial else None)
                    break
                add(kind, _snippet(bio_text, idx, idx + len(term)))
                break

    return methods


def contact_types_for(
    email: str | None = None,
    bio: str | None = None,
    external_links: Any | None = None,
) -> list[str]:
    return list(dict.fromkeys(method["type"] for method in extract_contact_methods(email, bio, external_links)))


def has_contact_method(
    email: str | None = None,
    bio: str | None = None,
    external_links: Any | None = None,
) -> bool:
    return any(method["type"] in DIRECT_CONTACT_TYPES for method in extract_contact_methods(email, bio, external_links))


def methods_to_text(methods: list[dict[str, Any]]) -> str:
    parts = []
    for method in methods:
        label = method.get("label") or method.get("type") or "Contact"
        value = method.get("value") or ""
        parts.append(f"{label}: {value}" if value else str(label))
    return "; ".join(parts)


def _classify_url(url: str) -> str | None:
    lower = url.lower()
    if "wa.me/" in lower or "whatsapp.com" in lower:
        return "whatsapp"
    if "instagram.com" in lower:
        return "instagram"
    if "t.me/" in lower or "telegram.me" in lower:
        return "telegram"
    if "line.me" in lower or "lin.ee" in lower:
        return "line"
    if "facebook.com" in lower or "fb.me" in lower or "m.me/" in lower:
        return "facebook"
    if any(host in lower for host in ("linktr.ee", "beacons.ai", "bio.site", "taplink", "stan.store")):
        return "link"
    return None


def _iter_external_link_values(external_links: Any | None) -> list[str]:
    if not external_links:
        return []
    data = external_links
    if isinstance(data, str):
        raw = data.strip()
        if not raw:
            return []
        if raw.startswith(("[", "{")):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = [raw]
        else:
            data = [raw]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, (list, tuple, set)):
        return []

    out: list[str] = []
    for item in data:
        if isinstance(item, str):
            out.append(item)
            continue
        if not isinstance(item, dict):
            continue
        for key in ("url", "href", "link", "profile_url", "value"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                out.append(value)
                break
    return out


def _normal_url(url: str) -> str:
    value = _clean_value(url)
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    return f"https://{value.lstrip('/')}"


def _nearby_phone(text: str, idx: int, window: int = 96) -> str:
    segment = text[idx: idx + window]
    for match in CHANNEL_PHONE_RE.finditer(segment):
        phone = _clean_value(match.group(0))
        digits = _phone_digits(phone)
        if 8 <= len(digits) <= 18:
            return phone
    return ""


def _whatsapp_href(phone: str) -> str:
    digits = _phone_digits(phone)
    return f"https://wa.me/{digits}" if digits else ""


def _tel_digits(phone: str) -> str:
    value = _clean_value(phone)
    if value.startswith("+"):
        return "+" + _phone_digits(value)
    if value.startswith("00"):
        return "+" + _phone_digits(value[2:])
    return _phone_digits(value)


def _phone_digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def _clean_instagram_handle(value: str) -> str:
    handle = str(value or "").strip().lstrip("@").strip(".,;:，。；、)）]】")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._]{1,28}[A-Za-z0-9]", handle):
        return ""
    if "." in handle and handle.lower().split(".", 1)[0] in {"com", "co", "net", "org"}:
        return ""
    if handle.lower() in {"www", "com", "gram", "instagram", "insta"}:
        return ""
    return handle


def _url_display_value(kind: str, url: str) -> str:
    value = _clean_value(url)
    if kind == "instagram":
        match = re.search(r"instagram\.com/([^/?#]+)", value, re.IGNORECASE)
        handle = _clean_instagram_handle(match.group(1)) if match else ""
        return f"@{handle}" if handle else value
    if kind == "whatsapp":
        match = re.search(r"(?:wa\.me/|phone=)(\d{8,18})", value, re.IGNORECASE)
        return match.group(1) if match else value
    return value


def _clean_value(value: str) -> str:
    return str(value or "").strip().strip(".,;:，。；、)）]】")


def _snippet(text: str, start: int, end: int, window: int = 96) -> str:
    if not text:
        return ""
    left = max(0, start - window // 2)
    right = min(len(text), end + window // 2)
    snippet = text[left:right].strip()
    if left > 0:
        snippet = "..." + snippet
    if right < len(text):
        snippet = snippet + "..."
    return snippet
