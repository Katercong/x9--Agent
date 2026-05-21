"""TK DM script generation — three strategies.

Strategy A (template): ${var} substitution using creator context from build_context().
Strategy B (ai):       LLM writes the entire script given creator context + system prompt.
Strategy C (hybrid):   Fixed X9 brand frame + LLM writes personalized opener only.

Saved prompts are stored as a JSON flat file in DATA_DIR so no DB migration is needed.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from string import Template
from typing import Any

from ..config import DATA_DIR, settings
from ..models.creator import Creator
from .outreach_service import build_context

log = logging.getLogger(__name__)

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
    ("feminine", "female", "sanitary", "pantyliner", "women"): "feminine_care",
    ("adult", "bladder", "incontinence"): "adult_care",
    ("pet", "dog", "cat", "animal"): "pet_care",
    ("baby", "infant", "diaper"): "baby_care",
}


def _detect_product_key(creator: Creator) -> str:
    raw = (getattr(creator, "recommended_product_type", "") or "").lower()
    for keywords, key in _PRODUCT_KEY_MAP.items():
        if any(k in raw for k in keywords):
            return key
    return ""


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------


def build_tk_context(creator: Creator, commission: int = 20) -> dict[str, Any]:
    """Build substitution context for TK DM scripts (English, personalized)."""
    ctx: dict[str, Any] = build_context(creator, language="en")
    product_key = _detect_product_key(creator)
    ctx["commission"] = str(commission)
    ctx["product_key"] = product_key or "all"
    ctx["product_para"] = _PRODUCT_PARA.get(product_key, _PRODUCT_PARA_DEFAULT)
    return ctx


# ---------------------------------------------------------------------------
# Strategy A — template + ${var} substitution
# ---------------------------------------------------------------------------

_TEMPLATE_A = """\
Hi @${handle},

I noticed your content${video_hint}${bio_hint}— your authentic style and engaged audience caught our attention.

We're X9, a care brand specializing in ${product_label}. We'd love to invite you as a TikTok Creator Partner.

Specifically, we'd love to feature ${product_para}.

You'll earn a ${commission}% commission on all sales from your content — no hard KPIs, just genuine collaboration.

If you're interested, we'd love to send an official shop invitation. Feel free to reach out anytime!

Looking forward to working together,
X9 Brand · Creator Partnerships"""


def generate_strategy_template(ctx: dict[str, Any]) -> str:
    """Strategy A: enhanced template with creator-specific variable substitution."""
    return Template(_TEMPLATE_A).safe_substitute(ctx)


# ---------------------------------------------------------------------------
# Strategy B — full AI generation
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_PROMPT_B = (
    "You write concise, personalized TikTok DM outreach scripts for X9, a care brand "
    "specializing in feminine care, adult care, pet care, and baby care products.\n\n"
    "Rules:\n"
    "- Write in English, warm and direct (TikTok DM tone, not a formal email)\n"
    "- Personalize to this creator's actual content, bio, and keywords — be specific\n"
    "- Under 300 words total\n"
    "- Structure: personalized opener referencing their specific content → brief brand intro "
    "→ why their audience fits this product → collab ask → commission info → friendly closing\n"
    "- Do not invent facts, fees, or product claims beyond what is provided\n"
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

    system_prompt = (custom_prompt or "").strip() or _DEFAULT_SYSTEM_PROMPT_B

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
    "Write a personalized 2-3 sentence opening for a TikTok DM from X9 (a {product_label} brand).\n\n"
    "The opener must:\n"
    "- Reference something specific from this creator's content, bio, or keywords — be concrete\n"
    "- Make a natural connection to why {product_label} would fit their audience\n"
    "- Be warm and direct, not corporate or generic\n"
    "- Plain text only. Do NOT include a greeting like 'Hi @handle' — just the observation sentences."
)

_HYBRID_OPENER_FALLBACK = (
    "I noticed your content${video_hint}${bio_hint}"
    "your authentic style and engaged audience really caught our attention."
)

_HYBRID_FRAME = (
    "Hi @{handle},\n\n"
    "{opener}\n\n"
    "We're X9, a care brand specializing in {product_label}. We'd love to invite you as a TikTok Creator Partner.\n\n"
    "Specifically, we'd love to feature {product_para}.\n\n"
    "You'll earn a {commission}% commission on all sales from your content — no hard KPIs, just genuine collaboration.\n\n"
    "If you're interested, we'd love to send an official shop invitation. Feel free to reach out anytime!\n\n"
    "Looking forward to working together,\n"
    "X9 Brand · Creator Partnerships"
)


def generate_strategy_hybrid(
    ctx: dict[str, Any],
    custom_prompt: str | None = None,
) -> tuple[str, str]:
    """Strategy C: fixed X9 brand frame + LLM writes personalized opener only.

    Returns ``(script, ai_status)`` where ai_status is one of:
    ``'hybrid' | 'template' | 'fallback'``
    """
    opener: str | None = None
    ai_status = "template"

    if settings.openai_api_key:
        product_label = ctx.get("product_label", "care products")
        system_prompt = (
            (custom_prompt or "").strip()
            or _DEFAULT_SYSTEM_PROMPT_C.format(product_label=product_label)
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
        handle=ctx.get("handle", ""),
        opener=opener,
        product_label=ctx.get("product_label", "care products"),
        product_para=ctx.get("product_para", _PRODUCT_PARA_DEFAULT),
        commission=ctx.get("commission", "20"),
    )
    return script, ai_status
