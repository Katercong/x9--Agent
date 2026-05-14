"""Resource & query registry — the single source of truth for /api/v1.

A "resource" maps to one SQLite table, plus metadata (upsert keys, JSON columns,
foreign-key lookups, optional auto-computed fields). Built-in resources are
hard-coded below; *dynamic* resources are persisted in the `_meta_resource`
table and registered at startup.
"""
from __future__ import annotations
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"

# ---------- Identifier validation (defense vs SQL injection on table/column names) ----------
IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
VALID_TYPES = {"TEXT", "INTEGER", "REAL", "BLOB", "NUMERIC"}


def safe_ident(s: str) -> str:
    if not isinstance(s, str) or not IDENT_RE.match(s):
        raise ValueError(f"invalid identifier: {s!r} (must match {IDENT_RE.pattern})")
    return s


# ---------- Auto-compute helpers ----------
def tier_for(followers: int | None) -> str | None:
    if followers is None:
        return None
    if followers >= 1_000_000: return "S"
    if followers >= 300_000:   return "A"
    if followers >= 100_000:   return "B"
    if followers >= 10_000:    return "C"
    return "D"


# ---------- Resource ----------
@dataclass
class Resource:
    name: str                                              # URL path: /api/v1/data/{name}
    table: str                                             # actual SQL table
    pk: str = "id"
    upsert_keys: list[str] = field(default_factory=list)   # used to dedupe in /bulk
    json_cols: list[str] = field(default_factory=list)
    fk_lookup: dict[str, tuple[str, list[str], str]] = field(default_factory=dict)
    auto_compute: dict[str, Callable[[dict], Any]] = field(default_factory=dict)
    description: str = ""
    is_dynamic: bool = False
    writable: bool = True


# ============================================================
# Built-in resources (always present)
# ============================================================
BUILTIN_RESOURCES: dict[str, Resource] = {
    r.name: r for r in [
        Resource(
            name="creators",
            table="creator",
            upsert_keys=["platform", "handle"],
            json_cols=["category_tags"],
            auto_compute={
                "tier": lambda row: tier_for(row.get("followers")) if "followers" in row else None,
                "profile_url": lambda row: (
                    f"https://www.tiktok.com/@{row.get('handle')}"
                    if not row.get("profile_url") and row.get("platform", "tiktok") == "tiktok" and row.get("handle")
                    else (f"https://www.instagram.com/{row.get('handle')}/"
                          if not row.get("profile_url") and row.get("platform") == "instagram" and row.get("handle")
                          else None)
                ),
            },
            description="TikTok / Instagram / YouTube 达人主表",
        ),
        Resource(
            name="products",
            table="product",
            upsert_keys=["sku_code"],
            json_cols=[
                "selling_points_en", "selling_points_zh", "pain_points_zh",
                "scenarios_en", "scenarios_zh", "vocabulary_en",
                "creative_angles_en", "safe_scenes_en", "creator_match_levels",
            ],
            description="X9 产品主表 (SKU 级)",
        ),
        Resource(
            name="outreach",
            table="outreach",
            upsert_keys=["id"],   # outreach is append-only by default; lookup by id
            fk_lookup={
                # input field -> (foreign table, lookup keys, foreign id column to fill)
                "creator_handle": ("creator", ["handle"], "creator_id"),
            },
            description="建联事件流水",
        ),
        Resource(
            name="product_images",
            table="product_image",
            upsert_keys=["id"],
            description="产品图片关联",
        ),
        Resource(
            name="categories",
            table="category",
            upsert_keys=["code"],
            description="产品类目",
        ),
        Resource(
            name="staff",
            table="staff",
            upsert_keys=["name"],
            description="团队人员",
        ),
        Resource(
            name="audit_log",
            table="audit_log",
            upsert_keys=["id"],
            writable=False,
            description="审计日志 (只读)",
        ),
    ]
}


# ============================================================
# _meta_resource: persisted registry for dynamic resources
# ============================================================
META_TABLE = "_meta_resource"

CREATE_META_SQL = f"""
CREATE TABLE IF NOT EXISTS {META_TABLE} (
    name        TEXT PRIMARY KEY,
    table_name  TEXT NOT NULL,
    pk          TEXT DEFAULT 'id',
    upsert_keys TEXT,                     -- JSON array
    json_cols   TEXT,                     -- JSON array
    fk_lookup   TEXT,                     -- JSON object (resource_field: [table, [keys], target_col])
    description TEXT,
    is_dynamic  INTEGER NOT NULL DEFAULT 1,
    writable    INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now'))
)
"""


