"""达人邀约话术生成器（feature: outreach_script）

POST /api/v1/ai/generate_outreach
    body: {
        "creator_id": int,
        "product_ids": [int, ...],
        "channel": "tiktok_dm" | "email" | "whatsapp",
        "language": "en" | "zh" | null,    # null = use creator country / config default
        "queue": bool,                      # true = also write to outbox table
        "template_family": "feminine" | "pet" | "auto"  # auto = pick based on creator/product category
    }
    response: {
        "subject": str | null,
        "body": str,
        "language": str,
        "channel": str,
        "compliance_flags": [{"phrase":"...", "suggestion":"..."}],
        "resolved_provider": str,
        "resolved_model": str,
        "tokens": {"input": int, "output": int},
        "outbox_id": int | null      # if queue=true
    }

Prompt assembled in 6 sections (in this order):
    1. Function system rule
    2. outreach_policy overrides (commission/sampling/shipping/banned phrases/signature)
    3. brand_profile summary scoped to category
    4. creator + product structured info
    5. Few-shot examples — same channel + same category, 3-5 best
    6. Forced JSON output schema
"""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_user_or_above
from app.llm import _call, get_provider_for_feature

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"
FEATURE_CODE = "outreach_script"

router = APIRouter()


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# ============================================================
# Helpers
# ============================================================
def load_app_config(con: sqlite3.Connection, prefix: str = "outreach.") -> dict:
    rows = con.execute(
        "SELECT key, value, value_type FROM app_config WHERE key LIKE ?",
        (prefix + "%",)
    ).fetchall()
    out = {}
    for r in rows:
        v = r["value"]
        if r["value_type"] in ("number",):
            try: v = float(v) if "." in v else int(v)
            except (TypeError, ValueError): pass
        elif r["value_type"] in ("json", "boolean"):
            try: v = json.loads(v)
            except (json.JSONDecodeError, TypeError): pass
        out[r["key"]] = v
    return out


def detect_template_family(creator: dict, products: list[dict]) -> str:
    """Decide which template family fits this combo."""
    # Priority: explicit category from product wins
    cats = {p.get("category_code") for p in products if p.get("category_code")}
    if cats == {"pet"}:
        return "pet"
    if "pet" in cats:
        return "pet"  # mixed → still prioritize pet voice if any pet product
    if cats and cats.issubset({"female_care"}):
        return "feminine"
    if "baby" in cats or "adult_care" in cats:
        return "general"
    # Fall back to creator's category_tags
    try:
        tags = json.loads(creator.get("category_tags") or "[]")
        if any("宠物" in t for t in tags): return "pet"
        if any("女性" in t for t in tags): return "feminine"
        if any(("母婴" in t or "婴" in t) for t in tags): return "general"
    except json.JSONDecodeError:
        pass
    return "feminine"


def family_to_scope(family: str) -> str:
    return {"pet": "pet", "feminine": "female_care", "general": "all"}.get(family, "all")


def detect_language(language: str | None, creator: dict, cfg: dict) -> str:
    if language and language != "auto":
        return language
    default = cfg.get("outreach.default_language", "en")
    if default and default != "auto-by-country":
        return default
    country = (creator.get("country") or "").upper()
    if country in {"CN", "TW", "HK", "MO"}:
        return "zh"
    return "en"


