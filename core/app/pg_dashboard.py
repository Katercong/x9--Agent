from __future__ import annotations

import math
import os
import json
import re
from pathlib import Path
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from psycopg import sql
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_MAP = ROOT / "exports" / "db_visualization.html"
PG_DSN = os.environ.get(
    "X9_PG_DSN",
    "postgresql://x9:x9_local_dev_2026@localhost:15432/x9db?connect_timeout=5",
)

IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

GROUPS = {
    "product": {
        "label": "Products",
        "color": "#287c73",
        "tables": {"category", "product", "product_image", "outreach_sku"},
    },
    "legacy": {
        "label": "Legacy BD",
        "color": "#b15f4a",
        "tables": {"creator", "outreach", "creator_product", "creator_competitor_collab", "staff"},
    },
    "lead": {
        "label": "Lead Intelligence",
        "color": "#4b76a8",
        "tables": {
            "tk_creators",
            "creators",
            "creator_tags",
            "creator_recommendations",
            "raw_observations",
            "review_tasks",
            "tag_definitions",
        },
    },
    "keywords": {
        "label": "Keywords",
        "color": "#9a7a2f",
        "tables": {"tk_hot_keyword", "keyword_snapshot", "scrape_run"},
    },
    "ai": {
        "label": "AI & Config",
        "color": "#596f3a",
        "tables": {
            "llm_provider",
            "llm_feature",
            "app_config",
            "brand_profile",
            "competitor_brand",
            "outreach_example",
            "outbox",
            "system_logs",
        },
    },
    "auth": {
        "label": "Auth",
        "color": "#7c5f9b",
        "tables": {"api_user", "api_key", "audit_log"},
    },
    "extension": {
        "label": "Extension",
        "color": "#8b6b3e",
        "tables": {"extension_sessions", "extension_commands", "extension_run_progress"},
    },
    "email": {
        "label": "Email",
        "color": "#3c7f9b",
        "tables": {"gmail_accounts", "outreach_templates", "outreach_emails", "webhook_subscriber"},
    },
    "metadata": {
        "label": "Metadata",
        "color": "#5b6b8c",
        "tables": {"_meta_query", "_meta_resource", "migration_manifest"},
    },
    "other": {"label": "Other", "color": "#6e737c", "tables": set()},
}


app = FastAPI(title="X9 PostgreSQL Dashboard", version="0.1.0")

NORMALIZED_HANDLE_SQL = """
lower(trim(regexp_replace(
  CASE
    WHEN coalesce(handle, '') ~ '^[A-Za-z0-9_.]+$' THEN handle
    WHEN coalesce(display_name, '') ~ '^[A-Za-z0-9_.]+$' THEN display_name
    ELSE coalesce(handle, '')
  END,
  '^@', '', 'g'
)))
"""

I18N = {
    "zh": {
        "lang_attr": "zh-CN",
        "page_title": "X9 PostgreSQL 数据看板",
        "subtitle": "实时视图 · x9db · localhost:15432",
        "schema_map": "结构图",
        "refresh": "刷新",
        "search_placeholder": "搜索表或字段",
        "loading_tables": "正在加载数据表...",
        "health_checks": "健康检查",
        "data_statistics": "数据统计",
        "rows_by_domain": "按业务域统计行数",
        "largest_tables": "最大数据表",
        "products_by_category": "按类目统计产品",
        "lead_fit_level": "Lead 匹配等级",
        "lead_email_coverage": "Lead 邮箱覆盖",
        "creator_merge_preview": "达人合并预览",
        "select_table": "请选择一张表",
        "loading": "加载中...",
        "all_groups": "全部",
        "stats": {
            "tables": "数据表",
            "rows": "行数",
            "columns": "字段",
            "indexes": "索引",
            "checks_ok": "检查通过",
        },
        "orphan_rows": "条孤儿记录",
        "raw_handles": "原始 handle",
        "normalized_entities": "归一化实体",
        "total": "总数",
        "all_three": "三表都有",
        "creator_only": "仅旧达人表",
        "tk_x9_only": "仅 TK+X9",
        "cols_short": "列",
        "idx_short": "索引",
        "rows_word": "行",
        "columns_word": "字段",
        "indexes_word": "索引",
        "columns_title": "字段",
        "sample_rows": "样例数据",
        "no_sample_rows": "没有样例数据",
        "groups": {
            "product": "产品",
            "legacy": "旧建联",
            "lead": "Lead 智能",
            "keywords": "关键词",
            "ai": "AI 与配置",
            "auth": "权限",
            "extension": "插件",
            "email": "邮件",
            "metadata": "元数据",
            "other": "其他",
        },
    },
    "en": {
        "lang_attr": "en",
        "page_title": "X9 PostgreSQL Dashboard",
        "subtitle": "Live view · x9db · localhost:15432",
        "schema_map": "Schema Map",
        "refresh": "Refresh",
        "search_placeholder": "Search table or column",
        "loading_tables": "Loading tables...",
        "health_checks": "Health Checks",
        "data_statistics": "Data Statistics",
        "rows_by_domain": "Rows by Domain",
        "largest_tables": "Largest Tables",
        "products_by_category": "Products by Category",
        "lead_fit_level": "Lead Fit Level",
        "lead_email_coverage": "Lead Email Coverage",
        "creator_merge_preview": "Creator Merge Preview",
        "select_table": "Select a table",
        "loading": "Loading...",
        "all_groups": "All",
        "stats": {
            "tables": "Tables",
            "rows": "Rows",
            "columns": "Columns",
            "indexes": "Indexes",
            "checks_ok": "Checks OK",
        },
        "orphan_rows": "orphan rows",
        "raw_handles": "Raw handles",
        "normalized_entities": "Normalized entities",
        "total": "Total",
        "all_three": "All three",
        "creator_only": "Creator only",
        "tk_x9_only": "TK+X9 only",
        "cols_short": "cols",
        "idx_short": "idx",
        "rows_word": "rows",
        "columns_word": "columns",
        "indexes_word": "indexes",
        "columns_title": "Columns",
        "sample_rows": "Sample Rows",
        "no_sample_rows": "No sample rows",
        "groups": {},
    },
}