def ensure_meta_table(con: sqlite3.Connection) -> None:
    con.execute(CREATE_META_SQL)
    # forward-compat: add `deprecated_note` column if missing (for soft deprecations)
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({META_TABLE})")]
    if "deprecated_note" not in cols:
        con.execute(f"ALTER TABLE {META_TABLE} ADD COLUMN deprecated_note TEXT")
    # ensure built-ins exist (idempotent insert)
    for r in BUILTIN_RESOURCES.values():
        con.execute(
            f"INSERT INTO {META_TABLE}(name,table_name,pk,upsert_keys,json_cols,fk_lookup,"
            "description,is_dynamic,writable) VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET table_name=excluded.table_name, "
            "pk=excluded.pk, upsert_keys=excluded.upsert_keys, json_cols=excluded.json_cols, "
            "fk_lookup=excluded.fk_lookup, description=excluded.description, "
            "is_dynamic=excluded.is_dynamic, writable=excluded.writable",
            (
                r.name, r.table, r.pk,
                json.dumps(r.upsert_keys),
                json.dumps(r.json_cols),
                json.dumps({k: list(v) for k, v in r.fk_lookup.items()}),
                r.description,
                int(r.is_dynamic),
                int(r.writable),
            ),
        )
    con.commit()


def load_resources(con: sqlite3.Connection) -> dict[str, Resource]:
    """Read meta table + return full registry. Re-runnable."""
    ensure_meta_table(con)
    out: dict[str, Resource] = {}
    cur = con.execute(f"SELECT * FROM {META_TABLE}")
    cols = [c[0] for c in cur.description]
    for row in cur.fetchall():
        d = dict(zip(cols, row))
        fk = json.loads(d.get("fk_lookup") or "{}")
        res = Resource(
            name=d["name"],
            table=d["table_name"],
            pk=d.get("pk") or "id",
            upsert_keys=json.loads(d.get("upsert_keys") or "[]"),
            json_cols=json.loads(d.get("json_cols") or "[]"),
            fk_lookup={k: tuple(v) for k, v in fk.items()},
            auto_compute=BUILTIN_RESOURCES[d["name"]].auto_compute if d["name"] in BUILTIN_RESOURCES else {},
            description=d.get("description") or "",
            is_dynamic=bool(d.get("is_dynamic")),
            writable=bool(d.get("writable", 1)),
        )
        # surface deprecation note if set (廖 那边可以根据这个收到提示)
        if d.get("deprecated_note"):
            res.description = (res.description or "") + f" [DEPRECATED: {d['deprecated_note']}]"
        out[d["name"]] = res
    return out


def register_dynamic(con: sqlite3.Connection, *, name: str, table: str, pk: str = "id",
                     upsert_keys: list[str] | None = None,
                     json_cols: list[str] | None = None,
                     fk_lookup: dict | None = None,
                     description: str = "") -> None:
    safe_ident(name)
    safe_ident(table)
    if pk:
        safe_ident(pk)
    for k in upsert_keys or []:
        safe_ident(k)
    for k in json_cols or []:
        safe_ident(k)
    con.execute(
        f"INSERT INTO {META_TABLE}(name,table_name,pk,upsert_keys,json_cols,fk_lookup,"
        "description,is_dynamic,writable) VALUES(?,?,?,?,?,?,?,1,1) "
        "ON CONFLICT(name) DO UPDATE SET upsert_keys=excluded.upsert_keys, "
        "json_cols=excluded.json_cols, fk_lookup=excluded.fk_lookup, "
        "description=excluded.description",
        (
            name, table, pk,
            json.dumps(upsert_keys or []),
            json.dumps(json_cols or []),
            json.dumps(fk_lookup or {}),
            description,
        ),
    )
    con.commit()


# ============================================================
# Named queries (saved SQL recipes for /api/v1/queries/<name>)
# ============================================================
@dataclass
class NamedQuery:
    name: str
    description: str
    sql: str                                    # may contain :param placeholders
    params: list[tuple[str, str, Any]] = field(default_factory=list)  # (name, type, default)


NAMED_QUERIES: dict[str, NamedQuery] = {}


def _q(name: str, description: str, sql: str, params: list[tuple] = None):
    NAMED_QUERIES[name] = NamedQuery(name, description, sql, params or [])


_q("creators_to_contact",
   "待发起邀约的达人 (status=prospect)",
   """
   SELECT id, handle, platform, profile_url, followers, tier, avg_views,
          gmv_30d_usd, pps, category_tags, country, source
   FROM creator
   WHERE current_status = 'prospect'
     AND (:category IS NULL OR category_tags LIKE '%' || :category || '%')
     AND (:min_followers IS NULL OR followers >= :min_followers)
   ORDER BY followers DESC NULLS LAST
   LIMIT :limit
   """,
   [("category", "str", None), ("min_followers", "int", None), ("limit", "int", 50)])

