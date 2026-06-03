from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx


PROMPT_VERSION = "llm-score-v3-us-channel-partner"


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float
    max_retries: int


@dataclass(frozen=True)
class LLMScoreResult:
    ok: bool
    score: int | None = None
    reason: str = ""
    suggestion: str = ""
    model: str = ""
    prompt_version: str = PROMPT_VERSION
    raw_response: str = ""
    error: str = ""


class LLMScoreError(RuntimeError):
    pass


def load_config() -> LLMConfig:
    # The recruitment scorer historically read LLM_* vars, but real deployments
    # only configure the OPENAI_* vars that the social pipeline already uses
    # (see services/xhs_lead_service.py + config.Settings). Fall back to OPENAI_*
    # so company / talent leads score with the same working credentials instead
    # of silently degrading to keyword-only scoring.
    base_url = os.getenv("LLM_BASE_URL", "").strip() or os.getenv("OPENAI_BASE_URL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "").strip()
    timeout_raw = (
        os.getenv("LLM_TIMEOUT_SECONDS", "").strip()
        or os.getenv("OPENAI_TIMEOUT", "").strip()
        or "30"
    )
    retries_raw = os.getenv("LLM_MAX_RETRIES", "2").strip()

    if not api_key:
        raise LLMScoreError("LLM_API_KEY / OPENAI_API_KEY is not configured")
    if not base_url:
        base_url = "https://api.openai.com/v1"
    if not model:
        model = "gpt-4o-mini"

    try:
        timeout_seconds = max(1.0, float(timeout_raw))
    except ValueError:
        timeout_seconds = 30.0
    try:
        max_retries = max(0, int(retries_raw))
    except ValueError:
        max_retries = 2

    return LLMConfig(
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )


def score_lead_with_llm(*, lead_type: str, search_keywords: str, lead: dict[str, Any]) -> LLMScoreResult:
    try:
        config = load_config()
        return _score_with_config(config, lead_type=lead_type, search_keywords=search_keywords, lead=lead)
    except Exception as exc:
        return LLMScoreResult(ok=False, error=str(exc), model=os.getenv("LLM_MODEL", "").strip())


def _score_with_config(
    config: LLMConfig,
    *,
    lead_type: str,
    search_keywords: str,
    lead: dict[str, Any],
) -> LLMScoreResult:
    payload = {
        "model": config.model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _system_prompt(lead_type)},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "prompt_version": PROMPT_VERSION,
                        "output_language": "Simplified Chinese",
                        "lead_type": lead_type,
                        "user_search_keywords": search_keywords,
                        "lead": _compact_lead(lead),
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }

    url = f"{config.base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    last_error = ""
    with httpx.Client(timeout=config.timeout_seconds) as client:
        for attempt in range(config.max_retries + 1):
            try:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                parsed = parse_llm_score(content)
                if _needs_chinese_translation(parsed):
                    parsed = _translate_score_result(client, config, headers, parsed)
                return LLMScoreResult(
                    ok=True,
                    score=parsed["score"],
                    reason=parsed["reason"],
                    suggestion=parsed["suggestion"],
                    model=config.model,
                    raw_response=content,
                )
            except Exception as exc:
                last_error = str(exc)
                if attempt < config.max_retries:
                    time.sleep(min(2.0, 0.35 * (attempt + 1)))

    return LLMScoreResult(ok=False, error=last_error, model=config.model)


