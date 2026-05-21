"""Idempotent v3 migration.

* Creates every table via SQLAlchemy metadata.
* Seeds tag_definitions with the v3 catalog (risk + positive + product
  category + content vertical + content format + collaboration tags).
* Safe to run multiple times; INSERT OR IGNORE on tag rows.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from desktop.backend.database import engine, init_db  # noqa: E402


TAGS = [
    # risk
    *[(c, "risk") for c in [
        "search_keyword_only_match", "weak_category_evidence", "missing_email",
        "unknown_content_format", "low_product_fit", "macro_low_fit",
        "manual_review_required", "conflicting_category_signals",
    ]],
    # positive
    *[(c, "positive") for c in [
        "has_email", "has_alt_contact", "high_followers", "medium_followers", "micro_creator",
        "strong_feminine_care_fit", "medium_feminine_care_fit",
        "high_commercial_value", "sample_collab_candidate",
        "affiliate_candidate", "brand_awareness_candidate",
        "strong_commerce_signal", "commerce_test_candidate",
        "repeat_target_tag_signal", "same_keyword_multi_video",
        "multi_keyword_discovery", "repeat_commerce_signal",
        "repeat_feminine_care_signal", "repeat_pet_care_signal",
        "repeat_home_care_signal", "repeat_adult_care_signal",
        "repeat_mom_baby_signal", "repeat_health_mask_signal",
    ]],
    # product category
    *[(c, "product_category") for c in [
        "feminine_care", "pet_care", "home_care", "adult_care",
        "mom_baby", "health_mask", "general_lifestyle",
    ]],
    # feminine product fit (granular SKU buckets)
    *[(c, "product_fit") for c in [
        "feminine_care_daily_liner", "period_care_pad", "sensitive_skin_care",
        "travel_hygiene_pack", "postpartum_mom_care", "teen_first_period_care",
        "wellness_self_care_bundle",
    ]],
    # content vertical
    *[(c, "content_vertical") for c in [
        "period_education_creator", "women_wellness_creator",
        "beauty_lifestyle_creator", "skin_body_care_creator", "self_care_creator",
        "mom_creator", "postpartum_creator", "pet_creator", "dog_creator",
        "home_cleaning_creator", "caregiver_creator", "general_lifestyle_creator",
    ]],
    # content format
    *[(c, "content_format") for c in [
        "ugc_creator", "review_style", "unboxing_style", "deal_finds_style",
        "routine_style", "educational_style", "problem_solution_style",
        "asmr_demo_style", "live_selling_style", "entertainment_style",
    ]],
    # collaboration
    *[(c, "collaboration") for c in [
        "email_available", "email_missing", "email_suspect", "multiple_emails",
        "personal_email", "agency_email", "brand_domain_email",
        "collab_friendly", "sample_friendly", "high_cost_risk",
        "brand_awareness_only", "conversion_focused",
    ]],
]


def main() -> int:
    init_db()
    seeded = 0
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_creators_current_status ON creators (current_status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_creators_store_assigned ON creators (store_assigned)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_creators_owner_bd ON creators (owner_bd)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_creators_collected_at ON creators (collected_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_raw_observations_collected_at ON raw_observations (collected_at)"))
        conn.execute(text("UPDATE creators SET collected_at = COALESCE(collected_at, created_at) WHERE collected_at IS NULL"))
        for code, t in TAGS:
            if engine.dialect.name == "sqlite":
                conn.execute(
                    text("""
                    INSERT OR IGNORE INTO tag_definitions (tag_code, tag_name, tag_type, is_active)
                    VALUES (:c, :n, :t, 1)
                    """),
                    {"c": code, "n": code.replace("_", " ").title(), "t": t},
                )
            else:
                conn.execute(
                    text("""
                    INSERT INTO tag_definitions (tag_code, tag_name, tag_type, is_active)
                    VALUES (:c, :n, :t, 1)
                    ON CONFLICT (tag_code) DO NOTHING
                    """),
                    {"c": code, "n": code.replace("_", " ").title(), "t": t},
                )
            seeded += 1
    print(f"Migration complete. tag_definitions considered: {seeded}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