_q("creators_follow_up",
   "已建联但 N 天没动静的达人，给 24h SOP 用",
   """
   SELECT id, handle, platform, profile_url, current_status, last_contact_date,
          owner_bd, store_assigned
   FROM creator
   WHERE current_status IN ('contacted','confirmed','sample_shipped','sample_delivered')
     AND COALESCE(last_contact_date, '') < date('now', '-' || :stale_days || ' days')
   ORDER BY last_contact_date ASC
   LIMIT :limit
   """,
   [("stale_days", "int", 2), ("limit", "int", 100)])

_q("outreach_video_tracking",
   "已发布视频但指标未刷新或过期的 outreach 行 (>:stale_hours 小时)",
   """
   SELECT o.id AS outreach_id, c.handle, c.platform, o.video_url,
          o.video_views, o.video_likes, o.video_comments, o.video_shares,
          o.metrics_updated_at, o.event_date
   FROM outreach o JOIN creator c ON c.id = o.creator_id
   WHERE o.video_url IS NOT NULL AND o.video_url != ''
     AND (o.metrics_updated_at IS NULL
          OR o.metrics_updated_at < datetime('now', '-' || :stale_hours || ' hours'))
   ORDER BY COALESCE(o.metrics_updated_at, '') ASC
   LIMIT :limit
   """,
   [("stale_hours", "int", 24), ("limit", "int", 100)])

_q("outreach_auth_pending",
   "视频已发但缺 Spark Ads 授权码",
   """
   SELECT o.id AS outreach_id, c.handle, c.platform, c.owner_bd,
          o.event_date, o.video_url, o.remark
   FROM outreach o JOIN creator c ON c.id = o.creator_id
   WHERE o.video_url IS NOT NULL AND o.video_url != ''
     AND (o.ad_auth_code IS NULL OR o.ad_auth_code = '')
   ORDER BY o.event_date ASC
   LIMIT :limit
   """,
   [("limit", "int", 100)])

_q("products_main_push",
   "主推 SKU 列表",
   """
   SELECT p.id, p.sku_code, p.name_en, p.name_zh, p.tier, p.positioning_zh,
          p.price_tiktok, p.creator_match_levels, c.code AS category_code, c.name_zh AS category_name
   FROM product p LEFT JOIN category c ON c.id = p.category_id
   WHERE p.is_main_push = 1
   ORDER BY p.tier, p.id
   LIMIT :limit
   """,
   [("limit", "int", 50)])

_q("creators_by_tier",
   "按等级筛达人",
   """
   SELECT id, handle, platform, profile_url, followers, tier, avg_views,
          gmv_30d_usd, pps, current_status, owner_bd
   FROM creator
   WHERE tier = :tier
   ORDER BY followers DESC NULLS LAST
   LIMIT :limit
   """,
   [("tier", "str", "A"), ("limit", "int", 100)])

# ===== 3.1.2 + 3.1.3 任务相关 =====
_q("creators_mid_tier_koc",
   "中腰部 KOC（1K-50W 粉，未排除，未与竞品合作）",
   """
   SELECT c.id, c.handle, c.platform, c.profile_url, c.followers, c.tier,
          c.avg_views, c.engagement_rate, c.gmv_30d_usd, c.pps,
          c.country, c.category_tags, c.current_status, c.owner_bd
   FROM creator c
   WHERE c.followers BETWEEN :min_followers AND :max_followers
     AND c.excluded = 0
     AND c.id NOT IN (SELECT DISTINCT creator_id FROM creator_competitor_collab)
     AND (:category IS NULL OR c.category_tags LIKE '%' || :category || '%')
     AND (:min_engagement IS NULL OR c.engagement_rate >= :min_engagement)
     AND (:country IS NULL OR c.country = :country)
   ORDER BY c.engagement_rate DESC NULLS LAST, c.followers DESC NULLS LAST
   LIMIT :limit
   """,
   [("min_followers", "int", 1000), ("max_followers", "int", 500000),
    ("category", "str", None), ("min_engagement", "float", None),
    ("country", "str", None), ("limit", "int", 100)])

