"""TK DM script generation — three strategies.

Strategy A (template): ${var} substitution using creator context from build_context().
Strategy B (ai):       LLM writes the entire script given creator context + system prompt.
Strategy C (hybrid):   Fixed X9 brand frame + LLM writes personalized opener only.

Saved prompts are stored as a JSON flat file in DATA_DIR so no DB migration is needed.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from string import Template
from typing import Any

from ..config import DATA_DIR, settings
from ..models.creator import Creator
from .outreach_service import build_context
from .product_asset_service import asset_prompt_context, normalize_product_key

log = logging.getLogger(__name__)

_SPACE_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")

# ---------------------------------------------------------------------------
# Saved prompt store (JSON file, no DB migration)
# ---------------------------------------------------------------------------

_PROMPTS_FILE = DATA_DIR / "tk_script_prompts.json"


def list_prompts() -> list[dict[str, Any]]:
    if not _PROMPTS_FILE.exists():
        return []
    try:
        return json.loads(_PROMPTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_prompt(name: str, prompt: str, strategy: str) -> dict[str, Any]:
    prompts = list_prompts()
    entry: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "name": name,
        "prompt": prompt,
        "strategy": strategy,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    prompts.append(entry)
    _PROMPTS_FILE.write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return entry


def delete_prompt(prompt_id: str) -> bool:
    prompts = list_prompts()
    new = [p for p in prompts if p.get("id") != prompt_id]
    if len(new) == len(prompts):
        return False
    _PROMPTS_FILE.write_text(
        json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True


# ---------------------------------------------------------------------------
# Product paragraph library
# ---------------------------------------------------------------------------

FIXED_COMMISSION = "20"
PRODUCT_SERIES = "Feminine Care, Baby Care, Adult Care, and Pet Care"

_PRODUCT_PARA: dict[str, str] = {
    "feminine_care": (
        "our feminine care products — sanitary pads and pantyliners — soft, breathable, "
        "and designed for everyday comfort and confidence"
    ),
    "adult_care": (
        "our adult care products — bladder control pads and daily protection — "
        "discreet, absorbent, and comfortable for everyday use"
    ),
    "pet_care": (
        "our pet care products — pet diapers and pads — designed with excellent "
        "leak protection, absorbency, and odor control"
    ),
    "baby_care": (
        "our baby care products — ultra-thin diapers and baby essentials — "
        "soft, breathable, and gentle for daily protection"
    ),
}
_PRODUCT_PARA_DEFAULT = (
    "our full range of care products — feminine care, baby care, adult care, "
    "and pet care — all designed for comfort and daily protection"
)

_PRODUCT_KEY_MAP: dict[tuple[str, ...], str] = {
    ("feminine", "female", "sanitary", "pantyliner", "women", "period", "pad", "liner"): "feminine_care",
    ("adult", "bladder", "incontinence"): "adult_care",
    ("pet", "dog", "cat", "animal"): "pet_care",
    ("baby", "infant", "diaper", "mom"): "baby_care",
}


def _detect_product_key(creator: Creator) -> str:
    raw = (
        (getattr(creator, "recommended_product_type", "") or "")
        or (getattr(creator, "primary_product_category", "") or "")
    ).lower()
    normalized = normalize_product_key(raw)
    if normalized != raw:
        return normalized
    for keywords, key in _PRODUCT_KEY_MAP.items():
        if any(k in raw for k in keywords):
            return key
    return ""


def _greeting_name(ctx: dict[str, Any]) -> str:
    raw = str(ctx.get("display_name") or ctx.get("handle") or "there").strip()
    raw = raw.lstrip("@").strip()
    if not raw:
        return "there"
    first = raw.split()[0].strip(" ,.;:")
    return first or raw


def _clean_personal_text(value: Any, limit: int = 92) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = _URL_RE.sub("", text)
    text = _EMAIL_RE.sub("", text)
    text = _SPACE_RE.sub(" ", text).strip(" -_,.;:|\"'")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip(" -_,.;:") + "..."


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _keyword_angle(value: str) -> str:
    parts = [
        _clean_personal_text(part, 28)
        for part in re.split(r"[,;|/]+", str(value or ""))
    ]
    parts = [part for part in parts if part]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:2])


def _personalized_interest(ctx: dict[str, Any]) -> str:
    raw_text = " ".join(
        str(ctx.get(key) or "")
        for key in (
            "video_title",
            "matched_keywords",
            "bio_excerpt",
            "recommendation_reason",
            "evidence_text",
        )
    ).lower()

    video_title = _clean_personal_text(ctx.get("video_title"), 76)
    if video_title:
        return (
            f'We came across your video "{video_title}" and really liked how '
            "natural and relatable it felt."
        )

    if _contains_any(raw_text, ("women over 40", "over 40", "40+")) and _contains_any(
        raw_text, ("wellness", "self-care", "self care")
    ):
        return (
            "We came across your content and really like how warmly you "
            "encourage women over 40 to care for themselves."
        )

    if _contains_any(raw_text, ("artist", "mom", "mother")) and _contains_any(
        raw_text, ("wellness", "self-care", "self care")
    ):
        return (
            "We came across your content and really like the personal, warm "
            "self-care perspective you share."
        )

    if _contains_any(raw_text, ("wellness", "self-care", "self care")):
        return (
            "We came across your content and really like how you make wellness "
            "and self-care feel approachable and personal."
        )

    if _contains_any(raw_text, ("beauty", "skincare", "makeup", "routine")):
        return (
            "We came across your content and really like how warm, practical, "
            "and easy to connect with your beauty content feels."
        )

    if _contains_any(raw_text, ("home", "lifestyle", "finds", "daily routine")):
        return (
            "We came across your content and really like how you turn everyday "
            "home and lifestyle finds into helpful recommendations."
        )

    if _contains_any(raw_text, ("pet", "dog", "cat", "puppy")):
        return (
            "We came across your content and really like how relatable and "
            "practical your pet content feels for everyday pet owners."
        )

    if _contains_any(raw_text, ("mom", "mother", "baby", "family", "parent")):
        return (
            "We came across your content and really like the warm, practical "
            "perspective you bring to family routines."
        )

    matched_keywords = _keyword_angle(ctx.get("matched_keywords", ""))
    if matched_keywords:
        return (
            f"We came across your content and really like your perspective on "
            f"{matched_keywords}."
        )

    bio_excerpt = _clean_personal_text(ctx.get("bio_excerpt"), 76)
    if bio_excerpt:
        return (
            "We came across your content and really like the personal voice "
            "you bring to your page."
        )

    return "We came across your content and really like what you create."


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------


def build_tk_context(
    creator: Creator,
    commission: int = 20,
    product_asset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build substitution context for TK DM scripts (English, personalized)."""
    ctx: dict[str, Any] = build_context(creator, language="en")
    product_key = _detect_product_key(creator)
    ctx["commission"] = FIXED_COMMISSION
    ctx["product_key"] = product_key or "all"
    ctx["product_series"] = PRODUCT_SERIES
    ctx["product_para"] = _PRODUCT_PARA.get(product_key, _PRODUCT_PARA_DEFAULT)
    ctx.update(asset_prompt_context(product_asset))
    ctx["commission"] = FIXED_COMMISSION
    ctx["product_series"] = PRODUCT_SERIES
    ctx["greeting_name"] = _greeting_name(ctx)
    ctx["personalized_interest"] = _personalized_interest(ctx)
    return ctx