BUSINESS_I18N = {
    "zh": {
        "lang_attr": "zh-CN",
        "page_title": "X9 业务数据看板",
        "subtitle": "给老板和公司团队看的实时经营数据 · 产品 · 达人 · 建联 · 热搜",
        "refresh": "刷新",
        "tech": "技术版",
        "schema": "结构图",
        "loading": "正在加载业务数据...",
        "sections": {
            "overview": "业务总览",
            "portfolio": "产品结构",
            "creator": "达人与 Lead 池",
            "outreach": "建联进展",
            "keywords": "TK 热搜与内容方向",
            "actions": "当前需要关注",
            "top_leads": "优先跟进 Lead",
        },
        "cards": {
            "products": "SKU 总数",
            "main_push": "主推 SKU",
            "images": "素材图片",
            "leads": "Lead 池",
            "email_rate": "Lead 邮箱覆盖",
            "outreach": "建联流水",
            "keywords": "热搜关键词",
            "unique_creators": "去重达人实体",
        },
        "charts": {
            "product_categories": "产品类目分布",
            "lead_fit": "Lead 匹配等级",
            "outreach_status": "建联状态",
            "creator_status": "旧达人状态",
            "keyword_category": "关键词品类",
            "owner_bd": "BD 负责人分布",
        },
        "actions": {
            "missing_email": "Lead 缺邮箱",
            "review_required": "需要人工审核",
            "unassigned": "未分配负责人",
            "unknown_keywords": "未分类关键词",
            "video_links": "已记录视频链接",
            "auth_codes": "已记录授权码",
        },
        "lead_cols": {
            "handle": "账号",
            "email": "邮箱",
            "fit": "匹配",
            "score": "推荐分",
            "category": "推荐品类",
            "priority": "优先级",
        },
        "empty": "暂无数据",
        "yes": "有",
        "no": "无",
        "language_link": "English",
        "language_href": "/en",
    },
    "en": {
        "lang_attr": "en",
        "page_title": "X9 Business Dashboard",
        "subtitle": "Executive view for products, creators, outreach, and TikTok keyword signals",
        "refresh": "Refresh",
        "tech": "Technical View",
        "schema": "Schema Map",
        "loading": "Loading business metrics...",
        "sections": {
            "overview": "Business Overview",
            "portfolio": "Product Portfolio",
            "creator": "Creator & Lead Pool",
            "outreach": "Outreach Progress",
            "keywords": "TikTok Keywords & Content Signals",
            "actions": "Needs Attention",
            "top_leads": "Priority Leads",
        },
        "cards": {
            "products": "Total SKUs",
            "main_push": "Main-push SKUs",
            "images": "Creative Assets",
            "leads": "Lead Pool",
            "email_rate": "Lead Email Coverage",
            "outreach": "Outreach Records",
            "keywords": "Hot Keywords",
            "unique_creators": "Deduped Creators",
        },
        "charts": {
            "product_categories": "Products by Category",
            "lead_fit": "Lead Fit Level",
            "outreach_status": "Outreach Status",
            "creator_status": "Legacy Creator Status",
            "keyword_category": "Keyword Category",
            "owner_bd": "BD Owner Split",
        },
        "actions": {
            "missing_email": "Leads missing email",
            "review_required": "Manual reviews needed",
            "unassigned": "Unassigned owners",
            "unknown_keywords": "Unclassified keywords",
            "video_links": "Video links recorded",
            "auth_codes": "Auth codes recorded",
        },
        "lead_cols": {
            "handle": "Handle",
            "email": "Email",
            "fit": "Fit",
            "score": "Score",
            "category": "Category",
            "priority": "Priority",
        },
        "empty": "No data",
        "yes": "Yes",
        "no": "No",
        "language_link": "中文",
        "language_href": "/zh",
    },
}


def safe_ident(name: str) -> str:
    if not IDENT_RE.match(name):
        raise HTTPException(400, f"invalid table name: {name}")
    return name


def group_for_table(table: str) -> str:
    for key, group in GROUPS.items():
        if table in group["tables"]:
            return key
    return "other"


def connect():
    return psycopg.connect(PG_DSN, row_factory=dict_row)


def fetch_scalar(cur, query: str, params: tuple[Any, ...] = ()) -> Any:
    cur.execute(query, params)
    row = cur.fetchone()
    return next(iter(row.values())) if row else None


def table_names(cur) -> list[str]:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    )
    return [row["table_name"] for row in cur.fetchall()]


def exact_count(cur, table: str) -> int:
    cur.execute(sql.SQL("SELECT COUNT(*) AS n FROM {}").format(sql.Identifier(table)))
    return int(cur.fetchone()["n"])


def table_size(cur, table: str) -> int:
    cur.execute("SELECT pg_total_relation_size(%s::regclass) AS bytes", (f"public.{table}",))
    return int(cur.fetchone()["bytes"])


def fetch_table_inventory(cur) -> list[dict[str, Any]]:
    names = table_names(cur)
    columns = fetch_columns(cur)
    indexes = fetch_indexes(cur)
    out = []
    for name in names:
        out.append(
            {
                "name": name,
                "group": group_for_table(name),
                "group_label": GROUPS[group_for_table(name)]["label"],
                "color": GROUPS[group_for_table(name)]["color"],
                "rows": exact_count(cur, name),
                "columns": len(columns.get(name, [])),
                "indexes": len(indexes.get(name, [])),
                "size_bytes": table_size(cur, name),
            }
        )
    return out


def fetch_columns(cur) -> dict[str, list[dict[str, Any]]]:
    cur.execute(
        """
        SELECT
          c.table_name,
          c.column_name,
          c.data_type,
          c.is_nullable,
          c.ordinal_position,
          EXISTS (
            SELECT 1
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON kcu.constraint_name = tc.constraint_name
             AND kcu.table_schema = tc.table_schema
             AND kcu.table_name = tc.table_name
            WHERE tc.table_schema = c.table_schema
              AND tc.table_name = c.table_name
              AND tc.constraint_type = 'PRIMARY KEY'
              AND kcu.column_name = c.column_name
          ) AS is_primary_key
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
        ORDER BY c.table_name, c.ordinal_position
        """
    )
    out: dict[str, list[dict[str, Any]]] = {}
    for row in cur.fetchall():
        out.setdefault(row["table_name"], []).append(
            {
                "name": row["column_name"],
                "type": row["data_type"],
                "nullable": row["is_nullable"] == "YES",
                "pk": bool(row["is_primary_key"]),
            }
        )
    return out


def fetch_indexes(cur) -> dict[str, list[dict[str, Any]]]:
    cur.execute(
        """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY tablename, indexname
        """
    )
    out: dict[str, list[dict[str, Any]]] = {}
    for row in cur.fetchall():
        out.setdefault(row["tablename"], []).append(
            {
                "name": row["indexname"],
                "unique": row["indexdef"].startswith("CREATE UNIQUE INDEX"),
                "definition": row["indexdef"],
            }
        )
    return out


def run_check(cur, label: str, query: str) -> dict[str, Any]:
    try:
        cur.execute(query)
        count = int(cur.fetchone()["n"])
        return {"label": label, "orphans": count, "ok": count == 0}
    except Exception as exc:  # noqa: BLE001 - dashboard should surface checks instead of failing.
        return {"label": label, "orphans": None, "ok": False, "error": str(exc)}


def health_checks(cur) -> list[dict[str, Any]]:
    return [
        run_check(
            cur,
            "api_key -> api_user",
            """
            SELECT COUNT(*) AS n
            FROM api_key k
            WHERE k.user_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM api_user u WHERE u.id = k.user_id)
            """,
        ),
        run_check(
            cur,
            "keyword_snapshot -> tk_hot_keyword",
            """
            SELECT COUNT(*) AS n
            FROM keyword_snapshot s
            WHERE s.keyword_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM tk_hot_keyword k WHERE k.id = s.keyword_id)
            """,
        ),
        run_check(
            cur,
            "outreach -> creator",
            """
            SELECT COUNT(*) AS n
            FROM outreach o
            WHERE o.creator_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM creator c WHERE c.id = o.creator_id)
            """,
        ),
        run_check(
            cur,
            "creator_tags -> creators",
            """
            SELECT COUNT(*) AS n
            FROM creator_tags t
            WHERE t.creator_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM creators c WHERE c.id = t.creator_id)
            """,
        ),
        run_check(
            cur,
            "creator_recommendations -> creators",
            """
            SELECT COUNT(*) AS n
            FROM creator_recommendations r
            WHERE r.creator_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM creators c WHERE c.id = r.creator_id)
            """,
        ),
        run_check(
            cur,
            "outreach_emails -> tk_creators",
            """
            SELECT COUNT(*) AS n
            FROM outreach_emails e
            WHERE e.creator_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM tk_creators c WHERE c.id::text = e.creator_id)
            """,
        ),
    ]


