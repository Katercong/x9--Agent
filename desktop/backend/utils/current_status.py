from __future__ import annotations

from typing import Any


CURRENT_STATUS_VALUES = ("待建联", "已建联", "待回复", "视频已发布", "已寄样")

_STATUS_ALIASES = {
    "待建联": "待建联",
    "未建联": "待建联",
    "待联系": "待建联",
    "待触达": "待建联",
    "to_be_contacted": "待建联",
    "pending_contact": "待建联",
    "已建联": "已建联",
    "建联": "已建联",
    "已联系": "已建联",
    "已触达": "已建联",
    "contacted": "已建联",
    "outreached": "已建联",
    "待回复": "待回复",
    "等待回复": "待回复",
    "待回": "待回复",
    "未回复": "待回复",
    "pending_reply": "待回复",
    "awaiting_reply": "待回复",
    "waiting_reply": "待回复",
    "视频已发布": "视频已发布",
    "已发布视频": "视频已发布",
    "已发布": "视频已发布",
    "video_published": "视频已发布",
    "published": "视频已发布",
    "已寄样": "已寄样",
    "寄样": "已寄样",
    "已发样": "已寄样",
    "样品已寄": "已寄样",
    "sample_sent": "已寄样",
    "sent_sample": "已寄样",
    "sampled": "已寄样",
}


def normalize_current_status(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.strip("。.;；,，")
    key = "_".join(text.lower().replace("-", "_").split())
    compact_key = key.replace("_", "")
    return _STATUS_ALIASES.get(key) or _STATUS_ALIASES.get(compact_key) or text
