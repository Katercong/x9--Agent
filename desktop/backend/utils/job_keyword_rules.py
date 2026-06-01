"""线索评分规则。

评分面向 BD 优先级：不是单纯算文本相关度，而是判断线索是否值得联系、
为什么值得联系、缺什么信息，以及下一步应该怎么做。
"""

from __future__ import annotations

from dataclasses import dataclass

NEXT_ACTIONS = {"contact_now", "find_contact", "review", "observe", "drop"}

CORE_BUSINESS = [
    "跨境销售", "跨境电商运营", "跨境电商", "亚马逊运营", "亚马逊", "amazon",
    "tiktok shop", "tiktokshop", "tiktok电商", "tiktok运营", "temu", "shein",
    "海外市场", "海外市场开发", "出口贸易", "外贸业务", "外贸销售", "国际贸易",
    "跨境贸易", "品牌出海", "海外运营", "跨境营销", "overseas",
    # 贵司护理用品相关品类：命中即视为高相关合作品类（适度加分）
    "护理用品", "护理", "母婴", "婴童", "个护", "个人护理",
    "纸尿裤", "拉拉裤", "卫生巾", "成人护理", "失禁用品",
]

# 渠道 / 分销 / 平台卖家等"帮我们把货卖进美国"的合作角色（已移除工厂/源头厂家等供应端词）
# 使用基础词（分销/代理/渠道/经销）以覆盖 分销商/海外分销/代理商/渠道拓展 等变体，避免同一概念重复计分
PARTNER_ROLE = [
    "分销", "代理", "渠道", "经销", "招商", "合作伙伴", "品牌方",
    "货代", "国际货代", "海外仓", "供应链", "跨境供应链", "贸易商", "一件代发",
    "进口商", "批发", "零售", "卖家", "平台卖家", "独立站",
]

# 业务拓展 / 市场动作信号（已移除招聘/急招/扩招/团队扩张等招聘语境词，避免把招聘当作合作关键词）
ACTIVITY_SIGNAL = [
    "市场开发", "渠道开发", "业务拓展", "平台招商", "招商加盟",
    "新业务", "增长", "开发客户", "负责海外", "负责美区",
]

# 美区市场 / 平台渠道正向信号（增强：Amazon US / TikTok Shop US / Walmart / FBA / FBT / 美区分销等）
MARKET_SIGNAL = [
    "美国", "北美", "美区", "北美市场", "美国市场", "美区市场", "美区拓展",
    "us market", "north america", "usa", "amazon us", "亚马逊美国",
    "tiktok shop us", "walmart", "沃尔玛", "fba", "fbt",
    "美区分销", "美国代理", "美国渠道", "北美渠道",
]

# 工厂判定不再纳入正向加分（改由 FACTORY_SIGNAL 做条件降权）
QUALITY_SIGNAL = [
    "品牌", "自有品牌", "团队", "公司规模", "成立",
    "出口", "库存", "仓储", "履约", "店铺", "旗舰店",
]

# 工厂 / 生产型企业降权信号：与贵司供应端重叠、合作必要性低，默认不是优先合作商
FACTORY_SIGNAL = [
    "工厂", "源头厂家", "生产厂家", "生产基地", "生产", "制造商", "制造",
    "工贸一体", "代工", "oem", "odm", "加工厂",
]

# 平台 / 渠道运营能力（用于判断工厂是否同时具备"强美区渠道"，不单独计分）
PLATFORM_CHANNEL = [
    "amazon", "亚马逊", "tiktok shop", "tiktokshop", "tiktok", "walmart", "沃尔玛",
    "独立站", "shopify", "ebay", "速卖通", "temu", "shein",
]

TALENT_CORE = [
    "跨境", "跨境电商", "外贸", "亚马逊", "amazon", "tiktok", "tiktok shop",
    "temu", "shein", "海外", "美区", "北美", "fba", "独立站",
    "护理用品", "母婴", "个护", "纸尿裤", "卫生巾",
]

TALENT_PARTNER = [
    "销售", "业务", "渠道", "招商", "bd", "商务", "运营", "店长", "经理",
    "主管", "总监", "负责人", "合伙人", "创业", "资源", "分销",
]

NEGATIVE_TALENT = [
    "it经理", "erp", "软件工程师", "信息部", "金融研究", "行政专员", "人事专员",
    "生产经理", "厂长", "品质经理", "会计", "出纳", "司机",
]


@dataclass(frozen=True)
class MatchResult:
    score: int
    matches: list[str]


def _norm(text: str) -> str:
    return (text or "").lower().strip()