def build_tk_email_subject(ctx: dict[str, Any]) -> str:
    """Short subject used when a TK script is inserted into the email flow."""
    display_name = (
        str(ctx.get("display_name") or "").strip()
        or f"@{str(ctx.get('handle') or '').strip()}"
        or "Creator"
    )
    return f"X9 x {display_name} - collaboration idea with 20% commission"


# ---------------------------------------------------------------------------
# Strategy A — template + ${var} substitution
# ---------------------------------------------------------------------------

_TEMPLATE_A = """\
Hi ${greeting_name},

I'm reaching out from X9. We're a care brand with four product series: ${product_series}. They cover everyday needs for women, babies, adults, and pets.

${personalized_interest} Your content feels natural and easy to trust, so we think there could be a good fit between your page and our care products.

We'd love to explore a collaboration with you. If you're interested, we can first share the product line that best matches your audience, along with product images, key details, and a simple content idea for you to review.

For this collaboration, we offer 20% commission on sales generated through your content. We'll also provide the product information and tracking support before you decide how to present it.

Looking forward to your reply. If this sounds interesting, just let us know and we'll send over the next details."""


def generate_strategy_template(ctx: dict[str, Any]) -> str:
    """Strategy A: enhanced template with creator-specific variable substitution."""
    return Template(_TEMPLATE_A).safe_substitute(ctx)


