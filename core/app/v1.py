"""Unified /api/v1 router — works on any registered resource (built-in or dynamic).

Endpoints
=========

Discovery
    GET    /api/v1/                        Server info + counts
    GET    /api/v1/resources               List all resources (= tables exposed via API)
    GET    /api/v1/resources/{name}        Resource metadata + column list

Schema mutation (auth)
    POST   /api/v1/tables                  Create new table + register as resource
    POST   /api/v1/tables/{name}/columns   Add column to existing table

Generic CRUD on any resource
    GET    /api/v1/data/{resource}                List rows (?limit=&offset=&q=&filter=...)
    GET    /api/v1/data/{resource}/{id}           Get one row by primary key
    POST   /api/v1/data/{resource}/bulk           Batch upsert         (auth)
    PATCH  /api/v1/data/{resource}/{id}           Partial update       (auth)
    DELETE /api/v1/data/{resource}/{id}           Delete one row       (auth)

Named queries
    GET    /api/v1/queries                 List saved query recipes
    GET    /api/v1/queries/{name}          Run one (params via querystring)
"""
from __future__ import annotations
import json
import os
import re as _re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg.rows import dict_row

from app.auth import require_authenticated, require_admin, require_user_or_above, assert_can
from app.registry import (
    BUILTIN_RESOURCES, DB_PATH, NAMED_QUERIES, Resource,
    VALID_TYPES, ensure_meta_table, load_resources, register_dynamic, safe_ident,
)

router = APIRouter()


def _load_shared_env() -> None:
    env_path = DB_PATH.parent.parent / ".env.shared"
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


_load_shared_env()
PG_DSN = os.environ.get(
    "X9_PG_DSN",
    "postgresql://x9:x9_local_dev_2026@127.0.0.1:15432/x9db?connect_timeout=5",
)
API_V1_BACKEND = os.environ.get("X9_API_V1_BACKEND", "postgres").strip().lower()


# ============================================================
# Helpers
# ============================================================
def get_con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys=ON")
    con.row_factory = sqlite3.Row
    return con


def get_pg_con() -> psycopg.Connection:
    return psycopg.connect(PG_DSN, row_factory=dict_row)


def use_pg_v1() -> bool:
    return API_V1_BACKEND not in {"sqlite", "sqlite3", "local_sqlite"}