def parse_llm_score(content: str) -> dict[str, Any]:
    raw = (content or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMScoreError(f"LLM response is not valid JSON: {exc}") from exc

    missing = [key for key in ("score", "reason", "suggestion") if key not in data]
    if missing:
        raise LLMScoreError(f"LLM response missing required fields: {', '.join(missing)}")

    try:
        score = int(round(float(data["score"])))
    except (TypeError, ValueError) as exc:
        raise LLMScoreError("LLM score must be numeric") from exc

    return {
        "score": max(0, min(100, score)),
        "reason": str(data.get("reason") or "").strip()[:1200],
        "suggestion": str(data.get("suggestion") or "").strip()[:1200],
    }


def _system_prompt(lead_type: str = "company") -> str:
    common = (
        "你是一名跨境电商 BD（商务拓展）线索评分助手。你服务的客户【贵司】是一家集研发、生产、销售于一体的"
        "护理用品企业（已具备 FDA / CE / ISO9001 等资质），当前目标是打开美国 / 北美市场，"
        "寻找当地的【市场渠道 / 销售 / 分销合作商】。请特别注意：贵司要找的是能帮它【把护理用品卖进美国市场】的"
        "渠道方，而不是给我们供货的供应商或代工厂。\n"
        "请把用户的搜索关键词当作业务意图，判断这条被抓取的线索作为【美区市场渠道 / 销售 / 分销合作商】的合作价值。\n"
        "只返回 JSON，且仅包含这三个字段：score、reason、suggestion。\n"
        "reason 和 suggestion 必须用简体中文书写；即使原始数据是英文，也要翻译成自然、专业的简体中文，不要写英文整句。\n"
        "评分档位（按美区渠道 / 分销合作价值打分，请尽量拉开区分度，避免分数都挤在低档）："
        "85-100=明确具备美国 / 北美市场渠道、平台店铺或分销资源，且与个护 / 母婴 / 护理用品品类高度相关，建议优先联系；"
        "70-84=有较明确的美区市场或渠道 / 分销 / 平台运营资源，方向匹配，仅个别合作条件需补充确认；"
        "55-69=有一定跨境 / 电商 / 渠道相关性或局部美区信号，合作潜力中等，建议跟进补充信息；"
        "40-54=相关性较弱或信息不足，合作价值不明确，可观察；"
        "0-39=与美区渠道合作基本无关（如纯招聘 / 培训 / 猎头 / 人力中介噪声，或完全无关行业），不建议跟进。\n"
        "【区分度要求】：命中的正向信号（美区市场、平台店铺、亚马逊 / TikTok Shop 运营、分销 / 代理 / 进口 / 批发零售渠道、"
        "相关品类、仓配 / FBA / 海外仓等）越多、越明确，分数应越高；只命中少量或模糊信号的线索应落在中低档；"
        "不要把大量线索都压在同一档位，应根据证据强弱给出有梯度的分数。\n"
        "【优先合作对象（应给高分）】："
        "美区 Amazon / TikTok Shop US / Walmart / 独立站卖家；"
        "美国 / 北美的分销商、代理商、进口商、批发零售渠道；"
        "拥有母婴 / 个护 / 纸尿裤 / 卫生巾 / 护理用品渠道资源的公司或团队；"
        "具备美国市场运营、仓配、FBA / FBT、海外仓履约能力的合作方。\n"
        "【低优先级 / 应降分对象】："
        "纯工厂 / 源头厂家 / 生产商 / 工贸一体但没有美国渠道；"
        "人力中介、培训机构、猎头、纯招聘等噪声；"
        "只有跨境关键词、却看不出任何美区渠道或合作资源的公司。\n"
        "【工厂 / 生产型企业的条件降权规则（重要）】："
        "工厂、源头厂家、生产型企业与贵司供应端重叠、合作必要性偏低，工厂属性是一个【负面信号，应适度降分】，"
        "但只是适度扣减（相对同等条件的线索约低 10～20 分），不要一刀切打到很低、更不要因为出现“生产/工厂”字样就直接判低分。"
        "在同等条件下，【非工厂、且命中亚马逊运营 / 跨境电商 / 渠道 / 分销等相关正向信号的公司，应高于工厂型公司】。"
        "若工厂同时具备明确的、可对外开放给第三方的美区销售 / 分销渠道（即愿意代理 / 分销【他人品牌】产品，而非只出口自家产品）、"
        "Amazon / TikTok Shop US / Walmart 等平台运营能力、分销资源或明确的对外合作意愿，"
        "才只做较小幅度降权、可保留中高分，并在 reason 中说明其工厂属性带来的风险与需确认项。\n"
        "【工厂 + 做美区生意 的特别谨慎规则（重要，优先级高于上一条）】："
        "当一家公司【明确既有工厂 / 生产能力，又在做美国 / 北美生意】时要尤其谨慎，绝不能因为它“做美区生意”就直接给中高分；"
        "必须先判断它做美区生意的【角色】："
        "（1）若它主要是把【自己工厂生产的同类产品（护理用品 / 个护 / 母婴等）】出口 / 自产自销到美国，"
        "则它与贵司属于【供应端重叠、甚至潜在竞争对手】，不是渠道合作方，应明显降分（通常 40 分及以下），"
        "并在 reason 中点明“疑似自产自销 / 与贵司供应端重叠 / 潜在竞争”；"
        "（2）只有当它是在【代理 / 分销 / 零售第三方品牌产品】、具备可对外开放的美区销售渠道 / 平台店铺 / 经销网络，"
        "且有为贵司这类第三方铺货 / 分销的可能时，才可作为潜在渠道合作方给予中等及以上分数，并仍需标注工厂属性风险。"
        "若信息不足以判断它在美区是“卖自家产品”还是“分销他人产品”，一律从严就低评分，"
        "并在 suggestion 中要求先确认其美区角色（自有品牌出口商 vs 第三方分销渠道）。\n"
        "严禁把这条线索当作招聘场景：reason 与 suggestion 中不得出现"
        "“面试、安排面试、招聘、招聘岗位、招聘需求、入职、录用、岗位匹配、团队匹配、候选人、候选人是否适合任职、任职资格、胜任力”等招聘用语，"
        "一律改用合作视角的表达（合作、对接、渠道、分销、代理、铺货、动销、试单、结算等）。\n"
        "判断依据（reason）应关注：是否有美国 / 北美市场渠道、Amazon / TikTok Shop US / Walmart / 独立站店铺、"
        "分销 / 代理 / 进口 / 批发零售网络；是否有母婴 / 个护 / 护理用品等相关品类经验；"
        "是否具备美国市场运营、仓配、FBA / FBT、海外仓履约能力；是否有联系方式、所在地区与合作意愿；"
        "是否为工厂 / 生产型企业（需降权并提示风险）；以及信息是否充分、有哪些缺口。\n"
        "合作跟进建议（suggestion）应关注：确认其美区渠道 / 平台店铺 / 分销资源覆盖；"
        "确认是否能代理 / 分销 / 铺货贵司的护理用品；确认美国市场动销、仓配与结算方式；"
        "补全联系方式或安排人工复核；绝不要建议面试或招聘动作。\n"
    )
    if lead_type == "talent":
        specific = (
            "本条线索来自人才 / 简历数据，但你要判断的是【此人是否可能成为美区渠道 / 销售 / 分销的个体合作资源】，"
            "请把对方视为个体渠道合作资源 / 运营合作资源 / 分销 BD 资源，"
            "例如：自带美区渠道或分销资源的个体卖家 / 操盘手、Amazon / TikTok Shop US / 独立站运营合作资源、"
            "渠道 BD、掌握美国本地代理 / 进口 / 批发零售资源的自由职业者，"
            "而不是把对方当作求职候选人来评估。\n"
            "若对方只有求职意向、却没有任何可合作、可调动的美区渠道 / 平台运营 / 分销资源证据，给较低分数，"
            "并在 suggestion 中建议先确认其合作意愿与可调动的渠道资源。\n"
        )
    else:
        specific = (
            "本条线索来自公司 / 职位数据，你要判断的是【这家公司是否可能成为贵司护理用品在美区市场的渠道 / 销售 / 分销合作方】，"
            "例如：美区平台卖家 / 品牌方、美国 / 北美的分销商 / 代理商 / 进口商、批发零售渠道、"
            "跨境电商运营 / 服务商、海外仓 / 仓配履约方。\n"
            "若该公司本质是工厂 / 源头厂家 / 生产型企业，请按上面的工厂条件降权规则处理："
            "仅适度降权（约低 10～20 分），并在其同时具备【对外开放的、面向第三方的】美区渠道 / 平台运营 / 分销资源时保留中高分；"
            "同等条件下非工厂且命中相关正向信号的公司应得更高分。\n"
            "特别地：当该公司【既有工厂又在做美区生意】时，务必先判断它在美区是“出口自家产品（供应端重叠 / 潜在竞争）”"
            "还是“分销第三方产品（潜在渠道）”——前者应明显降分，后者方可给中等及以上分；信息不足时从严就低。\n"
        )
    return common + specific


def _needs_chinese_translation(parsed: dict[str, Any]) -> bool:
    text = f"{parsed.get('reason') or ''} {parsed.get('suggestion') or ''}"
    if not text.strip():
        return False
    han_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    latin_words = len(re.findall(r"\b[A-Za-z][A-Za-z-]{2,}\b", text))
    if latin_words < 8:
        return False
    return latin_chars > max(80, han_chars * 2)


def _translate_score_result(
    client: httpx.Client,
    config: LLMConfig,
    headers: dict[str, str],
    parsed: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "model": config.model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You translate lead scoring JSON into Simplified Chinese. "
                    "Return JSON only with exactly score, reason, suggestion. "
                    "Keep score unchanged. Translate reason and suggestion into natural, professional Simplified Chinese. "
                    "Do not keep full English sentences."
                ),
            },
            {"role": "user", "content": json.dumps(parsed, ensure_ascii=False)},
        ],
    }
    response = client.post(f"{config.base_url}/chat/completions", headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()
    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    translated = parse_llm_score(content)
    translated["score"] = parsed["score"]
    return translated


def _compact_lead(lead: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in lead.items():
        if value is None or value == "":
            continue
        if isinstance(value, str):
            compact[key] = value[:3000]
        elif isinstance(value, list):
            compact[key] = [str(item)[:600] for item in value[:12] if item]
        elif isinstance(value, dict):
            compact[key] = {str(k): str(v)[:800] for k, v in list(value.items())[:30] if v not in (None, "")}
        else:
            compact[key] = value
    return compact
