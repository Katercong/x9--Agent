"""Outreach (建联) template rendering and AI-script abstraction.

Phase 1 (MVP): plain ``string.Template`` substitution against a context built
from the ``Creator`` row. Phase 2 will plug into an LLM behind
:func:`generate_with_ai`, but the router/UI never needs to change.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from string import Template
from typing import Any, Iterable

from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.outreach_template import OutreachTemplate
from ..utils.id_utils import new_id
from ..utils.json_utils import loads_json_list


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default templates — seeded into the DB on first boot.
# ---------------------------------------------------------------------------

DEFAULT_SIGNATURE_ZH = (
    "\n\n期待你的回复，\n${sender_name}\n${sender_signature}"
)
DEFAULT_SIGNATURE_EN = (
    "\n\nLooking forward to hearing from you,\n${sender_name}\n${sender_signature}"
)


def default_templates() -> list[dict[str, Any]]:
    """Built-in templates seeded on first launch.

    Keep these short and editable in UI later. ``${var}`` placeholders use
    safe ``string.Template`` substitution.
    """
    return [
        {
            "id": new_id("tpl"),
            "name": "样品合作 · 默认（中文）",
            "description": "面向寄样合作 / 赠品测评的标准开场。",
            "language": "zh",
            "collab_type": "sample_collab",
            "product_type": None,
            "is_default": 1,
            "is_active": 1,
            "sender_name": "X9 品牌合作",
            "sender_signature": "X9 Brand · Creator Partnerships",
            "subject_template": "Hi ${display_name}，想和你聊一个${product_label}的合作",
            "body_template": (
                "你好 @${handle}，\n\n"
                "我是 ${sender_name}，最近在 TikTok 看到你的内容${video_hint}，"
                "${bio_hint}觉得你的风格非常适合我们正在推的${product_label}。\n\n"
                "我们想做一次${collab_label}：免费寄样给你，希望你能拍一条真实使用感受的视频，"
                "不需要硬广，按你自己的风格来就好。\n\n"
                "如果有兴趣，回复这封邮件告诉我你的收件地址和最近的内容档期就行。\n"
                "也欢迎你提任何问题。"
                + DEFAULT_SIGNATURE_ZH
            ),
        },
        {
            "id": new_id("tpl"),
            "name": "联盟带货 · 默认（中文）",
            "description": "面向 affiliate / 联盟分成 的开场。",
            "language": "zh",
            "collab_type": "affiliate_collab",
            "product_type": None,
            "is_default": 0,
            "is_active": 1,
            "sender_name": "X9 品牌合作",
            "sender_signature": "X9 Brand · Affiliate Program",
            "subject_template": "Hi ${display_name}，邀请你加入我们的${product_label}联盟",
            "body_template": (
                "你好 @${handle}，\n\n"
                "我是 ${sender_name}。看到你${video_hint}做的内容很自然、互动也好，"
                "${bio_hint}所以想邀请你加入我们的${product_label}联盟计划。\n\n"
                "合作方式：你帮我们带货${product_label}，按订单分成，没有硬性 KPI；"
                "首单我们会先寄样让你确认产品质感再决定是否上链接。\n\n"
                "如果方便的话，可以告诉我你的收件信息和你常用的带货平台，我把详细方案发给你。"
                + DEFAULT_SIGNATURE_ZH
            ),
        },
        {
            "id": new_id("tpl"),
            "name": "Sample Collab · Default (English)",
            "description": "Default English opener for gifted/sample collabs.",
            "language": "en",
            "collab_type": "sample_collab",
            "product_type": None,
            "is_default": 0,
            "is_active": 1,
            "sender_name": "X9 Partnerships",
            "sender_signature": "X9 Brand · Creator Partnerships",
            "subject_template": "Hi ${display_name} — quick collab idea on ${product_label}",
            "body_template": (
                "Hi @${handle},\n\n"
                "I'm ${sender_name} from X9. I came across your TikTok${video_hint} "
                "${bio_hint}and your style feels like a great fit for our ${product_label} line.\n\n"
                "We'd love to send you a free sample for an honest, on-brand "
                "${collab_label}-style video — no script, just your real take.\n\n"
                "If that sounds interesting, just reply with a shipping address and a "
                "rough timing for your next post. Happy to answer any questions."
                + DEFAULT_SIGNATURE_EN
            ),
        },
        {
            "id": new_id("tpl"),
            "name": "通用建联 · 默认（中文）",
            "description": "未匹配到合作类型时的兜底模板。",
            "language": "zh",
            "collab_type": None,
            "product_type": None,
            "is_default": 1,
            "is_active": 1,
            "sender_name": "X9 品牌合作",
            "sender_signature": "X9 Brand · Creator Partnerships",
            "subject_template": "Hi ${display_name}，想和你聊一个内容合作",
            "body_template": (
                "你好 @${handle}，\n\n"
                "我是 ${sender_name}。${video_hint}${bio_hint}"
                "想和你聊一个${product_label}方向的合作。\n\n"
                "如果有兴趣，回复这封邮件，我把详细方案发给你。"
                + DEFAULT_SIGNATURE_ZH
            ),
        },
    ]


# ---------------------------------------------------------------------------
# Context building & rendering
# ---------------------------------------------------------------------------

PRODUCT_LABELS = {
    "feminine_care": "女性护理",
    "feminine_care_daily_liner": "日用护垫",
    "period_care_pad": "经期护理垫",
    "sensitive_skin_care": "敏感肌护理",
    "travel_hygiene_pack": "旅行卫生包",
    "postpartum_mom_care": "产后妈妈护理",
    "teen_first_period_care": "少女初潮护理",
    "wellness_self_care_bundle": "健康自护理组合",
    "pet_care": "宠物护理",
    "home_care": "家居护理",
    "adult_care": "成人护理",
    "mom_baby": "母婴",
    "health_mask": "健康口罩",
    "general_lifestyle": "生活方式",
}

PRODUCT_LABELS_EN = {
    "feminine_care": "feminine care",
    "feminine_care_daily_liner": "daily liners",
    "period_care_pad": "period care pads",
    "sensitive_skin_care": "sensitive skin care",
    "travel_hygiene_pack": "travel hygiene packs",
    "postpartum_mom_care": "postpartum care",
    "teen_first_period_care": "first-period care for teens",
    "wellness_self_care_bundle": "wellness and self-care bundles",
    "pet_care": "pet care",
    "home_care": "home care",
    "adult_care": "adult care",
    "mom_baby": "mom and baby care",
    "health_mask": "health masks",
    "general_lifestyle": "lifestyle products",
}

COLLAB_LABELS = {
    "sample_collab": "寄样合作",
    "gifted_review": "赠品测评",
    "affiliate_collab": "联盟分成",
    "paid_test_collab": "付费测试",
    "brand_awareness_collab": "品牌曝光",
}

COLLAB_LABELS_EN = {
    "sample_collab": "sample collaboration",
    "gifted_review": "gifted review",
    "affiliate_collab": "affiliate collaboration",
    "paid_test_collab": "paid test collaboration",
    "brand_awareness_collab": "brand awareness collaboration",
}

QUEUE_LABELS = {
    "feminine_conversion_queue": "feminine care conversion queue",
    "feminine_warm_lead_queue": "feminine care warm lead",
    "sample_collab_test_queue": "sample collaboration test",
    "affiliate_test_queue": "affiliate collaboration test",
    "macro_brand_awareness_queue": "macro creator brand awareness",
    "manual_review_queue": "manual review queue",
    "low_confidence_hold": "low-confidence hold",
    "general_lifestyle_hold": "general lifestyle hold",
    "not_recommended_queue": "not recommended",
    "no_contact_info_queue": "missing contact info",
}


@dataclass
class RenderResult:
    subject: str
    body: str
    context: dict[str, Any]
    template_id: str | None
    ai_used: bool = False
    # When use_ai=True and the model returned multiple alternates, the extra
    # ones beyond the chosen primary live here so the UI can offer N-pick-1.
    variants: list[dict[str, str]] | None = None
    tone: str | None = None
    language: str | None = None
    ai_status: str = "template"
    ai_message: str | None = None


def _label(value: str | None, mapping: dict[str, str], fallback: str = "") -> str:
    if not value:
        return fallback
    return mapping.get(value, value.replace("_", " "))


def _bio_excerpt(bio: str | None, max_chars: int = 120) -> str:
    if not bio:
        return ""
    text = " ".join(str(bio).split())
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def _format_keyword_list(values: Iterable[Any]) -> str:
    cleaned: list[str] = []
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s and s not in cleaned:
            cleaned.append(s)
        if len(cleaned) >= 3:
            break
    return "、".join(cleaned)


def _format_keywords_for_language(values: Iterable[Any], language: str) -> str:
    cleaned: list[str] = []
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s and s not in cleaned:
            cleaned.append(s)
        if len(cleaned) >= 3:
            break
    return ", ".join(cleaned) if language == "en" else "、".join(cleaned)


def build_context(
    creator: Creator,
    *,
    sender_name: str | None = None,
    sender_signature: str | None = None,
    language: str | None = None,
) -> dict[str, str]:
    """Build the ``${var}`` substitution context for one creator.

    Always returns string values so missing fields render as empty strings
    instead of raising ``KeyError`` from ``Template.substitute``.
    """
    lang = "en" if (language or "").lower().startswith("en") else "zh"
    matched_keywords = loads_json_list(creator.matched_keywords_json)
    keyword_str = _format_keywords_for_language(matched_keywords, lang)

    video_title = (creator.source_video_title or "").strip()
    video_hint = ""
    if video_title:
        snippet = video_title if len(video_title) <= 40 else video_title[:39] + "…"
        video_hint = f', especially your video "{snippet},"' if lang == "en" else f"——尤其是《{snippet}》——"
    elif keyword_str:
        video_hint = f" (keywords: {keyword_str})" if lang == "en" else f"（关键词：{keyword_str}）"

    bio_excerpt = _bio_excerpt(creator.bio)
    bio_hint = ""
    if bio_excerpt:
        bio_hint = f'your bio mentions "{bio_excerpt}", ' if lang == "en" else f"看了你简介里写的「{bio_excerpt}」，"
    elif keyword_str:
        bio_hint = f"you often post about {keyword_str}, " if lang == "en" else f"看你常出{keyword_str}相关内容，"

    product_labels = PRODUCT_LABELS_EN if lang == "en" else PRODUCT_LABELS
    collab_labels = COLLAB_LABELS_EN if lang == "en" else COLLAB_LABELS
    product_label = _label(
        creator.recommended_product_type,
        product_labels,
        fallback=("our new products" if lang == "en" else "我们的新品"),
    )
    collab_label = _label(
        creator.recommended_collab_type,
        collab_labels,
        fallback=("content collaboration" if lang == "en" else "内容合作"),
    )
    queue_label = _label(creator.queue_type, QUEUE_LABELS, fallback="")

    display_name = (creator.display_name or creator.handle or "there").strip()
    bio = " ".join(str(creator.bio or "").split())

    # Deep-personalization fields: fit_level + score + evidence snippets.
    # evidence_text_json is buckets of {bucket_name: [snippets...]}; we flatten
    # to <=480 chars total so the AI prompt stays small but grounded.
    evidence_text = _flatten_evidence(getattr(creator, "evidence_text_json", None))
    fit_level = (getattr(creator, "fit_level", None) or "").strip()
    primary_fit_score = getattr(creator, "primary_product_fit_score", None)

    context = {
        "handle": creator.handle or "",
        "display_name": display_name,
        "profile_url": creator.profile_url or "",
        "bio": bio,
        "bio_excerpt": bio_excerpt,
        "bio_hint": bio_hint,
        "matched_keywords": keyword_str,
        "video_title": video_title,
        "video_hint": video_hint,
        "source_video_title": video_title,
        "source_video_description": creator.source_video_description or "",
        "search_keyword": creator.search_keyword or "",
        "followers_count": creator.followers_count or "",
        "recommendation_reason": creator.recommendation_reason or "",
        "risk_summary": creator.risk_summary or "",
        "next_action": creator.next_action or "",
        "product_type": creator.recommended_product_type or "",
        "recommended_product_type": creator.recommended_product_type or "",
        "product_label": product_label,
        "collab_type": creator.recommended_collab_type or "",
        "recommended_collab_type": creator.recommended_collab_type or "",
        "collab_label": collab_label,
        "queue_type": creator.queue_type or "",
        "queue_label": queue_label,
        "store_assigned": creator.store_assigned or "",
        "owner_bd": creator.owner_bd or "",
        "fit_level": fit_level,
        "primary_product_fit_score": primary_fit_score or "",
        "evidence_text": evidence_text,
        "sender_name": sender_name or creator.owner_bd or ("X9 Partnerships" if lang == "en" else "X9 品牌合作"),
        "sender_signature": sender_signature or "X9 Brand · Creator Partnerships",
    }
    return {k: str(v) for k, v in context.items()}


def _flatten_evidence(raw: str | None, max_chars: int = 480) -> str:
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except Exception:
        return ""
    pieces: list[str] = []
    if isinstance(data, dict):
        for bucket, items in data.items():
            if not isinstance(items, list):
                continue
            for item in items:
                text = str(item).strip()
                if text:
                    pieces.append(f"[{bucket}] {text}")
    elif isinstance(data, list):
        pieces = [str(item).strip() for item in data if str(item).strip()]
    flat = " · ".join(pieces)
    return flat if len(flat) <= max_chars else flat[: max_chars - 1] + "…"


def _safe_render(template_str: str, context: dict[str, str]) -> str:
    """Render with ``Template.safe_substitute`` so missing keys leave the
    placeholder visible (handy for templates authored mid-flight) instead of
    blowing up the request."""
    return Template(template_str or "").safe_substitute(context)


def render_template(
    template: OutreachTemplate,
    creator: Creator,
    *,
    sender_name: str | None = None,
    sender_signature: str | None = None,
    language: str | None = None,
) -> RenderResult:
    ctx = build_context(
        creator,
        sender_name=sender_name or template.sender_name,
        sender_signature=sender_signature or template.sender_signature,
        language=language or template.language,
    )
    subject = _safe_render(template.subject_template, ctx).strip()
    body = _safe_render(template.body_template, ctx)
    return RenderResult(subject=subject, body=body, context=ctx, template_id=template.id)


def pick_template(
    db: Session,
    creator: Creator,
    *,
    template_id: str | None = None,
    language: str | None = None,
) -> OutreachTemplate | None:
    """Pick the best template for a creator.

    Resolution order (best → worst):
      1. explicit ``template_id``
      2. matches ``recommended_collab_type`` in requested ``language``
      3. ``is_default=1`` template in requested ``language``
      4. any template in requested ``language``
      5. matches ``recommended_collab_type`` in any language
      6. any ``is_default=1`` template
      7. any active template
    """
    if template_id:
        tpl = db.get(OutreachTemplate, template_id)
        if tpl and tpl.is_active:
            return tpl

    base_q = db.query(OutreachTemplate).filter(OutreachTemplate.is_active == 1)
    department_code = getattr(creator, "department_code", None)
    if department_code:
        base_q = base_q.filter(
            (OutreachTemplate.department_code == department_code) |
            (OutreachTemplate.department_code.is_(None))
        )
    collab = creator.recommended_collab_type
    lang = language or "zh"

    if collab:
        match = (
            base_q.filter(
                OutreachTemplate.collab_type == collab,
                OutreachTemplate.language == lang,
            )
            .order_by(OutreachTemplate.is_default.desc())
            .first()
        )
        if match:
            return match

    fallback = (
        base_q.filter(OutreachTemplate.collab_type.is_(None), OutreachTemplate.language == lang)
        .order_by(OutreachTemplate.is_default.desc())
        .first()
    )
    if fallback:
        return fallback

    language_match = (
        base_q.filter(OutreachTemplate.language == lang)
        .order_by(OutreachTemplate.is_default.desc())
        .first()
    )
    if language_match:
        return language_match

    if collab:
        match = (
            base_q.filter(OutreachTemplate.collab_type == collab)
            .order_by(OutreachTemplate.is_default.desc())
            .first()
        )
        if match:
            return match
    return base_q.order_by(OutreachTemplate.is_default.desc()).first()


def context_to_json(context: dict[str, Any]) -> str:
    return json.dumps(context, ensure_ascii=False)


def generate_x9_care_keyword_script(
    creator: Creator,
    keywords: str,
    *,
    sender_name: str | None = None,
    sender_signature: str | None = None,
) -> RenderResult:
    """Render the Mercy/X9 Care reference pitch from user-supplied keywords."""
    ctx = build_context(
        creator,
        sender_name=sender_name or "Mercy",
        sender_signature=sender_signature or "X9 Care",
        language="en",
    )
    terms = _split_keyword_prompt(keywords)
    keyword_text = ", ".join(terms)
    product_focus = _keyword_product_focus(terms, ctx.get("product_label") or "")
    style_phrase = _keyword_style_phrase(terms)
    content_ideas = _keyword_content_ideas(terms)
    display_name = ctx.get("display_name") or "there"
    subject = f"Hi {display_name}, X9 Care collaboration?"
    body = (
        f"Hi {display_name},\n\n"
        f"I'm Mercy from X9 - a care brand that produces high-quality {product_focus}.\n\n"
        f"I came across your page and love your {style_phrase}. "
        "You'd be a great fit as a brand ambassador for X9 Care.\n\n"
        "Here's what we offer:\n"
        "🎁 Free product samples (your choice)\n"
        "💰 10% commission on sales using your unique code on TikTok Shop\n"
        "🔁 Long-term collaboration potential\n\n"
        "What we're looking for:\n"
        f"📦 {content_ideas}\n"
        "🗣️ Natural, like recommending a friend\n"
        "👶🐾 Baby or pet face optional - we respect your privacy\n\n"
        "Interested?\n\n"
        "Just reply \"YES\" and I'll send more details.\n"
        "Or contact me on WhatsApp: +1 323 925 6391\n\n"
        "Thanks!\n"
        "Mercy\n"
        "X9 Care"
    )
    ctx.update(
        {
            "script_keywords": keyword_text,
            "product_focus": product_focus,
            "style_phrase": style_phrase,
            "content_ideas": content_ideas,
            "sender_name": "Mercy",
            "sender_signature": "X9 Care",
        }
    )
    return RenderResult(
        subject=subject,
        body=body,
        context=ctx,
        template_id=None,
        ai_used=False,
        tone="friendly",
        language="en",
        ai_status="keyword_reference",
        ai_message="X9 Care keyword reference script generated.",
    )


def _split_keyword_prompt(raw: str) -> list[str]:
    terms: list[str] = []
    for item in re.split(r"[,，;；\n|]+", raw or ""):
        term = " ".join(item.strip().split())
        if term and term.lower() not in {x.lower() for x in terms}:
            terms.append(term[:80])
        if len(terms) >= 10:
            break
    return terms


def _keyword_product_focus(terms: list[str], fallback_product: str) -> str:
    joined = " ".join(terms).lower()
    products: list[str] = []
    if any(word in joined for word in ("baby", "diaper", "diapers", "mom", "mother")):
        products.append("baby diapers")
    if any(word in joined for word in ("pet", "dog", "cat", "puppy", "kitten")):
        products.append("pet care pads")
    if any(word in joined for word in ("adult", "elder", "incontinence")):
        products.append("adult care products")
    if any(word in joined for word in ("sanitary", "pad", "pads", "liner", "period", "feminine")):
        products.append("sanitary pads and liners")
    if products:
        return ", ".join(dict.fromkeys(products))
    product = (fallback_product or "").strip()
    if product and product != "our new products":
        return product
    return "diapers, sanitary pads and liners for babies, adults, and pets"


def _keyword_style_phrase(terms: list[str]) -> str:
    stop = ("diaper", "pad", "liner", "commission", "sample", "tiktok", "shop", "whatsapp")
    style_terms = [term for term in terms if not any(word in term.lower() for word in stop)]
    if style_terms:
        return f"authentic style around {', '.join(style_terms[:3])}"
    return "authentic style"


def _keyword_content_ideas(terms: list[str]) -> str:
    joined = " ".join(terms).lower()
    ideas: list[str] = []
    if "unboxing" in joined:
        ideas.append("simple unboxing")
    if any(word in joined for word in ("daily", "routine", "use")):
        ideas.append("daily use")
    if any(word in joined for word in ("review", "testimonial")):
        ideas.append("review videos")
    if any(word in joined for word in ("reel", "reels", "tiktok", "short")):
        ideas.append("Reels/TikTok-style videos")
    if not ideas:
        ideas = ["simple unboxing", "daily use", "review videos (Reels/TikTok style)"]
    return ", ".join(dict.fromkeys(ideas))


# ---------------------------------------------------------------------------
# AI hook (Phase 2). Right now this is a thin pass-through so the router
# code can already be written against the AI surface; flipping ``use_ai=True``
# will wire in an LLM call without UI changes.
# ---------------------------------------------------------------------------


def generate_with_ai(
    template: OutreachTemplate,
    creator: Creator,
    *,
    use_ai: bool = False,
    sender_name: str | None = None,
    sender_signature: str | None = None,
    tone: str | None = None,
    language: str | None = None,
    max_length: int | None = None,
    n: int = 1,
) -> RenderResult:
    # Pull tone/language/max_length defaults from the template if the caller
    # didn't override them. AI outreach is intentionally English-only.
    effective_tone = tone or getattr(template, "tone", None) or "friendly"
    effective_language = "en" if use_ai else (language or template.language or "zh")
    effective_max_length = max_length or getattr(template, "max_length", None) or 600
    rendered = render_template(
        template,
        creator,
        sender_name=sender_name,
        sender_signature=sender_signature,
        language=effective_language,
    )
    rendered.tone = effective_tone
    rendered.language = effective_language
    if not use_ai:
        rendered.ai_status = "template"
        rendered.ai_message = "Template rendered."
        return rendered
    try:
        from ..config import settings  # noqa: WPS433
        from .ai_writer import polish_email  # noqa: WPS433  (optional plugin)
    except Exception as exc:
        log.warning("AI outreach writer unavailable: %s", exc)
        rendered.ai_status = "unavailable"
        rendered.ai_message = "AI writer is unavailable; template rendered."
        return rendered
    if not settings.openai_api_key:
        rendered.ai_status = "not_configured"
        rendered.ai_message = "OPENAI_API_KEY is not configured; template rendered."
        return rendered
    try:
        polished = polish_email(
            rendered.subject,
            rendered.body,
            rendered.context,
            tone=effective_tone,
            language=effective_language,
            max_length=effective_max_length,
            n=n,
        )
    except Exception as exc:  # pragma: no cover - never let AI errors break send
        log.warning("AI outreach generation failed: %s", exc)
        polished = None
        rendered.ai_status = "error"
        rendered.ai_message = "AI generation failed; template rendered."
    if isinstance(polished, dict):
        polished = [polished]
    if polished:
        rendered.subject = polished[0].get("subject", rendered.subject)
        rendered.body = polished[0].get("body", rendered.body)
        rendered.ai_used = True
        rendered.ai_status = "generated"
        rendered.ai_message = "AI outreach draft generated."
        if len(polished) > 1:
            rendered.variants = polished[1:]
    elif rendered.ai_status not in {"error", "not_configured", "unavailable"}:
        rendered.ai_status = "fallback"
        rendered.ai_message = "AI returned no usable draft; template rendered."
    return rendered