def _json_or(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() not in {"", "0", "false", "no", "none"}


def get_sqlite_resource(name: str) -> Resource:
    con = get_con()
    try:
        regs = load_resources(con)
    finally:
        con.close()
    if name not in regs:
        raise HTTPException(404, f"unknown resource '{name}' (try GET /api/v1/resources)")
    return regs[name]


def pg_load_resources(cur) -> dict[str, Resource]:
    cur.execute(
        """
        SELECT name, table_name, pk, upsert_keys, json_cols, fk_lookup,
               description, is_dynamic, writable, deprecated_note
        FROM _meta_resource
        ORDER BY name
        """
    )
    out: dict[str, Resource] = {}
    for row in cur.fetchall():
        fk = _json_or(row.get("fk_lookup"), {})
        res = Resource(
            name=row["name"],
            table=row["table_name"],
            pk=row.get("pk") or "id",
            upsert_keys=_json_or(row.get("upsert_keys"), []),
            json_cols=_json_or(row.get("json_cols"), []),
            fk_lookup={k: tuple(v) for k, v in fk.items()},
            auto_compute=BUILTIN_RESOURCES[row["name"]].auto_compute
            if row["name"] in BUILTIN_RESOURCES else {},
            description=row.get("description") or "",
            is_dynamic=_truthy(row.get("is_dynamic")),
            writable=_truthy(row.get("writable")),
        )
        if row.get("deprecated_note"):
            res.description = (res.description or "") + f" [DEPRECATED: {row['deprecated_note']}]"
        out[res.name] = res
    return out


def get_resource(name: str) -> Resource:
    if not use_pg_v1():
        return get_sqlite_resource(name)
    try:
        with get_pg_con() as con, con.cursor() as cur:
            regs = pg_load_resources(cur)
    except Exception as exc:
        raise HTTPException(503, f"PostgreSQL resource registry unavailable: {exc}") from exc
    if name not in regs:
        raise HTTPException(404, f"unknown resource '{name}' (try GET /api/v1/resources)")
    return regs[name]


def table_columns(con: sqlite3.Connection, table: str) -> list[dict]:
    safe_ident(table)
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return [{"cid": r[0], "name": r[1], "type": r[2], "notnull": bool(r[3]),
             "default": r[4], "pk": bool(r[5])} for r in rows]


def encode_for_db(payload: dict, json_cols: list[str]) -> dict:
    out = {}
    for k, v in payload.items():
        if k in json_cols and not isinstance(v, str):
            out[k] = json.dumps(v or [], ensure_ascii=False)
        else:
            out[k] = v
    return out


def decode_row(row: sqlite3.Row | None, json_cols: list[str]) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in json_cols:
        if k in d and isinstance(d[k], str) and d[k]:
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
        elif k in d and not d[k]:
            d[k] = []
    return d


def resolve_fk(con: sqlite3.Connection, payload: dict, fk_lookup: dict) -> tuple[dict, list[dict]]:
    """For each (input_field -> (table, keys, target_col)) lookup, fill target_col
    from input_field. Returns (cleaned_payload, errors_list)."""
    errors = []
    out = dict(payload)
    for input_field, (foreign_table, lookup_keys, target_col) in fk_lookup.items():
        if input_field not in out:
            continue
        lookup_value = out.pop(input_field)
        if lookup_value is None or lookup_value == "":
            continue
        # Build WHERE — single key or composite
        if len(lookup_keys) == 1:
            where = f"{lookup_keys[0]} = ?"
            args = [lookup_value]
        else:
            # composite key -> input must be dict like {"platform":"tiktok","handle":"x"}
            if not isinstance(lookup_value, dict):
                errors.append({"field": input_field, "error": f"composite key needs dict with {lookup_keys}"})
                continue
            where = " AND ".join([f"{k} = ?" for k in lookup_keys])
            args = [lookup_value.get(k) for k in lookup_keys]
        sql = f"SELECT id FROM {foreign_table} WHERE {where} LIMIT 1"
        row = con.execute(sql, args).fetchone()
        if not row:
            errors.append({"field": input_field, "value": lookup_value,
                           "error": f"foreign row not found in {foreign_table}"})
            continue
        out[target_col] = row[0]
    return out, errors


def get_columns_set(con: sqlite3.Connection, table: str) -> set[str]:
    return {c["name"] for c in table_columns(con, table)}


def pg_table_columns(cur, table: str) -> list[dict]:
    safe_ident(table)
    cur.execute(
        """
        SELECT ordinal_position AS cid,
               column_name AS name,
               data_type AS type,
               is_nullable <> 'YES' AS notnull,
               column_default AS "default",
               EXISTS (
                 SELECT 1
                 FROM information_schema.table_constraints tc
                 JOIN information_schema.key_column_usage kcu
                   ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                  AND tc.table_name = kcu.table_name
                 WHERE tc.constraint_type = 'PRIMARY KEY'
                   AND tc.table_schema = c.table_schema
                   AND tc.table_name = c.table_name
                   AND kcu.column_name = c.column_name
               ) AS pk
        FROM information_schema.columns c
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    rows = cur.fetchall()
    if not rows:
        raise HTTPException(404, f"table '{table}' not found in PostgreSQL")
    return rows


def pg_columns_set(cur, table: str) -> set[str]:
    return {c["name"] for c in pg_table_columns(cur, table)}


def pg_decode_row(row: dict | None, json_cols: list[str]) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in json_cols:
        if k in d and isinstance(d[k], str) and d[k]:
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
        elif k in d and not d[k]:
            d[k] = []
    return d


def pg_resolve_fk(cur, payload: dict, fk_lookup: dict) -> tuple[dict, list[dict]]:
    errors = []
    out = dict(payload)
    for input_field, (foreign_table, lookup_keys, target_col) in fk_lookup.items():
        if input_field not in out:
            continue
        lookup_value = out.pop(input_field)
        if lookup_value is None or lookup_value == "":
            continue
        safe_ident(foreign_table)
        for key in lookup_keys:
            safe_ident(key)
        if len(lookup_keys) == 1:
            where = f"{lookup_keys[0]} = %s"
            args = [lookup_value]
        else:
            if not isinstance(lookup_value, dict):
                errors.append({"field": input_field, "error": f"composite key needs dict with {lookup_keys}"})
                continue
            where = " AND ".join([f"{k} = %s" for k in lookup_keys])
            args = [lookup_value.get(k) for k in lookup_keys]
        cur.execute(f"SELECT id FROM {foreign_table} WHERE {where} LIMIT 1", args)
        row = cur.fetchone()
        if not row:
            errors.append({"field": input_field, "value": lookup_value,
                           "error": f"foreign row not found in {foreign_table}"})
            continue
        out[target_col] = row["id"]
    return out, errors


def pg_encode_for_db(payload: dict, json_cols: list[str]) -> dict:
    return encode_for_db(payload, json_cols)


def pg_count(cur, table: str, where_sql: str = "1=1", args: list[Any] | tuple[Any, ...] = ()) -> int:
    safe_ident(table)
    cur.execute(f"SELECT COUNT(*)::int AS count FROM {table} WHERE {where_sql}", args)
    row = cur.fetchone()
    return int(row["count"] if isinstance(row, dict) else row[0])


def _pg_text_columns(cols_meta: list[dict]) -> list[str]:
    text_types = {"text", "character varying", "character", "citext"}
    return [c["name"] for c in cols_meta if str(c.get("type") or "").lower() in text_types]


def _pg_order_clause(order_by: str | None, desc: bool, cols: set[str]) -> str:
    if not order_by:
        return ""
    pieces = []
    if "," in order_by or ":" in order_by:
        for part in order_by.split(","):
            part = part.strip()
            if ":" in part:
                c, d = part.split(":", 1)
                c = c.strip()
                d = d.strip().lower()
            else:
                c, d = part, "asc"
            if c in cols and d in ("asc", "desc"):
                pieces.append(f"{c} {d.upper()}")
    elif order_by in cols:
        pieces.append(f"{order_by} {'DESC' if desc else 'ASC'}")
    return "ORDER BY " + ", ".join(pieces) if pieces else ""


def pg_list_rows(
    resource: str,
    request: Request,
    limit: int,
    offset: int,
    q: str | None,
    order_by: str | None,
    desc: bool,
) -> dict:
    r = get_resource(resource)
    with get_pg_con() as con, con.cursor() as cur:
        cols_meta = pg_table_columns(cur, r.table)
        cols = {c["name"] for c in cols_meta}
        where = ["1=1"]
        args: list[Any] = []
        in_buckets: dict[str, list[str]] = {}
        op_suffixes = {"__gte": ">=", "__lte": "<=", "__gt": ">", "__lt": "<"}

        for k, v in request.query_params.multi_items():
            if k in {"limit", "offset", "q", "order_by", "desc"}:
                continue
            matched = False
            for suffix, sql_op in op_suffixes.items():
                if k.endswith(suffix):
                    col = k[:-len(suffix)]
                    if col in cols:
                        where.append(f"{col} {sql_op} %s")
                        args.append(v)
                    matched = True
                    break
            if matched:
                continue
            if k.endswith("__in"):
                col = k[:-4]
                if col in cols:
                    in_buckets.setdefault(col, []).extend(s for s in v.split(",") if s != "")
                continue
            if k.endswith("__like"):
                col = k[:-6]
                if col in cols:
                    where.append(f"{col} LIKE %s")
                    args.append(v)
                continue
            if k.endswith("__icontains"):
                col = k[:-11]
                if col in cols:
                    where.append(f"{col} ILIKE %s")
                    args.append(f"%{v}%")
                continue
            if k.endswith("__isnull"):
                col = k[:-8]
                if col in cols:
                    if v.lower() in ("true", "1", "yes"):
                        where.append(f"{col} IS NULL")
                    else:
                        where.append(f"{col} IS NOT NULL")
                continue
            if k in cols:
                where.append(f"{k} = %s")
                args.append(v)

        for col, vals in in_buckets.items():
            if vals:
                where.append(f"{col} = ANY(%s)")
                args.append(vals)

        if q:
            text_cols = _pg_text_columns(cols_meta)
            if text_cols:
                where.append("(" + " OR ".join([f"{c} ILIKE %s" for c in text_cols]) + ")")
                args.extend([f"%{q}%"] * len(text_cols))

        where_sql = " AND ".join(where)
        order = _pg_order_clause(order_by, desc, cols)
        cur.execute(
            f"SELECT * FROM {r.table} WHERE {where_sql} {order} LIMIT %s OFFSET %s",
            args + [limit, offset],
        )
        rows = [pg_decode_row(row, r.json_cols) for row in cur.fetchall()]
        total = pg_count(cur, r.table, where_sql, args)
    return {"resource": resource, "total": total, "limit": limit, "offset": offset, "items": rows}


def pg_get_row(resource: str, row_id: str) -> dict:
    r = get_resource(resource)
    safe_ident(r.pk)
    with get_pg_con() as con, con.cursor() as cur:
        cur.execute(f"SELECT * FROM {r.table} WHERE {r.pk} = %s", (row_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, f"{resource}#{row_id} not found")
    return pg_decode_row(row, r.json_cols)


def pg_bulk_upsert(resource: str, payload: dict) -> dict:
    r = get_resource(resource)
    if not r.writable:
        raise HTTPException(403, f"resource '{resource}' is read-only")
    items = payload.get("items") or []
    if not isinstance(items, list):
        raise HTTPException(400, "items must be a list")

    with get_pg_con() as con, con.cursor() as cur:
        cols = pg_columns_set(cur, r.table)
        inserted = updated = 0
        errors: list[dict] = []
        for idx, raw in enumerate(items):
            try:
                resolved, fk_errors = pg_resolve_fk(cur, dict(raw), r.fk_lookup)
                if fk_errors:
                    errors.append({"idx": idx, "fk_errors": fk_errors})
                    continue
                for col, fn in r.auto_compute.items():
                    if col in cols and col not in resolved:
                        value = fn(resolved)
                        if value is not None:
                            resolved[col] = value
                fields = {k: v for k, v in resolved.items() if k in cols}
                if not fields:
                    errors.append({"idx": idx, "error": "no recognized columns"})
                    continue
                fields = pg_encode_for_db(fields, r.json_cols)

                if r.upsert_keys and all(k in fields for k in r.upsert_keys):
                    where = " AND ".join([f"{k} = %s" for k in r.upsert_keys])
                    cur.execute(
                        f"SELECT {r.pk} FROM {r.table} WHERE {where} LIMIT 1",
                        [fields[k] for k in r.upsert_keys],
                    )
                    pre = cur.fetchone()
                    if pre:
                        update_keys = [k for k in fields if k not in r.upsert_keys]
                        if update_keys:
                            sets = ", ".join([f"{k} = %s" for k in update_keys])
                            cur.execute(
                                f"UPDATE {r.table} SET {sets} WHERE {r.pk} = %s",
                                [fields[k] for k in update_keys] + [pre[r.pk]],
                            )
                        updated += 1
                        continue

                columns = list(fields.keys())
                placeholders = ", ".join(["%s"] * len(columns))
                cur.execute(
                    f"INSERT INTO {r.table}({', '.join(columns)}) VALUES({placeholders})",
                    [fields[k] for k in columns],
                )
                inserted += 1
            except Exception as exc:
                errors.append({"idx": idx, "error": str(exc)})
        con.commit()
    return {
        "resource": resource,
        "inserted": inserted,
        "updated": updated,
        "skipped": len(items) - inserted - updated,
        "errors": errors,
    }


def pg_patch_row(resource: str, row_id: str, payload: dict) -> dict:
    r = get_resource(resource)
    if not r.writable:
        raise HTTPException(403, f"resource '{resource}' is read-only")
    with get_pg_con() as con, con.cursor() as cur:
        cols = pg_columns_set(cur, r.table)
        resolved, fk_errors = pg_resolve_fk(cur, dict(payload), r.fk_lookup)
        if fk_errors:
            raise HTTPException(400, {"fk_errors": fk_errors})
        for col, fn in r.auto_compute.items():
            if col in cols and col not in resolved:
                value = fn(resolved)
                if value is not None:
                    resolved[col] = value
        fields = {k: v for k, v in resolved.items() if k in cols and k != r.pk}
        if not fields:
            raise HTTPException(400, "no editable fields in payload")
        fields = pg_encode_for_db(fields, r.json_cols)
        cur.execute(f"SELECT {r.pk} FROM {r.table} WHERE {r.pk} = %s", (row_id,))
        if not cur.fetchone():
            raise HTTPException(404, f"{resource}#{row_id} not found")
        sets = ", ".join([f"{k} = %s" for k in fields])
        cur.execute(f"UPDATE {r.table} SET {sets} WHERE {r.pk} = %s", list(fields.values()) + [row_id])
        con.commit()
    return {"ok": True, "updated_fields": list(fields.keys())}


def pg_delete_row(resource: str, row_id: str) -> dict:
    r = get_resource(resource)
    if not r.writable:
        raise HTTPException(403, f"resource '{resource}' is read-only")
    with get_pg_con() as con, con.cursor() as cur:
        cur.execute(f"SELECT {r.pk} FROM {r.table} WHERE {r.pk} = %s", (row_id,))
        if not cur.fetchone():
            raise HTTPException(404, "row not found")
        cur.execute(f"DELETE FROM {r.table} WHERE {r.pk} = %s", (row_id,))
        con.commit()
    return {"ok": True, "deleted": {r.pk: row_id}}


# ============================================================
# Discovery
# ============================================================
@router.get("/api/v1/version")
def version() -> dict:
    """Server + per-resource version info. Stable URL, never goes away.

    廖 那边可以定期 poll 这个，看到 schema_changed_at 变化就知道张这边动 schema 了。
    """
    if use_pg_v1():
        resources = []
        with get_pg_con() as con, con.cursor() as cur:
            regs = pg_load_resources(cur)
            for name, r in regs.items():
                try:
                    cols = pg_table_columns(cur, r.table)
                except Exception:
                    cols = []
                resources.append({
                    "name": name, "table": r.table,
                    "column_count": len(cols),
                    "columns": [c["name"] for c in cols],
                })
        return {
            "api_version": "v1",
            "server_version": "2.1.0",
            "database_backend": "postgres",
            "compatibility": "additive (adding fields/resources/queries is non-breaking)",
            "resources": resources,
            "changelog_url": "/docs/CHANGELOG.md",
            "changelog_last_modified_ts": None,
        }

    con = get_con()
    try:
        regs = load_resources(con)
        resources = []
        for name, r in regs.items():
            try:
                cols = table_columns(con, r.table)
            except Exception:
                cols = []
            resources.append({
                "name": name, "table": r.table,
                "column_count": len(cols),
                "columns": [c["name"] for c in cols],
            })
    finally:
        con.close()
    # CHANGELOG mtime so 廖 那边能 poll 发现变化
    last_change = None
    try:
        cl = DB_PATH.parent / "docs" / "CHANGELOG.md"
        if cl.exists():
            last_change = cl.stat().st_mtime
    except Exception:
        pass
    return {
        "api_version": "v1",
        "server_version": "2.1.0",
        "database_backend": "sqlite",
        "compatibility": "additive (adding fields/resources/queries is non-breaking)",
        "resources": resources,
        "changelog_url": "/docs/CHANGELOG.md",
        "changelog_last_modified_ts": last_change,
    }


@router.get("/api/v1/")
def discovery() -> dict:
    if use_pg_v1():
        with get_pg_con() as con, con.cursor() as cur:
            regs = pg_load_resources(cur)
            counts: dict[str, int] = {}
            for name, r in regs.items():
                try:
                    counts[name] = pg_count(cur, r.table)
                except Exception:
                    counts[name] = -1
            cur.execute("SELECT name FROM _meta_query ORDER BY name")
            queries = [row["name"] for row in cur.fetchall()]
        return {
            "version": "v1",
            "database_backend": "postgres",
            "resources": sorted(regs.keys()),
            "queries": queries,
            "counts": counts,
            "auth": "Send X-API-Key header for write endpoints. Read endpoints are open.",
            "endpoints": {
                "discovery":     "GET  /api/v1/",
                "list_resources":"GET  /api/v1/resources",
                "get_resource":  "GET  /api/v1/resources/{name}",
                "create_table":  "POST /api/v1/tables (auth)",
                "add_column":    "POST /api/v1/tables/{name}/columns (auth)",
                "list_rows":     "GET  /api/v1/data/{resource}",
                "get_row":       "GET  /api/v1/data/{resource}/{id}",
                "bulk_upsert":   "POST /api/v1/data/{resource}/bulk (auth)",
                "patch_row":     "PATCH /api/v1/data/{resource}/{id} (auth)",
                "delete_row":    "DELETE /api/v1/data/{resource}/{id} (auth)",
                "list_queries":  "GET  /api/v1/queries",
                "run_query":     "GET  /api/v1/queries/{name}",
            },
        }

    con = get_con()
    regs = load_resources(con)
    counts: dict[str, int] = {}
    for name, r in regs.items():
        try:
            counts[name] = con.execute(f"SELECT COUNT(*) FROM {r.table}").fetchone()[0]
        except Exception:
            counts[name] = -1
    queries = []
    try:
        queries = sorted([r[0] for r in con.execute(
            "SELECT name FROM _meta_query ORDER BY name").fetchall()])
    except Exception:
        queries = sorted(NAMED_QUERIES.keys())
    con.close()
    return {
        "version": "v1",
        "resources": sorted(regs.keys()),
        "queries": queries,
        "counts": counts,
        "auth": "Send X-API-Key header for write endpoints. Read endpoints are open.",
        "endpoints": {
            "discovery":     "GET  /api/v1/",
            "list_resources":"GET  /api/v1/resources",
            "get_resource":  "GET  /api/v1/resources/{name}",
            "create_table":  "POST /api/v1/tables (auth)",
            "add_column":    "POST /api/v1/tables/{name}/columns (auth)",
            "list_rows":     "GET  /api/v1/data/{resource}",
            "get_row":       "GET  /api/v1/data/{resource}/{id}",
            "bulk_upsert":   "POST /api/v1/data/{resource}/bulk (auth)",
            "patch_row":     "PATCH /api/v1/data/{resource}/{id} (auth)",
            "delete_row":    "DELETE /api/v1/data/{resource}/{id} (auth)",
            "list_queries":  "GET  /api/v1/queries",
            "run_query":     "GET  /api/v1/queries/{name}",
        },
    }


@router.get("/api/v1/resources")
def list_resources() -> dict:
    if use_pg_v1():
        with get_pg_con() as con, con.cursor() as cur:
            regs = pg_load_resources(cur)
            out = []
            for r in regs.values():
                try:
                    cols = pg_table_columns(cur, r.table)
                except Exception as e:
                    cols = [{"error": str(e)}]
                out.append({
                    "name": r.name, "table": r.table, "pk": r.pk,
                    "upsert_keys": r.upsert_keys, "json_cols": r.json_cols,
                    "fk_lookup": {k: list(v) for k, v in r.fk_lookup.items()},
                    "writable": r.writable, "is_dynamic": r.is_dynamic,
                    "description": r.description, "columns": cols,
                })
        return {"database_backend": "postgres", "total": len(out), "items": out}

    con = get_con()
    regs = load_resources(con)
    out = []
    for r in regs.values():
        try:
            cols = table_columns(con, r.table)
        except Exception as e:
            cols = [{"error": str(e)}]
        out.append({
            "name": r.name, "table": r.table, "pk": r.pk,
            "upsert_keys": r.upsert_keys, "json_cols": r.json_cols,
            "fk_lookup": {k: list(v) for k, v in r.fk_lookup.items()},
            "writable": r.writable, "is_dynamic": r.is_dynamic,
            "description": r.description, "columns": cols,
        })
    con.close()
    return {"total": len(out), "items": out}


@router.get("/api/v1/resources/{name}")
def get_resource_meta(name: str) -> dict:
    if use_pg_v1():
        with get_pg_con() as con, con.cursor() as cur:
            regs = pg_load_resources(cur)
            if name not in regs:
                raise HTTPException(404, "unknown resource")
            r = regs[name]
            cols = pg_table_columns(cur, r.table)
            sample_count = pg_count(cur, r.table)
        return {"name": r.name, "table": r.table, "pk": r.pk,
                "upsert_keys": r.upsert_keys, "json_cols": r.json_cols,
                "fk_lookup": {k: list(v) for k, v in r.fk_lookup.items()},
                "writable": r.writable, "is_dynamic": r.is_dynamic,
                "description": r.description, "columns": cols,
                "row_count": sample_count, "database_backend": "postgres"}

    con = get_con()
    regs = load_resources(con)
    if name not in regs:
        con.close()
        raise HTTPException(404, "unknown resource")
    r = regs[name]
    cols = table_columns(con, r.table)
    sample_count = con.execute(f"SELECT COUNT(*) FROM {r.table}").fetchone()[0]
    con.close()
    return {"name": r.name, "table": r.table, "pk": r.pk,
            "upsert_keys": r.upsert_keys, "json_cols": r.json_cols,
            "fk_lookup": {k: list(v) for k, v in r.fk_lookup.items()},
            "writable": r.writable, "is_dynamic": r.is_dynamic,
            "description": r.description, "columns": cols, "row_count": sample_count}


# ============================================================
# Schema mutation
# ============================================================
@router.post("/api/v1/tables")
async def create_table(payload: dict,
                       user: dict = Depends(require_admin)) -> dict:
    """Create a new SQL table and auto-register it as a resource.

    body: {
      "name": "ad_campaigns",
      "table": "ad_campaign",                  // optional, defaults to name
      "description": "GMV 广告投放跟踪",
      "columns": [
        {"name": "campaign_id", "type": "TEXT", "unique": true, "not_null": true},
        {"name": "creator_id",  "type": "INTEGER", "fk": "creator(id)"},
        {"name": "status",      "type": "TEXT", "default": "running"},
        {"name": "spend_usd",   "type": "REAL", "default": 0}
      ],
      "upsert_keys": ["campaign_id"],
      "json_cols": [],
      "fk_lookup": {"creator_handle": ["creator", ["handle"], "creator_id"]}
    }

    The system always prepends `id INTEGER PRIMARY KEY AUTOINCREMENT` and
    adds `created_at TEXT DEFAULT (datetime('now'))` if not given.
    """
    name = payload.get("name")
    if not name:
        raise HTTPException(400, "missing 'name'")
    try:
        safe_ident(name)
        table = payload.get("table") or name
        safe_ident(table)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if name.startswith("_") or table.startswith("_"):
        raise HTTPException(400, "names starting with _ are reserved")
    assert_can(user, "admin", name)
    if use_pg_v1():
        raise HTTPException(501, "PostgreSQL schema changes are applied by migrations, not this SQLite-era endpoint")

    cols_def = payload.get("columns") or []
    if not cols_def:
        raise HTTPException(400, "must define at least one column")

    parts = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
    seen_names = {"id"}
    has_created_at = False
    for col in cols_def:
        cname = col.get("name")
        ctype = (col.get("type") or "TEXT").upper()
        try:
            safe_ident(cname)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if ctype not in VALID_TYPES:
            raise HTTPException(400, f"invalid type '{ctype}' for column {cname} (allowed: {sorted(VALID_TYPES)})")
        if cname in seen_names:
            raise HTTPException(400, f"duplicate column '{cname}'")
        seen_names.add(cname)
        if cname == "created_at":
            has_created_at = True
        piece = f"{cname} {ctype}"
        if col.get("not_null"):
            piece += " NOT NULL"
        if col.get("unique"):
            piece += " UNIQUE"
        if "default" in col and col["default"] is not None:
            v = col["default"]
            # default values are reformatted — strings get quoted
            if isinstance(v, str):
                # allow SQL functions written as "datetime('now')" by detecting parens
                if "(" in v and ")" in v:
                    piece += f" DEFAULT ({v})"
                else:
                    piece += f" DEFAULT '{v.replace(chr(39), chr(39)*2)}'"
            else:
                piece += f" DEFAULT {v}"
        if "fk" in col and col["fk"]:
            # fk: "creator(id)" -> REFERENCES creator(id)
            fk_target = col["fk"]
            if not all(c.isalnum() or c in "_()" for c in fk_target):
                raise HTTPException(400, f"invalid fk: {fk_target}")
            piece += f" REFERENCES {fk_target}"
        parts.append(piece)
    if not has_created_at:
        parts.append("created_at TEXT DEFAULT (datetime('now'))")

    create_sql = f"CREATE TABLE IF NOT EXISTS {table} (\n  " + ",\n  ".join(parts) + "\n)"

    con = get_con()
    try:
        existing = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if existing:
            raise HTTPException(409, f"table '{table}' already exists")
        con.execute(create_sql)
        con.commit()
        # auto-register
        register_dynamic(
            con,
            name=name,
            table=table,
            upsert_keys=payload.get("upsert_keys") or [],
            json_cols=payload.get("json_cols") or [],
            fk_lookup=payload.get("fk_lookup") or {},
            description=payload.get("description") or "",
        )
    finally:
        con.close()
    # webhook 通知（大变动 → 附带完整 schema dump 链接）
    try:
        from app.notifier import emit
        col_names = [c.get("name") for c in cols_def]
        emit("schema.create_table",
             summary=f"新建表 `{table}` (resource slug: `{name}`)",
             details=[f"列: {', '.join(col_names)}"],
             actor=user.get("username"))
    except Exception:
        pass
    return {"ok": True, "name": name, "table": table, "create_sql": create_sql}


@router.post("/api/v1/tables/{name}/columns")
async def add_column(name: str, payload: dict,
                     user: dict = Depends(require_admin)) -> dict:
    assert_can(user, "admin", name)
    if use_pg_v1():
        raise HTTPException(501, "PostgreSQL schema changes are applied by migrations, not this SQLite-era endpoint")
    """Add a single column to an existing dynamic table.

    body: {"name": "click_through_rate", "type": "REAL", "default": 0}
    """
    r = get_resource(name)
    # v3.8.0: admin（张/廖）可对内置表加列。is_dynamic 锁解除，权限走 require_admin。
    cname = payload.get("name")
    try:
        safe_ident(cname)
    except ValueError as e:
        raise HTTPException(400, str(e))
    ctype = (payload.get("type") or "TEXT").upper()
    if ctype not in VALID_TYPES:
        raise HTTPException(400, f"invalid type {ctype}")
    piece = f"{cname} {ctype}"
    if "default" in payload and payload["default"] is not None:
        v = payload["default"]
        if isinstance(v, str):
            if "(" in v and ")" in v:
                piece += f" DEFAULT ({v})"
            else:
                piece += f" DEFAULT '{v.replace(chr(39), chr(39)*2)}'"
        else:
            piece += f" DEFAULT {v}"
    con = get_con()
    try:
        cols = get_columns_set(con, r.table)
        if cname in cols:
            raise HTTPException(409, f"column '{cname}' already exists")
        con.execute(f"ALTER TABLE {r.table} ADD COLUMN {piece}")
        con.commit()
    finally:
        con.close()
    try:
        from app.notifier import emit
        emit("schema.add_column",
             summary=f"`{r.table}` ADD COLUMN `{cname}` {ctype}",
             actor=user.get("username"))
    except Exception:
        pass
    return {"ok": True, "added_column": cname, "type": ctype}


@router.delete("/api/v1/tables/{name}")
async def drop_table(name: str, confirm: bool = False,
                     user: dict = Depends(require_admin)) -> dict:
    assert_can(user, "admin", name)
    """Drop a dynamic table + remove its registration. **Refuses built-in tables.**

    Required: ?confirm=true (defense against accidental clicks).
    """
    if not confirm:
        raise HTTPException(400, "must pass ?confirm=true to actually drop")
    if use_pg_v1():
        raise HTTPException(501, "PostgreSQL schema changes are applied by migrations, not this SQLite-era endpoint")
    r = get_resource(name)
    if not r.is_dynamic:
        raise HTTPException(403, f"resource '{name}' is built-in; cannot DROP via API. "
                                  f"Use migrate_v*.py + restart for built-in schema changes.")
    con = get_con()
    try:
        con.execute(f"DROP TABLE IF EXISTS {r.table}")
        con.execute("DELETE FROM _meta_resource WHERE name=?", (name,))
        con.commit()
    finally:
        con.close()
    try:
        from app.notifier import emit
        emit("schema.drop_table",
             summary=f"⚠️ DROP TABLE `{r.table}` (resource `{name}` 已注销)",
             actor=user.get("username"))
    except Exception:
        pass
    return {"ok": True, "dropped_table": r.table, "unregistered_resource": name}


@router.delete("/api/v1/tables/{name}/columns/{col}")
async def drop_column(name: str, col: str, confirm: bool = False,
                      user: dict = Depends(require_admin)) -> dict:
    assert_can(user, "admin", name)
    """Drop a single column from any table (built-in or dynamic).

    SQLite >= 3.35 required (we have 3.43+).
    Required: ?confirm=true.
    Cannot drop columns referenced by upsert_keys, json_cols, or fk_lookup of the resource.
    """
    if not confirm:
        raise HTTPException(400, "must pass ?confirm=true to actually drop")
    if use_pg_v1():
        raise HTTPException(501, "PostgreSQL schema changes are applied by migrations, not this SQLite-era endpoint")
    try:
        safe_ident(col)
    except ValueError as e:
        raise HTTPException(400, str(e))
    r = get_resource(name)
    if col in r.upsert_keys:
        raise HTTPException(409, f"column '{col}' is in upsert_keys for resource '{name}'; "
                                  "remove from upsert_keys first via PATCH /_meta_resource")
    if col in (r.json_cols or []):
        raise HTTPException(409, f"column '{col}' is in json_cols; remove from json_cols first")
    if r.fk_lookup and any(col == v[2] for v in r.fk_lookup.values()):
        raise HTTPException(409, f"column '{col}' is referenced by fk_lookup; clear it first")
    con = get_con()
    try:
        cols = get_columns_set(con, r.table)
        if col not in cols:
            raise HTTPException(404, f"column '{col}' does not exist on {r.table}")
        if col == r.pk:
            raise HTTPException(409, f"refusing to drop primary key column '{col}'")
        con.execute(f"ALTER TABLE {r.table} DROP COLUMN {col}")
        con.commit()
    finally:
        con.close()
    try:
        from app.notifier import emit
        emit("schema.drop_column",
             summary=f"⚠️ `{r.table}` DROP COLUMN `{col}`",
             actor=user.get("username"))
    except Exception:
        pass
    return {"ok": True, "dropped_column": col, "from_table": r.table}


# ============================================================
# Schema dump + webhook 测试
# ============================================================
@router.get("/api/v1/schema/dump")
def schema_dump_endpoint(format: str = "markdown",
                         user: dict = Depends(require_authenticated)) -> Any:
    """完整 schema dump (markdown 或 json)。webhook 大变动通知里的链接打开会到这里。"""
    from app.notifier import build_schema_dump_markdown
    if format == "json":
        if use_pg_v1():
            with get_pg_con() as con, con.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    """
                )
                tables = [row["table_name"] for row in cur.fetchall()]
                out = {}
                for t in tables:
                    out[t] = {
                        "row_count": pg_count(cur, t),
                        "columns": pg_table_columns(cur, t),
                    }
            return {"ts": datetime.now().isoformat(), "database_backend": "postgres", "tables": out}

        con = get_con()
        try:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )]
            out = {}
            for t in tables:
                cnt = con.execute(f"SELECT COUNT(*) FROM \"{t}\"").fetchone()[0]
                cols = [{"name": c[1], "type": c[2], "notnull": bool(c[3]),
                         "default": c[4], "pk": bool(c[5])}
                        for c in con.execute(f"PRAGMA table_info(\"{t}\")")]
                out[t] = {"row_count": cnt, "columns": cols}
            return {"ts": datetime.now().isoformat(), "tables": out}
        finally:
            con.close()
    md = build_schema_dump_markdown()
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8")


