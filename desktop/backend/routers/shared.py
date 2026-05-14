from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from ..config import settings
from ..database import engine


router = APIRouter(prefix="/api/local/shared", tags=["shared"])


def _current_user(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    return user


def _rows(result) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in result]


def _table_exists(conn, table: str) -> bool:
    if engine.dialect.name == "sqlite":
        return bool(
            conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:table"),
                {"table": table},
            ).first()
        )
    return bool(
        conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :table
                """
            ),
            {"table": table},
        ).first()
    )


def _keyword_dashboard_from_db(stale_minutes: int) -> dict[str, Any]:
    with engine.connect() as conn:
        if not _table_exists(conn, "tk_hot_keyword"):
            return {
                "ts": datetime.now(timezone.utc).isoformat(),
                "warning": "tk_hot_keyword table is not available in this database",
                "totals": {
                    "active": 0,
                    "fresh": 0,
                    "uncategorized": 0,
                    "stale_threshold_minutes": stale_minutes,
                },
                "last_run": None,
                "by_category": [],
                "rising_top": [],
                "volume_top": [],
                "history_7d": [],
                "recent_runs": [],
            }

        if engine.dialect.name == "sqlite":
            fresh_sql = """
                SELECT COUNT(*) AS n
                FROM tk_hot_keyword
                WHERE is_active=1
                  AND last_seen_at >= datetime('now', '-' || :minutes || ' minutes')
            """
            history_sql = """
                SELECT date(captured_at) AS d, COUNT(DISTINCT keyword_id) AS n
                FROM keyword_snapshot
                WHERE captured_at >= date('now', '-7 days')
                GROUP BY d
                ORDER BY d
            """
        else:
            fresh_sql = """
                SELECT COUNT(*) AS n
                FROM tk_hot_keyword
                WHERE is_active=1
                  AND NULLIF(last_seen_at, '')::timestamp >= now() - (:minutes * interval '1 minute')
            """
            history_sql = """
                SELECT date(NULLIF(captured_at, '')::timestamp) AS d, COUNT(DISTINCT keyword_id) AS n
                FROM keyword_snapshot
                WHERE NULLIF(captured_at, '')::timestamp >= current_date - interval '7 days'
                GROUP BY d
                ORDER BY d
            """

        total_active = conn.execute(
            text("SELECT COUNT(*) AS n FROM tk_hot_keyword WHERE is_active=1")
        ).scalar_one()
        fresh_count = conn.execute(text(fresh_sql), {"minutes": stale_minutes}).scalar_one()
        uncategorized = conn.execute(
            text("SELECT COUNT(*) AS n FROM tk_hot_keyword WHERE category_hint IS NULL AND is_active=1")
        ).scalar_one()
        by_category = _rows(
            conn.execute(
                text(
                    """
                    SELECT COALESCE(category_hint, '(待分类)') AS cat, COUNT(*) AS n
                    FROM tk_hot_keyword
                    WHERE is_active=1
                    GROUP BY cat
                    ORDER BY n DESC
                    """
                )
            )
        )
        rising_top = _rows(
            conn.execute(
                text(
                    """
                    SELECT id, keyword, category_hint, search_volume, growth_rate,
                           rank_position, last_seen_at
                    FROM tk_hot_keyword
                    WHERE is_active=1 AND growth_rate IS NOT NULL
                    ORDER BY growth_rate DESC
                    LIMIT 8
                    """
                )
            )
        )
        volume_top = _rows(
            conn.execute(
                text(
                    """
                    SELECT id, keyword, category_hint, search_volume, growth_rate, last_seen_at
                    FROM tk_hot_keyword
                    WHERE is_active=1
                    ORDER BY search_volume IS NULL, search_volume DESC
                    LIMIT 8
                    """
                )
            )
        )

        history_7d: list[dict[str, Any]] = []
        if _table_exists(conn, "keyword_snapshot"):
            history_7d = _rows(conn.execute(text(history_sql)))

        last_run = None
        recent_runs: list[dict[str, Any]] = []
        if _table_exists(conn, "scrape_run"):
            last = conn.execute(
                text(
                    """
                    SELECT id, started_at, finished_at, source, region, status,
                           n_added, n_updated, n_errors
                    FROM scrape_run
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
            ).first()
            last_run = dict(last._mapping) if last else None
            recent_runs = _rows(
                conn.execute(
                    text(
                        """
                        SELECT id, started_at, finished_at, source, status,
                               n_added, n_updated, n_errors
                        FROM scrape_run
                        ORDER BY id DESC
                        LIMIT 5
                        """
                    )
                )
            )

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "active": total_active,
            "fresh": fresh_count,
            "uncategorized": uncategorized,
            "stale_threshold_minutes": stale_minutes,
        },
        "last_run": last_run,
        "by_category": by_category,
        "rising_top": rising_top,
        "volume_top": volume_top,
        "history_7d": history_7d,
        "recent_runs": recent_runs,
    }


