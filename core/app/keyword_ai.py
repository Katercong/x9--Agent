"""TK 热搜 AI 分析层 — 把"原始关键词"变成"可决策数据"。

POST /api/v1/ai/keywords/enrich
    给一批关键词分类（category_hint=NULL 的）+ 评估 X9 相关性 + 可选去重提示
    body: {
        "keyword_ids": [int,...]      (可选；不传时取最近 50 条 category_hint IS NULL 的)
        "max_items": 50,               (可选，默认 50)
        "scope": "uncategorized"|"all_recent" (默认 uncategorized)
    }
    response: {
        "enriched": [{id, keyword, category, x9_relevance, is_competitor, reason}, ...],
        "tokens": {input, output},
        "provider": ..., "model": ...
    }

GET /api/v1/keywords/dashboard
    实时仪表盘数据：最近抓取时间 / 趋势上升 top / 异动告警 / 类目分布
    无需认证（只读）
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
FEATURE_CODE = "title_optimizer"   # 复用同一个 feature 绑定（也可以独立）

router = APIRouter()


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# ============================================================
# 仪表盘（仅读，给前端轮询）
# ============================================================
@router.get("/api/v1/keywords/dashboard")
def keyword_dashboard(stale_minutes: int = 60) -> dict:
    """前端每 30s 轮询此端点拿最新状态。"""
    con = _con()
    try:
        # 最近 1 次抓取
        last_run = con.execute(
            "SELECT id, started_at, finished_at, source, region, status, "
            "n_added, n_updated, n_errors FROM scrape_run "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()

        # 总体统计
        total_active = con.execute(
            "SELECT COUNT(*) FROM tk_hot_keyword WHERE is_active=1"
        ).fetchone()[0]
        fresh_count = con.execute(
            "SELECT COUNT(*) FROM tk_hot_keyword "
            "WHERE is_active=1 AND last_seen_at >= datetime('now', '-' || ? || ' minutes')",
            (stale_minutes,)
        ).fetchone()[0]

        # 类目分布
        by_category = con.execute(
            "SELECT COALESCE(category_hint,'(待分类)') AS cat, COUNT(*) AS n "
            "FROM tk_hot_keyword WHERE is_active=1 GROUP BY cat ORDER BY n DESC"
        ).fetchall()

        # 上升 top — growth_rate 最高的 active 关键词
        rising = con.execute(
            "SELECT id, keyword, category_hint, search_volume, growth_rate, "
            "rank_position, last_seen_at FROM tk_hot_keyword "
            "WHERE is_active=1 AND growth_rate IS NOT NULL "
            "ORDER BY growth_rate DESC LIMIT 8"
        ).fetchall()

        # 总搜索量 top
        volume_top = con.execute(
            "SELECT id, keyword, category_hint, search_volume, growth_rate, last_seen_at "
            "FROM tk_hot_keyword WHERE is_active=1 "
            "ORDER BY search_volume DESC LIMIT 8"
        ).fetchall()

        # 待分类（category_hint IS NULL）
        uncategorized = con.execute(
            "SELECT COUNT(*) FROM tk_hot_keyword WHERE category_hint IS NULL AND is_active=1"
        ).fetchone()[0]

        # 历史 7 天每日新增（snapshot 角度）
        history = con.execute(
            "SELECT date(captured_at) AS d, COUNT(DISTINCT keyword_id) AS n "
            "FROM keyword_snapshot WHERE captured_at >= date('now','-7 days') "
            "GROUP BY d ORDER BY d"
        ).fetchall()

        # 最近 5 个 scrape run（运行历史）
        recent_runs = con.execute(
            "SELECT id, started_at, finished_at, source, status, "
            "n_added, n_updated, n_errors FROM scrape_run "
            "ORDER BY id DESC LIMIT 5"
        ).fetchall()
    finally:
        con.close()

    return {
        "ts": datetime.utcnow().isoformat(),
        "totals": {
            "active": total_active,
            "fresh": fresh_count,
            "uncategorized": uncategorized,
            "stale_threshold_minutes": stale_minutes,
        },
        "last_run": dict(last_run) if last_run else None,
        "by_category": [dict(r) for r in by_category],
        "rising_top": [dict(r) for r in rising],
        "volume_top": [dict(r) for r in volume_top],
        "history_7d": [dict(r) for r in history],
        "recent_runs": [dict(r) for r in recent_runs],
    }


@router.get("/api/v1/keywords/{kid}/trend")
def keyword_trend(kid: int, days: int = 30) -> dict:
    """单个关键词的历史趋势（折线图用）"""
    con = _con()
    try:
        kw = con.execute(
            "SELECT id, keyword, category_hint, search_volume, growth_rate, last_seen_at "
            "FROM tk_hot_keyword WHERE id=?", (kid,)
        ).fetchone()
        if not kw:
            raise HTTPException(404, "keyword not found")
        snaps = con.execute(
            "SELECT captured_at, search_volume, growth_rate, rank_position "
            "FROM keyword_snapshot "
            "WHERE keyword_id=? AND captured_at >= date('now','-' || ? || ' days') "
            "ORDER BY captured_at ASC",
            (kid, days)
        ).fetchall()
    finally:
        con.close()
    return {
        "keyword": dict(kw),
        "snapshots": [dict(s) for s in snaps],
        "days": days,
    }


# ============================================================
# AI 分析
# ============================================================
@router.post("/api/v1/ai/keywords/enrich", dependencies=[Depends(require_user_or_above)])
async def enrich_keywords(payload: dict | None = None,
                           user: dict = Depends(require_user_or_above)) -> dict:
    """对一批关键词做：分类（必填）+ X9 相关性评分（0-1）+ 是否疑似竞品词。"""
    payload = payload or {}
    ids = payload.get("keyword_ids") or []
    max_items = min(int(payload.get("max_items") or 50), 100)
    scope = payload.get("scope", "uncategorized")

    con = _con()
    try:
        if ids:
            placeholders = ",".join(["?"] * len(ids))
            rows = con.execute(
                f"SELECT id, keyword, category_hint, search_volume, growth_rate, notes "
                f"FROM tk_hot_keyword WHERE id IN ({placeholders})",
                ids
            ).fetchall()
        elif scope == "all_recent":
            rows = con.execute(
                "SELECT id, keyword, category_hint, search_volume, growth_rate, notes "
                "FROM tk_hot_keyword "
                "WHERE is_active=1 ORDER BY last_seen_at DESC LIMIT ?",
                (max_items,)
            ).fetchall()
        else:
            # default: uncategorized
            rows = con.execute(
                "SELECT id, keyword, category_hint, search_volume, growth_rate, notes "
                "FROM tk_hot_keyword WHERE is_active=1 AND category_hint IS NULL "
                "ORDER BY search_volume DESC NULLS LAST LIMIT ?",
                (max_items,)
            ).fetchall()
        items = [dict(r) for r in rows]
    finally:
        con.close()

    if not items:
        return {"enriched": [], "message": "nothing to enrich (no matches)"}

    # 构建 prompt
    sys_prompt = """你是一个电商 SEO 分类专家。对一批 TikTok 热搜关键词做以下分析：

