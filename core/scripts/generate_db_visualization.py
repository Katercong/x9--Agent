from __future__ import annotations

import argparse
import html
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql


DEFAULT_PG_DSN = "postgresql://x9:x9_local_dev_2026@localhost:15432/x9db"
DEFAULT_OUTPUT = Path(r"F:\Database\exports\db_visualization.html")


GROUPS = {
    "metadata": {
        "label": "Metadata",
        "color": "#5b6b8c",
        "tables": {"_meta_query", "_meta_resource", "migration_manifest"},
    },
    "auth": {
        "label": "Auth",
        "color": "#7c5f9b",
        "tables": {"api_user", "api_key", "audit_log"},
    },
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
    "other": {
        "label": "Other",
        "color": "#6e737c",
        "tables": set(),
    },
}


RELATION_OVERRIDES = {
    ("api_key", "user_id"): "api_user",
    ("product", "category_id"): "category",
    ("product_image", "product_id"): "product",
    ("outreach", "creator_id"): "creator",
    ("outreach_sku", "outreach_id"): "outreach",
    ("outreach_sku", "product_id"): "product",
    ("creator_product", "creator_id"): "creator",
    ("creator_product", "product_id"): "product",
    ("creator_competitor_collab", "creator_id"): "creator",
    ("creator_competitor_collab", "competitor_brand_id"): "competitor_brand",
    ("keyword_snapshot", "keyword_id"): "tk_hot_keyword",
    ("creator_tags", "creator_id"): "creators",
    ("creator_recommendations", "creator_id"): "creators",
    ("review_tasks", "creator_id"): "creators",
    ("outreach_emails", "creator_id"): "tk_creators",
    ("outreach_emails", "template_id"): "outreach_templates",
    ("llm_feature", "provider_code"): "llm_provider",
}


def fetch_database_shape(dsn: str) -> dict[str, Any]:
    with psycopg.connect(dsn) as con, con.cursor() as cur:
        tables = fetch_tables(cur)
        columns = fetch_columns(cur)
        indexes = fetch_indexes(cur)
        constraints = fetch_foreign_keys(cur)

        table_map = {table["name"]: table for table in tables}
        for table in tables:
            name = table["name"]
            table["group"] = group_for_table(name)
            table["columns"] = columns.get(name, [])
            table["indexes"] = indexes.get(name, [])
            table["column_count"] = len(table["columns"])
            table["index_count"] = len(table["indexes"])
            table["pk_columns"] = [
                c["name"] for c in table["columns"] if c.get("is_primary_key")
            ]

        relationships = infer_relationships(tables, constraints)
        checks = fetch_health_checks(cur)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "database": "x9db",
        "tables": tables,
        "relationships": relationships,
        "checks": checks,
        "groups": {
            key: {"label": value["label"], "color": value["color"]}
            for key, value in GROUPS.items()
        },
        "summary": {
            "tables": len(tables),
            "columns": sum(table["column_count"] for table in tables),
            "indexes": sum(table["index_count"] for table in tables),
            "rows": sum(table["rows"] for table in tables),
            "relationships": len(relationships),
            "non_empty_tables": sum(1 for table in tables if table["rows"] > 0),
            "largest_table": max(tables, key=lambda t: t["rows"])["name"] if tables else None,
        },
        "table_map": table_map,
    }


def fetch_tables(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    )
    names = [row[0] for row in cur.fetchall()]
    tables: list[dict[str, Any]] = []
    for name in names:
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(name)))
        rows = int(cur.fetchone()[0])
        cur.execute("SELECT pg_total_relation_size(%s::regclass)", (f"public.{name}",))
        size_bytes = int(cur.fetchone()[0])
        tables.append({"name": name, "rows": rows, "size_bytes": size_bytes})
    return tables


