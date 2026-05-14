"""Schema 变更广播 → 钉钉群机器人 / 通用 HTTP webhook。

设计：
  - emit(event, summary, details=None, full_dump=False)
  - 异步线程发，不阻塞调用方；失败只记日志不抛
  - 钉钉支持加签 (HMAC-SHA256) 或关键词模式
  - "大变动" (full_dump=True) 时附加完整 schema dump 链接

事件命名: schema.add_column / schema.drop_column / schema.create_table / schema.drop_table
         query.upsert / config.update
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import sqlite3
import threading
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"
DUMP_PATH_HINT = "/api/v1/schema/dump"

# 大变动事件（默认带完整 schema dump 链接）
MAJOR_EVENTS = {"schema.create_table", "schema.drop_table"}


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _dingtalk_sign(secret: str) -> tuple[str, str]:
    """钉钉加签模式: 返回 (timestamp, sign)"""
    ts = str(round(time.time() * 1000))
    string_to_sign = f"{ts}\n{secret}"
    h = hmac.new(secret.encode("utf-8"),
                 string_to_sign.encode("utf-8"),
                 digestmod=hashlib.sha256)
    sign = urllib.parse.quote_plus(base64.b64encode(h.digest()))
    return ts, sign


def _build_dingtalk_payload(*, title: str, text_md: str, keyword: str | None) -> dict:
    """钉钉 markdown 消息。如果配了关键词，确保正文出现"""
    if keyword and keyword not in text_md and keyword not in title:
        title = f"[{keyword}] {title}"
    return {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text_md},
        "at": {"isAtAll": False},
    }


def _post(sub: dict, payload: dict) -> tuple[bool, str]:
    """发送 webhook。返回 (success, message)。"""
    url = sub["url"]
    if sub["kind"] == "dingtalk" and sub.get("secret"):
        ts, sign = _dingtalk_sign(sub["secret"])
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}timestamp={ts}&sign={sign}"
    try:
        r = requests.post(url, json=payload, timeout=8)
        ok = (200 <= r.status_code < 300)
        # 钉钉返回 errcode=0 才算成功
        try:
            body = r.json()
            if isinstance(body, dict) and body.get("errcode", 0) != 0:
                return False, f"errcode={body.get('errcode')}: {body.get('errmsg')}"
        except Exception:
            pass
        return ok, f"HTTP {r.status_code}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _record_status(sub_id: int, success: bool, message: str) -> None:
    try:
        con = _con()
        con.execute(
            "UPDATE webhook_subscriber SET last_fired_at=datetime('now'), "
            "last_status=?, last_error=? WHERE id=?",
            ("ok" if success else "fail", None if success else message, sub_id)
        )
        con.commit()
        con.close()
    except Exception:
        pass


def _list_subscribers(event: str) -> list[dict]:
    con = _con()
    try:
        rows = con.execute(
            "SELECT id, name, kind, url, secret, keyword, events FROM webhook_subscriber "
            "WHERE active=1"
        ).fetchall()
    finally:
        con.close()
    out = []
    for r in rows:
        d = dict(r)
        # events filter (None / [] / null = 全收)
        try:
            evs = json.loads(d["events"] or "null")
        except Exception:
            evs = None
        if evs and event not in evs:
            continue
        out.append(d)
    return out


def _format_markdown(*, event: str, summary: str, details: list[str] | None,
                     full_dump_url: str | None, actor: str | None) -> tuple[str, str]:
    """返回 (title, markdown)"""
    title = f"X9 数据库变更: {event}"
    lines = [
        f"### 🗄️ X9 数据库变更",
        f"**事件**: `{event}`  ",
        f"**摘要**: {summary}  ",
        f"**操作人**: {actor or 'system'}  ",
        f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
    ]
    if details:
        lines.append("")
        lines.append("**详情**:")
        for d in details:
            lines.append(f"- {d}")
    if full_dump_url:
        lines.append("")
        lines.append(f"📋 **完整数据库结构**: [{full_dump_url}]({full_dump_url})")
    lines.append("")
    lines.append("> 廖那边: API 是契约，加字段/表不破坏现有代码；如对你有影响，请及时反馈。")
    return title, "\n".join(lines)


def emit(event: str, summary: str, *,
         details: list[str] | None = None,
         actor: str | None = None,
         full_dump: bool | None = None,
         host_hint: str | None = None) -> None:
    """主入口。fire-and-forget。"""
    subs = _list_subscribers(event)
    if not subs:
        return
    is_major = full_dump if full_dump is not None else (event in MAJOR_EVENTS)
    dump_url = None
    if is_major:
        # 廖打开链接需要带 admin key，这里只给路径相对地址作为提示
        prefix = host_hint or ""
        dump_url = f"{prefix}{DUMP_PATH_HINT}"

    title, md = _format_markdown(
        event=event, summary=summary, details=details,
        full_dump_url=dump_url, actor=actor,
    )

    def _worker():
        for sub in subs:
            if sub["kind"] == "dingtalk":
                payload = _build_dingtalk_payload(
                    title=title, text_md=md, keyword=sub.get("keyword"),
                )
            else:  # generic http
                payload = {
                    "event": event, "summary": summary,
                    "details": details or [], "actor": actor,
                    "ts": datetime.now().isoformat(),
                    "full_dump_url": dump_url,
                }
            ok, msg = _post(sub, payload)
            _record_status(sub["id"], ok, msg)

    threading.Thread(target=_worker, daemon=True).start()


# ============================================================
# 完整 schema dump (markdown)
# ============================================================
def build_schema_dump_markdown() -> str:
    con = _con()
    try:
        # 拉所有用户表
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        lines = [
            f"# X9 Database Schema Dump",
            f"_生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
            "",
            f"共 {len(tables)} 张表。",
            "",
        ]
        for t in tables:
            cnt = con.execute(f"SELECT COUNT(*) FROM \"{t}\"").fetchone()[0]
            lines.append(f"## `{t}`  ({cnt} 行)")
            lines.append("")
            lines.append("| 列名 | 类型 | 非空 | 默认值 | PK |")
            lines.append("|---|---|---|---|---|")
            for c in con.execute(f"PRAGMA table_info(\"{t}\")"):
                cid, name, ctype, notnull, dflt, pk = c
                lines.append(f"| `{name}` | {ctype} | {'✓' if notnull else ''} | "
                             f"{dflt or ''} | {'✓' if pk else ''} |")
            lines.append("")
        # 命名查询
        try:
            qs = con.execute(
                "SELECT name, description, sql FROM _meta_query ORDER BY name"
            ).fetchall()
            if qs:
                lines.append("---")
                lines.append("# 命名查询 (`_meta_query`)")
                lines.append("")
                for q in qs:
                    lines.append(f"### `{q['name']}`")
                    lines.append(f"_{q['description'] or ''}_")
                    lines.append("```sql")
                    lines.append(q["sql"])
                    lines.append("```")
                    lines.append("")
        except Exception:
            pass
        return "\n".join(lines)
    finally:
        con.close()