def fetch_creator(con: sqlite3.Connection, creator_id: int) -> dict:
    row = con.execute("SELECT * FROM creator WHERE id=?", (creator_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"creator id={creator_id} not found")
    return dict(row)


# ============================================================
# v3.9.1: 智能产品推荐 / 渠道自动选择 / fit-level 提示
# ============================================================

# 廖的 *_fit 列 → product.category.code
FIT_TO_CATEGORY = {
    "feminine_care_fit": "female_care",
    "pet_care_fit": "pet",
    "home_care_fit": "home_care",
    "adult_care_fit": "adult_care",
    "mom_baby_fit": "baby",
    "health_mask_fit": "mask",
}


def suggest_products_for_creator(con: sqlite3.Connection, creator: dict,
                                 limit: int = 3) -> list[dict]:
    """根据廖的 *_fit 评分 + recommended_product_type 给该达人推荐产品。

    规则：
      1. 优先看 recommended_product_type（廖 LLM 给出的明确推荐），匹配品类
      2. 否则取 *_fit 中分数最高的非零列
      3. 兜底用 primary_product_category（带 _fit 之前的旧字段）
      4. 最后兜底：creator.category_tags
      5. 在选定品类内取 is_main_push DESC, id ASC 前 limit 条
    """
    cat_code = None
    rec_type = (creator.get("recommended_product_type") or "").lower()
    if "pet" in rec_type or "training pad" in rec_type:
        cat_code = "pet"
    elif "feminine" in rec_type or "panty liner" in rec_type or "menstrual" in rec_type:
        cat_code = "female_care"
    elif "adult" in rec_type or "incontinence" in rec_type:
        cat_code = "adult_care"
    elif "baby" in rec_type or "diaper" in rec_type:
        cat_code = "baby"
    elif "mask" in rec_type:
        cat_code = "mask"
    elif "home" in rec_type:
        cat_code = "home_care"

    if not cat_code:
        # 取最高 *_fit 分（>0）
        best = max(FIT_TO_CATEGORY.items(),
                   key=lambda kv: creator.get(kv[0]) or 0,
                   default=(None, None))
        if best[0] and (creator.get(best[0]) or 0) > 0:
            cat_code = best[1]

    if not cat_code:
        ppc = (creator.get("primary_product_category") or "").lower()
        for k, v in FIT_TO_CATEGORY.items():
            if v.replace("_", " ") in ppc or v in ppc:
                cat_code = v
                break

    if not cat_code:
        try:
            tags = json.loads(creator.get("category_tags") or "[]")
            if any("宠物" in t for t in tags): cat_code = "pet"
            elif any("女性" in t for t in tags): cat_code = "female_care"
            elif any("母婴" in t or "婴" in t for t in tags): cat_code = "baby"
        except (json.JSONDecodeError, TypeError):
            pass

    if not cat_code:
        return []

    rows = con.execute(
        "SELECT p.*, c.code AS category_code, c.name_zh AS category_name "
        "FROM product p LEFT JOIN category c ON c.id=p.category_id "
        "WHERE c.code=? AND COALESCE(p.status,'active')='active' "
        "ORDER BY COALESCE(p.is_main_push,0) DESC, p.id ASC LIMIT ?",
        (cat_code, limit)
    ).fetchall()
    return [dict(r) for r in rows]


def auto_pick_channel(creator: dict) -> str:
    """has_email=1 且 email 非空 → email；否则 tiktok_dm。"""
    if creator.get("email") and (creator.get("has_email") or 0) >= 1:
        return "email"
    return "tiktok_dm"


def fit_level_cues(creator: dict) -> list[str]:
    """生成 system prompt 里的 fit-level 调调提示。返回字符串列表追加到 sys_parts。"""
    cues: list[str] = []
    fit = (creator.get("fit_level") or "").upper()
    pscore = creator.get("priority_score") or 0
    if fit in {"A", "S"} or pscore >= 60:
        cues.append("- This creator is HIGH-FIT (A/S tier or priority_score≥60): write warmly, frame as a long-term partnership invitation, mention you've followed their content.")
    elif fit == "B" or pscore >= 40:
        cues.append("- This creator is MEDIUM-FIT (B tier): standard professional pitch, no over-promising, keep it concise.")
    elif fit in {"C", "D"} or (0 < pscore < 40):
        cues.append("- This creator is LOWER-FIT (C/D tier): keep the pitch SHORT and tentative; do not flatter; do not promise long-term collaboration in the first message.")
    if (creator.get("review_required") or 0) >= 1:
        cues.append("- ⚠️ This creator is FLAGGED for manual review: keep the message tentative, avoid concrete commitments (specific commission rates, sample shipment promises). Use phrases like 'we'd love to explore' instead of 'we'll send you'.")
    if creator.get("risk_summary"):
        cues.append(f"- ⚠️ Known risk note (do not mention to creator, but adjust tone): {creator['risk_summary'][:200]}")
    return cues


def fetch_products(con: sqlite3.Connection, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    placeholders = ",".join(["?"] * len(ids))
    rows = con.execute(
        f"SELECT p.*, c.code AS category_code, c.name_zh AS category_name "
        f"FROM product p LEFT JOIN category c ON c.id=p.category_id "
        f"WHERE p.id IN ({placeholders})",
        ids
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_brand_profiles(con: sqlite3.Connection, scope: str, language: str) -> list[dict]:
    rows = con.execute(
        "SELECT * FROM brand_profile WHERE is_active=1 "
        "AND (category_scope=? OR category_scope='all') "
        "AND (language=? OR language='all') "
        "ORDER BY sort_order, id",
        (scope, language)
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_few_shots(con: sqlite3.Connection, *, channel: str, scope: str,
                    language: str, limit: int = 4) -> list[dict]:
    rows = con.execute(
        "SELECT * FROM outreach_example WHERE is_active=1 AND channel=? AND language=? "
        "AND (category_scope=? OR category_scope='all') "
        "ORDER BY COALESCE(quality_rating, 0) DESC, id DESC LIMIT ?",
        (channel, language, scope, limit)
    ).fetchall()
    return [dict(r) for r in rows]


def check_compliance(text: str, banned: list[str], replacements: dict) -> list[dict]:
    flags = []
    lower = text.lower()
    for phrase in banned:
        p_lower = phrase.lower()
        if p_lower in lower:
            flags.append({
                "phrase": phrase,
                "suggestion": replacements.get(phrase, "rephrase or remove"),
            })
    return flags


# ============================================================
# Prompt assembly
# ============================================================
def build_prompt(*, creator: dict, products: list[dict], channel: str,
                 language: str, family: str, cfg: dict,
                 brand_profiles: list[dict], few_shots: list[dict]) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt)."""

    # ---- Section 1: function system rule ----
    sys_parts = [
        "You are a professional outreach copywriter for X9, a US-based care brand.",
        "Your task: write ONE outreach message inviting a TikTok creator to collaborate.",
        "",
        f"Channel: {channel}",
        f"Language: {language} (write the body in this language)",
        f"Template family: {family} (do NOT use voice/details from other families)",
        "",
        "Hard rules:",
        "- Tone: warm, professional, concise; no hype. Match the BD examples below.",
        "- Length: tiktok_dm ≤ 220 words; email 250–400 words; whatsapp 80–150 words.",
        "- DO NOT promise medical effects (treat / cure / prevent disease).",
        "- DO NOT use absolutism (the safest / 100% leak-proof / best in the world).",
        "- DO NOT promise sales (guaranteed sales / no-risk return).",
        "- ALWAYS reference the actual sampling policy and commission given below.",
        "- DO NOT invent product features that aren't in the product info.",
        "- CRITICAL: Write the ENTIRE message in the target language. If creator/product info contains Chinese text, translate the CONCEPT but NEVER copy Chinese characters into the output.",
    ]

    # fit-level 调调提示（廖 lead 池信号 → 话术口吻）
    cues = fit_level_cues(creator)
    if cues:
        sys_parts.append("")
        sys_parts.append("# Tone calibration based on creator fit signals:")
        sys_parts.extend(cues)

    # ---- Section 2: outreach_policy ----
    sys_parts.append("\n# Outreach Policy (override for this campaign)\n")
    commission = cfg.get("outreach.commission_rate_default", 0.20)
    pct = f"{round(commission*100)}%" if isinstance(commission, (int, float)) else commission
    packs = cfg.get("outreach.sampling_packs_per_creator", 1)
    ship = cfg.get("outreach.shipping_days", 7)
    eligible = cfg.get("outreach.sampling_eligible_skus", "all_active")
    elig_text = "all our active SKUs" if eligible == "all_active" else f"specific SKUs: {eligible}"
    sys_parts.append(f"- Commission: {pct} on sales tracked through the creator's content")
    sys_parts.append(f"- Sampling: {packs} pack per creator, eligible: {elig_text}")
    sys_parts.append(f"- Shipping: ~{ship} days")
    sys_parts.append(f"- Signature: {cfg.get('outreach.signature', 'X9 Team')}")
    sys_parts.append(f"- Website: {cfg.get('outreach.brand_website', '')}")
    sys_parts.append(f"- Reply email: {cfg.get('outreach.brand_email', '')}")

    # ---- Section 3: brand profile (scoped) ----
    if brand_profiles:
        sys_parts.append("\n# Brand context\n")
        for bp in brand_profiles:
            sys_parts.append(f"- {bp['title']}: {bp['body_text']}")

    # ---- Section 4: creator + product structured info ----
    user_parts = []
    user_parts.append("# Target creator")
    user_parts.append(f"- handle: @{creator.get('handle')} ({creator.get('platform')})")
    user_parts.append(f"- tier: {creator.get('tier') or 'unknown'}")
    if creator.get("followers"):
        user_parts.append(f"- followers: {creator['followers']:,}")
    if creator.get("country"):
        user_parts.append(f"- country: {creator['country']}")
    try:
        tags = json.loads(creator.get("category_tags") or "[]")
        if tags:
            # 对于英文话术，标注中文标签仅供分类参考，不要在输出中直接使用
            if language == "en":
                user_parts.append(f"- content category (for targeting reference, do NOT copy verbatim): {', '.join(tags)}")
            else:
                user_parts.append(f"- content tags: {', '.join(tags)}")
    except json.JSONDecodeError:
        pass
    if creator.get("avg_views"):
        user_parts.append(f"- avg views: {creator['avg_views']:,}")

    # 廖 lead 池的评分/推荐信号 (来自 tk_creators ETL, v3.9.0)
    if creator.get("primary_product_category"):
        user_parts.append(f"- primary product category (auto-tagged): {creator['primary_product_category']}")
    if creator.get("fit_level"):
        user_parts.append(f"- fit level: {creator['fit_level']} (priority_score={creator.get('priority_score','?')})")
    if creator.get("recommended_product_type"):
        user_parts.append(f"- recommended product line: {creator['recommended_product_type']}")
    if creator.get("recommended_collab_type"):
        user_parts.append(f"- recommended collab type: {creator['recommended_collab_type']}")
    # 证据片段 — 帮助生成器写出基于真实内容的开场白，但禁止直接抄
    try:
        ev = json.loads(creator.get("evidence_text_json") or "{}")
        snippets = []
        for bucket in ("feminine_strong", "feminine_medium", "pet_care", "adult_care", "mom_baby", "commerce_signal"):
            for item in (ev.get(bucket) or [])[:2]:
                snip = (item.get("evidence_snippet") or "").strip()
                if snip:
                    snippets.append(f"  ({bucket}) {snip[:160]}")
        if snippets:
            user_parts.append("- recent content evidence (style cues only, do NOT quote verbatim):")
            user_parts.extend(snippets[:5])
    except (json.JSONDecodeError, TypeError):
        pass
    if creator.get("risk_summary"):
        user_parts.append(f"- ⚠️ risk note: {creator['risk_summary']}")
    if creator.get("recommendation_reason"):
        user_parts.append(f"- AI suggestion context: {creator['recommendation_reason'][:300]}")

    user_parts.append("\n# Products to introduce")
    for p in products:
        sp = []
        try:
            sp = json.loads(p.get("selling_points_en") or "[]")[:3]
        except json.JSONDecodeError:
            pass
        user_parts.append(f"- {p.get('sku_code')} · {p.get('name_en')} ({p.get('size_label')}, {p.get('pcs_per_pack')} pcs/pack)")
        # 定位：英文话术用 description_en，中文话术用 positioning_zh
        if language == "en" and p.get("description_en"):
            user_parts.append(f"  description: {p['description_en'][:200]}")
        elif p.get('positioning_zh'):
            user_parts.append(f"  positioning: {p['positioning_zh']}")
        for s in sp:
            user_parts.append(f"  • {s}")

    # ---- Section 5: few-shot examples ----
    if few_shots:
        sys_parts.append("\n# BD example messages (style reference, do not copy verbatim)\n")
        for i, ex in enumerate(few_shots, 1):
            tag = ex.get("template_key") or f"#{i}"
            sys_parts.append(f"## Example {i} ({tag} by {ex.get('author','?')}):")
            sys_parts.append(ex["body"][:1200])
            sys_parts.append("---")

    # ---- Section 6: JSON output schema ----
    sys_parts.append("\n# Output format (REQUIRED)\n")
    sys_parts.append("Return a SINGLE JSON object, nothing else (no preamble, no code fences):")
    sys_parts.append('{"subject": "<email subject or null for non-email>",')
    sys_parts.append(' "body": "<the message text — multi-line allowed>",')
    sys_parts.append(' "compliance_self_check": "<one-line: did you avoid all banned phrases? what did you double-check?>"}')

    user_parts.append("\n# Now write the message. Return ONLY the JSON object.")

    return "\n".join(sys_parts), "\n".join(user_parts)


# ============================================================
# Endpoint
# ============================================================
@router.post("/api/v1/ai/generate_outreach", dependencies=[Depends(require_user_or_above)])
async def generate_outreach(payload: dict, user: dict = Depends(require_user_or_above)) -> dict:
    creator_id = payload.get("creator_id")
    product_ids = payload.get("product_ids") or []
    if not creator_id:
        raise HTTPException(400, "creator_id required")
    channel = payload.get("channel", "auto")
    if channel not in {"tiktok_dm", "email", "whatsapp", "auto"}:
        raise HTTPException(400, "channel must be one of: tiktok_dm, email, whatsapp, auto")
    auto_products = payload.get("auto_select_products", True)
    if not isinstance(product_ids, list):
        raise HTTPException(400, "product_ids must be a list of integers (or omitted)")
    queue = bool(payload.get("queue", False))
    family_hint = payload.get("template_family", "auto")
    language_hint = payload.get("language")

    con = _con()
    try:
        creator = fetch_creator(con, creator_id)

        # 渠道自动选择
        auto_picked_channel = None
        if channel == "auto":
            channel = auto_pick_channel(creator)
            auto_picked_channel = channel

        # 产品自动推荐（product_ids 为空且允许 auto）
        suggested_products: list[dict] = []
        if not product_ids and auto_products:
            suggested_products = suggest_products_for_creator(con, creator, limit=3)
            product_ids = [p["id"] for p in suggested_products]
            products = suggested_products
            if not products:
                raise HTTPException(
                    400,
                    "no product_ids passed and no auto-suggestion possible "
                    "(廖的 *_fit / recommended_product_type / category_tags 都没值)"
                )
        else:
            products = fetch_products(con, product_ids)
            if len(products) != len(product_ids):
                missing = set(product_ids) - {p["id"] for p in products}
                raise HTTPException(404, f"product ids not found: {sorted(missing)}")

        cfg = load_app_config(con, "outreach.")

        family = (family_hint if family_hint and family_hint != "auto"
                  else detect_template_family(creator, products))
        scope = family_to_scope(family)
        language = detect_language(language_hint, creator, cfg)
        brand_profiles = fetch_brand_profiles(con, scope, language)
        few_shots = fetch_few_shots(con, channel=channel, scope=scope, language=language, limit=4)

        system_prompt, user_prompt = build_prompt(
            creator=creator, products=products, channel=channel,
            language=language, family=family, cfg=cfg,
            brand_profiles=brand_profiles, few_shots=few_shots,
        )

        # Resolve provider via feature binding
        prov, feat = get_provider_for_feature(FEATURE_CODE, include_key=True)

        # Call LLM
        try:
            result = _call(
                prov,
                messages=[{"role": "user", "content": user_prompt}],
                system=system_prompt,
                model=feat.get("model"),
                max_tokens=int(feat.get("max_tokens") or 1200),
                temperature=float(feat.get("temperature") if feat.get("temperature") is not None else 0.7),
            )
        except RuntimeError as e:
            raise HTTPException(502, f"LLM error: {e}")

        raw = (result.get("content") or "").strip()
        # strip code fences if model wrapped JSON in them
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.lstrip().startswith("json"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw
            raw = raw.rsplit("```", 1)[0].strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # fallback: treat the whole text as body
            parsed = {"subject": None, "body": raw, "compliance_self_check": "(LLM returned non-JSON)"}

        subject = parsed.get("subject")
        body = parsed.get("body") or ""

        # Compliance check
        banned = cfg.get("outreach.banned_phrases") or []
        replacements = cfg.get("outreach.banned_replacements") or {}
        flags = check_compliance(body + " " + (subject or ""), banned, replacements)

        # Optionally write to outbox
        outbox_id = None
        if queue:
            cur = con.execute(
                "INSERT INTO outbox(creator_id, product_ids, channel, language, "
                "subject, body, status, generated_by_feature, generation_meta_json, "
                "template_used, sent_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (creator_id, json.dumps(product_ids), channel, language,
                 subject, body, "draft", FEATURE_CODE,
                 json.dumps({
                     "provider": result.get("provider"),
                     "model": result.get("model"),
                     "tokens": {"input": result.get("input_tokens"),
                                "output": result.get("output_tokens")},
                     "compliance_flags": flags,
                     "family": family,
                     "self_check": parsed.get("compliance_self_check"),
                 }, ensure_ascii=False),
                 f"{family}.{channel}.generated", user.get("username"))
            )
            outbox_id = cur.lastrowid
            con.commit()

        return {
            "subject": subject,
            "body": body,
            "language": language,
            "channel": channel,
            "template_family": family,
            "compliance_flags": flags,
            "self_check": parsed.get("compliance_self_check"),
            "resolved_provider": result.get("provider"),
            "resolved_model": result.get("model"),
            "tokens": {
                "input": result.get("input_tokens"),
                "output": result.get("output_tokens"),
            },
            "few_shots_used": [{"template_key": fs.get("template_key"), "author": fs.get("author")} for fs in few_shots],
            "brand_profiles_used": [bp.get("title") for bp in brand_profiles],
            "outbox_id": outbox_id,
            "auto_picked_channel": auto_picked_channel,
            "auto_selected_products": [
                {"id": p["id"], "sku_code": p.get("sku_code"), "name_en": p.get("name_en")}
                for p in (suggested_products or [])
            ] if suggested_products else None,
            "fit_signals": {
                "fit_level": creator.get("fit_level"),
                "priority_score": creator.get("priority_score"),
                "review_required": bool(creator.get("review_required")),
                "risk_summary": creator.get("risk_summary"),
                "recommendation_reason": creator.get("recommendation_reason"),
            },
            "ts": datetime.utcnow().isoformat(),
        }
    finally:
        con.close()


@router.post("/api/v1/ai/outreach/suggest_products",
              dependencies=[Depends(require_user_or_above)])
async def suggest_products_endpoint(payload: dict) -> dict:
    """根据廖 lead 池字段给某达人推荐 N 个产品 + 自动渠道。前端"生成话术"
    打开窗口时调一下，预填产品列表与渠道下拉。"""
    creator_id = payload.get("creator_id")
    if not creator_id:
        raise HTTPException(400, "creator_id required")
    limit = int(payload.get("limit") or 3)
    con = _con()
    try:
        creator = fetch_creator(con, creator_id)
        products = suggest_products_for_creator(con, creator, limit=limit)
        return {
            "creator_id": creator_id,
            "channel_suggested": auto_pick_channel(creator),
            "products": [
                {"id": p["id"], "sku_code": p.get("sku_code"),
                 "name_en": p.get("name_en"), "category_code": p.get("category_code"),
                 "is_main_push": bool(p.get("is_main_push"))}
                for p in products
            ],
            "fit_signals": {
                "fit_level": creator.get("fit_level"),
                "priority_score": creator.get("priority_score"),
                "primary_product_category": creator.get("primary_product_category"),
                "recommended_product_type": creator.get("recommended_product_type"),
                "recommended_collab_type": creator.get("recommended_collab_type"),
                "review_required": bool(creator.get("review_required")),
                "risk_summary": creator.get("risk_summary"),
                "fit_scores": {
                    k: creator.get(k) for k in FIT_TO_CATEGORY.keys()
                    if creator.get(k) is not None
                },
            },
        }
    finally:
        con.close()


@router.get("/api/v1/ai/outreach/info")
def outreach_info() -> dict:
    """前端查询：邀约话术生成器是否启用，资源是否齐全。"""
    con = _con()
    try:
        # Provider readiness
        try:
            prov, feat = get_provider_for_feature(FEATURE_CODE, include_key=True)
            ready, reason = True, None
            provider_summary = {"code": prov["code"], "model": prov.get("default_model"),
                                "binding": "feature-bound" if feat.get("provider_code") else "global-fallback"}
        except Exception as e:
            from fastapi import HTTPException as HE
            ready = False
            reason = e.detail if isinstance(e, HE) else str(e)
            provider_summary = None

        # Resource availability
        n_examples = con.execute("SELECT COUNT(*) FROM outreach_example WHERE is_active=1").fetchone()[0]
        n_brand = con.execute("SELECT COUNT(*) FROM brand_profile WHERE is_active=1").fetchone()[0]
        cfg_keys = con.execute("SELECT COUNT(*) FROM app_config WHERE key LIKE 'outreach.%'").fetchone()[0]
    finally:
        con.close()

    return {
        "ready": ready,
        "reason": reason,
        "feature": FEATURE_CODE,
        "provider": provider_summary,
        "resources": {
            "outreach_example_active": n_examples,
            "brand_profile_active": n_brand,
            "app_config_outreach_keys": cfg_keys,
        },
    }
