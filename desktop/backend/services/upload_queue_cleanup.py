from __future__ import annotations

from typing import Any


def queue_cleanup_payload(payload: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    creator = source.get("creator") if isinstance(source.get("creator"), dict) else {}
    source_video = source.get("source_video") if isinstance(source.get("source_video"), dict) else {}

    cleanup: dict[str, Any] = {
        "clear_uploaded": True,
        "clear_retry": True,
        "clear_queue": True,
        "handle": creator.get("handle") or source.get("handle") or extra.get("handle"),
        "profile_url": creator.get("profile_url") or source.get("profile_url") or extra.get("profile_url"),
        "source_video_url": (
            source_video.get("video_url")
            or source.get("source_video_url")
            or source.get("video_url")
            or extra.get("source_video_url")
        ),
        "search_keyword": source.get("search_keyword") or extra.get("search_keyword"),
        "lead_status": source.get("lead_status") or extra.get("lead_status"),
    }
    for key, value in extra.items():
        if value is not None:
            cleanup[key] = value
    return cleanup


def attach_queue_cleanup(result: dict[str, Any], payload: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        result = {"ok": True, "result": result}
    result["queue_cleanup"] = queue_cleanup_payload(payload, **extra)
    return result