_q("creators_high_engagement",
   "按互动率排序的达人（默认 ≥3%）",
   """
   SELECT c.id, c.handle, c.followers, c.tier, c.engagement_rate,
          c.avg_views, c.country, c.current_status,
          (SELECT COUNT(*) FROM creator_competitor_collab WHERE creator_id=c.id) AS competitor_collabs
   FROM creator c
   WHERE c.excluded = 0
     AND c.engagement_rate IS NOT NULL
     AND c.engagement_rate >= :min_engagement
     AND (:max_followers IS NULL OR c.followers <= :max_followers)
   ORDER BY c.engagement_rate DESC LIMIT :limit
   """,
   [("min_engagement", "float", 0.03),
    ("max_followers", "int", None),
    ("limit", "int", 100)])

_q("creators_blacklisted",
   "已排除 / 已合作竞品的达人（黑名单视图）",
   """
   SELECT c.id, c.handle, c.tier, c.followers, c.excluded, c.excluded_reason,
          c.current_status,
          (SELECT GROUP_CONCAT(cb.display_name, '; ')
           FROM creator_competitor_collab ccc
           JOIN competitor_brand cb ON cb.id=ccc.competitor_brand_id
           WHERE ccc.creator_id=c.id) AS competitor_brands
   FROM creator c
   WHERE c.excluded = 1
      OR c.id IN (SELECT DISTINCT creator_id FROM creator_competitor_collab)
   ORDER BY c.id LIMIT :limit
   """,
   [("limit", "int", 200)])

_q("creators_by_content_match",
   "内容标签匹配某品类的达人（用于按 category 推荐）",
   """
   SELECT c.id, c.handle, c.tier, c.followers, c.engagement_rate,
          c.category_tags, c.country, c.current_status
   FROM creator c
   WHERE c.excluded = 0
     AND c.category_tags LIKE '%' || :category_keyword || '%'
     AND (:min_followers IS NULL OR c.followers >= :min_followers)
     AND (:max_followers IS NULL OR c.followers <= :max_followers)
     AND c.id NOT IN (SELECT DISTINCT creator_id FROM creator_competitor_collab)
   ORDER BY c.engagement_rate DESC NULLS LAST, c.followers DESC NULLS LAST
   LIMIT :limit
   """,
   [("category_keyword", "str", "女性护理"),
    ("min_followers", "int", None),
    ("max_followers", "int", None),
    ("limit", "int", 100)])

# ===== 任务 2.2.2 — TK 热搜关键词 =====
_q("hot_keywords_recent",
   "近 N 天的 TK 热搜关键词（按搜索量降序）",
   """
   SELECT id, keyword, source_platform, region, category_hint,
          search_volume, growth_rate, rank_position, last_seen_at
   FROM tk_hot_keyword
   WHERE is_active = 1
     AND last_seen_at >= date('now', '-' || :stale_days || ' days')
     AND (:platform IS NULL OR source_platform = :platform)
     AND (:region IS NULL OR region = :region)
   ORDER BY search_volume DESC NULLS LAST, growth_rate DESC NULLS LAST
   LIMIT :limit
   """,
   [("stale_days", "int", 30),
    ("platform", "str", "tiktok"),
    ("region", "str", "US"),
    ("limit", "int", 50)])

_q("hot_keywords_by_category",
   "按品类筛 TK 热搜关键词（搜索量 + 增长率排序）",
   """
   SELECT id, keyword, search_volume, growth_rate, rank_position, last_seen_at
   FROM tk_hot_keyword
   WHERE is_active = 1
     AND category_hint = :category
     AND last_seen_at >= date('now', '-' || :stale_days || ' days')
     AND (:platform IS NULL OR source_platform = :platform)
     AND (:region IS NULL OR region = :region)
   ORDER BY (COALESCE(search_volume, 0) * (1 + COALESCE(growth_rate, 0))) DESC
   LIMIT :limit
   """,
   [("category", "str", "female_care"),
    ("stale_days", "int", 30),
    ("platform", "str", "tiktok"),
    ("region", "str", "US"),
    ("limit", "int", 20)])

_q("hot_keywords_growing",
   "近期增长最快的 TK 热搜（适合趋势性投放）",
   """
   SELECT id, keyword, category_hint, source_platform, region,
          search_volume, growth_rate, rank_position, last_seen_at
   FROM tk_hot_keyword
   WHERE is_active = 1
     AND growth_rate IS NOT NULL
     AND growth_rate >= :min_growth
     AND last_seen_at >= date('now', '-' || :stale_days || ' days')
     AND (:category IS NULL OR category_hint = :category)
   ORDER BY growth_rate DESC LIMIT :limit
   """,
   [("min_growth", "float", 0.20),
    ("stale_days", "int", 14),
    ("category", "str", None),
    ("limit", "int", 30)])
