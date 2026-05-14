"""creator_compat — A 旧 `creator` 表 ↔ B 新 `creators` 表的字段映射层。

迁移背景:migrate_v16 把 A 的 `creator` 表数据按 (platform, handle) 合并到了
B 的 `creators` 表(B 是 PostgreSQL 上的统一达人主表,UUID 主键)。

`creators` 表新增了 `legacy_int_id` 列保存 A 原 id,以及 A 独有的字段:
  country, language, category_tags, avg_views, gmv_30d_usd, pps, sample_score,
  post_rate_est, whatsapp, instagram_handle, youtube_handle, source, quality_score,
  first_contact_date, last_contact_date

注:本次合并是增量的,**没有 rename 旧表**:
  - `creator` 表仍存在,FK 关系(creator_product / outreach 等)完整保留
  - 任何新写入都应走 `creators` 表
  - 现有读旧表的代码(main.py / pg_dashboard.py / outreach_ai.py)继续工作
  - 等所有读路径都改到 `creators` 后,可以 rename 老表为 `creator_legacy`

本模块给后续把代码切到 `creators` 时用,提供以下能力:
  - 字段名映射(A 风格 ↔ B 风格)
  - row 翻译(对外仍暴露 A 的字段名,内部读 B 的列)
  - id 翻译(廖的爬虫传整数 id,内部翻译到 UUID)

未在 import 时副作用任何东西。是个纯工具模块。
"""
from __future__ import annotations

from typing import Any


# A 的列 -> B 的列(差异部分;同名列不在此表)
A_TO_B_FIELD = {
    "id": "legacy_int_id",
    "followers": "followers_count",
}

# B 的列 -> A 的列(反向,用于响应裁剪)
B_TO_A_FIELD = {b: a for a, b in A_TO_B_FIELD.items()}


def a_payload_to_b(payload: dict[str, Any]) -> dict[str, Any]:
    """A 风格的 dict(廖的爬虫传入)-> B 风格的 dict(写 creators 表用)。

    例:{"followers": 12345, "handle": "@x"} -> {"followers_count": 12345, "handle": "@x"}
    """
    return {A_TO_B_FIELD.get(k, k): v for k, v in payload.items()}


def b_row_to_a(row: dict[str, Any]) -> dict[str, Any]:
    """B 风格的 dict(从 creators 表读出)-> A 风格的 dict(给廖的爬虫返回)。

    例:{"followers_count": 12345, "legacy_int_id": 7, ...}
        -> {"followers": 12345, "id": 7, ...}

    注:legacy_int_id 为 NULL 时(纯 B 来源的记录),id 字段会是 None,
    廖的客户端应该容忍 null id 或者用 UUID 作为 id。
    """
    out: dict[str, Any] = {}
    for k, v in row.items():
        a_key = B_TO_A_FIELD.get(k)
        if a_key:
            out[a_key] = v
        else:
            out[k] = v
    return out


def resolve_creator_id(con: Any, raw_id: Any) -> str | None:
    """把一个 id(可能是 A 的 int,或 B 的 uuid 字符串)解析到 B 的 UUID。

    廖的爬虫可能仍发整数 id;UI 可能发 UUID。同一个入口都能用。

    返回 creators.id(UUID 字符串)或 None(未找到)。
    """
    if raw_id is None:
        return None

    # 已是 UUID?(简单检查:长度>16 + 含 -)
    raw_str = str(raw_id)
    if len(raw_str) > 16 and "-" in raw_str:
        # 假设是 UUID,直接验证存在
        with con.cursor() as cur:
            cur.execute("SELECT id FROM creators WHERE id = %s", (raw_str,))
            row = cur.fetchone()
            return row[0] if row else None

    # 否则当 int 走 legacy_int_id 查
    try:
        int_id = int(raw_str)
    except (TypeError, ValueError):
        return None
    with con.cursor() as cur:
        cur.execute("SELECT id FROM creators WHERE legacy_int_id = %s", (int_id,))
        row = cur.fetchone()
        return row[0] if row else None
