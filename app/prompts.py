from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .schemas import AgentSuggestion


PROMPT_VERSION = "reply_followup_v1"
MAX_RENDERED_PROMPT_CHARS = 12000
OMITTED_MARKER = "[内容已省略]"

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://[^\s)\]}>,，。！？；：]+", re.IGNORECASE)
CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")


@dataclass(frozen=True)
class PromptPackage:
    """可被未来 LLM 客户端直接消费、也可被 run 审计复现的提示词包。"""

    prompt_version: str
    system_prompt: str
    user_prompt: str
    rendered_prompt: str
    reply_language: str
    warnings: list[str]


def build_prompt_package(context: dict[str, Any]) -> PromptPackage:
    """将结构化上下文转换为已脱敏且受长度约束的提示词。"""

    inbound_reply = context.get("inbound_reply") or {}
    reply_language = _detect_reply_language(f"{inbound_reply.get('subject') or ''}\n{inbound_reply.get('body') or ''}")
    system_prompt = _system_prompt(reply_language)
    sections = [
        ("当前达人回复", _current_reply_section(inbound_reply), 3500),
        ("产品信息", _product_section(context.get("product")), 2300),
        ("达人信息", _creator_section(context.get("creator") or {}), 1300),
        ("双向聊天历史", _history_section(context), 2600),
        ("历史事件", _json_section(context.get("recent_events") or []), 800),
        ("开放待办", _json_section(context.get("open_followup_tasks") or []), 600),
    ]
    user_prompt = _render_sections(sections, MAX_RENDERED_PROMPT_CHARS - len(system_prompt) - 16)
    rendered_prompt = f"SYSTEM\n{system_prompt}\n\nUSER\n{user_prompt}"
    if len(rendered_prompt) > MAX_RENDERED_PROMPT_CHARS:
        rendered_prompt = _truncate(rendered_prompt, MAX_RENDERED_PROMPT_CHARS)
        user_prompt = rendered_prompt.split("USER\n", 1)[-1]
    return PromptPackage(
        prompt_version=PROMPT_VERSION,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        rendered_prompt=rendered_prompt,
        reply_language=reply_language,
        warnings=[],
    )


def _system_prompt(reply_language: str) -> str:
    language_instruction = "Use Chinese for the suggested reply." if reply_language == "zh" else "Use English for the suggested reply."
    output_schema = json.dumps(AgentSuggestion.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
    return (
        "You are a creator outreach follow-up assistant. Use only the supplied context, do not invent product facts, "
        "and preserve human review when the information is incomplete or risky. "
        f"{language_instruction} Return only a JSON object conforming to this schema: {output_schema}"
    )


def _current_reply_section(reply: dict[str, Any]) -> str:
    return _json_section({"subject": reply.get("subject"), "body": reply.get("body")})


def _product_section(product: dict[str, Any] | None) -> str:
    if not product:
        return "产品档案缺失。"
    return _json_section(product)


def _creator_section(creator: dict[str, Any]) -> str:
    safe_creator = {
        "handle": creator.get("handle"),
        "display_name": creator.get("display_name"),
        "bio": creator.get("bio"),
        "followers_count": creator.get("followers_count"),
        "recommendation_reason": creator.get("recommendation_reason"),
        "recommended_product_type": creator.get("recommended_product_type"),
        "recommended_collab_type": creator.get("recommended_collab_type"),
    }
    return _json_section(safe_creator)


def _history_section(context: dict[str, Any]) -> str:
    history = {
        "recent_inbound_replies": context.get("recent_inbound_replies") or [],
        "recent_outreach_emails": context.get("recent_outreach_emails") or [],
    }
    return _json_section(history)


def _json_section(value: Any) -> str:
    return _redact(json.dumps(value, ensure_ascii=False, default=str))


def _redact(value: str) -> str:
    value = EMAIL_PATTERN.sub("[已脱敏邮箱]", value)
    return URL_PATTERN.sub("[已脱敏链接]", value)


def _detect_reply_language(value: str) -> str:
    return "zh" if CHINESE_PATTERN.search(value) else "en"


def _render_sections(sections: list[tuple[str, str, int]], budget: int) -> str:
    remaining = max(budget, 0)
    rendered = []
    for title, content, section_limit in sections:
        header = f"## {title}\n"
        if remaining <= len(header):
            break
        available = min(section_limit, remaining - len(header))
        section = f"{header}{_truncate(content, available)}"
        rendered.append(section)
        remaining -= len(section) + 2
    return "\n\n".join(rendered)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= len(OMITTED_MARKER):
        return OMITTED_MARKER[:limit]
    return f"{value[: limit - len(OMITTED_MARKER)]}{OMITTED_MARKER}"
