"""Keyword tables, evidence sources, and category-fit rules for v3.

Reorganised vs v2:
* feminine_care now resolves to a *granular SKU bucket* via
  `FEMININE_PRODUCT_BUCKETS` so the recommendation engine can answer
  "which product type" instead of just "which vertical".
* Evidence sources are tracked per hit so the rec engine can tell strong
  evidence (bio/title/description) from weak (search_keyword) and surface
  search_keyword_only_match correctly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Evidence sources — strong vs medium vs weak
# ---------------------------------------------------------------------------
STRONG_EVIDENCE_SOURCES = ("bio", "source_video_title", "source_video_description")
MEDIUM_EVIDENCE_SOURCES = ("hashtags", "external_links_text")
WEAK_EVIDENCE_SOURCES = ("search_keyword",)

ALL_EVIDENCE_SOURCES = STRONG_EVIDENCE_SOURCES + MEDIUM_EVIDENCE_SOURCES + WEAK_EVIDENCE_SOURCES


# ---------------------------------------------------------------------------
# Feminine-care: strong + adjacent + format keywords
# ---------------------------------------------------------------------------
FEMININE_STRONG_KEYWORDS: list[tuple[str, int, str]] = [
    # phrase, points, normalized tag
    ("feminine hygiene", 35, "feminine_hygiene"),
    ("feminine care", 35, "feminine_care"),
    ("period routine", 35, "period_routine"),
    ("period tips", 35, "period_tips"),
    ("period products", 35, "period_products"),
    ("panty liners", 30, "panty_liner"),
    ("panty liner", 30, "panty_liner"),
    ("sanitary pads", 30, "sanitary_pad"),
    ("sanitary pad", 30, "sanitary_pad"),
    ("liners", 30, "panty_liner"),
    ("liner", 30, "panty_liner"),
    ("pads", 30, "sanitary_pad"),
    ("pad", 30, "sanitary_pad"),
    ("menstrual", 30, "menstrual_care"),
    ("period", 25, "period_topic"),
    ("women health", 25, "women_health"),
    ("women wellness", 25, "women_wellness"),
]
FEMININE_STRONG_CAP = 60

FEMININE_ADJACENT_KEYWORDS: list[tuple[str, int, str]] = [
    ("self care", 12, "self_care"),
    ("body care", 12, "self_care"),
    ("wellness", 12, "wellness"),
    ("skincare", 10, "skincare"),
    ("skin", 10, "skincare"),
    ("beauty", 10, "beauty"),
    ("lifestyle", 8, "lifestyle"),
    ("girly", 8, "girly"),
    ("girl", 8, "girly"),
    ("makeup", 5, "makeup"),
    ("fashion", 5, "fashion"),
]
FEMININE_ADJACENT_CAP = 25

FEMININE_FORMAT_KEYWORDS: list[tuple[str, int, str]] = [
    ("ugc creator", 15, "ugc_creator"),
    ("ugc", 15, "ugc_creator"),
    ("reviews", 12, "review_style"),
    ("review", 12, "review_style"),
    ("unboxings", 12, "unboxing_style"),
    ("unboxing", 12, "unboxing_style"),
    ("hauls", 12, "deal_finds_style"),
    ("haul", 12, "deal_finds_style"),
    ("finds", 12, "deal_finds_style"),
    ("routines", 10, "routine_style"),
    ("routine", 10, "routine_style"),
    ("tips", 10, "routine_style"),
    ("asmr demo", 8, "asmr_demo_style"),
    ("asmr", 8, "asmr_demo_style"),
    ("live", 6, "live_selling_style"),
]
FEMININE_FORMAT_CAP = 15

FEMININE_SEARCH_KEYWORDS = (
    "sanitary pads", "menstrual care", "period pads", "panty liner", "period care",
)
FEMININE_SEARCH_KEYWORD_BONUS = 5

# ---------------------------------------------------------------------------
# Granular feminine-care product buckets — these decide
# `recommended_product_type` when feminine fit wins.
# Each bucket scans the same text for its own signature keywords.
# ---------------------------------------------------------------------------
FEMININE_PRODUCT_BUCKETS: dict[str, list[str]] = {
    "feminine_care_daily_liner": ["panty liner", "liner", "daily hygiene", "everyday freshness"],
    "period_care_pad": ["sanitary pad", "period pad", "period products", "menstrual", "period routine"],
    "sensitive_skin_care": ["sensitive skin", "fragrance free", "hypoallergenic", "soft cotton"],
    "travel_hygiene_pack": ["travel kit", "on the go", "purse essentials", "school essentials", "travel hygiene"],
    "postpartum_mom_care": ["postpartum", "after birth", "new mom", "maternity pads"],
    "teen_first_period_care": ["first period", "teen", "back to school period", "period education"],
    "wellness_self_care_bundle": ["self care", "body care", "wellness", "feminine wellness"],
}


# ---------------------------------------------------------------------------
# Other categories
# ---------------------------------------------------------------------------
PET_CARE_KEYWORDS = [
    "dog diaper", "dog diapers", "male dog wrap", "female dog diaper",
    "puppy training", "potty training", "senior dog", "dog hygiene",
    "dog mom", "dog dad", "pet care", "indoor dog", "pet cleanup", "pet accident",
]
HOME_CARE_KEYWORDS = [
    "underpad", "underpads", "bed pad", "bed protection", "disposable underpad",
    "home care", "caregiver", "elder care", "incontinence", "postpartum",
    "pet accident", "odor control", "home hygiene", "cleaning", "home routine",
]
ADULT_CARE_KEYWORDS = [
    "incontinence", "bladder leaks", "adult diaper", "adult diapers", "adult diaper pants",
    "caregiver", "elder care", "nursing care", "mobility care",
    "postpartum recovery", "postpartum care", "women health", "pelvic floor",
    "nurse", "cna", "healthcare",
]
MOM_BABY_KEYWORDS = [
    "baby diaper", "baby diapers", "newborn", "toddler", "diaper review",
    "breastfeeding", "nursing pads", "breast pads", "new mom", "mom life",
    "motherhood", "postpartum", "baby essentials", "diaper bag", "mom hacks", "parenting",
]
HEALTH_MASK_KEYWORDS = [
    "kn95", "disposable mask", "mask", "protection",
    "daily protection", "commute protection", "school protection", "office protection",
]

OTHER_CATEGORY_HIT_POINTS = 20

PRODUCT_CATEGORIES = (
    "feminine_care", "pet_care", "home_care", "adult_care",
    "mom_baby", "health_mask",
)


# ---------------------------------------------------------------------------
# Content format (max 100, scored independently)
# ---------------------------------------------------------------------------
CONTENT_FORMAT_KEYWORDS: list[tuple[str, int, str]] = [
    ("ugc creator", 35, "ugc_creator"),
    ("ugc", 35, "ugc_creator"),
    ("reviews", 30, "review_style"),
    ("review", 30, "review_style"),
    ("unboxings", 30, "unboxing_style"),
    ("unboxing", 30, "unboxing_style"),
    ("hauls", 30, "deal_finds_style"),
    ("haul", 30, "deal_finds_style"),
    ("finds", 30, "deal_finds_style"),
    ("how to", 25, "educational_style"),
    ("routines", 25, "routine_style"),
    ("routine", 25, "routine_style"),
    ("tips", 25, "routine_style"),
    ("skincare routine", 20, "routine_style"),
    ("beauty tips", 20, "routine_style"),
    ("asmr", 20, "asmr_demo_style"),
    ("live selling", 15, "live_selling_style"),
    ("live", 15, "live_selling_style"),
    ("comedy", 5, "entertainment_style"),
    ("meme", 5, "entertainment_style"),
    ("entertainment", 5, "entertainment_style"),
]


# ---------------------------------------------------------------------------
# Commerce signal (can lift low product-fit creators into low-cost tests)
# ---------------------------------------------------------------------------
COMMERCE_SIGNAL_KEYWORDS: list[tuple[str, int, str]] = [
    ("tiktok shop", 35, "tiktok_shop_seller"),
    ("shop my", 35, "shop_my_link"),
    ("shop link", 30, "shop_link"),
    ("storefront", 30, "storefront"),
    ("amazon storefront", 35, "amazon_storefront"),
    ("amazon finds", 35, "deal_finds_style"),
    ("amazon must haves", 35, "deal_finds_style"),
    ("tiktok made me buy", 35, "deal_finds_style"),
    ("affiliate", 35, "affiliate_creator"),
    ("commission", 30, "affiliate_creator"),
    ("discount code", 30, "coupon_creator"),
    ("coupon code", 30, "coupon_creator"),
    ("promo code", 30, "coupon_creator"),
    ("link in bio", 25, "link_in_bio"),
    ("ltk", 25, "storefront"),
    ("shopltk", 25, "storefront"),
    ("deals", 25, "deal_finds_style"),
    ("deal", 25, "deal_finds_style"),
    ("finds", 25, "deal_finds_style"),
    ("haul", 25, "haul_style"),
    ("hauls", 25, "haul_style"),
    ("unboxing", 25, "unboxing_style"),
    ("unboxings", 25, "unboxing_style"),
    ("review", 20, "review_style"),
    ("reviews", 20, "review_style"),
    ("pr friendly", 30, "collab_friendly"),
    ("collab pr", 30, "collab_friendly"),
    ("collab", 25, "collab_friendly"),
    ("pr", 20, "collab_friendly"),
    ("business email", 20, "business_contact"),
    ("ugc creator", 30, "ugc_creator"),
    ("ugc", 30, "ugc_creator"),
    ("live selling", 30, "live_selling_style"),
]


# ---------------------------------------------------------------------------
# Audience bonuses (capped at 10 — only an *extra* nudge, never primary)
# ---------------------------------------------------------------------------
AUDIENCE_RULES: list[tuple[str, int, list[str]]] = [
    ("women_wellness_audience", 5, ["women health", "women wellness", "wellness", "feminine"]),
    ("new_mom_audience", 5, ["new mom", "mom life", "motherhood", "newborn"]),
    ("postpartum_audience", 5, ["postpartum"]),
    ("pet_owner_audience", 5, ["pet care", "pet mom", "pet dad", "pet owner"]),
    ("dog_owner_audience", 5, ["dog mom", "dog dad", "puppy", "senior dog"]),
    ("caregiver_audience", 5, ["caregiver", "elder care", "nursing care", "cna", "nurse"]),
    ("young_women_audience", 4, ["girly", "girl", "young women", "college girl"]),
    ("home_cleaning_audience", 4, ["home routine", "cleaning", "home hygiene", "odor control"]),
    ("amazon_shopper_audience", 3, ["amazon finds", "amazon must haves", "tiktok made me buy"]),
    ("budget_shopper_audience", 2, ["budget", "deal", "drugstore", "affordable"]),
]
AUDIENCE_BONUS_CAP = 10


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
PERSONAL_EMAIL_DOMAINS = {
    "gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "yahoo.co.uk",
    "icloud.com", "me.com", "live.com", "aol.com", "proton.me", "protonmail.com",
    "msn.com", "qq.com", "163.com", "126.com",
}
AGENCY_EMAIL_HINTS = (
    "management", "talent", "agency", "select", "undercurrent",
    "starline", "mgmt", "studio", "collective", "iala",
)
SUSPICIOUS_LOCAL_PARTS = {"info", "no-reply", "noreply", "test", "example", "support"}


# ---------------------------------------------------------------------------
# Risk tags + thresholds
# ---------------------------------------------------------------------------
RISK_TAG_DEFINITIONS = [
    "search_keyword_only_match",
    "weak_category_evidence",
    "missing_email",
    "unknown_content_format",
    "low_product_fit",
    "macro_low_fit",
    "manual_review_required",
    "conflicting_category_signals",
    "product_fit_uncertain_but_commerce_strong",
]

POSITIVE_TAG_DEFINITIONS = [
    "has_email",
    "has_alt_contact",
    "high_followers",
    "medium_followers",
    "micro_creator",
    "strong_feminine_care_fit",
    "medium_feminine_care_fit",
    "high_commercial_value",
    "sample_collab_candidate",
    "affiliate_candidate",
    "brand_awareness_candidate",
    "strong_commerce_signal",
    "commerce_test_candidate",
    "repeat_target_tag_signal",
    "same_keyword_multi_video",
    "multi_keyword_discovery",
    "repeat_commerce_signal",
    "repeat_feminine_care_signal",
    "repeat_pet_care_signal",
    "repeat_home_care_signal",
    "repeat_adult_care_signal",
    "repeat_mom_baby_signal",
    "repeat_health_mask_signal",
]

GENERIC_PAGE_TITLE = "TikTok - Make Your Day"


# ---------------------------------------------------------------------------
# Follower scale curve (spec section 8)
# ---------------------------------------------------------------------------
def follower_scale_score(followers: int | None) -> int:
    f = followers or 0
    if f < 10_000:
        return 20
    if f < 50_000:
        return 40
    if f < 200_000:
        return 60
    if f < 1_000_000:
        return 80
    return 90


# ---------------------------------------------------------------------------
# Cutoffs
# ---------------------------------------------------------------------------
def fit_level_for(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def primary_fit_label(score: int) -> str:
    if score >= 80:
        return "Strong Fit"
    if score >= 60:
        return "Good Fit"
    if score >= 40:
        return "Medium Fit"
    if score >= 20:
        return "Weak Fit"
    return "No Clear Fit"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@dataclass
class KeywordHit:
    keyword: str
    points: int
    tag_code: str
    evidence_source: str
    evidence_snippet: str


_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize(text: str | None) -> str:
    if not text:
        return ""
    return _NON_WORD.sub(" ", text.lower()).strip()


def phrase_present(needle: str, haystack_norm: str) -> bool:
    n = needle.lower().strip()
    if not n:
        return False
    return f" {n} " in f" {haystack_norm} "


def find_keyword_hits(table: list[tuple[str, int, str]], sources: dict[str, str]) -> list[KeywordHit]:
    hits: list[KeywordHit] = []
    for src, raw in sources.items():
        h = normalize(raw)
        if not h:
            continue
        for kw, pts, tag in table:
            if phrase_present(kw, h):
                hits.append(KeywordHit(kw, pts, tag, src, _snip(raw, kw)))
    return hits


def find_simple_keywords(keywords: list[str], sources: dict[str, str]) -> list[KeywordHit]:
    table = [(k, 1, k.replace(" ", "_")) for k in keywords]
    return find_keyword_hits(table, sources)


def _snip(raw: str, needle: str, window: int = 50) -> str:
    if not raw:
        return ""
    idx = raw.lower().find(needle.lower())
    if idx < 0:
        return raw[:window]
    start = max(0, idx - window // 2)
    end = min(len(raw), idx + len(needle) + window // 2)
    return raw[start:end].strip()


def cap(value: int, ceiling: int) -> int:
    return min(value, ceiling)


def classify_email(email: str | None) -> dict:
    out = {"kind": "missing", "is_valid": False, "is_suspect": False, "domain": ""}
    if not email or "@" not in email:
        return out
    local, _, domain = email.lower().strip().partition("@")
    out["domain"] = domain
    if not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", email.lower().strip()):
        out["is_suspect"] = True
        out["kind"] = "suspect"
        return out
    out["is_valid"] = True
    if local in SUSPICIOUS_LOCAL_PARTS:
        out["is_suspect"] = True
    if domain in PERSONAL_EMAIL_DOMAINS:
        out["kind"] = "personal"
    elif any(h in domain for h in AGENCY_EMAIL_HINTS):
        out["kind"] = "agency"
    else:
        out["kind"] = "brand_domain"
    return out


def pick_feminine_product_bucket(text_norm: str, fallback: str = "feminine_care_daily_liner") -> str:
    """Walk the bucket dictionary in declaration order and return the first
    one whose signature phrases match. Falls back to daily_liner — the
    everyday SKU — when feminine fit is positive but no bucket matched."""
    for bucket, phrases in FEMININE_PRODUCT_BUCKETS.items():
        for phrase in phrases:
            if phrase_present(phrase, text_norm):
                return bucket
    return fallback
