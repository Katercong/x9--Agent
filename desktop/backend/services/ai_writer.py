"""AI-assisted outreach copywriter.

``polish_email`` receives a baseline template draft + creator context and
returns one or more personalized variants. The caller (router) owns
fallback behavior so any LLM outage degrades to the un-polished template.

Personalization knobs:
* ``tone`` — formal / casual / friendly. Drives system-prompt phrasing.
* ``language`` — zh / en / es / ja. Forces output language.
* ``max_length`` — soft target body length in chars.
* ``n`` — number of distinct variants to return (1-3). Used by the
  N-choose-1 picker on the frontend.

The creator context now includes ``fit_level``, ``primary_product_fit_score``
and a flattened ``evidence_text`` block (built by ``build_context`` in
``outreach_service``) so generations are grounded in real signals instead
of just the recommendation reason.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from ..config import settings


log = logging.getLogger(__name__)


VALID_TONES = {"formal", "casual", "friendly"}
VALID_LANGUAGES = {"zh", "en", "es", "ja"}
TONE_DESCRIPTIONS = {
    "formal": "Write in a polite, professional tone. Use complete sentences and respectful greetings.",
    "casual": "Write in a casual, peer-to-peer tone. Short sentences, conversational, no corporate jargon.",
    "friendly": "Write in a warm, friendly tone. Direct but enthusiastic; light on formality.",
}
LANGUAGE_NAMES = {
    "zh": "Simplified Chinese (中文)",
    "en": "English",
    "es": "Spanish (Español)",
    "ja": "Japanese (日本語)",
}


def polish_email(
    subject: str,
    body: str,
    context: dict[str, Any],
    *,
    tone: str | None = None,
    language: str | None = None,
    max_length: int | None = None,
    n: int = 1,
) -> list[dict[str, str]] | None:
    """Personalize an outreach draft with OpenAI Chat Completions.

    Returns a list of ``{"subject": str, "body": str}`` variants on success,
    or ``None`` when the API is not configured / errored / produced unusable
    content. The original draft should remain the source of truth.
    """
    if not settings.openai_api_key:
        return None

    tone_key = (tone or "friendly").strip().lower()
    if tone_key not in VALID_TONES:
        tone_key = "friendly"
    lang_key = (language or "en").strip().lower()
    if lang_key not in VALID_LANGUAGES:
        lang_key = "en"
    n_variants = max(1, min(3, int(n or 1)))
    body_limit = int(max_length) if max_length else 600

    payload = _build_payload(subject, body, context, tone_key, lang_key, body_limit, n_variants)

    try:
        response = requests.post(
            _chat_completions_url(),
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=settings.openai_timeout,
        )
        response.raise_for_status()
        choices = response.json().get("choices") or []
    except Exception as exc:  # pragma: no cover — caller falls back to template
        log.warning("AI outreach generation failed: %s", exc)
        return None

    variants: list[dict[str, str]] = []
    for choice in choices:
        try:
            raw = choice.get("message", {}).get("content")
            parsed = _parse_json_object(raw)
        except Exception:
            continue
        polished_subject = str(parsed.get("subject") or "").strip()
        polished_body = str(parsed.get("body") or "").strip()
        if not polished_subject or not polished_body:
            continue
        if "${" in polished_subject or "${" in polished_body:
            continue
        variants.append({"subject": polished_subject[:200], "body": polished_body})

    if not variants:
        return None

    # Some providers ignore the `n` parameter; fall back to repeating
    # the request serially so the caller still gets the variants they asked
    # for (best-effort — we don't retry beyond what we already have).
    while len(variants) < n_variants:
        extra = _generate_once(subject, body, context, tone_key, lang_key, body_limit)
        if not extra:
            break
        if extra not in variants:
            variants.append(extra)
        else:
            # Avoid infinite loop when the model is deterministic.
            break

    return variants[:n_variants]


def _generate_once(
    subject: str,
    body: str,
    context: dict[str, Any],
    tone: str,
    language: str,
    body_limit: int,
) -> dict[str, str] | None:
    payload = _build_payload(subject, body, context, tone, language, body_limit, n=1)
    try:
        response = requests.post(
            _chat_completions_url(),
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=settings.openai_timeout,
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
        parsed = _parse_json_object(raw)
    except Exception as exc:  # pragma: no cover
        log.warning("AI outreach extra variant failed: %s", exc)
        return None
    polished_subject = str(parsed.get("subject") or "").strip()
    polished_body = str(parsed.get("body") or "").strip()
    if not polished_subject or not polished_body:
        return None
    if "${" in polished_subject or "${" in polished_body:
        return None
    return {"subject": polished_subject[:200], "body": polished_body}


def _build_payload(
    subject: str,
    body: str,
    context: dict[str, Any],
    tone: str,
    language: str,
    body_limit: int,
    n: int,
) -> dict[str, Any]:
    system_prompt = (
        "You write concise creator outreach emails for X9. "
        "Use only the facts provided. Do not invent campaign terms, fees, "
        "discounts, deadlines, creator metrics, or product claims. "
        "Personalize naturally using the recommendation reason, product, "
        "collaboration type, queue, creator bio, fit level, and evidence "
        "snippets. The main message must be grounded in those reference "
        "fields. Use the queue and fit level to decide tone and commitment "
        "level, but do not awkwardly mention internal queue codes or scores. "
        f"{TONE_DESCRIPTIONS[tone]} "
        f"Output strictly in {LANGUAGE_NAMES[language]}. "
        f"Keep the body under {body_limit} characters. "
        "Return strict JSON with keys subject and body. The body must be plain text."
    )
    user_prompt = json.dumps(
        {
            "task": "Rewrite the baseline outreach email so it feels tailored to this creator.",
            "baseline": {"subject": subject, "body": body},
            "creator": _compact_context(context),
            "rules": [
                "Use the recommendation reason as the explanation for why this creator is relevant.",
                "Use the product field to name the product direction being pitched.",
                "Use the collaboration field to describe the exact ask.",
                "Use the queue and fit_level fields to choose how cautious or direct the ask should be.",
                "If evidence snippets are provided, weave at most one concrete reference into the body — do not list them all.",
                "Mention at most one specific detail from the creator bio; do not quote long bio text.",
                "If the queue or reason is cautious, or fit_level is C/D, keep the ask low-commitment and avoid paid-budget language.",
                "If fit_level is A or S, you may invite to a longer-term collaboration conversation.",
                "Do not include placeholders like ${name}.",
                "Do not overpraise or sound automated.",
            ],
        },
        ensure_ascii=False,
    )
    payload: dict[str, Any] = {
        "model": settings.openai_model or "gpt-4o-mini",
        "temperature": 0.7,
        "max_tokens": min(1200, body_limit * 4 + 300),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if n > 1:
        payload["n"] = n
    return payload


def _chat_completions_url() -> str:
    return settings.openai_base_url.rstrip("/") + "/chat/completions"


def _parse_json_object(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


def _compact_context(context: dict[str, Any]) -> dict[str, Any]:
    primary = {
        "reason": context.get("recommendation_reason") or "",
        "product": context.get("product_label") or context.get("recommended_product_type") or "",
        "collaboration": context.get("collab_label") or context.get("recommended_collab_type") or "",
        "queue": context.get("queue_label") or context.get("queue_type") or "",
        "creator_bio": context.get("bio_excerpt") or context.get("bio") or "",
        "fit_level": context.get("fit_level") or "",
        "fit_score": context.get("primary_product_fit_score") or "",
        "evidence": context.get("evidence_text") or "",
    }
    keys = (
        "handle",
        "display_name",
        "profile_url",
        "bio",
        "bio_excerpt",
        "recommendation_reason",
        "recommended_product_type",
        "product_label",
        "recommended_collab_type",
        "collab_label",
        "queue_type",
        "queue_label",
        "source_video_title",
        "source_video_description",
        "matched_keywords",
        "followers_count",
        "store_assigned",
        "owner_bd",
        "risk_summary",
        "next_action",
        "fit_level",
        "primary_product_fit_score",
        "evidence_text",
    )
    out: dict[str, Any] = {}
    out["primary_reference_fields"] = {
        key: str(value).strip()[:800]
        for key, value in primary.items()
        if str(value or "").strip()
    }
    for key in keys:
        value = context.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        out[key] = text[:800]
    return out