1. **category** (必填): 从这 7 个里选一个：female_care / pet / baby / adult_care / home_care / mask / other
2. **x9_relevance** (0-1): 这个关键词跟 X9 (一个做女性护理/母婴/成人护理/宠物护理的品牌) 多相关？
   - 1.0 = 完全相关 (例如 "organic cotton pads")
   - 0.5 = 部分相关 (例如 "feminine hygiene" — 太宽泛)
   - 0 = 无关 (例如 "bluetooth headphones")
3. **is_competitor_term**: 是否是竞品品牌词？(true/false)。例如 "Always pads", "lola period", "kotex".
4. **reason**: 一句话理由（中英文都可，<60 字）

输出严格 JSON 数组，长度等于输入数量，按输入顺序：
[
  {"id": 12, "category": "female_care", "x9_relevance": 0.95, "is_competitor_term": false, "reason": "..."},
  ...
]
不要任何 markdown 代码块，只输出 JSON 数组。"""

    user_prompt_lines = ["请分析以下关键词："]
    for it in items:
        user_prompt_lines.append(
            f"id={it['id']}: \"{it['keyword']}\" (vol≈{it.get('search_volume') or '?'}, growth={it.get('growth_rate') or '?'})"
        )
    user_prompt = "\n".join(user_prompt_lines)

    prov, feat = get_provider_for_feature(FEATURE_CODE, include_key=True)

    try:
        result = _call(
            prov,
            messages=[{"role": "user", "content": user_prompt}],
            system=sys_prompt,
            model=feat.get("model"),
            max_tokens=int(feat.get("max_tokens") or 2000),
            temperature=0.2,
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
        if not isinstance(parsed, list):
            parsed = parsed.get("items") if isinstance(parsed, dict) else []
    except json.JSONDecodeError:
        raise HTTPException(502, f"LLM returned invalid JSON: {raw[:300]}")

    # Apply updates
    con = _con()
    n_updated = 0
    enriched_out = []
    valid_categories = {"female_care", "pet", "baby", "adult_care", "home_care", "mask", "other"}
    try:
        for it in parsed:
            kid = it.get("id")
            cat = it.get("category")
            relevance = it.get("x9_relevance")
            is_comp = it.get("is_competitor_term")
            reason = it.get("reason", "")
            if not kid:
                continue
            if cat not in valid_categories:
                cat = None  # don't force invalid categories
            update_fields = {}
            if cat:
                update_fields["category_hint"] = cat
            # Append AI reasoning to notes
            old_notes = con.execute(
                "SELECT notes FROM tk_hot_keyword WHERE id=?", (kid,)
            ).fetchone()
            old_notes_text = old_notes[0] if old_notes and old_notes[0] else ""
            new_notes = old_notes_text + (f" [AI@{datetime.utcnow().strftime('%m-%d')}: " +
                                           f"cat={cat}, rel={relevance}, comp={is_comp}, {reason}]")
            update_fields["notes"] = new_notes[:500]
            # If x9_relevance is very low (e.g. < 0.2), suggest deactivating
            if relevance is not None and float(relevance) < 0.2:
                update_fields["is_active"] = 0
            sets = ",".join([f"{k}=?" for k in update_fields])
            con.execute(
                f"UPDATE tk_hot_keyword SET {sets} WHERE id=?",
                list(update_fields.values()) + [kid]
            )
            n_updated += 1
            enriched_out.append({
                "id": kid,
                "keyword": next((it2["keyword"] for it2 in items if it2["id"] == kid), None),
                "category": cat,
                "x9_relevance": relevance,
                "is_competitor_term": is_comp,
                "reason": reason,
                "deactivated": (relevance is not None and float(relevance) < 0.2),
            })
        con.commit()
    finally:
        con.close()

    return {
        "enriched": enriched_out,
        "n_input": len(items),
        "n_updated": n_updated,
        "tokens": {
            "input": result.get("input_tokens"),
            "output": result.get("output_tokens"),
        },
        "provider": result.get("provider"),
        "model": result.get("model"),
        "ts": datetime.utcnow().isoformat(),
    }


# ============================================================
# AI 关键词头脑风暴（v3.10.1）
# ============================================================
@router.post("/api/v1/ai/keywords/suggest", dependencies=[Depends(require_user_or_above)])
async def suggest_keywords(payload: dict | None = None,
                            user: dict = Depends(require_user_or_above)) -> dict:
    """让 LLM 头脑风暴 N 个 TikTok 热搜关键词建议。
    返回 suggestion 列表，前端勾选后通过 /api/v1/data/tk_hot_keywords/bulk 写入。

    body: {
        "category_hint": "female_care"|"pet"|"baby"|"adult_care"|"home_care"|"mask"|null,
        "count": 10,                 // 1-30
        "notes": "想推 organic 系列",  // 可选指引
        "region": "US"               // 默认 US
    }
    response: {
        "suggestions": [{"keyword","category_hint","rationale","expected_relevance","competitor_risk"}, ...],
        "tokens": {input,output}, "provider", "model"
    }
    """
    payload = payload or {}
    cat = payload.get("category_hint")
    count = int(payload.get("count") or 10)
    if count < 1 or count > 30:
        raise HTTPException(400, "count must be 1-30")
    region = (payload.get("region") or "US").upper()
    extra_notes = (payload.get("notes") or "").strip()

    valid_cats = {"female_care", "pet", "baby", "adult_care", "home_care", "mask"}
    if cat and cat not in valid_cats:
        raise HTTPException(400, f"category_hint must be one of {sorted(valid_cats)} or null")

    # 拉现有关键词避免重复推荐
    con = _con()
    try:
        existing = [r[0] for r in con.execute(
            "SELECT keyword FROM tk_hot_keyword WHERE region=? "
            "AND (? IS NULL OR category_hint=?) AND is_active=1 LIMIT 100",
            (region, cat, cat)
        )]
    finally:
        con.close()

    sys_prompt = """你是 TikTok 美区 SEO 选词专家，给 X9 品牌选热搜关键词。
