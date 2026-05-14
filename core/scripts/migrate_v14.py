"""migrate_v14: 把 tk_creators (廖 lead 池) 的评分/推荐/证据字段并入 creator 主表，
并做一次 ETL UPSERT，使 (platform, lower(handle)) 维度上 creator 包含廖的最新值。

执行结果:
- creator 新增 50 列（廖独有的字段，全部 NULL 友好）
- ETL 规则:
  * 64 行 (platform, handle) 重叠: 廖的字段覆盖到 creator，BD 字段 (owner_bd / current_status /
    first_contact_date / last_contact_date / store_assigned) 不覆盖
  * 66 行 lead 独有: INSERT 进 creator (current_status='prospect', source='scraper_liao')
  * 2 行 creator 独有: 不动
- tk_creators 表保留作为廖爬虫的原始落地（每天可继续 UPSERT）

幂等: 列已存在则跳过; ETL 走 INSERT ... ON CONFLICT(platform, handle) DO UPDATE。

回滚: 这 50 列均允许 NULL, 不影响现有读路径; 如需回滚, 走 DROP COLUMN 端点
（v3.8.2 已开放）或 migrate_v14_rollback.py。
"""
from __future__ import annotations
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "database.db"

# 50 列（不含 followers_count, 它映射到 creator.followers）
NEW_COLS: list[tuple[str, str]] = [
    ("bio", "TEXT"),
    ("has_email", "INTEGER"),
    ("external_links_json", "TEXT"),
    ("source_video_url", "TEXT"),
    ("source_video_title", "TEXT"),
    ("source_video_description", "TEXT"),
    ("search_keyword", "TEXT"),
    ("collected_at", "TEXT"),
    ("last_seen_at", "TEXT"),
    # 优先级 / 队列
    ("priority_score", "INTEGER"),
    ("fit_level", "TEXT"),
    ("priority_level", "TEXT"),
    ("queue_type", "TEXT"),
    # 品类匹配分
    ("primary_product_category", "TEXT"),
    ("primary_product_fit_score", "INTEGER"),
    ("feminine_care_fit", "INTEGER"),
    ("pet_care_fit", "INTEGER"),
    ("home_care_fit", "INTEGER"),
    ("adult_care_fit", "INTEGER"),
    ("mom_baby_fit", "INTEGER"),
    ("health_mask_fit", "INTEGER"),
    # 质量子分
    ("data_quality_score", "INTEGER"),
    ("contactability_score", "INTEGER"),
    ("content_format_score", "INTEGER"),
    ("commercial_value_score", "INTEGER"),
    ("follower_scale_score", "INTEGER"),
    ("audience_fit_score", "INTEGER"),
    # 推荐
    ("recommendation_status", "TEXT"),
    ("recommended_product_type", "TEXT"),
    ("recommended_collab_type", "TEXT"),
    ("outreach_priority", "TEXT"),
    ("recommendation_score", "INTEGER"),
    ("recommendation_reason", "TEXT"),
    ("risk_summary", "TEXT"),
    ("next_action", "TEXT"),
    ("review_required", "INTEGER"),
    ("review_status", "TEXT"),
    # 证据
    ("fit_evidence_source_json", "TEXT"),
    ("matched_keywords_json", "TEXT"),
    ("evidence_strength", "TEXT"),
    ("evidence_text_json", "TEXT"),
    ("risk_tags_json", "TEXT"),
    ("positive_tags_json", "TEXT"),
    ("content_format_status", "TEXT"),
    # 版本戳
    ("score_version", "TEXT"),
    ("tag_version", "TEXT"),
    ("rec_version", "TEXT"),
    ("scored_at", "TEXT"),
    ("tagged_at", "TEXT"),
    ("recommended_at", "TEXT"),
]

# BD 字段: 同步时不覆盖 creator 已有非空值
BD_FIELDS = {
    "owner_bd", "current_status", "first_contact_date",
    "last_contact_date", "store_assigned", "notes",
}


def add_columns(con: sqlite3.Connection) -> int:
    existing = {c[1] for c in con.execute("PRAGMA table_info(creator)")}
    added = 0
    for name, typ in NEW_COLS:
        if name in existing:
            continue
        con.execute(f"ALTER TABLE creator ADD COLUMN {name} {typ}")
        added += 1
    con.commit()
    return added