def fetch_columns(cur: psycopg.Cursor) -> dict[str, list[dict[str, Any]]]:
    cur.execute(
        """
        SELECT
          c.table_name,
          c.column_name,
          c.data_type,
          c.is_nullable,
          c.column_default,
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
        table, name, data_type, nullable, default, ordinal, is_pk = row
        out.setdefault(table, []).append(
            {
                "name": name,
                "type": data_type,
                "nullable": nullable == "YES",
                "default": default,
                "ordinal": ordinal,
                "is_primary_key": bool(is_pk),
            }
        )
    return out


def fetch_indexes(cur: psycopg.Cursor) -> dict[str, list[dict[str, Any]]]:
    cur.execute(
        """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY tablename, indexname
        """
    )
    out: dict[str, list[dict[str, Any]]] = {}
    for table, name, definition in cur.fetchall():
        out.setdefault(table, []).append(
            {
                "name": name,
                "unique": "CREATE UNIQUE INDEX" in definition,
                "definition": definition,
            }
        )
    return out


def fetch_foreign_keys(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT
          tc.table_name AS source_table,
          kcu.column_name AS source_column,
          ccu.table_name AS target_table,
          ccu.column_name AS target_column,
          tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
        ORDER BY source_table, source_column
        """
    )
    return [
        {
            "source": row[0],
            "source_column": row[1],
            "target": row[2],
            "target_column": row[3],
            "kind": "foreign_key",
            "label": row[4],
        }
        for row in cur.fetchall()
    ]


