"""标题优化器（任务 2.2.2）— TK 热搜关键词埋入产品标题，优化电商搜索权重。

POST /api/v1/ai/optimize_title
    body: {
        "product_id": int,
        "platform": "tiktok" | "temu" | "ebay" | "independent",
        "region": "US" | "UK" | ...   (default "US")
        "keyword_ids": [int, ...]     (optional - if omitted, system picks top relevant)
        "n_variants": 5                (optional - default 5, max 8)
    }
    response: {
        "variants": [
            {"title": "...", "char_count": 87, "rationale": "uses 'period underwear'..."},
            ...
        ],
        "platform_limits": {"max_chars": 100, "recommended_chars": "60-90"},
        "keywords_used": [{"keyword":"...","search_volume":...,"growth_rate":...}, ...],
        "compliance_flags": [...],
        "resolved_provider": "...", "resolved_model": "...",
        "tokens": {"input":..., "output":...}
    }

GET /api/v1/ai/title/info
    Returns readiness status + bound provider + keyword data freshness.
"""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_user_or_above
from app.llm import _call, get_provider_for_feature

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"
FEATURE_CODE = "title_optimizer"

router = APIRouter()


PLATFORM_LIMITS = {
    "tiktok":      {"max_chars": 100, "recommended": "60-90", "label": "TikTok Shop"},
    "temu":        {"max_chars": 80,  "recommended": "50-70", "label": "Temu"},
    "ebay":        {"max_chars": 80,  "recommended": "50-75", "label": "eBay"},
    "independent": {"max_chars": 100, "recommended": "60-95", "label": "X9 独立站"},
}


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def fetch_product(con: sqlite3.Connection, pid: int) -> dict:
    row = con.execute(
        "SELECT p.*, c.code AS category_code, c.name_zh AS category_name "
        "FROM product p LEFT JOIN category c ON c.id=p.category_id WHERE p.id=?",
        (pid,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"product id={pid} not found")
    d = dict(row)
    for col in ("selling_points_en", "vocabulary_en", "creative_angles_en"):
        try:
            d[col] = json.loads(d.get(col) or "[]")
        except (TypeError, json.JSONDecodeError):
            d[col] = []
    return d


def fetch_keywords(con: sqlite3.Connection, *, category_code: str | None,
                   platform: str, region: str, ids: list[int] | None,
                   stale_days: int = 30, limit: int = 8) -> list[dict]:
    if ids:
        placeholders = ",".join(["?"] * len(ids))
        rows = con.execute(
            f"SELECT * FROM tk_hot_keyword WHERE id IN ({placeholders}) AND is_active=1",
            ids
        ).fetchall()
        return [dict(r) for r in rows]

    # auto-pick: same category, fresh, weighted by volume * (1+growth)
    where = ["is_active=1",
             "last_seen_at >= date('now', '-' || ? || ' days')",
             "source_platform=?", "region=?"]
    args: list = [stale_days, platform, region]
    if category_code:
        where.append("(category_hint=? OR category_hint IS NULL)")
        args.append(category_code)
    sql = (f"SELECT * FROM tk_hot_keyword WHERE {' AND '.join(where)} "
           "ORDER BY (COALESCE(search_volume,0) * (1 + COALESCE(growth_rate,0))) DESC "
           "LIMIT ?")
    args.append(limit)
    rows = con.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def load_banned(con: sqlite3.Connection) -> tuple[list[str], dict]:
    row = con.execute(
        "SELECT value FROM app_config WHERE key='outreach.banned_phrases'"
    ).fetchone()
    banned = []
    if row and row["value"]:
        try: banned = json.loads(row["value"])
        except json.JSONDecodeError: pass
    row = con.execute(
        "SELECT value FROM app_config WHERE key='outreach.banned_replacements'"
    ).fetchone()
    repl = {}
    if row and row["value"]:
        try: repl = json.loads(row["value"])
        except json.JSONDecodeError: pass
    return banned, repl


def check_compliance(text: str, banned: list[str], replacements: dict) -> list[dict]:
    flags = []
    lower = text.lower()
    for p in banned:
        if p.lower() in lower:
            flags.append({"phrase": p, "suggestion": replacements.get(p, "rephrase")})
    return flags


def build_prompt(*, product: dict, keywords: list[dict], platform: str,
                 limits: dict, n_variants: int, banned: list[str]) -> tuple[str, str]:
    # ---- system ----
    sys = [
        "You are an e-commerce SEO specialist optimizing product titles for X9, a US care brand.",
        "Goal: produce title variants that maximize discoverability via target-platform search.",
        "",
        f"Target platform: {limits['label']}",
        f"Hard char limit: ≤ {limits['max_chars']} chars (count incl. spaces)",
        f"Recommended length: {limits['recommended']} chars",
        f"Number of variants requested: {n_variants}",
        "",
        "Hard rules:",
        "- Each variant MUST be unique (different keyword pairing or angle)",
        "- Front-load 1 primary keyword from the list below in the first 30 chars",
        "- Include 1-2 attribute words (size / count / 'fragrance free' / 'cotton' etc) from the actual product spec",
        "- Format pattern: [Brand X9] + [Primary Keyword] + [Key Attribute] + [Spec/Pack]",
        "- DO NOT exceed the char limit (truncated titles lose ranking)",
        "- DO NOT use medical claims (treat / cure / prevent / FDA-approved → use FDA registered)",
        "- DO NOT use absolutism (the safest / 100% leak-proof / best in the world)",
        "- DO NOT invent features that aren't in the product info below",
        "- Match casing of the platform: TikTok prefers Title Case, Temu/eBay flexible",
        "",
        "Banned phrases (will fail compliance review):",
        ", ".join(banned[:14]) if banned else "(none)",
    ]

    # ---- user ----
    usr = ["# Product to optimize"]
    usr.append(f"- SKU: {product.get('sku_code')}")
    usr.append(f"- English name (current): {product.get('name_en')}")
    usr.append(f"- Category: {product.get('category_name')} / {product.get('subcategory') or ''}")
    usr.append(f"- Spec / size: {product.get('size_label') or '?'}")
    usr.append(f"- Pack: {product.get('pcs_per_pack') or '?'} pcs/pack")
    sp = product.get("selling_points_en") or []
    if sp:
        usr.append(f"- Top selling points: {' | '.join(sp[:3])}")
    vocab = product.get("vocabulary_en") or []
    if vocab:
        usr.append(f"- SEO vocabulary: {', '.join(vocab[:8])}")
    if product.get("proof"):
        usr.append(f"- Compliance: {product['proof']}")

    usr.append("\n# Hot keywords to consider (rank order, freshest first)")
    if keywords:
        for k in keywords[:8]:
            vol = k.get("search_volume")
            gr = k.get("growth_rate")
            line = f"- \"{k['keyword']}\""
            extras = []
            if vol: extras.append(f"vol≈{vol:,}")
            if gr is not None: extras.append(f"WoW {gr*100:+.0f}%")
            if k.get("rank_position"): extras.append(f"rank #{k['rank_position']}")
            if extras: line += "  (" + ", ".join(extras) + ")"
            usr.append(line)
    else:
        usr.append("- (no fresh keyword data — generate generic SEO-optimized titles based on product info)")

    usr.append("\n# Output format (REQUIRED)")
    usr.append("Return a SINGLE JSON object — no preamble, no code fences, no markdown:")
    usr.append('{"variants": [')
    usr.append('  {"title": "...", "char_count": 87, "primary_keyword": "...", "rationale": "one short sentence"},')
    usr.append('  ...')
    usr.append(']}')

    return "\n".join(sys), "\n".join(usr)


# ============================================================
# Endpoints
# ============================================================
@router.get("/api/v1/ai/title/info")
def title_info() -> dict:
    con = _con()
    try:
        # provider
        try:
            prov, feat = get_provider_for_feature(FEATURE_CODE, include_key=True)
            ready = True; reason = None
            provider_summary = {"code": prov["code"], "model": prov.get("default_model"),
                                "binding": "feature-bound" if feat.get("provider_code") else "global-fallback"}
        except Exception as e:
            from fastapi import HTTPException as HE
            ready = False
            reason = e.detail if isinstance(e, HE) else str(e)
            provider_summary = None

        n_kw = con.execute(
            "SELECT COUNT(*) FROM tk_hot_keyword WHERE is_active=1"
        ).fetchone()[0]
        n_recent = con.execute(
            "SELECT COUNT(*) FROM tk_hot_keyword "
            "WHERE is_active=1 AND last_seen_at >= date('now','-30 days')"
        ).fetchone()[0]
        n_seed = con.execute(
            "SELECT COUNT(*) FROM tk_hot_keyword WHERE notes LIKE 'bootstrap_seed%'"
        ).fetchone()[0]
        last_update = con.execute(
            "SELECT MAX(updated_at) FROM tk_hot_keyword"
        ).fetchone()[0]
    finally:
        con.close()

    return {
        "ready": ready,
        "reason": reason,
        "feature": FEATURE_CODE,
        "provider": provider_summary,
        "keywords": {
            "total_active": n_kw,
            "fresh_30d": n_recent,
            "bootstrap_seeds": n_seed,
            "last_keyword_update": last_update,
            "warning": "data is bootstrap seeds — replace via 廖's scraper for real production results"
                if n_kw == n_seed and n_seed > 0 else None,
        },
        "platforms": PLATFORM_LIMITS,
    }


@router.post("/api/v1/ai/optimize_title", dependencies=[Depends(require_user_or_above)])
async def optimize_title(payload: dict, user: dict = Depends(require_user_or_above)) -> dict:
    pid = payload.get("product_id")
    if not pid:
        raise HTTPException(400, "product_id required")
    platform = payload.get("platform", "tiktok")
    if platform not in PLATFORM_LIMITS:
        raise HTTPException(400, f"platform must be one of {list(PLATFORM_LIMITS)}")
    region = payload.get("region", "US")
    n_variants = max(1, min(8, int(payload.get("n_variants") or 5)))
    keyword_ids = payload.get("keyword_ids") or []

    con = _con()
    try:
        product = fetch_product(con, int(pid))
        keywords = fetch_keywords(
            con,
            category_code=product.get("category_code"),
            platform=platform if platform != "independent" else "tiktok",  # 独立站 reuse tiktok kw
            region=region,
            ids=keyword_ids if keyword_ids else None,
            limit=8,
        )
        banned, replacements = load_banned(con)
        limits = PLATFORM_LIMITS[platform]

        sys_prompt, usr_prompt = build_prompt(
            product=product, keywords=keywords, platform=platform,
            limits=limits, n_variants=n_variants, banned=banned,
        )

        prov, feat = get_provider_for_feature(FEATURE_CODE, include_key=True)

        try:
            result = _call(
                prov,
                messages=[{"role": "user", "content": usr_prompt}],
                system=sys_prompt,
                model=feat.get("model"),
                max_tokens=int(feat.get("max_tokens") or 800),
                temperature=float(feat.get("temperature") if feat.get("temperature") is not None else 0.6),
            )
        except RuntimeError as e:
            raise HTTPException(502, f"LLM error: {e}")

        raw = (result.get("content") or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.lstrip().startswith("json"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw
            raw = raw.rsplit("```", 1)[0].strip()
        try:
            parsed = json.loads(raw)
            variants = parsed.get("variants") or []
        except json.JSONDecodeError:
            # graceful fallback: split lines as variants
            variants = [{"title": line.strip("- *0123456789. "), "rationale": "(LLM returned non-JSON, parsed line-by-line)"}
                        for line in raw.split("\n") if 20 < len(line.strip()) < 120][:n_variants]

        # Post-process: char count + compliance per variant
        clean_variants = []
        for v in variants[:n_variants]:
            title = (v.get("title") or "").strip()
            if not title: continue
            char_count = len(title)
            flags = check_compliance(title, banned, replacements)
            over_limit = char_count > limits["max_chars"]
            clean_variants.append({
                "title": title,
                "char_count": char_count,
                "primary_keyword": v.get("primary_keyword"),
                "rationale": v.get("rationale", ""),
                "compliance_flags": flags,
                "over_limit": over_limit,
            })

        return {
            "product": {"id": product["id"], "sku_code": product["sku_code"],
                        "current_name_en": product.get("name_en")},
            "platform": platform,
            "region": region,
            "platform_limits": limits,
            "variants": clean_variants,
            "keywords_used": [{
                "id": k["id"], "keyword": k["keyword"],
                "search_volume": k.get("search_volume"),
                "growth_rate": k.get("growth_rate"),
                "is_bootstrap": (k.get("notes") or "").startswith("bootstrap_seed"),
            } for k in keywords],
            "resolved_provider": result.get("provider"),
            "resolved_model": result.get("model"),
            "tokens": {"input": result.get("input_tokens"),
                       "output": result.get("output_tokens")},
            "generated_by": user.get("username"),
            "ts": datetime.utcnow().isoformat(),
        }
    finally:
        con.close()
