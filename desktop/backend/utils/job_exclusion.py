"""
竞品/排除词管理 —— 基于本地 JSON 的轻量级方案

文件格式 (data/exclusion_presets.json):
{
  "active": ["default", "user_kuajing"],   // 当前生效的方案 id 列表（多选求并集）
  "presets": [
    {"id": "default", "name": "内置·明显非客户", "builtin": true, "keywords": [...]},
    {"id": "user_xxx", "name": "用户自定义...", "builtin": false, "keywords": [...]}
  ]
}

排除策略：命中任一关键词 → 标记 excluded=1，不进入正常评分流程（依然入库供审计）。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from threading import RLock

from ..config import DATA_DIR

# Store the exclusion presets under X9's shared data dir (same place as the
# local SQLite / exports), not next to the source file.
_DATA_PATH = Path(DATA_DIR) / "exclusion_presets.json"
_lock = RLock()


# 贵司自有/关联公司关键词：这些公司是“我们自己”，绝不应被采集或评分。
# 该清单为始终生效的硬性兜底（不依赖用户在界面里是否勾选对应方案），
# 以确保“后续不要爬取自家公司数据”这一要求不会因为方案被关闭而失效。
SELF_COMPANY_KEYWORDS = [
    "蓝蜻蜓",
    "福建蓝蜻蜓",
    "福建蓝蜻蜓护理用品",
    "福建蓝蜻蜓护理用品股份",
]

PLATFORM_OPERATOR_KEYWORDS = {
    "字节跳动",
    "腾讯",
    "阿里巴巴",
    "京东",
    "拼多多",
    "美团",
    "百度",
    "tiktok shop",
    "tiktokshop",
}


DEFAULT_PRESETS = [
    {
        "id": "default_self",
        "name": "内置·贵司自有/关联公司（始终生效）",
        "builtin": True,
        "keywords": list(SELF_COMPANY_KEYWORDS),
    },
    {
        "id": "default_competitors",
        "name": "内置·明显竞品/非合作对象",
        "builtin": True,
        "keywords": [
            # 大型平台/巨头本身不会是分销客户
            "字节跳动", "腾讯", "阿里巴巴", "京东", "拼多多", "美团", "百度",
            "tiktok shop", "tiktokshop", "tikTok shop",  # 官方平台
            # 同行竞品（分销服务商）—— 按需补充
            "分销宝", "分销中国",
            # 招聘代运营服务商，不是真正的卖家
            "代运营公司", "代运营服务",
        ],
    },
    {
        "id": "default_irrelevant",
        "name": "内置·明显跨行业（教培/医疗等）",
        "builtin": True,
        "keywords": [
            "教育培训", "考研", "K12", "幼儿园", "驾校",
            "医院", "诊所", "牙科",
            "房地产", "二手房", "中介",
            "保险", "理财", "P2P",
        ],
    },
]


def _ensure_file() -> None:
    _DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _DATA_PATH.exists():
        _DATA_PATH.write_text(
            json.dumps(
                {"active": ["default_competitors"], "presets": DEFAULT_PRESETS},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def load_state() -> dict:
    with _lock:
        _ensure_file()
        try:
            state = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            state = {"active": ["default_competitors"], "presets": DEFAULT_PRESETS}

    # 强制把缺失的内置方案补回来（不覆盖用户改的关键词）
    existing_ids = {p["id"] for p in state.get("presets", [])}
    for default in DEFAULT_PRESETS:
        if default["id"] not in existing_ids:
            state.setdefault("presets", []).append(default)
    state.setdefault("active", ["default_competitors"])
    # 贵司自有公司方案始终启用（即使是旧配置文件没有该方案），确保不会采集/评分自家公司。
    if "default_self" not in state["active"]:
        state["active"].append("default_self")
    return state


def save_state(state: dict) -> None:
    with _lock:
        _DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        _DATA_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def list_presets() -> dict:
    return load_state()


def upsert_preset(preset: dict) -> dict:
    name = (preset.get("name") or "").strip()
    keywords = [k.strip() for k in (preset.get("keywords") or []) if isinstance(k, str) and k.strip()]
    if not name:
        raise ValueError("name is required")

    state = load_state()
    pid = preset.get("id") or f"user_{uuid.uuid4().hex[:10]}"
    found = next((p for p in state["presets"] if p["id"] == pid), None)
    if found:
        if found.get("builtin"):
            # 允许修改内置方案的关键词，但不能改名字/标志
            found["keywords"] = keywords or found["keywords"]
        else:
            found["name"] = name
            found["keywords"] = keywords
    else:
        state["presets"].append({"id": pid, "name": name, "builtin": False, "keywords": keywords})
    save_state(state)
    return next(p for p in state["presets"] if p["id"] == pid)


def delete_preset(preset_id: str) -> None:
    state = load_state()
    target = next((p for p in state["presets"] if p["id"] == preset_id), None)
    if not target:
        raise ValueError(f"preset not found: {preset_id}")
    if target.get("builtin"):
        raise ValueError("内置方案不允许删除，可清空关键词")
    state["presets"] = [p for p in state["presets"] if p["id"] != preset_id]
    state["active"] = [a for a in state.get("active", []) if a != preset_id]
    save_state(state)


def set_active(active_ids: list[str]) -> dict:
    state = load_state()
    valid = {p["id"] for p in state["presets"]}
    state["active"] = [a for a in active_ids if a in valid]
    save_state(state)
    return state


def active_keywords() -> list[str]:
    """所有被启用方案的关键词（去重，小写化）。"""
    state = load_state()
    active = set(state.get("active", []))
    out: list[str] = []
    seen: set[str] = set()
    for p in state["presets"]:
        if p["id"] not in active:
            continue
        for kw in p.get("keywords", []):
            low = kw.lower().strip()
            if low and low not in seen:
                seen.add(low)
                out.append(kw)
    return out


def check_excluded(*texts: str) -> tuple[bool, str | None]:
    """
    返回 (是否命中, 命中的关键词)。
    texts 是公司名/简介/JD 等，任一命中即返回 True。
    """
    company_name = (texts[0] if texts else "").lower()
    joined = " ".join(t for t in texts if t).lower()
    if not joined:
        return False, None
    # 1) 始终优先排除贵司自有/关联公司（硬性兜底，不受界面方案开关影响）。
    for kw in SELF_COMPANY_KEYWORDS:
        if kw and kw.lower() in joined:
            return True, f"贵司自有公司({kw})"
    # 2) 再按当前启用方案的关键词排除。
    for kw in active_keywords():
        low = kw.lower()
        # 平台名是强渠道信号，不能因为简介里写"阿里巴巴国际站商家"
        # 或 JD 写"TikTok Shop 运营"就误判为官方平台本体。
        if low in PLATFORM_OPERATOR_KEYWORDS and low not in company_name:
            continue
        if low in joined:
            return True, kw
    return False, None
