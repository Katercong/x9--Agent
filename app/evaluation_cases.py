from __future__ import annotations

from typing import Any


ROUTE_EXPECTATIONS = {
    "interested": ("send_campaign_details", "pending_followup", True),
    "need_more_info": ("send_campaign_details", "pending_followup", True),
    "negotiation": ("clarify_terms", "pending_followup", True),
    "not_interested": ("acknowledge_and_close", "dropped", True),
    "unclear": ("ask_clarifying_question", "pending_followup", True),
}


def _case(case_id: str, category: str, body: str, language: str) -> dict[str, Any]:
    action, status, requires_human_review = ROUTE_EXPECTATIONS[category]
    return {
        "id": case_id,
        "language": language,
        "context": {
            "reply_category": category,
            "product": {
                "name": "Aurora Wireless Earbuds",
                "product_type": "wireless earbuds",
                "summary": "Noise-cancelling earbuds for everyday commuting.",
                "selling_points": ["active noise cancellation", "30-hour battery"],
                "target_audience": "commuters and lifestyle audiences",
                "collaboration_requirements": "Short-form product demonstration.",
                "forbidden_claims": ["medical benefit"],
            },
            "creator": {
                "id": f"synthetic_{case_id}",
                "handle": f"creator_{case_id}",
                "display_name": "Synthetic Creator",
                "bio": "Lifestyle and consumer technology creator.",
                "followers_count": 82000,
                "recommendation_reason": "Audience engages with practical lifestyle products.",
                "recommended_product_type": "wireless earbuds",
                "recommended_collab_type": "product review",
            },
            "inbound_reply": {"id": f"reply_{case_id}", "subject": "Collaboration", "body": body},
            "recent_inbound_replies": [],
            "recent_outreach_emails": [],
            "recent_events": [],
            "open_followup_tasks": [],
        },
        "expected": {
            "reply_category": category,
            "next_action": action,
            "suggested_status": status,
            "requires_human_review": requires_human_review,
        },
    }


PILOT_SPECS = (
    ("interested_en_01", "interested", "This sounds like a good fit. I would be happy to collaborate.", "en"),
    ("interested_en_02", "interested", "Yes, I am interested in reviewing these earbuds.", "en"),
    ("interested_en_03", "interested", "I like the product direction and would love to hear the next steps.", "en"),
    ("interested_zh_01", "interested", "这个产品方向很适合我的受众，我愿意合作。", "zh"),
    ("interested_zh_02", "interested", "我对这次合作感兴趣，可以继续沟通。", "zh"),
    ("need_info_en_01", "need_more_info", "Could you send the campaign brief and key deliverables?", "en"),
    ("need_info_en_02", "need_more_info", "Please share more information about the timeline and content requirements.", "en"),
    ("need_info_en_03", "need_more_info", "I need the product details before I can confirm interest.", "en"),
    ("need_info_zh_01", "need_more_info", "请先提供合作详情、时间线和内容要求。", "zh"),
    ("need_info_zh_02", "need_more_info", "可以介绍一下产品卖点和合作形式吗？", "zh"),
    ("negotiation_en_01", "negotiation", "What is the budget range for one short video?", "en"),
    ("negotiation_en_02", "negotiation", "I am open to it, but my rate depends on the deliverables.", "en"),
    ("negotiation_en_03", "negotiation", "Can we discuss commission, samples, and usage rights?", "en"),
    ("negotiation_zh_01", "negotiation", "可以合作，不过我想先确认预算和佣金。", "zh"),
    ("negotiation_zh_02", "negotiation", "样品和视频使用权限的条款需要再谈一下。", "zh"),
    ("decline_en_01", "not_interested", "Thank you, but I am not interested in this campaign.", "en"),
    ("decline_en_02", "not_interested", "No thanks, this is not a fit for my channel right now.", "en"),
    ("decline_zh_01", "not_interested", "谢谢邀请，但这次我暂不考虑合作。", "zh"),
    ("decline_zh_02", "not_interested", "感谢联系，这个产品目前不适合我的内容方向。", "zh"),
    ("unclear_en_01", "unclear", "Maybe. What did you have in mind?", "en"),
    ("unclear_en_02", "unclear", "I saw the message. Can you clarify?", "en"),
    ("unclear_en_03", "unclear", "Let me know what you need from me.", "en"),
    ("unclear_zh_01", "unclear", "我看到了，可以再说明一下吗？", "zh"),
    ("unclear_zh_02", "unclear", "这个合作具体是怎样的？", "zh"),
)


def get_suite(name: str) -> list[dict[str, Any]]:
    if name != "pilot":
        raise ValueError(f"unknown evaluation suite: {name}")
    return [_case(f"pilot_{case_id}", category, body, language) for case_id, category, body, language in PILOT_SPECS]
