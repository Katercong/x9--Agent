from __future__ import annotations

from typing import Any


STATUS_PENDING_CONTACT = "待建联"
STATUS_CONTACTED = "已建联"
STATUS_PENDING_FOLLOWUP = "待跟进"
STATUS_COMMUNICATING = "沟通中"
STATUS_SAMPLE_SHIPPED = "已寄样"
STATUS_SAMPLE_DELIVERED = "样品签收"
STATUS_VIDEO_PUBLISHED = "视频已发布"
STATUS_AUTHORIZED = "已授权"
STATUS_AD_RUNNING = "广告投放中"

CURRENT_STATUS_VALUES = (
    STATUS_PENDING_CONTACT,
    STATUS_CONTACTED,
    STATUS_PENDING_FOLLOWUP,
    STATUS_COMMUNICATING,
    STATUS_SAMPLE_SHIPPED,
    STATUS_SAMPLE_DELIVERED,
    STATUS_VIDEO_PUBLISHED,
    STATUS_AUTHORIZED,
    STATUS_AD_RUNNING,
)

_STATUS_ALIASES = {
    "待建联": STATUS_PENDING_CONTACT,
    "未建联": STATUS_PENDING_CONTACT,
    "待联系": STATUS_PENDING_CONTACT,
    "待触达": STATUS_PENDING_CONTACT,
    "to_be_contacted": STATUS_PENDING_CONTACT,
    "pending_contact": STATUS_PENDING_CONTACT,
    "prospect": STATUS_PENDING_CONTACT,
    "recommended": STATUS_PENDING_CONTACT,
    "已建联": STATUS_CONTACTED,
    "建联": STATUS_CONTACTED,
    "已联系": STATUS_CONTACTED,
    "已触达": STATUS_CONTACTED,
    "contacted": STATUS_CONTACTED,
    "outreached": STATUS_CONTACTED,
    "sent": STATUS_CONTACTED,
    "email_sent": STATUS_CONTACTED,
    "待跟进": STATUS_PENDING_FOLLOWUP,
    "需跟进": STATUS_PENDING_FOLLOWUP,
    "待回复": STATUS_PENDING_FOLLOWUP,
    "等待回复": STATUS_PENDING_FOLLOWUP,
    "待回": STATUS_PENDING_FOLLOWUP,
    "未回复": STATUS_PENDING_FOLLOWUP,
    "已回复": STATUS_PENDING_FOLLOWUP,
    "pending_followup": STATUS_PENDING_FOLLOWUP,
    "pending_follow_up": STATUS_PENDING_FOLLOWUP,
    "needs_followup": STATUS_PENDING_FOLLOWUP,
    "needs_follow_up": STATUS_PENDING_FOLLOWUP,
    "pending_reply": STATUS_PENDING_FOLLOWUP,
    "awaiting_reply": STATUS_PENDING_FOLLOWUP,
    "waiting_reply": STATUS_PENDING_FOLLOWUP,
    "reply_received": STATUS_PENDING_FOLLOWUP,
    "inbound_reply": STATUS_PENDING_FOLLOWUP,
    "replied": STATUS_PENDING_FOLLOWUP,
    "沟通中": STATUS_COMMUNICATING,
    "已确认": STATUS_COMMUNICATING,
    "确认合作": STATUS_COMMUNICATING,
    "communicating": STATUS_COMMUNICATING,
    "confirmed": STATUS_COMMUNICATING,
    "已寄样": STATUS_SAMPLE_SHIPPED,
    "寄样": STATUS_SAMPLE_SHIPPED,
    "已发样": STATUS_SAMPLE_SHIPPED,
    "样品已寄": STATUS_SAMPLE_SHIPPED,
    "sample_sent": STATUS_SAMPLE_SHIPPED,
    "sent_sample": STATUS_SAMPLE_SHIPPED,
    "sample_shipped": STATUS_SAMPLE_SHIPPED,
    "sampled": STATUS_SAMPLE_SHIPPED,
    "样品签收": STATUS_SAMPLE_DELIVERED,
    "已签收": STATUS_SAMPLE_DELIVERED,
    "sample_delivered": STATUS_SAMPLE_DELIVERED,
    "delivered": STATUS_SAMPLE_DELIVERED,
    "视频已发布": STATUS_VIDEO_PUBLISHED,
    "已发布视频": STATUS_VIDEO_PUBLISHED,
    "已发视频": STATUS_VIDEO_PUBLISHED,
    "已发布": STATUS_VIDEO_PUBLISHED,
    "video_published": STATUS_VIDEO_PUBLISHED,
    "published": STATUS_VIDEO_PUBLISHED,
    "已授权": STATUS_AUTHORIZED,
    "广告授权": STATUS_AUTHORIZED,
    "ad_authorized": STATUS_AUTHORIZED,
    "authorized": STATUS_AUTHORIZED,
    "partnered": STATUS_AUTHORIZED,
    "广告投放中": STATUS_AD_RUNNING,
    "ad_running": STATUS_AD_RUNNING,
    "running": STATUS_AD_RUNNING,
}


def normalize_current_status(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.strip("。;；，,")
    key = "_".join(text.lower().replace("-", "_").split())
    compact_key = key.replace("_", "")
    return _STATUS_ALIASES.get(key) or _STATUS_ALIASES.get(compact_key) or text
