"""Import creators + outreach events from the weekly statistics workbooks
and the Creator Marketplace evaluation table.

Sources:
  C达人建联/达人建联每周统计表.xlsx          (12 rows)
  C达人建联/达人建联每周统计表(3).xlsx       (131 rows, most comprehensive)
  C达人建联/达人建联每周统计表(4).xlsx       (31 rows)
  C达人建联/TikTok Shop Creator Marketplace 达人申样筛选评估表.xlsx
  C达人建联/3月份达人建联统计表.xlsx          (BD staff totals -> staff table)

Each weekly table is a forward-fill style sheet:
  店铺名 | 负责人 | 日期 | 建联达人数 | 寄样达人 handle | 佣金 | 寄样数量 |
  寄样产品 | 是否提供视频 | 链接 | 授权码 | 备注

When the leading store/bd/date cells are blank, they inherit from the previous row.

Re-runnable (idempotent):
  - creators upsert on (platform, handle)
  - outreach inserts ONLY if a same-day same-handle same-status row doesn't exist
"""
from __future__ import annotations
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"
INTERN_C = Path(r"F:\实习生\C达人建联")

WEEKLY_FILES = [
    INTERN_C / "达人建联每周统计表.xlsx",
    INTERN_C / "达人建联每周统计表(3).xlsx",
    INTERN_C / "达人建联每周统计表(4).xlsx",
]
CM_FILE = INTERN_C / "TikTok Shop Creator Marketplace 达人申样筛选评估表.xlsx"
MARCH_FILE = INTERN_C / "3月份达人建联统计表.xlsx"

# ============================================================
# Helpers
# ============================================================
def parse_followers(raw: str) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip().upper().replace(",", "")
    if not s:
        return None
    m = re.match(r"([\d.]+)\s*([KMB]?)", s)
    if not m:
        return None
    val = float(m.group(1))
    suffix = m.group(2)
    mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suffix, 1)
    return int(val * mult)


def tier_for(followers: int | None) -> str | None:
    if followers is None:
        return None
    if followers >= 1_000_000:
        return "S"
    if followers >= 300_000:
        return "A"
    if followers >= 100_000:
        return "B"
    if followers >= 10_000:
        return "C"
    return "D"


def clean_handle(raw: str) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in {"nan", "none"}:
        return None
    # take first line if multi-line (e.g. "@tiffkidd30\nTiffany")
    s = s.split("\n")[0].strip()
    s = s.lstrip("@").strip()
    s = re.sub(r"\s+", "", s)
    if not s or len(s) < 2:
        return None
    if "..." in s:
        return None
    return s


def parse_date(raw: str, default_year: int = 2026) -> str | None:
    if not raw:
        return None
    s = str(raw).strip()
    if not s or s.lower() in {"nan", "none"}:
        return None
    # "Feb 9-Feb 12" -> first part
    s = re.split(r"[-–—~至到]", s)[0].strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d", "%B %d", "%b %d %Y", "%Y/%m/%d"):
        try:
            d = datetime.strptime(s, fmt)
            if d.year < 2020:
                d = d.replace(year=default_year)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def parse_commission(raw) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        v = float(raw)
        if v > 1:  # someone wrote "5" for 5%
            v = v / 100
        return round(v, 4)
    except (ValueError, TypeError):
        return None


# Product name -> representative SKU code (best-effort match)
SAMPLE_NAME_TO_SKU = [
    (r"period\s*underwear", "BU06PML1"),
    (r"cotton\s*cover\s*panty\s*liner", "BU02P155"),
    (r"cotton\s*cover\s*pads", "BU01R240"),
    (r"cotton[\s-]*based\s*pads", "BU01R240"),
    (r"ultra\s*thin\s*pads", "BU04R245"),
    (r"micro\s*panty\s*liners?", "BU02P155"),
    (r"bladder\s*control\s*pads", "CU05W185"),
    (r"women.*incontinence", "CU05W185"),
    (r"men.*pads", "CU05W185"),
    (r"postpartum\s*pads", "CU07M445"),
    (r"adult\s*diaper\s*with\s*tabs", "CU01M001B1"),
    (r"protective\s*underwear|disposable\s*briefs", "CU02M001B1"),
    (r"baby\s*diapers?|ultra\s*thin\s*baby", "AU01M003A1"),
    (r"nursing\s*pads", "DU03B115"),
    (r"male\s*wraps?", "EU05DDXS"),
    (r"pet\s*diapers?\s*\(?female", "EU06FDXS"),
    (r"pet\s*diapers?\s*\(?male", "EU05DDXS"),
    (r"training\s*pads", "EU01P660"),
    (r"underpads.*lavender|lavender.*underpads", "EU03P565A1"),
    (r"underpads.*charcoal|charcoal.*underpads", "EU04565A1"),
    (r"underpads", "EU02P565A1"),
]