@router.post("/api/v1/webhooks/{webhook_id}/test")
async def test_webhook(webhook_id: int,
                       user: dict = Depends(require_admin)) -> dict:
    """admin 一键发条测试消息验证钉钉机器人配置。"""
    from app.notifier import emit
    emit("schema.test",
         summary="✅ 这是一条测试消息。如果你看到这条，说明钉钉 webhook 已就绪。",
         details=[f"订阅者 id: {webhook_id}", f"由 {user.get('username')} 触发"],
         actor=user.get("username"),
         full_dump=False)
    return {"ok": True, "fired_for_id": webhook_id, "note": "异步发送，几秒内到达；查看 webhook_subscriber.last_status"}


# ============================================================
# Generic CRUD
# ============================================================
@router.get("/api/v1/data/{resource}")
def list_rows(
    resource: str,
    request: Request,
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    q: str | None = None,
    order_by: str | None = None,
    desc: bool = False,
) -> dict:
    """List rows. Supports:
      - ?limit=&offset=
      - ?q=<text>                       — substring search on TEXT columns
      - ?<col>=<val>                    — equality filter on any column
      - ?<col>__gte / __lte / __gt / __lt = <val>   — range filters (P0)
      - ?<col>__in=a,b,c                — IN list (also accepts repeated ?<col>__in=a&<col>__in=b)
      - ?<col>__like=<sql_like>         — raw SQL LIKE (caller controls % wildcards)
      - ?<col>__icontains=<text>        — case-insensitive substring (auto-wraps %text%)
      - ?<col>__isnull=true|false       — IS NULL / IS NOT NULL
      - ?order_by=<col>&desc=true       — single sort (legacy)
      - ?order_by=col1:desc,col2:asc    — multi-key sort (v3.8.1)
    """
    if use_pg_v1():
        return pg_list_rows(resource, request, limit, offset, q, order_by, desc)

    r = get_resource(resource)
    con = get_con()
    try:
        cols = get_columns_set(con, r.table)
        where = ["1=1"]
        args: list[Any] = []
        # accumulate __in values (key may repeat)
        in_buckets: dict[str, list[str]] = {}
        OP_SUFFIXES = {"__gte": ">=", "__lte": "<=", "__gt": ">", "__lt": "<"}

        for k, v in request.query_params.multi_items():
            if k in {"limit", "offset", "q", "order_by", "desc"}:
                continue
            # advanced operators
            matched = False
            for suf, sql_op in OP_SUFFIXES.items():
                if k.endswith(suf):
                    col = k[:-len(suf)]
                    if col in cols:
                        where.append(f"{col} {sql_op} ?")
                        args.append(v)
                    matched = True
                    break
            if matched:
                continue
            if k.endswith("__in"):
                col = k[:-4]
                if col in cols:
                    in_buckets.setdefault(col, []).extend(s for s in v.split(",") if s != "")
                continue
            if k.endswith("__like"):
                col = k[:-6]
                if col in cols:
                    where.append(f"{col} LIKE ?")
                    args.append(v)
                continue
            if k.endswith("__icontains"):
                col = k[:-11]
                if col in cols:
                    # SQLite LIKE is case-insensitive for ASCII by default
                    where.append(f"{col} LIKE ?")
                    args.append(f"%{v}%")
                continue
            if k.endswith("__isnull"):
                col = k[:-8]
                if col in cols:
                    if v.lower() in ("true", "1", "yes"):
                        where.append(f"{col} IS NULL")
                    else:
                        where.append(f"{col} IS NOT NULL")
                continue
            # equality (legacy)
            if k not in cols:
                continue
            where.append(f"{k} = ?")
            args.append(v)

        for col, vals in in_buckets.items():
            if not vals:
                continue
            placeholders = ",".join(["?"] * len(vals))
            where.append(f"{col} IN ({placeholders})")
            args.extend(vals)

        if q:
            text_cols = [c["name"] for c in table_columns(con, r.table) if "TEXT" in (c["type"] or "").upper()]
            if text_cols:
                where.append("(" + " OR ".join([f"{c} LIKE ?" for c in text_cols]) + ")")
                args.extend([f"%{q}%"] * len(text_cols))

        # multi-key order_by: "col1:desc,col2:asc" or legacy single col + desc=true
        order = ""
        if order_by:
            if "," in order_by or ":" in order_by:
                pieces = []
                for part in order_by.split(","):
                    part = part.strip()
                    if ":" in part:
                        c, d = part.split(":", 1)
                        c = c.strip(); d = d.strip().lower()
                    else:
                        c, d = part, "asc"
                    if c in cols and d in ("asc", "desc"):
                        pieces.append(f"{c} {d.upper()}")
                if pieces:
                    order = "ORDER BY " + ", ".join(pieces)
            elif order_by in cols:
                order = f"ORDER BY {order_by} {'DESC' if desc else 'ASC'}"
        sql = f"SELECT * FROM {r.table} WHERE {' AND '.join(where)} {order} LIMIT ? OFFSET ?"
        rows = [decode_row(row, r.json_cols) for row in con.execute(sql, args + [limit, offset])]
        total = con.execute(f"SELECT COUNT(*) FROM {r.table} WHERE {' AND '.join(where)}", args).fetchone()[0]
    finally:
        con.close()
    return {"resource": resource, "total": total, "limit": limit, "offset": offset, "items": rows}