@app.get("/", response_class=HTMLResponse)
def dashboard(lang: str = Query(default="zh", pattern="^(zh|en)$")) -> HTMLResponse:
    return HTMLResponse(render_business_dashboard(lang))


@app.get("/zh", response_class=HTMLResponse)
def dashboard_zh() -> HTMLResponse:
    return HTMLResponse(render_business_dashboard("zh"))


@app.get("/en", response_class=HTMLResponse)
def dashboard_en() -> HTMLResponse:
    return HTMLResponse(render_business_dashboard("en"))


@app.get("/tech/zh", response_class=HTMLResponse)
def technical_dashboard_zh() -> HTMLResponse:
    return HTMLResponse(render_dashboard("zh"))


@app.get("/tech/en", response_class=HTMLResponse)
def technical_dashboard_en() -> HTMLResponse:
    return HTMLResponse(render_dashboard("en"))


@app.get("/schema-map")
def schema_map() -> FileResponse:
    if not SCHEMA_MAP.exists():
        raise HTTPException(404, "db_visualization.html not found")
    return FileResponse(SCHEMA_MAP)


@app.get("/api/summary")
def api_summary() -> dict[str, Any]:
    with connect() as con, con.cursor() as cur:
        tables = fetch_table_inventory(cur)
        total_rows = sum(t["rows"] for t in tables)
        group_rows: dict[str, int] = {}
        group_tables: dict[str, int] = {}
        for item in tables:
            group_rows[item["group"]] = group_rows.get(item["group"], 0) + item["rows"]
            group_tables[item["group"]] = group_tables.get(item["group"], 0) + 1

        key_counts = {}
        for table in [
            "product",
            "product_image",
            "creator",
            "tk_creators",
            "creators",
            "outreach",
            "creator_tags",
            "creator_recommendations",
            "raw_observations",
            "tk_hot_keyword",
            "keyword_snapshot",
        ]:
            key_counts[table] = exact_count(cur, table)

        category_products = fetch_rows(
            cur,
            """
            SELECT c.code, c.name_zh, COUNT(p.id)::int AS products
            FROM category c
            LEFT JOIN product p ON p.category_id = c.id
            GROUP BY c.id, c.code, c.name_zh, c.sort_order
            ORDER BY c.sort_order, c.code
            """,
        )
        lead_fit = fetch_rows(
            cur,
            """
            SELECT COALESCE(fit_level, 'unknown') AS label, COUNT(*)::int AS value
            FROM tk_creators
            GROUP BY 1
            ORDER BY value DESC, label
            """,
        )
        lead_email = fetch_rows(
            cur,
            """
            SELECT CASE WHEN has_email = 1 THEN 'has_email' ELSE 'missing_email' END AS label,
                   COUNT(*)::int AS value
            FROM tk_creators
            GROUP BY 1
            ORDER BY label
            """,
        )
        top_tables = sorted(tables, key=lambda x: x["rows"], reverse=True)[:12]
        checks = health_checks(cur)

    return {
        "database": "x9db",
        "tables": len(tables),
        "rows": total_rows,
        "columns": sum(t["columns"] for t in tables),
        "indexes": sum(t["indexes"] for t in tables),
        "key_counts": key_counts,
        "top_tables": top_tables,
        "group_rows": [
            {
                "group": key,
                "label": GROUPS[key]["label"],
                "color": GROUPS[key]["color"],
                "rows": rows,
                "tables": group_tables[key],
            }
            for key, rows in sorted(group_rows.items(), key=lambda kv: kv[1], reverse=True)
        ],
        "category_products": category_products,
        "lead_fit": lead_fit,
        "lead_email": lead_email,
        "checks": checks,
    }


