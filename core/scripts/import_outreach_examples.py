"""Import historical outreach scripts from 跨境运营日SOP流程及目标.xlsx into outreach_example.

Three sheets parsed:
  邀约话术              -> tiktok_dm / feminine
  邀约话术-独立站       -> tiktok_dm / feminine (independent site flow)
  邀约or引流独立站话术  -> tiktok_dm / feminine (alt flow)

Each row pattern in xlsx:
  col[0] = "1 吴鑫然" (number + author)
  col[1] = full body text (multi-line)

Idempotent: matches by (template_key, author).
"""
from __future__ import annotations
import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"
SOURCE_XLSX = Path(r"F:\实习生\C达人建联\跨境运营日SOP流程及目标.xlsx")

SHEETS = [
    # (sheet_name, template_prefix, notes)
    ("邀约话术", "feminine.tiktok_dm.bd", "BD 手写邀约话术（直接挂车）"),
    ("邀约话术-独立站", "feminine.tiktok_dm.indep_site", "邀约 + 引流独立站合作话术"),
    ("邀约or引流独立站话术", "feminine.tiktok_dm.alt", "邀约 / 引流独立站 — 备选话术"),
]

AUTHOR_RE = re.compile(r"^\s*(\d+)\s*[. ]?\s*(\S+)\s*$")


def parse_sheet(sheet_name: str) -> list[dict]:
    df = pd.read_excel(SOURCE_XLSX, sheet_name=sheet_name, header=None).fillna("")
    out = []
    for _, row in df.iterrows():
        cells = [str(x).strip() for x in row.tolist()]
        if len(cells) < 2:
            continue
        head, body = cells[0], cells[1]
        if not head or not body:
            continue
        m = AUTHOR_RE.match(head)
        if not m:
            continue
        seq, author = m.group(1), m.group(2)
        if len(body) < 30:
            continue
        out.append({
            "seq": int(seq),
            "author": author,
            "body": body.strip(),
        })
    return out


def upsert(con: sqlite3.Connection, *, template_key: str, author: str,
           channel: str, language: str, category_scope: str,
           subject: str | None, body: str, notes: str) -> bool:
    existing = con.execute(
        "SELECT id FROM outreach_example WHERE template_key=? AND author=?",
        (template_key, author)
    ).fetchone()
    if existing:
        return False
    con.execute(
        "INSERT INTO outreach_example(template_key, author, channel, language, "
        "category_scope, subject, body, quality_rating, notes) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (template_key, author, channel, language, category_scope,
         subject, body, None, notes)
    )
    return True


def main() -> None:
    if not SOURCE_XLSX.exists():
        print(f"[import] WARN: source not found {SOURCE_XLSX}")
        return
    con = sqlite3.connect(DB_PATH)

    n_added = 0
    n_skipped = 0
    for sheet_name, prefix, notes in SHEETS:
        try:
            entries = parse_sheet(sheet_name)
        except Exception as e:
            print(f"[import] WARN: sheet {sheet_name!r} read error: {e}")
            continue
        for e in entries:
            template_key = f"{prefix}.{e['seq']:02d}_{_slug(e['author'])}"
            ok = upsert(
                con,
                template_key=template_key,
                author=e["author"],
                channel="tiktok_dm",
                language="en",
                category_scope="female_care",   # 全部偏向女性护理（实际看了内容确认）
                subject=None,
                body=e["body"],
                notes=f"sheet: {sheet_name} - {notes}",
            )
            if ok:
                n_added += 1
            else:
                n_skipped += 1

    con.commit()
    n_total = con.execute("SELECT COUNT(*) FROM outreach_example").fetchone()[0]
    print(f"[import_outreach_examples] +{n_added} new, {n_skipped} already exist")
    by_scope = con.execute(
        "SELECT category_scope, channel, COUNT(*) FROM outreach_example "
        "GROUP BY category_scope, channel ORDER BY 1, 2"
    ).fetchall()
    print(f"[import_outreach_examples] total={n_total}, breakdown:")
    for scope, ch, cnt in by_scope:
        print(f"   {scope:14s} {ch:14s} {cnt}")
    con.close()


def _slug(s: str) -> str:
    return re.sub(r"[^\w]", "", s)[:30]


if __name__ == "__main__":
    main()