@router.get("/api/v1/data/{resource}/{row_id}")
def get_row(resource: str, row_id: str) -> dict:
    if use_pg_v1():
        return pg_get_row(resource, row_id)

    r = get_resource(resource)
    con = get_con()
    try:
        row = con.execute(f"SELECT * FROM {r.table} WHERE {r.pk} = ?", (row_id,)).fetchone()
    finally:
        con.close()
    if not row:
        raise HTTPException(404, f"{resource}#{row_id} not found")
    return decode_row(row, r.json_cols)


@router.post("/api/v1/data/{resource}/bulk")
async def bulk_upsert(resource: str, payload: dict,
                      user: dict = Depends(require_user_or_above)) -> dict:
    """Batch upsert. Dedup by `upsert_keys` defined on the resource.
    body: {"items": [{...}, {...}]}"""
    assert_can(user, "write", resource)
    if use_pg_v1():
        return pg_bulk_upsert(resource, payload)

    r = get_resource(resource)
    if not r.writable:
        raise HTTPException(403, f"resource '{resource}' is read-only")
    items = payload.get("items") or []
    if not isinstance(items, list):
        raise HTTPException(400, "items must be a list")

    con = get_con()
    try:
        cols = get_columns_set(con, r.table)
        inserted = updated = 0
        errors: list[dict] = []
        for idx, raw in enumerate(items):
            try:
                # 1. resolve foreign-key lookups
                resolved, fk_errors = resolve_fk(con, dict(raw), r.fk_lookup)
                if fk_errors:
                    errors.append({"idx": idx, "fk_errors": fk_errors})
                    continue
                # 2. apply auto-compute
                for col, fn in r.auto_compute.items():
                    if col in cols and col not in resolved:
                        v = fn(resolved)
                        if v is not None:
                            resolved[col] = v
                # 3. drop unknown columns silently (keeps API forward-compatible)
                fields = {k: v for k, v in resolved.items() if k in cols}
                if not fields:
                    errors.append({"idx": idx, "error": "no recognized columns"})
                    continue
                fields = encode_for_db(fields, r.json_cols)

                # 4. determine if exists (using upsert_keys)
                if r.upsert_keys and all(k in fields for k in r.upsert_keys):
                    where = " AND ".join([f"{k}=?" for k in r.upsert_keys])
                    pre = con.execute(f"SELECT {r.pk} FROM {r.table} WHERE {where} LIMIT 1",
                                      [fields[k] for k in r.upsert_keys]).fetchone()
                    if pre:
                        # UPDATE existing
                        sets = ",".join([f"{k}=?" for k in fields if k not in r.upsert_keys])
                        if sets:
                            con.execute(
                                f"UPDATE {r.table} SET {sets} WHERE {r.pk}=?",
                                [fields[k] for k in fields if k not in r.upsert_keys] + [pre[0]],
                            )
                        updated += 1
                        continue
                # 5. INSERT new row
                cs = list(fields.keys())
                placeholders = ",".join(["?"] * len(cs))
                con.execute(f"INSERT INTO {r.table}({','.join(cs)}) VALUES({placeholders})",
                            [fields[k] for k in cs])
                inserted += 1
            except Exception as e:
                errors.append({"idx": idx, "error": str(e)})
        con.commit()
    finally:
        con.close()
    return {"resource": resource, "inserted": inserted, "updated": updated,
            "skipped": len(items) - inserted - updated, "errors": errors}


