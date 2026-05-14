"""商品裂变文案生成器

POST /api/v1/ai/clone_product
    body: {
        "sku": "PP-SWIM-BLK-L",
        "dry_run": true,
        "global_style": "偏向年轻化、活泼的 Z 世代风格",   // 全局风格追加（可选）
        "variants": [
            // 模式 1: 内置角度预设
            {"angle": "comfort"},
            // 模式 2: 预设 + 局部覆盖
            {"angle": "scenario", "override": {"tone": "更活泼的 Z 世代语气"}},
            // 模式 3: 完全自定义三要素
            {"custom": {"focus": "竹纤维材质", "tone": "高端 spa 品牌感", "persona": "注重品质的 30+ 女性"}},
            // 模式 4: 运营直接输入 prompt（最灵活，直接对 AI 说）
            {"free_prompt": "这款产品要给送礼的人看，主打有心意、好包装，不提价格"},
        ],
        // 向后兼容: variants 为空时，用 angles+n 快捷方式
        "angles": ["comfort", "scenario"],
        "n": 3,
        "save_as_preset": "夏季活动专用"   // 可选：把 global_style+variants 存为命名预设
    }

GET  /api/v1/ai/clone_product/angles            内置角度列表
GET  /api/v1/ai/clone_product/presets           运营保存的预设
POST /api/v1/ai/clone_product/presets           保存预设
PUT  /api/v1/ai/clone_product/presets/{id}      更新预设
DELETE /api/v1/ai/clone_product/presets/{id}    删除预设

OpenAI Key 由管理员在 Settings → LLM Features → product_clone 里绑定，前端不持有 key。
"""
from __future__ import annotations

import difflib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row

from app.auth import require_user_or_above, require_admin
from app.llm import _call, get_provider_for_feature

router = APIRouter()

FEATURE_CODE  = "product_clone"
TITLE_MAX     = 255
SIM_THRESHOLD = 0.72
MAX_RETRIES   = 2

ROOT      = Path(__file__).resolve().parent.parent
_SQLITE   = ROOT / "database.db"
_PG_DSN   = os.environ.get(
    "X9_PG_DSN",
    "postgresql://x9:x9_local_dev_2026@localhost:15432/x9db?connect_timeout=5",
)

# ─── 内置角度矩阵 ─────────────────────────────────────────────────────────────
# 每条: focus(内容侧重) · tone(语气) · persona(目标受众) · image_hint(图片选取建议)
# 这些是"快捷选项"，运营可在此基础上覆盖任意字段，或完全绕过用自由 prompt。