@router.get("/keywords/dashboard")
def keywords_dashboard(request: Request, stale_minutes: int = 60) -> dict[str, Any]:
    _current_user(request)
    stale_minutes = max(1, min(int(stale_minutes or 60), 24 * 60))
    return _keyword_dashboard_from_db(stale_minutes)


@router.get("/assistant/info")
def assistant_info(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    return {
        "ok": True,
        "ready": bool(settings.openai_api_key),
        "model": settings.openai_model,
        "base_url": settings.openai_base_url,
        "department_code": user.get("department_code"),
        "department_name": user.get("department_name"),
    }


@router.post("/assistant/chat")
async def assistant_chat(request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    user = _current_user(request)
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")

    payload = payload or {}
    messages = payload.get("messages") or []
    if not isinstance(messages, list):
        raise HTTPException(status_code=400, detail="messages must be a list")

    clean_messages = []
    for msg in messages[-20:]:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = str(msg.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            clean_messages.append({"role": role, "content": content[:4000]})
    if not clean_messages:
        raise HTTPException(status_code=400, detail="empty message")

    dept = user.get("department_name") or user.get("department_code") or "未知"
    system = f"""你是 X9 跨境电商 AI 助手，服务于内部的达人线索与建联管理系统（Desktop 工作台）。
当前用户部门：{dept}。回答要简洁、具体、可执行，先给结论再给步骤。

## 系统页面

- **业务看板（Dashboard）**：汇总关键指标 — 达人总数、各 fit 等级分布、建联发送量、近期回复数。
- **采集监控（Collection）**：爬虫任务状态，查看最新爬取结果和错误日志。
- **推荐列表（Recommendations）**：系统根据 TikTok 热搜自动生成的达人推荐，可按品类筛选。
- **达人线索（Creators）**：完整达人库，支持按 fit_level / queue / 关键词筛选，可查看每位达人的详情和历史建联记录。
- **建联管理（Outreach）**：管理外发邮件的草稿、发送、回复状态；支持 AI 润色邮件。
- **TikTok 热搜（Hot Keywords）**：实时热搜词按品类展示，辅助内容选题和达人选择。
- **AI 助手（当前）**：本功能，回答操作和业务问题。

## 关键概念

- **Fit Level（契合度）**：S > A > B > C > D，表示达人与 X9 产品的匹配程度。S/A 级优先建联，C/D 级保持观望。
- **Queue（队列）**：建联优先级，如"主推队列"、"跟进中"、"待冷却"。队列决定了当前是否适合发邮件。
- **建联模板**：预设邮件框架，按达人信息自动填充后可选用 AI 润色。支持 tone（formal/casual/friendly）和语言（中/英/西班牙/日语）。
- **AI 润色**：在建联预览页点击"生成 AI 版本"，基于达人资料生成个性化邮件，可在发送前手动编辑。

## 注意事项

- 你没有写权限，无法代替用户操作；告知操作路径，让用户自己点。
- 不确定的内容直接说"不知道"，不要编造。
- 不要输出任何密码、API key 或敏感凭证。"""
    body = {
        "model": settings.openai_model,
        "messages": [{"role": "system", "content": system}] + clean_messages,
        "temperature": 0.2,
    }
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=settings.openai_timeout) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            data = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"assistant request failed: {exc}") from exc
    if response.status_code >= 400:
        detail = data.get("error", {}).get("message") if isinstance(data, dict) else None
        raise HTTPException(status_code=502, detail=detail or f"assistant HTTP {response.status_code}")

    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        if isinstance(data, dict)
        else ""
    )
    return {
        "ok": True,
        "message": content,
        "model": data.get("model") if isinstance(data, dict) else settings.openai_model,
        "usage": data.get("usage") if isinstance(data, dict) else None,
    }