X9 业务范围: 女性护理 (卫生巾/护垫/卫生棉条)、母婴 (婴儿尿不湿)、成人护理 (失禁产品)、宠物 (宠物尿垫)、家居清洁、口罩。

输出严格 JSON 对象，不要 markdown 代码块：
{"suggestions": [
  {"keyword": "...", "category_hint": "female_care|pet|baby|adult_care|home_care|mask",
   "rationale": "<一句话理由, 中英文都可, ≤80字>",
   "expected_relevance": "high|medium|low",
   "competitor_risk": "low|medium|high"},
  ...
]}

要求:
- 关键词必须是英文, 全小写, 不带 # 或 @
- 长度 1-5 词为主 (TikTok 搜索特征)
- 区分 generic 词 (period underwear) vs 长尾词 (organic cotton period underwear for teens)
- competitor_risk=high 表示该词主要被竞品占据 (Always/Kotex/Lola/Tena/Pampers/Huggies/Petsafe), 不推荐做主词
- 不要重复输入里的"已存在词"
- 优先 medium-relevance 长尾 + 一两条 high-relevance generic"""

    user_lines = [f"region: {region}"]
    if cat:
        user_lines.append(f"目标品类: {cat}")
    else:
        user_lines.append("目标品类: 全部 X9 业务范围")
    user_lines.append(f"需要数量: {count}")
    if extra_notes:
        user_lines.append(f"额外指引: {extra_notes}")
    if existing:
        user_lines.append(f"\n已存在的关键词（不要重复推荐）: {', '.join(existing[:50])}")
    user_prompt = "\n".join(user_lines)

    prov, feat = get_provider_for_feature(FEATURE_CODE, include_key=True)
    try:
        result = _call(
            prov,
            messages=[{"role": "user", "content": user_prompt}],
            system=sys_prompt,
            model=feat.get("model"),
            max_tokens=int(feat.get("max_tokens") or 1500),
            temperature=0.6,
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
    except json.JSONDecodeError:
        raise HTTPException(502, f"LLM returned invalid JSON: {raw[:300]}")

    suggestions = parsed.get("suggestions") if isinstance(parsed, dict) else parsed
    if not isinstance(suggestions, list):
        raise HTTPException(502, "LLM output missing suggestions array")

    # 过滤已存在 + 标记
    existing_lower = {k.lower() for k in existing}
    cleaned = []
    for s in suggestions:
        kw = (s.get("keyword") or "").strip().lower()
        if not kw or kw in existing_lower:
            continue
        cleaned.append({
            "keyword": kw,
            "category_hint": s.get("category_hint") if s.get("category_hint") in valid_cats else cat,
            "rationale": s.get("rationale", ""),
            "expected_relevance": s.get("expected_relevance", "medium"),
            "competitor_risk": s.get("competitor_risk", "low"),
            "region": region,
            "source_platform": "tiktok",
        })

    return {
        "suggestions": cleaned,
        "n_returned": len(cleaned),
        "n_filtered_dup": len(suggestions) - len(cleaned),
        "tokens": {
            "input": result.get("input_tokens"),
            "output": result.get("output_tokens"),
        },
        "provider": result.get("provider"),
        "model": result.get("model"),
        "ts": datetime.utcnow().isoformat(),
    }