def _hits(text: str, keywords: list[str], limit: int = 6) -> list[str]:
    n = _norm(text)
    found: list[str] = []
    for kw in keywords:
        if kw.lower() in n and kw not in found:
            found.append(kw)
            if len(found) >= limit:
                break
    return found


def _score_bucket(text: str, keywords: list[str], points: int, cap: int) -> MatchResult:
    matches = _hits(text, keywords)
    return MatchResult(min(len(matches) * points, cap), matches)


def _quality(has_name: bool, has_core_payload: bool, has_contact: bool, suspicious: bool = False) -> str:
    if suspicious or not has_name:
        return "low"
    if has_core_payload and has_contact:
        return "high"
    if has_core_payload:
        return "medium"
    return "low"


def _tier(score: int) -> str | None:
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return None


def _action(score: int, has_contact: bool, quality: str, risk: int = 0) -> str:
    if risk <= -30 or quality == "low":
        return "drop" if score < 45 else "review"
    if score >= 80 and has_contact:
        return "contact_now"
    if score >= 65 and not has_contact:
        return "find_contact"
    if score >= 45:
        return "review"
    return "observe"


def score_text(text: str) -> tuple[int, list[str]]:
    """Backward-compatible keyword score used by older docs/scripts."""
    fit = _score_bucket(text, CORE_BUSINESS, 15, 45)
    partner = _score_bucket(text, PARTNER_ROLE, 10, 30)
    market = _score_bucket(text, MARKET_SIGNAL, 5, 15)
    return fit.score + partner.score + market.score, fit.matches + partner.matches + market.matches


def score_company(
    company_name: str = "",
    industry: str = "",
    company_description: str = "",
    size_range: str = "",
    city: str = "",
    jd_titles: list[str] | None = None,
    jd_descriptions: list[str] | None = None,
    has_contact: bool = False,
    risk: int = 0,
) -> dict:
    corpus = " ".join(
        filter(None, [company_name, industry, company_description, size_range, city] + (jd_titles or []) + (jd_descriptions or []))
    )
    # 命中越多正向信号分越高，拉开区分度（适度加分）
    fit = _score_bucket(corpus, CORE_BUSINESS, 12, 34)
    partner = _score_bucket(corpus, PARTNER_ROLE, 10, 28)
    activity = _score_bucket(corpus, ACTIVITY_SIGNAL + (jd_titles or []), 5, 15)
    market = _score_bucket(corpus, MARKET_SIGNAL, 8, 20)
    quality_signal = _score_bucket(corpus, QUALITY_SIGNAL, 3, 10)
    contact_score = 15 if has_contact else 0

    suspicious = any(token in _norm(company_name)[:12] for token in ("自我评价", "工作经历", "求职意向", "教育经历"))
    has_core_payload = bool(industry or company_description or jd_titles or jd_descriptions)
    data_quality = _quality(bool(company_name), has_core_payload, has_contact, suspicious=suspicious)
    if data_quality == "low":
        risk -= 12

    # 工厂条件降权：工厂/生产型企业与贵司供应端重叠，合作必要性偏低，作为负面信号【适度降分】（不一刀切）。
    # 若同时具备美区市场信号 + 渠道/平台运营能力（强美区渠道），仅轻微降权、保留中高分；
    # 否则适度降权，但不再强制限制最高分，仍允许凭借其他正向信号拉开区分度。
    factory_hits = _hits(corpus, FACTORY_SIGNAL)
    has_channel_capability = bool(partner.matches) or bool(_hits(corpus, PLATFORM_CHANNEL))
    strong_us_channel = bool(market.matches) and has_channel_capability
    factory_note = ""
    if factory_hits:
        if strong_us_channel:
            risk -= 5
            factory_note = "含工厂/生产属性（供应端重叠，但有美区渠道信号，需复核合作角色）"
        else:
            risk -= 12
            factory_note = "含工厂/生产属性（供应端重叠，已适度降权）"

    breakdown = {
        "fit": fit.score,
        "partner": partner.score,
        "activity": activity.score,
        "contact": contact_score,
        "quality": quality_signal.score,
        "market": market.score,
        "risk": risk,
    }
    # 工厂仅通过 risk 适度降权，不再强制限制最高分，保留与其他正向信号的区分度
    score = max(0, min(100, sum(breakdown.values())))
    tags = fit.matches + partner.matches + activity.matches + market.matches
    cooperation_type = _company_cooperation_type(tags, corpus)
    next_action = _action(score, has_contact, data_quality, risk)
    tier = _tier(score)
    if score >= 80 and not has_contact:
        tier = "B"

    reason = _reason(tags, has_contact, data_quality, next_action, factory_note)
    return {
        "score": score,
        "tier": tier,
        "matched_keywords": tags[:12],
        "us_market": bool(market.matches),
        "cooperation_type": cooperation_type,
        "lead_tags": tags[:12],
        "score_breakdown": breakdown,
        "score_reason": reason,
        "data_quality": data_quality,
        "next_action": next_action,
    }