ANGLES: dict[str, dict[str, str]] = {
    "comfort": {
        "label": "Comfort",
        "focus": "comfort, feel and material quality",
        "tone": "warm and personal, like a recommendation from a friend",
        "persona": "everyday users aged 25-45 who prioritize softness and wearability",
        "image_hint": "fabric texture or skin-contact surface closeup",
        "desc_zh": "舒适触感 — 强调材质、手感、穿着体验",
    },
    "scenario": {
        "label": "Scenario",
        "focus": "specific use scenarios and lifestyle occasions (gym, travel, work, night)",
        "tone": "lifestyle-oriented and relatable, active energy",
        "persona": "active women aged 22-38 with an on-the-go lifestyle",
        "image_hint": "lifestyle or in-use shot (outdoor, gym, travel context)",
        "desc_zh": "生活场景 — 强调运动/旅行/日常具体使用情境",
    },
    "value": {
        "label": "Value",
        "focus": "price per use, pack size and cost-effectiveness vs alternatives",
        "tone": "practical and direct, numbers-forward",
        "persona": "budget-conscious buyers comparing options on price and quantity",
        "image_hint": "pack/quantity shot that emphasizes how much you get",
        "desc_zh": "性价比 — 强调单价、包量、对比竞品划算",
    },
    "relief": {
        "label": "Relief",
        "focus": "solving specific frustrations: leakage, irritation, poor fit, anxiety",
        "tone": "empathetic and solution-focused, speak to the problem first",
        "persona": "users frustrated with current products and looking for a real fix",
        "image_hint": "before/after graphic or problem-solution visual",
        "desc_zh": "痛点解决 — 先说问题，再说解决方案",
    },
    "gift": {
        "label": "Gift",
        "focus": "gift-giving occasion, presentation and caring for someone else",
        "tone": "warm and celebratory, emotional",
        "persona": "shoppers buying for a daughter, sister, friend or partner",
        "image_hint": "packaged product or gift presentation flatlay",
        "desc_zh": "礼品赠送 — 适合送礼场景，情感化语气",
    },
    "eco": {
        "label": "Eco",
        "focus": "eco-friendly materials, reusability, chemical-free and health safety",
        "tone": "conscious and informative, ingredient-label reader energy",
        "persona": "eco-aware shoppers who read labels and prefer sustainable options",
        "image_hint": "material closeup or certification/ingredient label",
        "desc_zh": "环保健康 — 强调天然材质、无添加、可持续",
    },
    "spec": {
        "label": "Spec",
        "focus": "technical specifications: dimensions, absorbency, certifications, pack counts",
        "tone": "factual and clinical, spec-sheet style",
        "persona": "detail-oriented buyers who want exact numbers before buying",
        "image_hint": "spec infographic or label/certification closeup",
        "desc_zh": "规格参数 — 数字、认证、规格一览，适合理性买家",
    },
    "trust": {
        "label": "Trust",
        "focus": "brand credibility, bestseller status, quality assurance and social proof",
        "tone": "confident with implicit social proof, reassuring",
        "persona": "first-time buyers who need reassurance before clicking Add to Cart",
        "image_hint": "awards badge, bestseller tag or quality certification graphic",
        "desc_zh": "品牌信任 — 畅销、品质背书，适合首次购买者",
    },
}

_DEFAULT_ORDER = ["comfort", "scenario", "value", "relief", "gift", "eco", "spec", "trust"]

_SYSTEM_PROMPT = """\
You are a senior e-commerce content writer for X9, a US personal care brand.
Write ONE unique product listing for the assigned style and target persona.

Platform rules:
- Title: ≤ {title_max} characters (count every character including spaces). Use Title Case.
- Description: engaging prose, 2-4 sentences. No bullet points here.
- Selling points: exactly 3 concise strings, each ≤ 120 chars, each starting with a strong action verb.

Content rules:
- Product facts are GROUND TRUTH — do not invent sizes, materials, certifications or counts.
- Never exceed the title character limit.
- No medical claims: avoid "treat / cure / prevent / FDA-approved" → use "dermatologist tested" or "FDA registered".
- No absolutes: avoid "best in the world", "100% leak-proof", "safest ever".
- Write in clear, natural American English.
- Banned phrases: {banned}.

Output: a single valid JSON object — no markdown, no preamble, nothing else.
Required keys: "title", "description", "selling_points" (array of 3 strings).\
"""

# ─── DB helpers ──────────────────────────────────────────────────────────────

def _pg():
    return psycopg.connect(_PG_DSN, row_factory=dict_row)

def _sq():
    con = sqlite3.connect(_SQLITE)
    con.row_factory = sqlite3.Row
    return con