def infer_relationships(
    tables: list[dict[str, Any]], foreign_keys: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    table_names = {table["name"] for table in tables}
    relationships = list(foreign_keys)
    seen = {
        (item["source"], item["source_column"], item["target"], item["target_column"])
        for item in relationships
    }
    table_by_name = {table["name"]: table for table in tables}

    for source, source_column_target in RELATION_OVERRIDES.items():
        source_table, source_column = source
        target = source_column_target
        if source_table not in table_names or target not in table_names:
            continue
        key = (source_table, source_column, target, "id")
        if key in seen:
            continue
        relationships.append(
            {
                "source": source_table,
                "source_column": source_column,
                "target": target,
                "target_column": "id",
                "kind": "inferred",
                "label": source_column,
                "weight": relationship_weight(table_by_name, source_table, target),
            }
        )
        seen.add(key)

    return relationships


def relationship_weight(
    table_by_name: dict[str, dict[str, Any]], source: str, target: str
) -> int:
    return max(1, int(math.log10(max(table_by_name[source]["rows"], table_by_name[target]["rows"], 1)) + 1))


def fetch_health_checks(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    checks = [
        (
            "api_key -> api_user",
            """
            SELECT COUNT(*)
            FROM api_key k
            WHERE k.user_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM api_user u WHERE u.id = k.user_id)
            """,
        ),
        (
            "keyword_snapshot -> tk_hot_keyword",
            """
            SELECT COUNT(*)
            FROM keyword_snapshot s
            WHERE s.keyword_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM tk_hot_keyword k WHERE k.id = s.keyword_id)
            """,
        ),
        (
            "outreach -> creator",
            """
            SELECT COUNT(*)
            FROM outreach o
            WHERE o.creator_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM creator c WHERE c.id = o.creator_id)
            """,
        ),
        (
            "creator_tags -> creators",
            """
            SELECT COUNT(*)
            FROM creator_tags t
            WHERE t.creator_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM creators c WHERE c.id = t.creator_id)
            """,
        ),
        (
            "creator_recommendations -> creators",
            """
            SELECT COUNT(*)
            FROM creator_recommendations r
            WHERE r.creator_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM creators c WHERE c.id = r.creator_id)
            """,
        ),
        (
            "outreach_emails -> tk_creators",
            """
            SELECT COUNT(*)
            FROM outreach_emails e
            WHERE e.creator_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM tk_creators c WHERE c.id::text = e.creator_id)
            """,
        ),
    ]
    out: list[dict[str, Any]] = []
    for label, query in checks:
        try:
            cur.execute(query)
            orphans = int(cur.fetchone()[0])
            out.append({"label": label, "orphans": orphans, "ok": orphans == 0})
        except Exception as exc:  # noqa: BLE001 - visualization should survive missing future tables.
            out.append({"label": label, "orphans": None, "ok": False, "error": str(exc)})
    return out


def group_for_table(table: str) -> str:
    for key, group in GROUPS.items():
        if table in group["tables"]:
            return key
    return "other"


def render_html(data: dict[str, Any]) -> str:
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = f"X9 Database Map · {html.escape(data['generated_at'])}"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #f7f8fb;
      --panel: #ffffff;
      --panel-2: #f0f3f7;
      --border: #d7dde7;
      --text: #18202b;
      --muted: #667085;
      --accent: #2563a9;
      --good: #1d7a54;
      --warn: #a56315;
      --bad: #b42318;
      --shadow: 0 8px 24px rgba(20, 31, 49, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 13px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    button, input, select {{ font: inherit; }}
    .app {{
      height: 100vh;
      display: grid;
      grid-template-rows: auto 1fr;
      min-width: 320px;
    }}
    header {{
      display: grid;
      grid-template-columns: minmax(260px, 1fr) auto;
      gap: 16px;
      align-items: center;
      padding: 14px 18px;
      background: #ffffff;
      border-bottom: 1px solid var(--border);
    }}
    h1 {{
      margin: 0;
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .subtitle {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 2px;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(5, minmax(72px, 1fr));
      gap: 8px;
      min-width: 480px;
    }}
    .stat {{
      background: var(--panel-2);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 10px;
      min-height: 52px;
    }}
    .stat b {{
      display: block;
      font-size: 17px;
      line-height: 1.1;
      white-space: nowrap;
    }}
    .stat span {{
      display: block;
      color: var(--muted);
      font-size: 11px;
      margin-top: 4px;
      white-space: nowrap;
    }}
    main {{
      display: grid;
      grid-template-columns: 310px minmax(420px, 1fr) 390px;
      gap: 12px;
      padding: 12px;
      min-height: 0;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      min-height: 0;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .toolbar {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      padding: 10px;
      border-bottom: 1px solid var(--border);
      background: #ffffff;
    }}
    .toolbar select, .toolbar input {{
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #fff;
      min-height: 34px;
      padding: 6px 8px;
      color: var(--text);
    }}
    .tabs {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 4px;
      padding: 8px;
      border-bottom: 1px solid var(--border);
      background: #fff;
    }}
    .tab {{
      min-height: 32px;
      border: 1px solid var(--border);
      background: var(--panel-2);
      border-radius: 6px;
      color: var(--text);
      cursor: pointer;
    }}
    .tab.active {{
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }}
    .table-list {{
      height: calc(100vh - 173px);
      overflow: auto;
    }}
    .table-row {{
      width: 100%;
      display: grid;
      grid-template-columns: 12px 1fr auto;
      align-items: center;
      gap: 8px;
      border: 0;
      border-bottom: 1px solid #eef1f5;
      background: #fff;
      padding: 9px 10px;
      text-align: left;
      cursor: pointer;
      min-height: 48px;
    }}
    .table-row:hover, .table-row.active {{ background: #eef5fb; }}
    .dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      display: inline-block;
    }}
    .table-name {{
      font-weight: 650;
      overflow-wrap: anywhere;
      line-height: 1.25;
    }}
    .table-meta {{
      color: var(--muted);
      font-size: 11px;
      margin-top: 2px;
    }}
    .count {{
      color: var(--muted);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }}
    .graph-panel {{
      display: grid;
      grid-template-rows: auto 1fr auto;
      min-height: 0;
    }}
    .graph-head {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: center;
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      background: #fff;
    }}
    .graph-title {{
      font-weight: 700;
      font-size: 14px;
    }}
    .graph-actions {{
      display: flex;
      gap: 6px;
      align-items: center;
    }}
    .icon-btn {{
      min-width: 34px;
      height: 32px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #fff;
      cursor: pointer;
      color: var(--text);
    }}
    .icon-btn:hover {{ background: var(--panel-2); }}
    svg {{
      width: 100%;
      height: 100%;
      display: block;
      background:
        linear-gradient(#eef2f7 1px, transparent 1px),
        linear-gradient(90deg, #eef2f7 1px, transparent 1px);
      background-size: 28px 28px;
    }}
    .edge {{
      stroke: #8b98aa;
      stroke-opacity: .55;
      fill: none;
    }}
    .edge.foreign_key {{ stroke: #2e7d62; stroke-opacity: .7; }}
    .node circle {{
      stroke: rgba(255,255,255,.95);
      stroke-width: 2;
      cursor: pointer;
    }}
    .node text {{
      pointer-events: none;
      font-size: 11px;
      fill: #111827;
      paint-order: stroke;
      stroke: #fff;
      stroke-width: 4px;
      stroke-linejoin: round;
    }}
    .node.selected circle {{
      stroke: #111827;
      stroke-width: 3;
    }}
    .legend {{
      display: flex;
      gap: 8px 12px;
      flex-wrap: wrap;
      padding: 8px 10px;
      border-top: 1px solid var(--border);
      background: #fff;
      color: var(--muted);
      font-size: 11px;
    }}
    .legend-item {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      white-space: nowrap;
    }}
    .detail {{
      height: calc(100vh - 104px);
      overflow: auto;
    }}
    .detail-head {{
      padding: 14px;
      border-bottom: 1px solid var(--border);
      background: #fff;
    }}
    .detail-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-weight: 750;
      font-size: 16px;
    }}
    .pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
    }}
    .pill {{
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 3px 8px;
      background: var(--panel-2);
      color: var(--muted);
      font-size: 11px;
      white-space: nowrap;
    }}
    .section {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--border);
    }}
    .section h2 {{
      margin: 0 0 8px;
      font-size: 13px;
      line-height: 1.2;
    }}
    .columns {{
      display: grid;
      gap: 6px;
    }}
    .col-row {{
      display: grid;
      grid-template-columns: minmax(90px, 1fr) minmax(74px, auto) auto;
      gap: 8px;
      align-items: center;
      padding: 7px 8px;
      background: #fafbfc;
      border: 1px solid #edf0f4;
      border-radius: 6px;
      min-height: 35px;
    }}
    .col-name {{ font-weight: 600; overflow-wrap: anywhere; }}
    .col-type {{ color: var(--muted); font-size: 11px; overflow-wrap: anywhere; }}
    .key {{
      border-radius: 5px;
      color: #fff;
      background: #6b7280;
      font-size: 10px;
      padding: 2px 5px;
      white-space: nowrap;
    }}
    .key.pk {{ background: #805ad5; }}
    .index-list, .relation-list, .check-list {{
      display: grid;
      gap: 7px;
    }}
    .small-row {{
      padding: 8px;
      border: 1px solid #edf0f4;
      border-radius: 6px;
      background: #fafbfc;
      overflow-wrap: anywhere;
    }}
    .small-row b {{ display: block; margin-bottom: 2px; }}
    .ok {{ color: var(--good); }}
    .warn {{ color: var(--warn); }}
    .bad {{ color: var(--bad); }}
    .hidden {{ display: none !important; }}
    @media (max-width: 1120px) {{
      header {{ grid-template-columns: 1fr; }}
      .stats {{ min-width: 0; grid-template-columns: repeat(5, minmax(64px, 1fr)); }}
      main {{ grid-template-columns: 280px minmax(360px, 1fr); }}
      .detail.panel {{ display: none; }}
    }}
    @media (max-width: 760px) {{
      .app {{ height: auto; min-height: 100vh; }}
      header {{ padding: 12px; }}
      .stats {{ grid-template-columns: repeat(2, minmax(120px, 1fr)); }}
      main {{ grid-template-columns: 1fr; padding: 8px; }}
      .table-list {{ height: 320px; }}
      .graph-panel {{ min-height: 540px; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <header>
      <div>
        <h1>X9 Database Map</h1>
        <div class="subtitle"><span id="generatedAt"></span> · PostgreSQL x9db</div>
      </div>
      <div class="stats" id="stats"></div>
    </header>
    <main>
      <aside class="panel">
        <div class="toolbar">
          <input id="search" placeholder="Search table or column" autocomplete="off">
          <select id="groupFilter" aria-label="Group"></select>
        </div>
        <div class="tabs">
          <button class="tab active" data-tab="tables">Tables</button>
          <button class="tab" data-tab="checks">Checks</button>
          <button class="tab" data-tab="relations">Links</button>
        </div>
        <div id="tableList" class="table-list"></div>
      </aside>
      <section class="panel graph-panel">
        <div class="graph-head">
          <div class="graph-title" id="graphTitle">Schema Graph</div>
          <div class="graph-actions">
            <button class="icon-btn" id="fitBtn" title="Fit">⌖</button>
            <button class="icon-btn" id="labelsBtn" title="Labels">Aa</button>
          </div>
        </div>
        <svg id="graph" role="img" aria-label="Database schema graph"></svg>
        <div class="legend" id="legend"></div>
      </section>
      <aside class="panel detail" id="detail"></aside>
    </main>
  </div>
  <script>
    const DB_DATA = {data_json};
    const state = {{
      selected: DB_DATA.tables[0]?.name,
      tab: 'tables',
      search: '',
      group: 'all',
      labels: true,
      layout: null
    }};

    const byName = Object.fromEntries(DB_DATA.tables.map(t => [t.name, t]));
    const fmt = new Intl.NumberFormat('en-US');
    const sizeFmt = bytes => {{
      if (bytes < 1024) return bytes + ' B';
      const units = ['KB', 'MB', 'GB'];
      let n = bytes / 1024;
      let i = 0;
      while (n >= 1024 && i < units.length - 1) {{ n /= 1024; i++; }}
      return (n >= 100 ? n.toFixed(0) : n.toFixed(1)) + ' ' + units[i];
    }};
    const groupColor = g => DB_DATA.groups[g]?.color || DB_DATA.groups.other.color;
    const groupLabel = g => DB_DATA.groups[g]?.label || g;

    function init() {{
      document.getElementById('generatedAt').textContent = DB_DATA.generated_at;
      renderStats();
      renderGroupFilter();
      renderLegend();
      wireEvents();
      renderSidebar();
      renderDetail();
      renderGraph();
    }}

    function renderStats() {{
      const s = DB_DATA.summary;
      document.getElementById('stats').innerHTML = [
        ['Tables', s.tables],
        ['Rows', fmt.format(s.rows)],
        ['Columns', s.columns],
        ['Indexes', s.indexes],
        ['Links', s.relationships],
      ].map(([label, value]) => `<div class="stat"><b>${{value}}</b><span>${{label}}</span></div>`).join('');
    }}

    function renderGroupFilter() {{
      const select = document.getElementById('groupFilter');
      const groups = Object.entries(DB_DATA.groups)
        .filter(([key]) => key === 'all' || key === 'other' || DB_DATA.tables.some(t => t.group === key));
      select.innerHTML = `<option value="all">All groups</option>` +
        groups.map(([key, value]) => key === 'all' ? '' : `<option value="${{key}}">${{value.label}}</option>`).join('');
    }}

    function renderLegend() {{
      document.getElementById('legend').innerHTML = Object.entries(DB_DATA.groups)
        .filter(([key]) => DB_DATA.tables.some(t => t.group === key))
        .map(([key, group]) => `<span class="legend-item"><span class="dot" style="background:${{group.color}}"></span>${{group.label}}</span>`)
        .join('');
    }}

    function wireEvents() {{
      document.getElementById('search').addEventListener('input', e => {{
        state.search = e.target.value.trim().toLowerCase();
        renderSidebar();
        renderGraph();
      }});
      document.getElementById('groupFilter').addEventListener('change', e => {{
        state.group = e.target.value;
        renderSidebar();
        renderGraph();
      }});
      document.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => {{
        document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.tab = btn.dataset.tab;
        renderSidebar();
      }}));
      document.getElementById('fitBtn').addEventListener('click', () => renderGraph(true));
      document.getElementById('labelsBtn').addEventListener('click', () => {{
        state.labels = !state.labels;
        renderGraph();
      }});
      window.addEventListener('resize', () => renderGraph(true));
    }}

    function tableMatches(t) {{
      if (state.group !== 'all' && t.group !== state.group) return false;
      if (!state.search) return true;
      const blob = [
        t.name,
        groupLabel(t.group),
        ...t.columns.map(c => c.name + ' ' + c.type),
        ...t.indexes.map(i => i.name),
      ].join(' ').toLowerCase();
      return blob.includes(state.search);
    }}

    function filteredTables() {{
      return DB_DATA.tables.filter(tableMatches);
    }}

    function renderSidebar() {{
      const el = document.getElementById('tableList');
      if (state.tab === 'checks') {{
        el.innerHTML = `<div class="section"><div class="check-list">${{DB_DATA.checks.map(c => `
          <div class="small-row">
            <b class="${{c.ok ? 'ok' : 'bad'}}">${{c.label}}</b>
            <span>${{c.orphans === null ? c.error : fmt.format(c.orphans) + ' orphan rows'}}</span>
          </div>`).join('')}}</div></div>`;
        return;
      }}
      if (state.tab === 'relations') {{
        el.innerHTML = `<div class="section"><div class="relation-list">${{DB_DATA.relationships.map(r => `
          <button class="small-row" style="text-align:left;cursor:pointer" onclick="selectTable('${{r.source}}')">
            <b>${{r.source}}.${{r.source_column}}</b>
            <span>${{r.target}}.${{r.target_column}} · ${{r.kind}}</span>
          </button>`).join('')}}</div></div>`;
        return;
      }}
      const rows = filteredTables().sort((a, b) => b.rows - a.rows || a.name.localeCompare(b.name));
      el.innerHTML = rows.map(t => `
        <button class="table-row ${{state.selected === t.name ? 'active' : ''}}" onclick="selectTable('${{t.name}}')">
          <span class="dot" style="background:${{groupColor(t.group)}}"></span>
          <span>
            <span class="table-name">${{t.name}}</span>
            <span class="table-meta">${{groupLabel(t.group)}} · ${{t.column_count}} cols · ${{t.index_count}} idx</span>
          </span>
          <span class="count">${{fmt.format(t.rows)}}</span>
        </button>`).join('');
    }}

    window.selectTable = function(name) {{
      state.selected = name;
      renderSidebar();
      renderDetail();
      renderGraph();
    }};

    function renderDetail() {{
      const t = byName[state.selected] || DB_DATA.tables[0];
      if (!t) return;
      const incoming = DB_DATA.relationships.filter(r => r.target === t.name);
      const outgoing = DB_DATA.relationships.filter(r => r.source === t.name);
      const detail = document.getElementById('detail');
      detail.innerHTML = `
        <div class="detail-head">
          <div class="detail-title">
            <span>${{t.name}}</span>
            <span class="dot" style="background:${{groupColor(t.group)}}"></span>
          </div>
          <div class="pills">
            <span class="pill">${{groupLabel(t.group)}}</span>
            <span class="pill">${{fmt.format(t.rows)}} rows</span>
            <span class="pill">${{t.column_count}} columns</span>
            <span class="pill">${{sizeFmt(t.size_bytes)}}</span>
          </div>
        </div>
        <div class="section">
          <h2>Columns</h2>
          <div class="columns">${{t.columns.map(c => `
            <div class="col-row">
              <span class="col-name">${{c.name}}</span>
              <span class="col-type">${{c.type}}</span>
              <span class="key ${{c.is_primary_key ? 'pk' : ''}}">${{c.is_primary_key ? 'PK' : (c.nullable ? 'NULL' : 'REQ')}}</span>
            </div>`).join('')}}</div>
        </div>
        <div class="section">
          <h2>Relationships</h2>
          <div class="relation-list">
            ${{outgoing.map(r => `<div class="small-row"><b>${{r.source_column}} → ${{r.target}}</b><span>${{r.kind}}</span></div>`).join('') || '<div class="small-row">No outgoing links</div>'}}
            ${{incoming.map(r => `<div class="small-row"><b>${{r.source}} → ${{r.target_column}}</b><span>incoming · ${{r.kind}}</span></div>`).join('') || ''}}
          </div>
        </div>
        <div class="section">
          <h2>Indexes</h2>
          <div class="index-list">${{t.indexes.map(i => `
            <div class="small-row"><b>${{i.name}}</b><span>${{i.unique ? 'unique' : 'index'}}</span></div>`).join('') || '<div class="small-row">No indexes</div>'}}</div>
        </div>`;
    }}

    function renderGraph(forceFit=false) {{
      const svg = document.getElementById('graph');
      const box = svg.getBoundingClientRect();
      const width = Math.max(420, box.width || 800);
      const height = Math.max(420, box.height || 620);
      svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
      svg.innerHTML = '';

      const tables = filteredTables();
      const names = new Set(tables.map(t => t.name));
      const relationships = DB_DATA.relationships.filter(r => names.has(r.source) && names.has(r.target));
      const nodes = tables.map(t => ({{
        ...t,
        r: 8 + Math.min(20, Math.log10(Math.max(t.rows, 1)) * 7),
      }}));
      const nodeByName = Object.fromEntries(nodes.map(n => [n.name, n]));

      layoutNodes(nodes, relationships, width, height, forceFit);

      const edgeLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      const nodeLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      svg.append(edgeLayer, nodeLayer);

      relationships.forEach(r => {{
        const s = nodeByName[r.source], t = nodeByName[r.target];
        if (!s || !t) return;
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('class', `edge ${{r.kind}}`);
        line.setAttribute('x1', s.x);
        line.setAttribute('y1', s.y);
        line.setAttribute('x2', t.x);
        line.setAttribute('y2', t.y);
        line.setAttribute('stroke-width', Math.max(1.2, r.weight || 1));
        edgeLayer.append(line);
      }});

      nodes.forEach(n => {{
        const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('class', `node ${{n.name === state.selected ? 'selected' : ''}}`);
        g.setAttribute('transform', `translate(${{n.x}},${{n.y}})`);
        g.addEventListener('click', () => selectTable(n.name));

        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('r', n.r);
        circle.setAttribute('fill', groupColor(n.group));
        g.append(circle);

        if (state.labels || n.name === state.selected) {{
          const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          text.setAttribute('text-anchor', 'middle');
          text.setAttribute('y', n.r + 14);
          text.textContent = n.name;
          g.append(text);
        }}
        nodeLayer.append(g);
      }});

      document.getElementById('graphTitle').textContent =
        `${{tables.length}} tables · ${{relationships.length}} links`;
    }}

    function layoutNodes(nodes, relationships, width, height, forceFit) {{
      const groups = [...new Set(nodes.map(n => n.group))].sort();
      const groupCenters = Object.fromEntries(groups.map((g, i) => {{
        const angle = -Math.PI / 2 + i * Math.PI * 2 / Math.max(groups.length, 1);
        return [g, {{
          x: width / 2 + Math.cos(angle) * width * 0.28,
          y: height / 2 + Math.sin(angle) * height * 0.28
        }}];
      }}));
      nodes.forEach((n, i) => {{
        if (!forceFit && state.layout?.[n.name]) {{
          n.x = state.layout[n.name].x * width;
          n.y = state.layout[n.name].y * height;
          return;
        }}
        const center = groupCenters[n.group] || {{x: width/2, y: height/2}};
        const angle = i * 2.399963229728653;
        n.x = center.x + Math.cos(angle) * (28 + (i % 7) * 8);
        n.y = center.y + Math.sin(angle) * (28 + (i % 7) * 8);
      }});

      const nodeByName = Object.fromEntries(nodes.map(n => [n.name, n]));
      for (let step = 0; step < 260; step++) {{
        nodes.forEach(n => {{ n.vx = (n.vx || 0) * 0.72; n.vy = (n.vy || 0) * 0.72; }});
        for (let i = 0; i < nodes.length; i++) {{
          for (let j = i + 1; j < nodes.length; j++) {{
            const a = nodes[i], b = nodes[j];
            let dx = a.x - b.x, dy = a.y - b.y;
            let d2 = dx * dx + dy * dy || 1;
            const min = a.r + b.r + 54;
            if (d2 < min * min) {{
              const d = Math.sqrt(d2);
              const push = (min - d) * 0.018;
              dx /= d; dy /= d;
              a.vx += dx * push; a.vy += dy * push;
              b.vx -= dx * push; b.vy -= dy * push;
            }}
          }}
        }}
        relationships.forEach(r => {{
          const a = nodeByName[r.source], b = nodeByName[r.target];
          if (!a || !b) return;
          const dx = b.x - a.x, dy = b.y - a.y;
          const d = Math.sqrt(dx * dx + dy * dy) || 1;
          const target = 135;
          const pull = (d - target) * 0.004;
          a.vx += dx / d * pull; a.vy += dy / d * pull;
          b.vx -= dx / d * pull; b.vy -= dy / d * pull;
        }});
        nodes.forEach(n => {{
          const center = groupCenters[n.group] || {{x: width/2, y: height/2}};
          n.vx += (center.x - n.x) * 0.0025;
          n.vy += (center.y - n.y) * 0.0025;
          n.x = Math.min(width - n.r - 38, Math.max(n.r + 38, n.x + n.vx));
          n.y = Math.min(height - n.r - 28, Math.max(n.r + 28, n.y + n.vy));
        }});
      }}
      state.layout = Object.fromEntries(nodes.map(n => [n.name, {{x: n.x / width, y: n.y / height}}]));
    }}

    init();
  </script>
</body>
</html>
"""


def write_visualization(dsn: str, output: Path) -> dict[str, Any]:
    data = fetch_database_shape(dsn)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(data), encoding="utf-8")
    return {
        "output": str(output),
        "tables": data["summary"]["tables"],
        "rows": data["summary"]["rows"],
        "columns": data["summary"]["columns"],
        "relationships": data["summary"]["relationships"],
        "generated_at": data["generated_at"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an offline PostgreSQL schema visualization.")
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = write_visualization(args.pg_dsn, Path(args.output))
    print(json.dumps(result, ensure_ascii=False, indent=2))