# ---------------------------------------------------------------------------
# Strategy B — full AI generation
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_PROMPT_B = (
    "You write concise TikTok/email outreach scripts for X9.\n\n"
    "Mandatory business logic, do not change or contradict it:\n"
    "- X9 is a brand with four product series: Feminine Care, Baby Care, Adult Care, and Pet Care.\n"
    "- Say we came across the creator's content and are interested in what they create.\n"
    "- Say we would love to explore a collaboration.\n"
    "- Offer exactly 20% commission on sales.\n"
    "- Close by looking forward to their reply.\n\n"
    "Writing rules:\n"
    "- Write in English, warm, natural, and creator-friendly, like a real BD message.\n"
    "- Keep the message complete but not long: 5-6 short paragraphs, 130-170 words.\n"
    "- You may personalize one phrase using the creator's content, bio, keywords, or selected SKU, but do not add new offers.\n"
    "- Do not mention paid tests, samples, free products, hard KPIs, fees, shipping, WhatsApp, or any commission rate other than 20%.\n"
    "- Return plain text only. No subject line. No JSON."
)


def generate_strategy_ai(
    ctx: dict[str, Any],
    custom_prompt: str | None = None,
) -> tuple[str, str]:
    """Strategy B: LLM generates the entire script.

    Returns ``(script, ai_status)`` where ai_status is one of:
    ``'generated' | 'not_configured' | 'fallback'``
    """
    if not settings.openai_api_key:
        return generate_strategy_template(ctx), "not_configured"

    return generate_strategy_template(ctx), "final_rules"

    extra_prompt = (custom_prompt or "").strip()
    system_prompt = (
        _DEFAULT_SYSTEM_PROMPT_B
        if not extra_prompt
        else f"{_DEFAULT_SYSTEM_PROMPT_B}\n\nOptional style notes from user:\n{extra_prompt}"
    )

    user_content = json.dumps(
        {
            "task": "Write a personalized TikTok DM outreach script for this creator.",
            "creator": {
                "handle": ctx.get("handle", ""),
                "display_name": ctx.get("display_name", ""),
                "bio_excerpt": ctx.get("bio_excerpt", ""),
                "bio": (ctx.get("bio", "") or "")[:300],
                "video_title": ctx.get("video_title", ""),
                "matched_keywords": ctx.get("matched_keywords", ""),
                "recommendation_reason": ctx.get("recommendation_reason", ""),
                "product_label": ctx.get("product_label", ""),
                "selected_sku": {
                    "name": ctx.get("product_asset_name", ""),
                    "sku_code": ctx.get("product_sku_code", ""),
                    "selling_points": ctx.get("product_selling_points", ""),
                    "product_description": ctx.get("product_para", ""),
                },
                "collab_type": ctx.get("collab_label", ""),
                "followers_count": ctx.get("followers_count", ""),
                "evidence": (ctx.get("evidence_text", "") or "")[:300],
                "commission_pct": ctx.get("commission", "20"),
            },
        },
        ensure_ascii=False,
    )

    import requests  # noqa: PLC0415

    try:
        resp = requests.post(
            settings.openai_base_url.rstrip("/") + "/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_model or "gpt-4o-mini",
                "temperature": 0.75,
                "max_tokens": 600,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            },
            timeout=float(settings.openai_timeout or 30),
        )
        resp.raise_for_status()
        script = resp.json()["choices"][0]["message"]["content"].strip()
        return script, "generated"
    except Exception as exc:
        log.warning("TK script AI generation (strategy B) failed: %s", exc)
        return generate_strategy_template(ctx), "fallback"