@router.patch("/api/v1/data/{resource}/{row_id}")
async def patch_row(resource: str, row_id: str, payload: dict,
                    user: dict = Depends(require_user_or_above)) -> dict:
    assert_can(user, "write", resource)
    if use_pg_v1():
        return pg_patch_row(resource, row_id, payload)

    r = get_resource(resource)
    if not r.writable:
        raise HTTPException(403, f"resource '{resource}' is read-only")
    con = get_con()
    try:
        cols = get_columns_set(con, r.table)
        # FK resolution (rare for PATCH but allowed)
        resolved, fk_errors = resolve_fk(con, dict(payload), r.fk_lookup)
        if fk_errors:
            raise HTTPException(400, {"fk_errors": fk_errors})
        # auto-compute (e.g. tier when followers changes)
        for col, fn in r.auto_compute.items():
            if col in cols and col not in resolved:
                v = fn(resolved)
                if v is not None:
                    resolved[col] = v
        fields = {k: v for k, v in resolved.items() if k in cols and k != r.pk}
        if not fields:
            raise HTTPException(400, "no editable fields in payload")
        fields = encode_for_db(fields, r.json_cols)
        existing = con.execute(f"SELECT {r.pk} FROM {r.table} WHERE {r.pk}=?", (row_id,)).fetchone()
        if not existing:
            raise HTTPException(404, f"{resource}#{row_id} not found")
        sets = ",".join([f"{k}=?" for k in fields])
        con.execute(f"UPDATE {r.table} SET {sets} WHERE {r.pk}=?",
                    list(fields.values()) + [row_id])
        con.commit()
    finally:
        con.close()
    return {"ok": True, "updated_fields": list(fields.keys())}