def _load_product(sku: str) -> dict:
    with _pg() as pg, pg.cursor() as cur:
        cur.execute(
            """SELECT p.*, c.code AS category_code, c.name_zh AS category_name
               FROM product p LEFT JOIN category c ON p.category_id = c.id
               WHERE p.sku_code = %s""",
            (sku,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, f"SKU '{sku}' not found")
    for col in ("selling_points_en", "selling_points_zh", "pain_points_zh",
                "scenarios_en", "scenarios_zh", "vocabulary_en",
                "creative_angles_en", "safe_scenes_en", "creator_match_levels"):
        if isinstance(row.get(col), str):
            try: row[col] = json.loads(row[col])
            except (TypeError, json.JSONDecodeError): row[col] = []
    return dict(row)


def _load_banned() -> list[str]:
    try:
        con = _sq()
        row = con.execute(
            "SELECT value FROM app_config WHERE key='outreach.banned_phrases'"
        ).fetchone()
        con.close()
        if row and row["value"]:
            return json.loads(row["value"])
    except Exception:
        pass
    return []


def _create_product_in_pg(payload: dict) -> dict:
    from app.main import get_pg_con, PRODUCT_EDITABLE, PRODUCT_JSON_COLS, encode_for_db, get_product
    with get_pg_con() as con, con.cursor() as cur:
        cur.execute("SELECT 1 FROM product WHERE sku_code = %s", (payload["sku_code"],))
        if cur.fetchone():
            raise HTTPException(409, f"sku_code '{payload['sku_code']}' already exists")
        if payload.get("category_code"):
            cur.execute("SELECT id FROM category WHERE code = %s", (payload["category_code"],))
            cat = cur.fetchone()
            if cat:
                payload["category_id"] = cat["id"]
        payload.pop("category_code", None)
        fields = {k: v for k, v in payload.items() if k in PRODUCT_EDITABLE | {"sku_code", "category_id"}}
        fields = encode_for_db(fields, PRODUCT_JSON_COLS)
        cols = list(fields.keys())
        cur.execute(
            f"INSERT INTO product({','.join(cols)}) VALUES({','.join(['%s']*len(cols))}) RETURNING id",
            list(fields.values()),
        )
    return get_product(payload["sku_code"])

# ─── Variant spec resolver ────────────────────────────────────────────────────

def _resolve_variant_spec(spec: dict, idx: int) -> dict:
    """Normalise one variant spec into {label, sku_suffix, style_section_text}."""
    if spec.get("free_prompt"):
        return {
            "label": f"Custom{idx}",
            "sku_suffix": f"C{idx}",
            "mode": "free",
            "style_text": spec["free_prompt"].strip(),
        }
    if spec.get("custom"):
        c = spec["custom"]
        return {
            "label": (c.get("focus") or "Custom")[:10].title().replace(" ", ""),
            "sku_suffix": f"C{idx}",
            "mode": "custom",
            "focus":   c.get("focus", ""),
            "tone":    c.get("tone", ""),
            "persona": c.get("persona", ""),
            "image_hint": c.get("image_hint", ""),
        }
    # angle (+ optional override)
    angle_key = spec.get("angle") or _DEFAULT_ORDER[min(idx - 1, len(_DEFAULT_ORDER) - 1)]
    if angle_key not in ANGLES:
        raise HTTPException(400, f"unknown angle '{angle_key}'. valid: {list(ANGLES.keys())}")
    base = dict(ANGLES[angle_key])
    override = spec.get("override") or {}
    merged = {**base, **{k: v for k, v in override.items() if v}}
    return {
        "label":      merged["label"],
        "sku_suffix": merged["label"].upper()[:4],
        "mode":       "angle",
        "angle_key":  angle_key,
        "focus":      merged["focus"],
        "tone":       merged["tone"],
        "persona":    merged["persona"],
        "image_hint": merged.get("image_hint", ""),
    }

# ─── Prompt construction ─────────────────────────────────────────────────────

def _product_block(p: dict) -> list[str]:
    lines = [
        "# Product Data (facts only — do not invent anything)",
        f"- SKU: {p.get('sku_code')}",
        f"- Name: {p.get('name_en')}",
        f"- Category: {p.get('category_name', '')} / {p.get('subcategory') or ''}",
        f"- Size / spec: {p.get('size_label') or 'N/A'}",
        f"- Pack: {p.get('pcs_per_pack') or '?'} pcs/pack",
    ]
    for field, label in [
        ("selling_points_en", "Selling points"),
        ("scenarios_en",      "Use scenarios"),
        ("creative_angles_en","Creative angles"),
    ]:
        vals = p.get(field) or []
        if vals:
            lines.append(f"- {label}: {' | '.join(str(v) for v in vals[:5])}")
    if p.get("target_audience_en"):
        lines.append(f"- Target audience: {p['target_audience_en']}")
    vocab = p.get("vocabulary_en") or []
    if vocab:
        lines.append(f"- SEO vocabulary: {', '.join(str(v) for v in vocab[:10])}")
    if p.get("proof"):
        lines.append(f"- Certifications: {p['proof']}")
    return lines


def _build_prompt(product: dict, resolved: dict, global_style: str,
                  forbidden: list[str], num: int, total: int) -> str:
    lines = _product_block(product)
    lines.append("")

    if resolved["mode"] == "free":
        lines += [
            f"# Style Instruction from operator (variant {num} of {total})",
            resolved["style_text"],
        ]
    else:
        lines += [
            f"# Variant Assignment ({num} of {total})",
            f"- Content angle : {resolved['focus']}",
            f"- Writing tone  : {resolved['tone']}",
            f"- Target persona: {resolved['persona']}",
        ]
        if resolved.get("image_hint"):
            lines.append(f"- Image hint    : {resolved['image_hint']}")

    if global_style:
        lines += ["", f"# Global style note (apply to all variants)", global_style]

    if forbidden:
        lines += [
            "",
            "# Forbidden phrases (already in prior variants — do NOT repeat):",
            ", ".join(f'"{p}"' for p in forbidden[:25]),
        ]

    lines += [
        "",
        '# Required JSON output (no extras):',
        '{"title": "Title Case ≤255 chars", "description": "2-4 sentence prose", '
        '"selling_points": ["Verb point 1", "Verb point 2", "Verb point 3"]}',
    ]
    return "\n".join(lines)

# ─── Similarity + phrase extraction ─────────────────────────────────────────

def _sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()

def _extract_phrases(text: str, n: int = 15) -> list[str]:
    words = text.lower().split()
    seen: set[str] = set()
    out: list[str] = []
    for i in range(len(words) - 1):
        p = f"{words[i]} {words[i+1]}"
        if p not in seen and len(p) > 8:
            seen.add(p); out.append(p)
    for i in range(len(words) - 2):
        p = f"{words[i]} {words[i+1]} {words[i+2]}"
        if p not in seen and len(p) > 12:
            seen.add(p); out.append(p)
    return out[:n]

# ─── Core generation ─────────────────────────────────────────────────────────

def _gen_one(provider: dict, feat: dict, product: dict, resolved: dict,
             global_style: str, forbidden: list[str],
             num: int, total: int, banned: list[str]) -> dict | None:
    system = _SYSTEM_PROMPT.format(
        title_max=TITLE_MAX,
        banned=", ".join(banned[:12]) if banned else "none",
    )
    for attempt in range(MAX_RETRIES + 1):
        raw_result = _call(
            provider,
            messages=[{"role": "user",
                       "content": _build_prompt(product, resolved, global_style, forbidden, num, total)}],
            system=system,
            model=feat.get("model"),
            max_tokens=int(feat.get("max_tokens") or 700),
            temperature=float(feat.get("temperature") if feat.get("temperature") is not None else 0.85),
        )
        raw = (raw_result.get("content") or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.lstrip().startswith("json"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw
            raw = raw.rsplit("```", 1)[0].strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}

        title = (parsed.get("title") or "").strip()
        desc  = (parsed.get("description") or "").strip()
        sps   = [s.strip() for s in (parsed.get("selling_points") or []) if s.strip()]

        if not title or len(title) > TITLE_MAX:
            continue

        return {
            "angle":             resolved.get("angle_key", resolved["mode"]),
            "mode":              resolved["mode"],
            "variant_label":     resolved["label"],
            "sku_code":          f"{product['sku_code']}-{resolved['sku_suffix']}",
            "title":             title,
            "title_chars":       len(title),
            "description":       desc,
            "selling_points_en": sps,
            "image_hint":        resolved.get("image_hint", ""),
            "_tokens": {
                "input":  raw_result.get("input_tokens", 0),
                "output": raw_result.get("output_tokens", 0),
            },
        }
    return None

# ─── Preset helpers ───────────────────────────────────────────────────────────

def _save_preset(name: str, global_style: str, variants: list[dict], user: str) -> dict:
    con = _sq()
    try:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        con.execute(
            """INSERT INTO product_clone_preset (name, global_style, variants, created_by, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   global_style=excluded.global_style,
                   variants=excluded.variants,
                   updated_at=excluded.updated_at""",
            (name, global_style or "", json.dumps(variants, ensure_ascii=False), user, now),
        )
        con.commit()
        row = con.execute("SELECT * FROM product_clone_preset WHERE name=?", (name,)).fetchone()
        return dict(row)
    finally:
        con.close()

# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/api/v1/ai/clone_product/angles")
def list_angles() -> dict:
    """内置角度列表，供前端渲染选择卡片。"""
    return {
        "angles": [
            {
                "code":       code,
                "label":      a["label"],
                "desc_zh":    a.get("desc_zh", ""),
                "focus":      a["focus"],
                "tone":       a["tone"],
                "persona":    a["persona"],
                "image_hint": a["image_hint"],
            }
            for code, a in ANGLES.items()
        ],
        "default_order": _DEFAULT_ORDER,
    }


@router.get("/api/v1/ai/clone_product/presets",
            dependencies=[Depends(require_user_or_above)])
def list_presets() -> dict:
    con = _sq()
    try:
        rows = con.execute(
            "SELECT id, name, store_code, global_style, variants, created_by, created_at, updated_at "
            "FROM product_clone_preset ORDER BY updated_at DESC"
        ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            try: d["variants"] = json.loads(d["variants"])
            except Exception: d["variants"] = []
            items.append(d)
        return {"items": items}
    finally:
        con.close()


@router.post("/api/v1/ai/clone_product/presets",
             dependencies=[Depends(require_user_or_above)])
async def create_preset(payload: dict, user: dict = Depends(require_user_or_above)) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    variants = payload.get("variants") or []
    if not isinstance(variants, list):
        raise HTTPException(400, "variants must be a list")
    result = _save_preset(name, payload.get("global_style", ""), variants, user.get("username", ""))
    return result


@router.put("/api/v1/ai/clone_product/presets/{preset_id}",
            dependencies=[Depends(require_user_or_above)])
async def update_preset(preset_id: int, payload: dict,
                        user: dict = Depends(require_user_or_above)) -> dict:
    con = _sq()
    try:
        row = con.execute("SELECT * FROM product_clone_preset WHERE id=?", (preset_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"preset {preset_id} not found")
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        fields: dict = {}
        if "name" in payload:
            fields["name"] = payload["name"]
        if "global_style" in payload:
            fields["global_style"] = payload["global_style"]
        if "variants" in payload:
            fields["variants"] = json.dumps(payload["variants"], ensure_ascii=False)
        if not fields:
            raise HTTPException(400, "nothing to update")
        fields["updated_at"] = now
        sets = ",".join(f"{k}=?" for k in fields)
        con.execute(f"UPDATE product_clone_preset SET {sets} WHERE id=?",
                    list(fields.values()) + [preset_id])
        con.commit()
        row = con.execute("SELECT * FROM product_clone_preset WHERE id=?", (preset_id,)).fetchone()
        d = dict(row)
        try: d["variants"] = json.loads(d["variants"])
        except Exception: pass
        return d
    finally:
        con.close()


@router.delete("/api/v1/ai/clone_product/presets/{preset_id}",
               dependencies=[Depends(require_user_or_above)])
def delete_preset(preset_id: int) -> dict:
    con = _sq()
    try:
        if not con.execute("SELECT 1 FROM product_clone_preset WHERE id=?", (preset_id,)).fetchone():
            raise HTTPException(404, f"preset {preset_id} not found")
        con.execute("DELETE FROM product_clone_preset WHERE id=?", (preset_id,))
        con.commit()
        return {"ok": True, "deleted_id": preset_id}
    finally:
        con.close()


@router.post("/api/v1/ai/clone_product",
             dependencies=[Depends(require_user_or_above)])
async def clone_product(payload: dict,
                        user: dict = Depends(require_user_or_above)) -> dict:
    sku = (payload.get("sku") or "").strip()
    if not sku:
        raise HTTPException(400, "sku required")

    dry_run: bool = bool(payload.get("dry_run", True))
    global_style: str = (payload.get("global_style") or "").strip()

    # Build variant spec list
    raw_variants: list[dict] = payload.get("variants") or []
    if not raw_variants:
        # Backward-compat: angles + n
        n = max(1, min(8, int(payload.get("n") or 4)))
        angle_list: list[str] = [a.strip() for a in (payload.get("angles") or [])]
        if angle_list:
            invalid = [a for a in angle_list if a not in ANGLES]
            if invalid:
                raise HTTPException(400, f"unknown angles: {invalid}")
            raw_variants = [{"angle": a} for a in angle_list[:n]]
        else:
            raw_variants = [{"angle": a} for a in _DEFAULT_ORDER[:n]]

    # Resolve all specs
    resolved_specs = [_resolve_variant_spec(spec, i + 1) for i, spec in enumerate(raw_variants)]

    # Load product + provider
    product = _load_product(sku)
    banned  = _load_banned()

    try:
        provider, feat = get_provider_for_feature(FEATURE_CODE, include_key=True)
    except HTTPException:
        raise HTTPException(
            400,
            f"No LLM provider configured for '{FEATURE_CODE}'. "
            "Ask admin to bind a provider in Settings → LLM → Features."
        )

    # Generate
    clones: list[dict] = []
    forbidden_phrases: list[str] = []
    total_tokens = {"input": 0, "output": 0}
    total = len(resolved_specs)

    for i, resolved in enumerate(resolved_specs, start=1):
        variant = _gen_one(provider, feat, product, resolved,
                           global_style, forbidden_phrases, i, total, banned)
        if variant is None:
            continue

        this_text = f"{variant['title']} {variant['description']} {' '.join(variant['selling_points_en'])}"
        max_sim = max(
            (_sim(this_text,
                  f"{c['title']} {c['description']} {' '.join(c['selling_points_en'])}")
             for c in clones),
            default=0.0,
        )
        variant["max_similarity"]    = round(max_sim, 3)
        variant["similarity_warning"] = max_sim > SIM_THRESHOLD

        tok = variant.pop("_tokens", {})
        total_tokens["input"]  += tok.get("input", 0)
        total_tokens["output"] += tok.get("output", 0)

        new_phrases = _extract_phrases(this_text)
        seen_set = set(forbidden_phrases)
        forbidden_phrases.extend(p for p in new_phrases if p not in seen_set)
        forbidden_phrases = forbidden_phrases[:40]

        clones.append(variant)

    # Optionally create products
    created_skus: list[str] = []
    if not dry_run and clones:
        base = {k: product.get(k) for k in [
            "category_code", "series", "size_label",
            "pcs_per_pack", "packs_per_case",
            "price_tiktok", "price_temu", "price_ebay",
            "price_ebay_local", "price_independent",
            "currency", "tier", "proof",
            "selling_points_zh", "scenarios_en", "vocabulary_en",
        ] if product.get(k) is not None}
        for c in clones:
            new_p = {**base, "sku_code": c["sku_code"], "name_en": c["title"],
                     "description_en": c["description"],
                     "selling_points_en": c["selling_points_en"],
                     "is_main_push": 0, "status": "active"}
            try:
                r = _create_product_in_pg(new_p)
                created_skus.append(r.get("sku_code", c["sku_code"]))
            except HTTPException as e:
                created_skus.append(f"{c['sku_code']} ({'already exists' if e.status_code == 409 else str(e.detail)})")

    # Optionally save preset
    if payload.get("save_as_preset") and raw_variants:
        _save_preset(str(payload["save_as_preset"]), global_style,
                     raw_variants, user.get("username", ""))

    return {
        "source":      {"id": product.get("id"), "sku_code": sku,
                        "name_en": product.get("name_en"),
                        "category": product.get("category_name")},
        "clones":      clones,
        "created_skus": created_skus,
        "dry_run":     dry_run,
        "platform": {
            "title_max_chars": TITLE_MAX,
            "image_max_count": 9,
            "image_size_px":   "600×600",
            "image_formats":   ["JPG", "JPEG", "PNG"],
            "sku_rule":        "Main variant first; capitalize first letter of each variant name",
        },
        "resolved_provider": provider.get("code"),
        "resolved_model":    feat.get("model") or provider.get("default_model"),
        "tokens":            total_tokens,
        "generated_by":      user.get("username"),
        "ts":                datetime.utcnow().isoformat(),
    }