def map_samples_to_skus(raw: str) -> list[str]:
    if not raw:
        return []
    s = str(raw).lower()
    found = []
    seen = set()
    # split on / , 、 和
    parts = re.split(r"[/,，、]+", s)
    for part in parts:
        for pat, sku in SAMPLE_NAME_TO_SKU:
            if re.search(pat, part):
                if sku not in seen:
                    seen.add(sku)
                    found.append(sku)
                break
    return found


def derive_status(video_url: str | None, has_video_flag, ad_code: str | None,
                  remark: str | None, sample_qty: int) -> str:
    text = " ".join([str(x) for x in (remark or "", str(has_video_flag or ""))]).lower()
    if ad_code and str(ad_code).strip():
        return "ad_authorized"
    if video_url and str(video_url).strip():
        return "video_published"
    if "已发布" in str(remark or "") or "video posted" in text:
        return "video_published"
    if "运输中" in str(remark or "") or "shipping" in text or "shipped" in text:
        return "sample_shipped"
    if sample_qty and sample_qty > 0:
        return "sample_shipped"
    if str(has_video_flag or "").strip().lower() in {"是", "yes"}:
        return "video_published"
    return "contacted"


# ============================================================
# Parser
# ============================================================
def parse_weekly(fp: Path) -> list[dict]:
    df = pd.read_excel(fp, sheet_name=0, header=None)
    df = df.fillna("")
    # find header row (the row that contains "店铺名" and "达人")
    header_row = None
    for i in range(min(5, len(df))):
        rowstr = " ".join(str(x) for x in df.iloc[i].tolist())
        if "店铺名" in rowstr and ("达人" in rowstr or "Handle" in rowstr):
            header_row = i
            break
    if header_row is None:
        return []
    cols = [str(x) for x in df.iloc[header_row].tolist()]

    def find_col(*needles: str) -> int | None:
        for idx, name in enumerate(cols):
            for n in needles:
                if n in name:
                    return idx
        return None

    c_store = find_col("店铺名", "Store")
    c_bd = find_col("负责人", "Person")
    c_date = find_col("日期", "Date")
    c_qty_contacted = find_col("建联达人数", "Number of Influencers")
    c_handle = find_col("达人社交账号", "寄样达人", "Handle")
    c_comm = find_col("佣金", "Commission")
    c_sample_qty = find_col("寄样数量", "Sample Quantity")
    c_samples = find_col("寄样产品", "Samples Sent")
    c_video_flag = find_col("是否提供视频", "Video Provided")
    c_link = find_col("Link", "🔗", "链接")
    c_code = find_col("Code", "Authorization", "授权码")
    c_remark = find_col("备注", "Remarks")

    out = []
    last_store = last_bd = last_date = ""
    for i in range(header_row + 1, len(df)):
        row = df.iloc[i].tolist()

        store = str(row[c_store]).strip() if c_store is not None else ""
        bd = str(row[c_bd]).strip() if c_bd is not None else ""
        date_raw = str(row[c_date]).strip() if c_date is not None else ""

        if store: last_store = store
        if bd: last_bd = bd
        if date_raw: last_date = date_raw

        handle = clean_handle(str(row[c_handle])) if c_handle is not None else None
        if not handle:
            continue

        comm = parse_commission(row[c_comm]) if c_comm is not None else None
        try:
            sample_qty = int(float(row[c_sample_qty])) if c_sample_qty is not None and str(row[c_sample_qty]).strip() else 0
        except (ValueError, TypeError):
            sample_qty = 0
        samples_text = str(row[c_samples]).strip() if c_samples is not None else ""
        video_flag = str(row[c_video_flag]).strip() if c_video_flag is not None else ""
        link = str(row[c_link]).strip() if c_link is not None else ""
        code = str(row[c_code]).strip() if c_code is not None else ""
        remark = str(row[c_remark]).strip() if c_remark is not None else ""

        out.append(dict(
            store=last_store,
            bd=last_bd,
            date=parse_date(last_date),
            handle=handle,
            commission=comm,
            sample_qty=sample_qty,
            samples_text=samples_text,
            video_flag=video_flag,
            video_url=link if link.startswith("http") else None,
            ad_code=code if code and code != "要授权码" else None,
            remark=remark,
            source_file=fp.name,
        ))
    return out