@router.delete("/api/v1/data/{resource}/{row_id}")
async def delete_row(resource: str, row_id: str,
                     user: dict = Depends(require_admin)) -> dict:
    assert_can(user, "admin", resource)
    if use_pg_v1():
        return pg_delete_row(resource, row_id)

    r = get_resource(resource)
    if not r.writable:
        raise HTTPException(403, f"resource '{resource}' is read-only")
    con = get_con()
    try:
        existing = con.execute(f"SELECT {r.pk} FROM {r.table} WHERE {r.pk}=?", (row_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "row not found")
        con.execute(f"DELETE FROM {r.table} WHERE {r.pk}=?", (row_id,))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "deleted": {r.pk: row_id}}


# ============================================================
# Named queries — backed by _meta_query table (hot-editable, no restart)
# ============================================================
import re as _re
_QUERY_HEAD_RE = _re.compile(r"^\s*(?:--[^\n]*\n)*\s*(WITH|SELECT)\b", _re.IGNORECASE)


def _validate_query_sql(sql: str) -> None:
    if not sql or not sql.strip():
        raise HTTPException(400, "sql is required")
    if not _QUERY_HEAD_RE.match(sql):
        raise HTTPException(400, "only SELECT or WITH (CTE) statements are allowed")
    body = sql.rstrip().rstrip(";").rstrip()
    if ";" in body:
        raise HTTPException(400, "multi-statement SQL is not allowed (no ; in body)")