@app.get("/api/business-summary")
def api_business_summary() -> dict[str, Any]:
    with connect() as con, con.cursor() as cur:
        product = fetch_one(
            cur,
            """
            SELECT COUNT(*)::int AS total,
                   COUNT(*) FILTER (WHERE COALESCE(is_main_push, 0) = 1)::int AS main_push,
                   COUNT(*) FILTER (WHERE COALESCE(status, 'active') = 'active')::int AS active
            FROM product
            """,
        )
        assets = fetch_one(
            cur,
            """
            SELECT COUNT(*)::int AS product_images
            FROM product_image
            """,
        )
        leads = fetch_one(
            cur,
            """
            SELECT COUNT(*)::int AS total,
                   COUNT(*) FILTER (WHERE has_email = 1)::int AS with_email,
                   COUNT(*) FILTER (WHERE has_email <> 1 OR has_email IS NULL)::int AS missing_email,
                   COUNT(*) FILTER (WHERE fit_level IN ('A', 'B'))::int AS fit_ab,
                   COUNT(*) FILTER (WHERE review_required = 1)::int AS review_required
            FROM tk_creators
            """,
        )
        outreach = fetch_one(
            cur,
            """
            SELECT COUNT(*)::int AS total,
                   COUNT(*) FILTER (WHERE video_url IS NOT NULL AND trim(video_url) <> '')::int AS video_links,
                   COUNT(*) FILTER (WHERE ad_auth_code IS NOT NULL AND trim(ad_auth_code) <> '')::int AS auth_codes
            FROM outreach
            """,
        )
        keywords = fetch_one(
            cur,
            """
            SELECT COUNT(*)::int AS total,
                   COUNT(*) FILTER (WHERE category_hint IS NULL OR category_hint = 'unknown')::int AS unknown
            FROM tk_hot_keyword
            """,
        )
        unique_creators = fetch_one(
            cur,
            """
            WITH
            c AS (SELECT DISTINCT lower(trim(platform)) p, {norm} h FROM creator),
            tk AS (SELECT DISTINCT lower(trim(platform)) p, {norm} h FROM tk_creators),
            x AS (SELECT DISTINCT lower(trim(platform)) p, {norm} h FROM creators),
            keys AS (SELECT p,h FROM c UNION SELECT p,h FROM tk UNION SELECT p,h FROM x)
            SELECT COUNT(*)::int AS total
            FROM keys
            """.format(norm=NORMALIZED_HANDLE_SQL),
        )
        unassigned = fetch_one(
            cur,
            """
            SELECT COUNT(*)::int AS total
            FROM creator
            WHERE owner_bd IS NULL OR trim(owner_bd) = ''
            """,
        )
        product_categories = fetch_rows(
            cur,
            """
            SELECT c.code AS key,
                   COALESCE(c.name_zh, c.name_en, c.code) AS label,
                   COUNT(p.id)::int AS value
            FROM category c
            LEFT JOIN product p ON p.category_id = c.id
            GROUP BY c.id, c.code, c.name_zh, c.name_en, c.sort_order
            ORDER BY c.sort_order, c.code
            """,
        )
        lead_fit = fetch_rows(
            cur,
            """
            SELECT COALESCE(fit_level, 'unknown') AS label, COUNT(*)::int AS value
            FROM tk_creators
            GROUP BY 1
            ORDER BY value DESC, label
            """,
        )
        outreach_status = fetch_rows(
            cur,
            """
            SELECT COALESCE(status, 'unknown') AS label, COUNT(*)::int AS value
            FROM outreach
            GROUP BY 1
            ORDER BY value DESC, label
            """,
        )
        creator_status = fetch_rows(
            cur,
            """
            SELECT COALESCE(current_status, 'unknown') AS label, COUNT(*)::int AS value
            FROM creator
            GROUP BY 1
            ORDER BY value DESC, label
            """,
        )
        keyword_category = fetch_rows(
            cur,
            """
            SELECT COALESCE(category_hint, 'unknown') AS label, COUNT(*)::int AS value
            FROM tk_hot_keyword
            GROUP BY 1
            ORDER BY value DESC, label
            """,
        )
        owner_bd = fetch_rows(
            cur,
            """
            SELECT COALESCE(NULLIF(trim(owner_bd), ''), 'unassigned') AS label,
                   COUNT(*)::int AS value
            FROM creator
            GROUP BY 1
            ORDER BY value DESC, label
            LIMIT 8
            """,
        )
        top_leads = fetch_rows(
            cur,
            """
            SELECT handle,
                   display_name,
                   email,
                   fit_level,
                   recommendation_score,
                   primary_product_category,
                   outreach_priority
            FROM tk_creators
            ORDER BY recommendation_score DESC NULLS LAST, priority_score DESC NULLS LAST, id ASC
            LIMIT 10
            """,
        )

    email_rate = round((leads["with_email"] or 0) * 100 / max(leads["total"] or 0, 1), 1)
    return {
        "headline": {
            "products": product["total"],
            "main_push": product["main_push"],
            "product_images": assets["product_images"],
            "leads": leads["total"],
            "lead_email_rate": email_rate,
            "outreach": outreach["total"],
            "keywords": keywords["total"],
            "unique_creators": unique_creators["total"],
        },
        "actions": {
            "missing_email": leads["missing_email"],
            "review_required": leads["review_required"],
            "unassigned": unassigned["total"],
            "unknown_keywords": keywords["unknown"],
            "video_links": outreach["video_links"],
            "auth_codes": outreach["auth_codes"],
        },
        "charts": {
            "product_categories": product_categories,
            "lead_fit": lead_fit,
            "outreach_status": outreach_status,
            "creator_status": creator_status,
            "keyword_category": keyword_category,
            "owner_bd": owner_bd,
        },
        "top_leads": top_leads,
    }


@app.get("/api/tables")
def api_tables() -> list[dict[str, Any]]:
    with connect() as con, con.cursor() as cur:
        return fetch_table_inventory(cur)


