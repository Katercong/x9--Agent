"""Single source of truth for mapping (platform, raw source) -> the canonical
creator-acquisition bucket the three dashboards split on.

Used by both the ingest path (services/collector_service.py, persisted onto
Creator.source) and the read path (routers/collector.py) so a creator is
classified identically wherever it is looked at.
"""
from __future__ import annotations

SOURCE_SHOP = "tiktok_shop"
SOURCE_X9_LEADS = "x9_leads"
SOURCE_TABLE_IMPORT = "table_import"
SOURCE_OTHER = "other"

ALL_SOURCES = (SOURCE_SHOP, SOURCE_X9_LEADS, SOURCE_TABLE_IMPORT, SOURCE_OTHER)


def classify_source(platform: str | None, source: str | None) -> str:
    p = (platform or "").lower()
    s = (source or "").lower()
    if p == "tiktok_shop" or "tiktok_shop" in s:
        return SOURCE_SHOP
    if "table_import" in s:
        return SOURCE_TABLE_IMPORT
    if "creator_lead_browser" in s or s == "chrome_extension":
        return SOURCE_X9_LEADS
    return SOURCE_OTHER