def etl_upsert(con: sqlite3.Connection) -> dict:
    # 取 tk_creators 全部 + 当前 creator 全部（用于判断重叠/独有）
    creator_keys = {
        (r[0], r[1].lower()) for r in
        con.execute("SELECT platform, handle FROM creator")
    }

    # 廖字段列表（同步过去的）
    sync_cols = [n for n, _ in NEW_COLS]
    # creator.followers ← tk.followers_count
    sync_cols_select = ", ".join(["t.followers_count"] + [f"t.{c}" for c in sync_cols])

    rows = con.execute(
        f"SELECT t.platform, t.handle, t.display_name, t.profile_url, t.email, "
        f"       {sync_cols_select} "
        f"FROM tk_creators t"
    ).fetchall()

    overlap_updated = 0
    inserted = 0

    for r in rows:
        platform = r[0] or "tiktok"
        handle = r[1]
        if not handle:
            continue
        key = (platform, handle.lower())
        display_name = r[2]
        profile_url = r[3]
        email = r[4]
        followers_count = r[5]
        # r[6:] 对应 sync_cols
        liao_vals = list(r[6:])

        if key in creator_keys:
            # 重叠: 用廖的值覆盖（仅非空），BD 字段不动
            sets = []
            args = []
            # followers ← followers_count（仅当 tk 有值）
            if followers_count is not None:
                sets.append("followers=COALESCE(?, followers)")
                args.append(followers_count)
            # email 仅当 creator 现为空时填
            if email:
                sets.append("email=COALESCE(NULLIF(email,''), ?)")
                args.append(email)
            # display_name / profile_url 同上
            if display_name:
                sets.append("display_name=COALESCE(NULLIF(display_name,''), ?)")
                args.append(display_name)
            if profile_url:
                sets.append("profile_url=COALESCE(NULLIF(profile_url,''), ?)")
                args.append(profile_url)
            # 廖的字段：非空就覆盖
            for col, val in zip(sync_cols, liao_vals):
                if val is not None and val != "":
                    sets.append(f"{col}=?")
                    args.append(val)
            if sets:
                sets.append("updated_at=datetime('now')")
                args.extend([platform, handle])
                con.execute(
                    f"UPDATE creator SET {','.join(sets)} "
                    f"WHERE platform=? AND lower(handle)=lower(?)",
                    args,
                )
                overlap_updated += 1
        else:
            # 新增: INSERT 进 creator
            cols = (["platform", "handle", "display_name", "profile_url", "email",
                     "followers", "current_status", "source"] + sync_cols)
            placeholders = ",".join(["?"] * len(cols))
            vals = ([platform, handle, display_name, profile_url, email,
                     followers_count, "prospect", "scraper_liao"] + liao_vals)
            try:
                con.execute(
                    f"INSERT INTO creator({','.join(cols)}) VALUES({placeholders})",
                    vals,
                )
                inserted += 1
                creator_keys.add(key)
            except sqlite3.IntegrityError as e:
                # UNIQUE(platform, handle) 冲突 — 大小写差异，转 UPDATE
                print(f"  [skip] {platform}/{handle}: {e}")

    con.commit()
    return {"overlap_updated": overlap_updated, "inserted": inserted}


def main() -> None:
    con = sqlite3.connect(DB)
    try:
        before = con.execute("SELECT COUNT(*) FROM creator").fetchone()[0]
        added = add_columns(con)
        result = etl_upsert(con)
        after = con.execute("SELECT COUNT(*) FROM creator").fetchone()[0]
        print(f"[migrate_v14] columns added: {added}")
        print(f"[migrate_v14] creator rows: {before} -> {after} (+{after-before})")
        print(f"[migrate_v14] overlap updated: {result['overlap_updated']}")
        print(f"[migrate_v14] new lead inserted: {result['inserted']}")
        # 抽样验证
        sample = con.execute(
            "SELECT id, handle, priority_score, fit_level, recommendation_reason "
            "FROM creator WHERE priority_score IS NOT NULL LIMIT 3"
        ).fetchall()
        print(f"[migrate_v14] sample with 廖字段:")
        for s in sample:
            print(f"    {s}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