@app.get("/api/table/{name}")
def api_table(name: str, limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    table = safe_ident(name)
    with connect() as con, con.cursor() as cur:
        names = table_names(cur)
        if table not in names:
            raise HTTPException(404, f"unknown table: {table}")
        columns = fetch_columns(cur).get(table, [])
        indexes = fetch_indexes(cur).get(table, [])
        cur.execute(sql.SQL("SELECT * FROM {} LIMIT %s").format(sql.Identifier(table)), (limit,))
        rows = cur.fetchall()
        return {
            "name": table,
            "group": group_for_table(table),
            "rows_total": exact_count(cur, table),
            "columns": columns,
            "indexes": indexes,
            "sample": rows,
        }


@app.get("/api/creator-merge")
def api_creator_merge() -> dict[str, Any]:
    with connect() as con, con.cursor() as cur:
        raw_overlap = fetch_one(
            cur,
            """
            WITH
            c AS (SELECT id::text creator_id, lower(trim(platform)) p, lower(trim(regexp_replace(handle,'^@','','g'))) h FROM creator),
            tk AS (SELECT id::text tk_id, lower(trim(platform)) p, lower(trim(regexp_replace(handle,'^@','','g'))) h FROM tk_creators),
            x AS (SELECT id::text x9_id, lower(trim(platform)) p, lower(trim(regexp_replace(handle,'^@','','g'))) h FROM creators),
            keys AS (SELECT p,h FROM c UNION SELECT p,h FROM tk UNION SELECT p,h FROM x)
            SELECT
              COUNT(*)::int total_union,
              COUNT(*) FILTER (WHERE c.creator_id IS NOT NULL)::int in_creator,
              COUNT(*) FILTER (WHERE tk.tk_id IS NOT NULL)::int in_tk,
              COUNT(*) FILTER (WHERE x.x9_id IS NOT NULL)::int in_x9,
              COUNT(*) FILTER (WHERE c.creator_id IS NOT NULL AND tk.tk_id IS NOT NULL AND x.x9_id IS NOT NULL)::int in_all_three,
              COUNT(*) FILTER (WHERE c.creator_id IS NOT NULL AND tk.tk_id IS NULL AND x.x9_id IS NULL)::int creator_only,
              COUNT(*) FILTER (WHERE c.creator_id IS NULL AND tk.tk_id IS NOT NULL AND x.x9_id IS NOT NULL)::int tk_x9_only
            FROM keys k
            LEFT JOIN c USING(p,h)
            LEFT JOIN tk USING(p,h)
            LEFT JOIN x USING(p,h)
            """,
        )
        heuristic_overlap = fetch_one(
            cur,
            """
            WITH
            c AS (
              SELECT DISTINCT lower(trim(platform)) p, {norm} h
              FROM creator
            ),
            tk AS (
              SELECT DISTINCT lower(trim(platform)) p, {norm} h
              FROM tk_creators
            ),
            x AS (
              SELECT DISTINCT lower(trim(platform)) p, {norm} h
              FROM creators
            ),
            keys AS (SELECT p,h FROM c UNION SELECT p,h FROM tk UNION SELECT p,h FROM x)
            SELECT
              COUNT(*)::int total_distinct_entities,
              COUNT(*) FILTER (WHERE EXISTS(SELECT 1 FROM c WHERE c.p=keys.p AND c.h=keys.h))::int in_creator,
              COUNT(*) FILTER (WHERE EXISTS(SELECT 1 FROM tk WHERE tk.p=keys.p AND tk.h=keys.h))::int in_tk,
              COUNT(*) FILTER (WHERE EXISTS(SELECT 1 FROM x WHERE x.p=keys.p AND x.h=keys.h))::int in_x9,
              COUNT(*) FILTER (
                WHERE EXISTS(SELECT 1 FROM c WHERE c.p=keys.p AND c.h=keys.h)
                  AND EXISTS(SELECT 1 FROM tk WHERE tk.p=keys.p AND tk.h=keys.h)
                  AND EXISTS(SELECT 1 FROM x WHERE x.p=keys.p AND x.h=keys.h)
              )::int in_all_three
            FROM keys
            """.format(norm=NORMALIZED_HANDLE_SQL),
        )
        duplicates = {}
        for table in ["creator", "tk_creators", "creators"]:
            duplicates[table] = fetch_rows(
                cur,
                sql.SQL(
                    """
                    SELECT {norm} AS canonical_handle,
                           COUNT(*)::int AS rows,
                           array_agg(id::text ORDER BY id::text) AS ids,
                           array_agg(handle ORDER BY id::text) AS handles,
                           array_agg(display_name ORDER BY id::text) AS display_names
                    FROM {}
                    GROUP BY 1
                    HAVING COUNT(*) > 1
                    ORDER BY rows DESC, canonical_handle
                    LIMIT 20
                    """
                ).format(sql.Identifier(table), norm=sql.SQL(NORMALIZED_HANDLE_SQL)),
            )
    return {
        "raw_overlap": raw_overlap,
        "heuristic_overlap": heuristic_overlap,
        "duplicate_groups": duplicates,
    }


@app.get("/api/keyword-trend")
def api_keyword_trend() -> dict[str, Any]:
    with connect() as con, con.cursor() as cur:
        rows = fetch_rows(
            cur,
            """
            SELECT k.keyword,
                   s.captured_at::text AS captured_at,
                   s.search_volume,
                   s.growth_rate,
                   s.rank_position
            FROM keyword_snapshot s
            JOIN tk_hot_keyword k ON k.id = s.keyword_id
            ORDER BY k.keyword, s.captured_at
            LIMIT 500
            """,
        )
    return {"items": rows}


def fetch_rows(cur, query: Any, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(query, params)
    return list(cur.fetchall())


def fetch_one(cur, query: Any, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    cur.execute(query, params)
    return dict(cur.fetchone() or {})


def render_dashboard(lang: str) -> str:
    text = I18N.get(lang, I18N["zh"])
    return (
        DASHBOARD_HTML
        .replace("__LANG_ATTR__", text["lang_attr"])
        .replace("__PAGE_TITLE__", text["page_title"])
        .replace("__SUBTITLE__", text["subtitle"])
        .replace("__SCHEMA_MAP__", text["schema_map"])
        .replace("__REFRESH__", text["refresh"])
        .replace("__SEARCH_PLACEHOLDER__", text["search_placeholder"])
        .replace("__LOADING_TABLES__", text["loading_tables"])
        .replace("__HEALTH_CHECKS__", text["health_checks"])
        .replace("__DATA_STATISTICS__", text["data_statistics"])
        .replace("__ROWS_BY_DOMAIN__", text["rows_by_domain"])
        .replace("__LARGEST_TABLES__", text["largest_tables"])
        .replace("__PRODUCTS_BY_CATEGORY__", text["products_by_category"])
        .replace("__LEAD_FIT_LEVEL__", text["lead_fit_level"])
        .replace("__LEAD_EMAIL_COVERAGE__", text["lead_email_coverage"])
        .replace("__CREATOR_MERGE_PREVIEW__", text["creator_merge_preview"])
        .replace("__SELECT_TABLE__", text["select_table"])
        .replace("__TEXT_JSON__", json.dumps(text, ensure_ascii=False))
    )


def render_business_dashboard(lang: str) -> str:
    text = BUSINESS_I18N.get(lang, BUSINESS_I18N["zh"])
    return (
        BUSINESS_DASHBOARD_HTML
        .replace("__LANG_ATTR__", text["lang_attr"])
        .replace("__PAGE_TITLE__", text["page_title"])
        .replace("__SUBTITLE__", text["subtitle"])
        .replace("__TEXT_JSON__", json.dumps(text, ensure_ascii=False))
    )


BUSINESS_DASHBOARD_HTML = r"""
<!doctype html>
<html lang="__LANG_ATTR__">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__PAGE_TITLE__</title>
  <style>
    :root{--bg:#f6f7f9;--panel:#fff;--line:#d9dee7;--text:#17202a;--muted:#667085;--blue:#2f6ea6;--green:#287c73;--orange:#b15f4a;--gold:#9a7a2f;--red:#b42318;--shadow:0 8px 24px rgba(20,31,49,.08)}
    *{box-sizing:border-box}
    body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;letter-spacing:0}
    button,a{font:inherit}
    header{display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:18px 22px;background:#fff;border-bottom:1px solid var(--line)}
    h1{margin:0 0 4px;font-size:22px;line-height:1.2}
    .sub{color:var(--muted);font-size:13px}
    .actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
    .btn{height:34px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--text);padding:0 11px;display:inline-flex;align-items:center;text-decoration:none;cursor:pointer}
    .btn.primary{background:var(--blue);border-color:var(--blue);color:#fff}
    main{padding:14px;display:grid;gap:14px}
    .cards{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:12px}
    .card,.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;box-shadow:var(--shadow)}
    .card{padding:14px;min-height:92px}
    .card b{display:block;font-size:28px;line-height:1.1;font-variant-numeric:tabular-nums}
    .card span{display:block;color:var(--muted);font-size:12px;margin-top:8px}
    .grid{display:grid;grid-template-columns:1.2fr .8fr;gap:14px}
    .panel{overflow:hidden}
    .panel h2{margin:0;padding:13px 14px;border-bottom:1px solid var(--line);font-size:16px}
    .panel-body{padding:14px}
    .charts{display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:14px}
    .chart{border:1px solid var(--line);border-radius:8px;background:#fafbfc;padding:12px;min-height:230px}
    .chart h3{margin:0 0 10px;font-size:14px}
    .bars{display:grid;gap:9px}
    .bar{display:grid;grid-template-columns:minmax(92px,150px) 1fr auto;gap:9px;align-items:center}
    .bar-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .track{height:13px;background:#e9eef4;border-radius:999px;overflow:hidden}
    .fill{height:100%;border-radius:999px;background:var(--blue)}
    .value{font-variant-numeric:tabular-nums;color:var(--muted)}
    .attention{display:grid;gap:9px}
    .attention-row{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;border:1px solid var(--line);border-radius:8px;background:#fafbfc;padding:11px}
    .attention-row b{font-size:20px;font-variant-numeric:tabular-nums}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th,td{padding:9px 10px;border-bottom:1px solid #edf0f4;text-align:left;white-space:nowrap;max-width:220px;overflow:hidden;text-overflow:ellipsis}
    th{background:#f1f4f7;color:#344054;font-weight:700}
    .pill{display:inline-flex;align-items:center;border-radius:999px;border:1px solid var(--line);padding:2px 8px;background:#f8fafc;font-size:12px}
    .muted{color:var(--muted)}
    .loading{padding:20px;color:var(--muted)}
    @media(max-width:1120px){.cards{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}.charts{grid-template-columns:1fr}}
    @media(max-width:720px){header{grid-template-columns:1fr}.actions{justify-content:flex-start}.cards{grid-template-columns:1fr}main{padding:10px}.bar{grid-template-columns:1fr}.value{justify-self:end}th,td{max-width:140px}}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>__PAGE_TITLE__</h1>
      <div class="sub">__SUBTITLE__</div>
    </div>
    <div class="actions">
      <a class="btn" id="langLink"></a>
      <a class="btn" href="/tech/zh" target="_blank" id="techLink"></a>
      <a class="btn" href="/schema-map" target="_blank" id="schemaLink"></a>
      <button class="btn primary" onclick="loadBusiness()" id="refreshBtn"></button>
    </div>
  </header>
  <main>
    <section class="cards" id="cards"><div class="loading">__SUBTITLE__</div></section>
    <section class="grid">
      <div class="panel">
        <h2 id="portfolioTitle"></h2>
        <div class="panel-body charts">
          <div class="chart"><h3 id="catTitle"></h3><div class="bars" id="productCategories"></div></div>
          <div class="chart"><h3 id="fitTitle"></h3><div class="bars" id="leadFit"></div></div>
          <div class="chart"><h3 id="outreachTitle"></h3><div class="bars" id="outreachStatus"></div></div>
          <div class="chart"><h3 id="keywordTitle"></h3><div class="bars" id="keywordCategory"></div></div>
          <div class="chart"><h3 id="creatorTitle"></h3><div class="bars" id="creatorStatus"></div></div>
          <div class="chart"><h3 id="ownerTitle"></h3><div class="bars" id="ownerBd"></div></div>
        </div>
      </div>
      <div class="panel">
        <h2 id="actionsTitle"></h2>
        <div class="panel-body attention" id="attention"></div>
      </div>
    </section>
    <section class="panel">
      <h2 id="topLeadsTitle"></h2>
      <div class="panel-body" style="overflow:auto">
        <table>
          <thead><tr id="leadHead"></tr></thead>
          <tbody id="leadRows"></tbody>
        </table>
      </div>
    </section>
  </main>
<script>
const TEXT=__TEXT_JSON__;
const fmt=new Intl.NumberFormat('en-US');
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statusLabel=v=>String(v??'unknown').replaceAll('_',' ');
function setLabels(){
  document.getElementById('langLink').textContent=TEXT.language_link;
  document.getElementById('langLink').href=TEXT.language_href;
  document.getElementById('techLink').textContent=TEXT.tech;
  document.getElementById('schemaLink').textContent=TEXT.schema;
  document.getElementById('refreshBtn').textContent=TEXT.refresh;
  document.getElementById('portfolioTitle').textContent=TEXT.sections.overview;
  document.getElementById('catTitle').textContent=TEXT.charts.product_categories;
  document.getElementById('fitTitle').textContent=TEXT.charts.lead_fit;
  document.getElementById('outreachTitle').textContent=TEXT.charts.outreach_status;
  document.getElementById('keywordTitle').textContent=TEXT.charts.keyword_category;
  document.getElementById('creatorTitle').textContent=TEXT.charts.creator_status;
  document.getElementById('ownerTitle').textContent=TEXT.charts.owner_bd;
  document.getElementById('actionsTitle').textContent=TEXT.sections.actions;
  document.getElementById('topLeadsTitle').textContent=TEXT.sections.top_leads;
  const c=TEXT.lead_cols;
  document.getElementById('leadHead').innerHTML=[c.handle,c.email,c.fit,c.score,c.category,c.priority].map(x=>`<th>${x}</th>`).join('');
}
async function loadBusiness(){
  document.getElementById('cards').innerHTML=`<div class="loading">${TEXT.loading}</div>`;
  const r=await fetch('/api/business-summary');
  if(!r.ok) throw new Error(await r.text());
  render(await r.json());
}
function render(data){
  const h=data.headline;
  const cards=[
    [TEXT.cards.products,h.products],
    [TEXT.cards.main_push,h.main_push],
    [TEXT.cards.images,h.product_images],
    [TEXT.cards.leads,h.leads],
    [TEXT.cards.email_rate,h.lead_email_rate+'%'],
    [TEXT.cards.outreach,h.outreach],
    [TEXT.cards.keywords,h.keywords],
    [TEXT.cards.unique_creators,h.unique_creators],
  ];
  document.getElementById('cards').innerHTML=cards.map(([label,val])=>`<div class="card"><b>${val}</b><span>${label}</span></div>`).join('');
  bars('productCategories',data.charts.product_categories,'label','value','#287c73');
  bars('leadFit',data.charts.lead_fit,'label','value','#2f6ea6');
  bars('outreachStatus',data.charts.outreach_status,'label','value','#b15f4a');
  bars('keywordCategory',data.charts.keyword_category,'label','value','#9a7a2f');
  bars('creatorStatus',data.charts.creator_status,'label','value','#7c5f9b');
  bars('ownerBd',data.charts.owner_bd,'label','value','#596f3a');
  const a=data.actions;
  const attention=[
    [TEXT.actions.missing_email,a.missing_email],
    [TEXT.actions.review_required,a.review_required],
    [TEXT.actions.unassigned,a.unassigned],
    [TEXT.actions.unknown_keywords,a.unknown_keywords],
    [TEXT.actions.video_links,a.video_links],
    [TEXT.actions.auth_codes,a.auth_codes],
  ];
  document.getElementById('attention').innerHTML=attention.map(([label,val])=>`<div class="attention-row"><span>${label}</span><b>${fmt.format(val)}</b></div>`).join('');
  document.getElementById('leadRows').innerHTML=(data.top_leads.length?data.top_leads:[]).map(x=>`<tr><td title="${esc(x.display_name||x.handle)}">${esc(x.handle||x.display_name)}</td><td>${x.email?'<span class="pill">'+TEXT.yes+'</span>':'<span class="muted">'+TEXT.no+'</span>'}</td><td>${esc(x.fit_level||'')}</td><td>${fmt.format(x.recommendation_score||0)}</td><td>${esc(statusLabel(x.primary_product_category))}</td><td>${esc(x.outreach_priority||'')}</td></tr>`).join('') || `<tr><td colspan="6" class="muted">${TEXT.empty}</td></tr>`;
}
function bars(id,rows,labelKey,valueKey,color){
  const max=Math.max(1,...rows.map(r=>Number(r[valueKey]||0)));
  document.getElementById(id).innerHTML=rows.map(r=>{
    const val=Number(r[valueKey]||0), pct=Math.max(3,val/max*100);
    return `<div class="bar"><div class="bar-label" title="${esc(r[labelKey])}">${esc(statusLabel(r[labelKey]))}</div><div class="track"><div class="fill" style="width:${pct}%;background:${color}"></div></div><div class="value">${fmt.format(val)}</div></div>`;
  }).join('');
}
setLabels();
loadBusiness().catch(e=>{document.body.innerHTML=`<pre style="padding:20px;color:#b42318">${esc(e.stack||e)}</pre>`});
</script>
</body>
</html>
"""


DASHBOARD_HTML = r"""
<!doctype html>
<html lang="__LANG_ATTR__">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__PAGE_TITLE__</title>
  <style>
    :root {
      --bg:#f6f7f9; --panel:#fff; --line:#d8dee8; --text:#17202a; --muted:#667085;
      --blue:#2f6ea6; --green:#287c73; --orange:#b15f4a; --purple:#7c5f9b;
      --yellow:#9a7a2f; --red:#b42318; --ok:#1d7a54; --shadow:0 8px 24px rgba(20,31,49,.08);
    }
    *{box-sizing:border-box}
    body{margin:0;background:var(--bg);color:var(--text);font:13px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;letter-spacing:0}
    button,input,select{font:inherit}
    .app{min-height:100vh;display:grid;grid-template-rows:auto 1fr}
    header{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;padding:14px 18px;background:#fff;border-bottom:1px solid var(--line)}
    h1{font-size:18px;margin:0 0 2px;font-weight:760}
    .sub{color:var(--muted);font-size:12px}
    .head-actions{display:flex;gap:8px;align-items:center}
    .btn{height:34px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--text);padding:0 10px;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center}
    .btn.primary{background:var(--blue);border-color:var(--blue);color:#fff}
    main{display:grid;grid-template-columns:310px minmax(460px,1fr) 390px;gap:12px;padding:12px;min-height:0}
    .panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;box-shadow:var(--shadow);min-height:0;overflow:hidden}
    .stats{display:grid;grid-template-columns:repeat(5,minmax(100px,1fr));gap:10px;padding:12px}
    .stat{border:1px solid var(--line);border-radius:8px;background:#f8fafc;padding:10px;min-height:66px}
    .stat b{display:block;font-size:22px;line-height:1.1;font-variant-numeric:tabular-nums}
    .stat span{display:block;margin-top:6px;color:var(--muted);font-size:11px}
    .toolbar{display:grid;grid-template-columns:1fr auto;gap:8px;padding:10px;border-bottom:1px solid var(--line)}
    input,select{width:100%;min-height:34px;border:1px solid var(--line);border-radius:6px;padding:6px 8px;background:#fff;color:var(--text)}
    .table-list{height:calc(100vh - 151px);overflow:auto}
    .table-row{width:100%;border:0;border-bottom:1px solid #edf0f4;background:#fff;display:grid;grid-template-columns:12px 1fr auto;gap:8px;align-items:center;min-height:48px;padding:9px 10px;text-align:left;cursor:pointer}
    .table-row:hover,.table-row.active{background:#eef5fb}
    .dot{width:10px;height:10px;border-radius:50%;display:inline-block}
    .name{font-weight:700;overflow-wrap:anywhere}
    .meta{font-size:11px;color:var(--muted);margin-top:2px}
    .count{font-variant-numeric:tabular-nums;color:var(--muted)}
    .content{height:calc(100vh - 88px);overflow:auto}
    .section{padding:12px;border-bottom:1px solid var(--line)}
    .section h2{margin:0 0 10px;font-size:14px}
    .charts{display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:12px}
    .chart{border:1px solid var(--line);border-radius:8px;background:#fff;min-height:230px;padding:12px}
    .chart h3{margin:0 0 10px;font-size:13px}
    .bars{display:grid;gap:8px}
    .bar{display:grid;grid-template-columns:minmax(86px,140px) 1fr auto;gap:8px;align-items:center}
    .bar-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .bar-track{height:12px;background:#edf1f5;border-radius:999px;overflow:hidden}
    .bar-fill{height:100%;border-radius:999px;background:var(--blue)}
    .bar-value{font-variant-numeric:tabular-nums;color:var(--muted)}
    .checks{display:grid;grid-template-columns:repeat(3,minmax(160px,1fr));gap:8px}
    .check{border:1px solid var(--line);border-radius:8px;padding:9px;background:#f8fafc}
    .check b{display:block;margin-bottom:3px}
    .ok{color:var(--ok)}.bad{color:var(--red)}
    .detail{height:calc(100vh - 88px);overflow:auto}
    .detail-head{padding:14px;border-bottom:1px solid var(--line)}
    .detail-title{font-size:16px;font-weight:760;display:flex;justify-content:space-between;gap:8px}
    .pills{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
    .pill{border:1px solid var(--line);border-radius:999px;padding:3px 8px;background:#f1f4f7;color:var(--muted);font-size:11px}
    .cols{display:grid;gap:6px}
    .col{display:grid;grid-template-columns:minmax(90px,1fr) minmax(72px,auto) auto;gap:8px;align-items:center;border:1px solid #edf0f4;border-radius:6px;background:#fafbfc;padding:7px 8px}
    .col b{overflow-wrap:anywhere}.type{color:var(--muted);font-size:11px;overflow-wrap:anywhere}
    .key{font-size:10px;border-radius:5px;background:#6b7280;color:#fff;padding:2px 5px}.key.pk{background:var(--purple)}
    .sample{overflow:auto;max-height:360px;border:1px solid var(--line);border-radius:8px}
    table{border-collapse:collapse;width:100%;font-size:12px}
    th,td{border-bottom:1px solid #edf0f4;padding:7px 8px;text-align:left;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    th{background:#f1f4f7;position:sticky;top:0;z-index:1}
    .merge-grid{display:grid;grid-template-columns:repeat(2,minmax(240px,1fr));gap:12px}
    .mini{border:1px solid var(--line);border-radius:8px;background:#f8fafc;padding:10px}
    .mini h3{margin:0 0 8px;font-size:13px}
    .loading{padding:16px;color:var(--muted)}
    @media(max-width:1180px){main{grid-template-columns:280px 1fr}.detail{display:none}.charts{grid-template-columns:1fr}.checks{grid-template-columns:1fr 1fr}}
    @media(max-width:760px){header{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}main{grid-template-columns:1fr}.table-list,.content,.detail{height:auto;max-height:none}.checks{grid-template-columns:1fr}}
  </style>
</head>
<body>
<div class="app">
  <header>
    <div>
      <h1>__PAGE_TITLE__</h1>
      <div class="sub">__SUBTITLE__</div>
    </div>
    <div class="head-actions">
      <a class="btn" href="/zh">中文</a>
      <a class="btn" href="/en">English</a>
      <a class="btn" href="/schema-map" target="_blank">__SCHEMA_MAP__</a>
      <button class="btn primary" onclick="refreshAll()">__REFRESH__</button>
    </div>
  </header>
  <main>
    <aside class="panel">
      <div class="toolbar">
        <input id="search" placeholder="__SEARCH_PLACEHOLDER__">
        <select id="group"></select>
      </div>
      <div id="tableList" class="table-list loading">__LOADING_TABLES__</div>
    </aside>
    <section class="panel content">
      <div class="stats" id="stats"></div>
      <div class="section">
        <h2>__HEALTH_CHECKS__</h2>
        <div class="checks" id="checks"></div>
      </div>
      <div class="section">
        <h2>__DATA_STATISTICS__</h2>
        <div class="charts">
          <div class="chart"><h3>__ROWS_BY_DOMAIN__</h3><div class="bars" id="groupRows"></div></div>
          <div class="chart"><h3>__LARGEST_TABLES__</h3><div class="bars" id="topTables"></div></div>
          <div class="chart"><h3>__PRODUCTS_BY_CATEGORY__</h3><div class="bars" id="categoryProducts"></div></div>
          <div class="chart"><h3>__LEAD_FIT_LEVEL__</h3><div class="bars" id="leadFit"></div></div>
          <div class="chart"><h3>__LEAD_EMAIL_COVERAGE__</h3><div class="bars" id="leadEmail"></div></div>
          <div class="chart"><h3>__CREATOR_MERGE_PREVIEW__</h3><div id="mergePreview" class="merge-grid"></div></div>
        </div>
      </div>
    </section>
    <aside class="panel detail" id="detail"><div class="loading">__SELECT_TABLE__</div></aside>
  </main>
</div>
<script>
const TEXT=__TEXT_JSON__;
const state={tables:[],summary:null,merge:null,selected:null,search:'',group:'all'};
const fmt=new Intl.NumberFormat('en-US');
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sizeFmt=bytes=>{if(bytes<1024)return bytes+' B';const u=['KB','MB','GB'];let n=bytes/1024,i=0;while(n>=1024&&i<u.length-1){n/=1024;i++}return (n>=100?n.toFixed(0):n.toFixed(1))+' '+u[i]};
const groupLabel=t=>TEXT.groups?.[t.group]||t.group_label;
async function j(url){const r=await fetch(url);if(!r.ok)throw new Error(await r.text());return r.json()}
async function refreshAll(){
  document.getElementById('stats').innerHTML=`<div class="loading">${TEXT.loading}</div>`;
  const [summary,tables,merge]=await Promise.all([j('/api/summary'),j('/api/tables'),j('/api/creator-merge')]);
  state.summary=summary;state.tables=tables;state.merge=merge;state.selected=state.selected||tables[0]?.name;
  renderGroups();renderStats();renderChecks();renderCharts();renderTables();renderDetail(state.selected);
}
function renderGroups(){
  const seen=[...new Set(state.tables.map(t=>t.group))].sort();
  const labels=Object.fromEntries(state.tables.map(t=>[t.group,groupLabel(t)]));
  document.getElementById('group').innerHTML=`<option value="all">${TEXT.all_groups}</option>`+seen.map(g=>`<option value="${g}">${esc(labels[g]||g)}</option>`).join('');
}
function renderStats(){
  const s=state.summary;
  const cards=[[TEXT.stats.tables,s.tables],[TEXT.stats.rows,fmt.format(s.rows)],[TEXT.stats.columns,s.columns],[TEXT.stats.indexes,s.indexes],[TEXT.stats.checks_ok,s.checks.filter(c=>c.ok).length+'/'+s.checks.length]];
  document.getElementById('stats').innerHTML=cards.map(([k,v])=>`<div class="stat"><b>${v}</b><span>${k}</span></div>`).join('');
}
function renderChecks(){
  document.getElementById('checks').innerHTML=state.summary.checks.map(c=>`<div class="check"><b class="${c.ok?'ok':'bad'}">${esc(c.label)}</b><span>${c.orphans==null?esc(c.error):fmt.format(c.orphans)+' '+TEXT.orphan_rows}</span></div>`).join('');
}
function bars(id,rows,labelKey,valueKey,colorKey){
  const max=Math.max(1,...rows.map(r=>Number(r[valueKey]||0)));
  document.getElementById(id).innerHTML=rows.map(r=>{
    const val=Number(r[valueKey]||0), pct=Math.max(2,val/max*100), color=r[colorKey]||'#2f6ea6';
    return `<div class="bar"><div class="bar-label" title="${esc(r[labelKey])}">${esc(r[labelKey])}</div><div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${color}"></div></div><div class="bar-value">${fmt.format(val)}</div></div>`;
  }).join('');
}
function renderCharts(){
  const s=state.summary;
  bars('groupRows',s.group_rows,'label','rows','color');
  bars('topTables',s.top_tables,'name','rows','color');
  bars('categoryProducts',s.category_products,'code','products');
  bars('leadFit',s.lead_fit,'label','value');
  bars('leadEmail',s.lead_email,'label','value');
  const raw=state.merge.raw_overlap, h=state.merge.heuristic_overlap;
  document.getElementById('mergePreview').innerHTML=[
    [TEXT.raw_handles,raw.total_union,raw.in_all_three,raw.creator_only,raw.tk_x9_only],
    [TEXT.normalized_entities,h.total_distinct_entities,h.in_all_three,'-','-']
  ].map(r=>`<div class="mini"><h3>${r[0]}</h3><div>${TEXT.total}: <b>${r[1]}</b></div><div>${TEXT.all_three}: <b>${r[2]}</b></div><div>${TEXT.creator_only}: <b>${r[3]}</b></div><div>${TEXT.tk_x9_only}: <b>${r[4]}</b></div></div>`).join('');
}
function tableMatches(t){
  if(state.group!=='all'&&t.group!==state.group)return false;
  if(!state.search)return true;
  return [t.name,groupLabel(t)].join(' ').toLowerCase().includes(state.search);
}
function renderTables(){
  const rows=state.tables.filter(tableMatches).sort((a,b)=>b.rows-a.rows||a.name.localeCompare(b.name));
  document.getElementById('tableList').innerHTML=rows.map(t=>`<button class="table-row ${state.selected===t.name?'active':''}" onclick="selectTable('${t.name}')"><span class="dot" style="background:${t.color}"></span><span><span class="name">${esc(t.name)}</span><span class="meta">${esc(groupLabel(t))} · ${t.columns} ${TEXT.cols_short} · ${t.indexes} ${TEXT.idx_short} · ${sizeFmt(t.size_bytes)}</span></span><span class="count">${fmt.format(t.rows)}</span></button>`).join('');
}
async function selectTable(name){state.selected=name;renderTables();await renderDetail(name)}
async function renderDetail(name){
  if(!name)return;
  const t=await j('/api/table/'+encodeURIComponent(name)+'?limit=40');
  const cols=t.columns.map(c=>`<div class="col"><b>${esc(c.name)}</b><span class="type">${esc(c.type)}</span><span class="key ${c.pk?'pk':''}">${c.pk?'PK':(c.nullable?'NULL':'REQ')}</span></div>`).join('');
  const sample=t.sample||[];
  const headers=sample[0]?Object.keys(sample[0]):[];
  const tableHtml=headers.length?`<div class="sample"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${sample.map(r=>`<tr>${headers.map(h=>`<td title="${esc(r[h])}">${esc(r[h])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:`<div class="meta">${TEXT.no_sample_rows}</div>`;
  document.getElementById('detail').innerHTML=`<div class="detail-head"><div class="detail-title"><span>${esc(t.name)}</span><span class="dot" style="background:${state.tables.find(x=>x.name===t.name)?.color||'#777'}"></span></div><div class="pills"><span class="pill">${fmt.format(t.rows_total)} ${TEXT.rows_word}</span><span class="pill">${t.columns.length} ${TEXT.columns_word}</span><span class="pill">${t.indexes.length} ${TEXT.indexes_word}</span></div></div><div class="section"><h2>${TEXT.columns_title}</h2><div class="cols">${cols}</div></div><div class="section"><h2>${TEXT.sample_rows}</h2>${tableHtml}</div>`;
}
document.getElementById('search').addEventListener('input',e=>{state.search=e.target.value.trim().toLowerCase();renderTables()});
document.getElementById('group').addEventListener('change',e=>{state.group=e.target.value;renderTables()});
refreshAll().catch(e=>{document.body.innerHTML='<pre style="padding:20px;color:#b42318">'+esc(e.stack||e)+'</pre>'});
</script>
</body>
</html>
"""