def score_talent_profile(data: dict) -> dict:
    text = " ".join(
        str(data.get(k) or "")
        for k in ("desired_title", "raw_summary", "major", "experience", "city", "notes")
    )
    core = _score_bucket(text, TALENT_CORE, 10, 30)
    partner = _score_bucket(text, TALENT_PARTNER, 7, 25)
    market = _score_bucket(text, MARKET_SIGNAL, 5, 10)
    negative = _score_bucket(text, NEGATIVE_TALENT, -15, 0)

    exp = _norm(str(data.get("experience") or ""))
    seniority = 0
    if any(k in exp for k in ("8年", "10年", "8年以上", "10年以上")):
        seniority = 12
    elif any(k in exp for k in ("5年", "5-8", "6年", "7年")):
        seniority = 9
    elif any(k in exp for k in ("3年", "3-5", "4年")):
        seniority = 5

    has_contact = bool(data.get("contact_email") or data.get("contact_phone") or data.get("wechat"))
    contact_score = 10 if has_contact else 0
    active = 8 if any(k in _norm(text) for k in ("离职", "正在找工作", "自由职业", "合作", "合伙", "创业")) else 0
    risk = -20 if negative.matches and not core.matches else 0
    has_core_payload = bool(data.get("desired_title") or data.get("raw_summary"))
    data_quality = _quality(bool(data.get("desired_title") or data.get("name_masked")), has_core_payload, has_contact)

    breakdown = {
        "fit": core.score,
        "partner": partner.score,
        "activity": active,
        "contact": contact_score,
        "quality": seniority,
        "market": market.score,
        "risk": risk,
    }
    score = max(0, min(100, sum(breakdown.values())))
    tags = core.matches + partner.matches + market.matches
    cooperation_type = _talent_cooperation_type(tags, text)
    next_action = _action(score, has_contact, data_quality, risk)
    tier = _tier(score)
    if score >= 80 and not has_contact:
        tier = "B"

    return {
        "score": score,
        "tier": tier,
        "matched_keywords": tags[:12],
        "cooperation_type": cooperation_type,
        "lead_tags": tags[:12],
        "score_breakdown": breakdown,
        "score_reason": _reason(tags, has_contact, data_quality, next_action),
        "data_quality": data_quality,
        "next_action": next_action,
    }


def _company_cooperation_type(tags: list[str], text: str) -> str:
    n = _norm(text)
    if any(k in n for k in ("货代", "物流", "海外仓", "仓储", "fba", "fbt")):
        return "service_provider"
    # 先识别渠道/品牌卖家：工厂若同时具备渠道/平台信号，应归为渠道方而非纯供应端
    if any(k in n for k in ("分销", "代理", "渠道", "招商", "经销", "进口", "批发", "零售")):
        return "channel_partner"
    if any(k in n for k in ("品牌", "店铺", "卖家", "商家", "独立站", "amazon", "亚马逊", "tiktok", "walmart")):
        return "brand_seller"
    # 没有任何渠道/品牌信号的工厂/生产型企业 → 供应端（降权对象）
    if any(k in n for k in ("工厂", "生产", "供应商", "源头厂家", "工贸", "制造", "代工", "oem", "odm")):
        return "supplier"
    if tags:
        return "prospect"
    return "unknown"


def _talent_cooperation_type(tags: list[str], text: str) -> str:
    n = _norm(text)
    if any(k in n for k in ("渠道", "招商", "销售", "业务", "bd", "商务")):
        return "individual_bd"
    if any(k in n for k in ("运营", "店长", "亚马逊", "tiktok")):
        return "operator"
    if any(k in n for k in ("供应链", "货代", "海外仓")):
        return "supply_chain"
    if tags:
        return "individual_partner"
    return "unknown"


def _reason(tags: list[str], has_contact: bool, data_quality: str, next_action: str, factory_note: str = "") -> str:
    parts: list[str] = []
    if tags:
        parts.append("命中 " + " / ".join(tags[:4]))
    else:
        parts.append("暂未命中核心合作信号")
    if factory_note:
        parts.append(factory_note)
    parts.append("有联系方式" if has_contact else "缺联系方式")
    if data_quality == "low":
        parts.append("数据需复核")
    action_label = {
        "contact_now": "建议立即触达",
        "find_contact": "建议先补联系方式",
        "review": "建议人工复核",
        "observe": "可观察",
        "drop": "建议放弃",
    }.get(next_action, next_action)
    parts.append(action_label)
    return "；".join(parts)