def parse_cm(fp: Path) -> list[dict]:
    """Creator Marketplace evaluation table - extra metrics for one or more handles."""
    df = pd.read_excel(fp, sheet_name=0, header=None).fillna("")
    out = []
    for i in range(len(df)):
        row = [str(x).strip() for x in df.iloc[i].tolist()]
        # data rows look like: [num, handle, followers, sample_score, post_rate, gmv, avg_views, pps]
        if len(row) < 8:
            continue
        if not row[0] or not row[0].isdigit():
            continue
        handle = clean_handle(row[1])
        if not handle:
            continue
        out.append(dict(
            handle=handle,
            followers=parse_followers(row[2]),
            sample_score=float(row[3]) if row[3].replace(".","",1).isdigit() else None,
            post_rate_est=float(row[4]) if row[4].replace(".","",1).isdigit() else None,
            gmv_30d_usd=parse_followers(row[5].lstrip("$")),  # "$290.0K" -> 290000
            avg_views=int(float(row[6])) if row[6].replace(".","",1).isdigit() else None,
            pps=float(row[7]) if row[7].replace(".","",1).isdigit() else None,
        ))
    return out


def parse_march(fp: Path) -> list[dict]:
    """3月份达人建联统计表 - BD staff totals (not creators)."""
    df = pd.read_excel(fp, sheet_name=0, header=None).fillna("")
    out = []
    for i in range(2, len(df)):
        row = [str(x).strip() for x in df.iloc[i].tolist()]
        if len(row) < 6 or not row[0].isdigit():
            continue
        out.append(dict(
            name=row[1],
            contacted=int(float(row[2])) if row[2].replace(".","",1).isdigit() else 0,
            confirmed=int(float(row[3])) if row[3].replace(".","",1).isdigit() else 0,
            samples=int(float(row[4])) if row[4].replace(".","",1).isdigit() else 0,
            videos=int(float(row[5])) if row[5].replace(".","",1).isdigit() else 0,
        ))
    return out


# ============================================================
# Persist
# ============================================================
def upsert_creator(con: sqlite3.Connection, *, handle: str, **fields) -> int:
    fields["handle"] = handle
    fields.setdefault("platform", "tiktok")
    fields.setdefault("profile_url", f"https://www.tiktok.com/@{handle}")
    cols = list(fields.keys())
    placeholders = ",".join(["?"] * len(cols))
    update_set = ",".join([
        f"{c}=COALESCE(NULLIF(excluded.{c},''), {c})"
        for c in cols if c not in {"handle", "platform"}
    ])
    sql = (
        f"INSERT INTO creator({','.join(cols)}) VALUES({placeholders}) "
        f"ON CONFLICT(platform,handle) DO UPDATE SET {update_set}"
    )
    con.execute(sql, [fields[c] for c in cols])
    cid = con.execute(
        "SELECT id FROM creator WHERE platform=? AND handle=?",
        (fields["platform"], handle),
    ).fetchone()[0]
    return cid