# ---------------------------------------------------------------------------
# Strategy C — hybrid: fixed frame + AI personalized opener
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_PROMPT_C = (
    "Write one short personalized sentence for a TikTok DM or email from X9.\n\n"
    "The opener must:\n"
    "- Say we came across the creator's content and are interested in what they create.\n"
    "- Optionally mention one specific content angle if provided.\n"
    "- Do not mention products, commission, samples, fees, or greetings.\n"
    "- Plain text only."
)

_HYBRID_OPENER_FALLBACK = (
    "We came across your content and are interested in what you create."
)

_HYBRID_FRAME = (
    "Hi {greeting_name},\n\n"
    "I'm reaching out from X9. We're a care brand with four product series: {product_series}. "
    "They cover everyday needs for women, babies, adults, and pets.\n\n"
    "{opener} Your content feels natural and easy to trust, so we think there could be a good fit between your page and our care products.\n\n"
    "We'd love to explore a collaboration with you. If you're interested, we can first share the product line that best matches your audience, along with product images, key details, and a simple content idea for you to review.\n\n"
    "For this collaboration, we offer {commission}% commission on sales generated through your content. We'll also provide the product information and tracking support before you decide how to present it.\n\n"
    "Looking forward to your reply. If this sounds interesting, just let us know and we'll send over the next details.\n\n"
    "Best,\n"
    "X9 Team"
)


def generate_strategy_hybrid(
    ctx: dict[str, Any],
    custom_prompt: str | None = None,
) -> tuple[str, str]:
    """Strategy C: fixed X9 brand frame + LLM writes personalized opener only.

    Returns ``(script, ai_status)`` where ai_status is one of:
    ``'hybrid' | 'template' | 'fallback'``
    """
    return generate_strategy_template(ctx), "final_rules"

    opener: str | None = None
    ai_status = "template"

    if settings.openai_api_key:
        product_label = ctx.get("product_label", "care products")
        extra_prompt = (custom_prompt or "").strip()
        base_prompt = _DEFAULT_SYSTEM_PROMPT_C.format(product_label=product_label)
        system_prompt = (
            base_prompt
            if not extra_prompt
            else f"{base_prompt}\n\nOptional style notes from user:\n{extra_prompt}"
        )
        user_content = json.dumps(
            {
                "creator": {
                    "handle": ctx.get("handle", ""),
                    "bio_excerpt": ctx.get("bio_excerpt", ""),
                    "bio": (ctx.get("bio", "") or "")[:200],
                    "video_title": ctx.get("video_title", ""),
                    "matched_keywords": ctx.get("matched_keywords", ""),
                    "recommendation_reason": ctx.get("recommendation_reason", ""),
                    "product_label": product_label,
                    "selected_sku": {
                        "name": ctx.get("product_asset_name", ""),
                        "sku_code": ctx.get("product_sku_code", ""),
                        "selling_points": ctx.get("product_selling_points", ""),
                    },
                },
            },
            ensure_ascii=False,
        )

        import requests  # noqa: PLC0415

        try:
            resp = requests.post(
                settings.openai_base_url.rstrip("/") + "/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_model or "gpt-4o-mini",
                    "temperature": 0.7,
                    "max_tokens": 150,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                },
                timeout=float(settings.openai_timeout or 30),
            )
            resp.raise_for_status()
            opener = resp.json()["choices"][0]["message"]["content"].strip()
            ai_status = "hybrid"
        except Exception as exc:
            log.warning("TK hybrid opener generation failed: %s", exc)
            ai_status = "fallback"

    if not opener:
        opener = Template(_HYBRID_OPENER_FALLBACK).safe_substitute(ctx).strip()

    script = _HYBRID_FRAME.format(
        greeting_name=ctx.get("greeting_name", _greeting_name(ctx)),
        opener=opener,
        product_series=ctx.get("product_series", PRODUCT_SERIES),
        commission=ctx.get("commission", "20"),
    )
    return script, ai_status