def _load_query_from_db(name: str, con: sqlite3.Connection) -> dict | None:
    row = con.execute(
        "SELECT name, description, sql, params, is_builtin FROM _meta_query WHERE name=?",
        (name,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["params"] = json.loads(d["params"]) if d.get("params") else []
    except json.JSONDecodeError:
        d["params"] = []
    return d


_PG_NAMED_PARAM_RE = _re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


def _pg_sql_placeholders(sql: str) -> str:
    if "%(" in sql:
        return sql
    return _PG_NAMED_PARAM_RE.sub(r"%(\1)s", sql)


def _parse_query_params(value: Any) -> list:
    parsed = _json_or(value, [])
    return parsed if isinstance(parsed, list) else []


def _load_query_from_pg(name: str, cur) -> dict | None:
    cur.execute(
        "SELECT name, description, sql, params, is_builtin FROM _meta_query WHERE name = %s",
        (name,),
    )
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["params"] = _parse_query_params(d.get("params"))
    return d


def _bind_named_query_params(q: dict, request: Request) -> dict[str, Any]:
    bind: dict[str, Any] = {}
    qp = request.query_params
    for p in q["params"]:
        pname, ptype, pdefault = p[0], p[1], p[2]
        raw = qp.get(pname)
        if raw is None or raw == "":
            bind[pname] = pdefault
            continue
        try:
            bind[pname] = {"int": int, "str": str, "float": float}[ptype](raw)
        except (ValueError, KeyError):
            raise HTTPException(400, f"param {pname!r} expects {ptype}")
    return bind


def _named_query_page(request: Request) -> tuple[int | None, int]:
    raw_limit = request.query_params.get("limit")
    if raw_limit is None or raw_limit == "":
        return None, 0
    try:
        limit = int(raw_limit)
        offset = int(request.query_params.get("offset") or 0)
    except ValueError:
        raise HTTPException(400, "limit and offset must be integers")
    if limit < 1 or limit > 1000:
        raise HTTPException(400, "limit must be between 1 and 1000")
    if offset < 0:
        raise HTTPException(400, "offset must be >= 0")
    return limit, offset


def _named_query_sql(sql: str) -> str:
    return sql.strip().rstrip(";")


@router.get("/api/v1/queries")
def list_queries() -> dict:
    if use_pg_v1():
        with get_pg_con() as con, con.cursor() as cur:
            cur.execute(
                "SELECT name, description, sql, params, is_builtin FROM _meta_query "
                "ORDER BY is_builtin DESC, name"
            )
            rows = cur.fetchall()
        out = []
        for r in rows:
            params = _parse_query_params(r.get("params"))
            out.append({
                "name": r["name"], "description": r["description"],
                "is_builtin": _truthy(r["is_builtin"]),
                "params": [{"name": p[0], "type": p[1], "default": p[2]} for p in params],
                "url": f"/api/v1/queries/{r['name']}",
            })
        return {"database_backend": "postgres", "items": out}

    con = get_con()
    try:
        rows = [dict(r) for r in con.execute(
            "SELECT name, description, sql, params, is_builtin FROM _meta_query "
            "ORDER BY is_builtin DESC, name")]
    finally:
        con.close()
    out = []
    for r in rows:
        try:
            params = json.loads(r["params"]) if r.get("params") else []
        except json.JSONDecodeError:
            params = []
        out.append({
            "name": r["name"], "description": r["description"],
            "is_builtin": bool(r["is_builtin"]),
            "params": [{"name": p[0], "type": p[1], "default": p[2]} for p in params],
            "url": f"/api/v1/queries/{r['name']}",
        })
    return {"items": out}


@router.get("/api/v1/queries/{name}")
def run_query(name: str, request: Request) -> dict:
    if use_pg_v1():
        with get_pg_con() as con, con.cursor() as cur:
            q = _load_query_from_pg(name, cur)
            if not q:
                raise HTTPException(404, f"unknown query '{name}' (try GET /api/v1/queries)")
            bind = _bind_named_query_params(q, request)
            limit, offset = _named_query_page(request)
            sql = _pg_sql_placeholders(_named_query_sql(q["sql"]))
            if limit is not None:
                cur.execute(f"SELECT COUNT(*) AS count FROM ({sql}) AS named_query_count", bind)
                total = int(cur.fetchone()["count"])
                page_bind = {**bind, "__limit": limit, "__offset": offset}
                cur.execute(
                    f"SELECT * FROM ({sql}) AS named_query_page LIMIT %(__limit)s OFFSET %(__offset)s",
                    page_bind,
                )
            else:
                cur.execute(sql, bind)
                total = None
            rows = [dict(r) for r in cur.fetchall()]
        return {"query": name, "params": bind, "total": total if total is not None else len(rows), "items": rows,
                "database_backend": "postgres"}

    con = get_con()
    try:
        q = _load_query_from_db(name, con)
        if not q:
            raise HTTPException(404, f"unknown query '{name}' (try GET /api/v1/queries)")
        bind: dict[str, Any] = {}
        qp = request.query_params
        for p in q["params"]:
            pname, ptype, pdefault = p[0], p[1], p[2]
            raw = qp.get(pname)
            if raw is None or raw == "":
                bind[pname] = pdefault
                continue
            try:
                bind[pname] = {"int": int, "str": str, "float": float}[ptype](raw)
            except (ValueError, KeyError):
                raise HTTPException(400, f"param {pname!r} expects {ptype}")
        limit, offset = _named_query_page(request)
        sql = _named_query_sql(q["sql"])
        if limit is not None:
            total = con.execute(f"SELECT COUNT(*) FROM ({sql}) AS named_query_count", bind).fetchone()[0]
            page_bind = {**bind, "__limit": limit, "__offset": offset}
            rows = [
                dict(r)
                for r in con.execute(
                    f"SELECT * FROM ({sql}) AS named_query_page LIMIT :__limit OFFSET :__offset",
                    page_bind,
                )
            ]
        else:
            rows = [dict(r) for r in con.execute(sql, bind)]
            total = len(rows)
    finally:
        con.close()
    return {"query": name, "params": bind, "total": total, "items": rows}


@router.post("/api/v1/queries", dependencies=[Depends(require_user_or_above)])
async def create_query(payload: dict) -> dict:
    """Add or override a named query without restarting.

    body: {
      "name": "creators_with_video_recent",
      "description": "拿到一周内有发视频的达人",
      "sql": "SELECT c.handle FROM creator c JOIN outreach o ON ... WHERE ... AND o.event_date > date('now','-7 days')",
      "params": [["limit","int",100]]
    }
    """
    name = payload.get("name")
    sql = payload.get("sql")
    if not name or not sql:
        raise HTTPException(400, "name and sql are required")
    if not all(c.isalnum() or c == "_" for c in name):
        raise HTTPException(400, "name must be alphanumeric or _")
    _validate_query_sql(sql)
    params = payload.get("params") or []
    if not isinstance(params, list):
        raise HTTPException(400, "params must be a list of [name,type,default]")
    if use_pg_v1():
        with get_pg_con() as con, con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO _meta_query(name,description,sql,params,is_builtin,updated_at)
                VALUES(%s,%s,%s,%s,0,CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                  description = EXCLUDED.description,
                  sql = EXCLUDED.sql,
                  params = EXCLUDED.params,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (name, payload.get("description", ""), sql, json.dumps(params, ensure_ascii=False)),
            )
            con.commit()
        return {"ok": True, "name": name, "database_backend": "postgres"}

    con = get_con()
    try:
        existing = con.execute(
            "SELECT is_builtin FROM _meta_query WHERE name=?", (name,)).fetchone()
        if existing and existing["is_builtin"]:
            # 张 wants to override a builtin — keep it builtin so the original code
            # version stays (it was used during seed) but allow updates here.
            pass
        con.execute(
            "INSERT INTO _meta_query(name,description,sql,params,is_builtin,updated_at) "
            "VALUES(?,?,?,?,0,datetime('now')) "
            "ON CONFLICT(name) DO UPDATE SET description=excluded.description, "
            "sql=excluded.sql, params=excluded.params, updated_at=datetime('now')",
            (name, payload.get("description", ""), sql, json.dumps(params))
        )
        con.commit()
    finally:
        con.close()
    return {"ok": True, "name": name}


@router.put("/api/v1/queries/{name}", dependencies=[Depends(require_user_or_above)])
async def update_query(name: str, payload: dict) -> dict:
    if "sql" in payload:
        _validate_query_sql(payload["sql"])
    fields: dict[str, Any] = {}
    if "description" in payload: fields["description"] = payload["description"]
    if "sql" in payload: fields["sql"] = payload["sql"]
    if "params" in payload:
        if not isinstance(payload["params"], list):
            raise HTTPException(400, "params must be a list")
        fields["params"] = json.dumps(payload["params"])
    if not fields:
        raise HTTPException(400, "no editable fields in payload")
    fields["updated_at"] = "datetime('now')"   # placeholder, replaced below
    if use_pg_v1():
        with get_pg_con() as con, con.cursor() as cur:
            cur.execute("SELECT 1 FROM _meta_query WHERE name = %s", (name,))
            if not cur.fetchone():
                raise HTTPException(404, f"query '{name}' not found")
            set_keys = [k for k in fields if k != "updated_at"]
            sets = ", ".join([f"{k} = %s" for k in set_keys])
            if sets:
                sets += ", updated_at = CURRENT_TIMESTAMP"
            else:
                sets = "updated_at = CURRENT_TIMESTAMP"
            args = [fields[k] for k in set_keys] + [name]
            cur.execute(f"UPDATE _meta_query SET {sets} WHERE name = %s", args)
            con.commit()
        return {"ok": True, "name": name, "updated_fields": list(fields.keys()),
                "database_backend": "postgres"}

    con = get_con()
    try:
        if not con.execute("SELECT 1 FROM _meta_query WHERE name=?", (name,)).fetchone():
            raise HTTPException(404, f"query '{name}' not found")
        sets = ", ".join([f"{k}=?" for k in fields if k != "updated_at"]) + ", updated_at=datetime('now')"
        args = [v for k, v in fields.items() if k != "updated_at"] + [name]
        con.execute(f"UPDATE _meta_query SET {sets} WHERE name=?", args)
        con.commit()
    finally:
        con.close()
    return {"ok": True, "name": name, "updated_fields": list(fields.keys())}


@router.delete("/api/v1/queries/{name}", dependencies=[Depends(require_admin)])
async def delete_query(name: str) -> dict:
    if use_pg_v1():
        with get_pg_con() as con, con.cursor() as cur:
            cur.execute("SELECT is_builtin FROM _meta_query WHERE name = %s", (name,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, f"query '{name}' not found")
            if _truthy(row["is_builtin"]):
                raise HTTPException(403, "cannot delete a builtin query (override via PUT instead)")
            cur.execute("DELETE FROM _meta_query WHERE name = %s", (name,))
            con.commit()
        return {"ok": True, "deleted": name, "database_backend": "postgres"}

    con = get_con()
    try:
        row = con.execute("SELECT is_builtin FROM _meta_query WHERE name=?", (name,)).fetchone()
        if not row:
            raise HTTPException(404, f"query '{name}' not found")
        if row["is_builtin"]:
            raise HTTPException(403, "cannot delete a builtin query (override via PUT instead)")
        con.execute("DELETE FROM _meta_query WHERE name=?", (name,))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "deleted": name}