def insert_outreach(con: sqlite3.Connection, creator_id: int, ev: dict, sku_codes: list[str]) -> int:
    # de-dup heuristic: same creator, date, video_url, ad_code, status -> already inserted
    status = derive_status(ev.get("video_url"), ev.get("video_flag"), ev.get("ad_code"),
                           ev.get("remark"), ev.get("sample_qty", 0))
    existing = con.execute(
        "SELECT id FROM outreach WHERE creator_id=? AND COALESCE(event_date,'')=COALESCE(?, '') "
        "AND COALESCE(video_url,'')=COALESCE(?, '') AND COALESCE(ad_auth_code,'')=COALESCE(?, '') "
        "AND COALESCE(status,'')=?",
        (creator_id, ev.get("date"), ev.get("video_url"), ev.get("ad_code"), status),
    ).fetchone()
    if existing:
        return existing[0]
    cur = con.execute(
        "INSERT INTO outreach(creator_id,event_date,store_name,bd_owner,action,status,channel,"
        "sample_qty,commission_rate,video_url,ad_auth_code,remark) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (creator_id, ev.get("date"), ev.get("store"), ev.get("bd"),
         status, status, "dm",
         ev.get("sample_qty", 0), ev.get("commission"),
         ev.get("video_url"), ev.get("ad_code"), ev.get("remark"))
    )
    oid = cur.lastrowid
    for sku in sku_codes:
        pid = con.execute("SELECT id FROM product WHERE sku_code=?", (sku,)).fetchone()
        if pid:
            con.execute(
                "INSERT OR IGNORE INTO outreach_sku(outreach_id,product_id,qty) VALUES(?,?,?)",
                (oid, pid[0], ev.get("sample_qty", 1) or 1),
            )
    return oid


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys=ON")

    # --- staff (from March table) ---
    if MARCH_FILE.exists():
        for s in parse_march(MARCH_FILE):
            note = json.dumps({"contacted": s["contacted"], "confirmed": s["confirmed"],
                               "samples": s["samples"], "videos": s["videos"],
                               "month": "2026-03"}, ensure_ascii=False)
            con.execute(
                "INSERT INTO staff(name,role,note) VALUES(?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET note=excluded.note",
                (s["name"], "BD", note),
            )
        con.commit()
        print(f"[import_creators] staff entries upserted")

    # --- merge weekly events ---
    all_events: list[dict] = []
    for f in WEEKLY_FILES:
        if not f.exists():
            print(f"[import_creators] WARN: missing {f}")
            continue
        rows = parse_weekly(f)
        print(f"[import_creators] {f.name}: parsed {len(rows)} outreach rows")
        all_events.extend(rows)

    # --- de-dup events by (handle, date, video_url, ad_code) before insert ---
    seen: set = set()
    deduped = []
    for ev in all_events:
        key = (ev["handle"], ev.get("date"), ev.get("video_url") or "", ev.get("ad_code") or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)
    print(f"[import_creators] {len(all_events)} events -> {len(deduped)} unique")

    # --- creator metrics from CM table ---
    cm_rows = parse_cm(CM_FILE) if CM_FILE.exists() else []
    cm_lookup = {r["handle"]: r for r in cm_rows}
    print(f"[import_creators] CM evaluation rows: {len(cm_rows)}")

    # --- upsert each creator + outreach ---
    creator_ids: dict[str, int] = {}
    for ev in deduped:
        handle = ev["handle"]
        cm = cm_lookup.get(handle, {})
        followers = cm.get("followers")
        fields = dict(
            display_name="",
            country="US",  # default
            category_tags=json.dumps(["女性护理"], ensure_ascii=False),  # default; refinable later
            followers=followers,
            tier=tier_for(followers) or "C",  # default to C if unknown
            avg_views=cm.get("avg_views"),
            gmv_30d_usd=cm.get("gmv_30d_usd"),
            pps=cm.get("pps"),
            sample_score=cm.get("sample_score"),
            post_rate_est=cm.get("post_rate_est"),
            current_status=derive_status(ev.get("video_url"), ev.get("video_flag"),
                                         ev.get("ad_code"), ev.get("remark"),
                                         ev.get("sample_qty", 0)),
            store_assigned=ev.get("store") or None,
            owner_bd=ev.get("bd") or None,
            first_contact_date=ev.get("date"),
            last_contact_date=ev.get("date"),
            source="weekly_import",
        )
        cid = upsert_creator(con, handle=handle, **fields)
        creator_ids[handle] = cid
        sku_codes = map_samples_to_skus(ev.get("samples_text", ""))
        insert_outreach(con, cid, ev, sku_codes)

    # ensure CM-only handles also exist
    for h, cm in cm_lookup.items():
        if h in creator_ids:
            con.execute(
                "UPDATE creator SET followers=COALESCE(?, followers), "
                "avg_views=COALESCE(?, avg_views), gmv_30d_usd=COALESCE(?, gmv_30d_usd), "
                "pps=COALESCE(?, pps), sample_score=COALESCE(?, sample_score), "
                "post_rate_est=COALESCE(?, post_rate_est), tier=? "
                "WHERE id=?",
                (cm.get("followers"), cm.get("avg_views"), cm.get("gmv_30d_usd"),
                 cm.get("pps"), cm.get("sample_score"), cm.get("post_rate_est"),
                 tier_for(cm.get("followers")) or "C", creator_ids[h])
            )
        else:
            upsert_creator(
                con, handle=h,
                followers=cm.get("followers"),
                tier=tier_for(cm.get("followers")) or "C",
                avg_views=cm.get("avg_views"),
                gmv_30d_usd=cm.get("gmv_30d_usd"),
                pps=cm.get("pps"),
                sample_score=cm.get("sample_score"),
                post_rate_est=cm.get("post_rate_est"),
                current_status="prospect",
                source="cm_import",
                category_tags=json.dumps(["女性护理"], ensure_ascii=False),
            )
    con.commit()

    n_creator = con.execute("SELECT COUNT(*) FROM creator").fetchone()[0]
    n_out = con.execute("SELECT COUNT(*) FROM outreach").fetchone()[0]
    n_link = con.execute("SELECT COUNT(*) FROM outreach_sku").fetchone()[0]
    by_status = con.execute(
        "SELECT current_status, COUNT(*) FROM creator GROUP BY current_status ORDER BY 2 DESC"
    ).fetchall()
    print(f"[import_creators] creators={n_creator}  outreach_events={n_out}  sku_links={n_link}")
    for s, c in by_status:
        print(f"   {s or '(null)':20s} {c}")
    con.close()


if __name__ == "__main__":
    main()
