"""Export the product catalog into JSON shapes:

  exports/products.json          -- our canonical shape (rich, with images)
  exports/tk_content_products.json -- compatible with TK_Content workbench's `customProducts`
  exports/creators.json          -- creators master
  exports/outreach.json          -- event log

Run after data changes; safe to re-run.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"
OUT = ROOT / "exports"
OUT.mkdir(exist_ok=True)

JSON_COLS_PRODUCT = {
    "selling_points_en", "selling_points_zh", "pain_points_zh",
    "scenarios_en", "scenarios_zh", "vocabulary_en",
    "creative_angles_en", "safe_scenes_en", "creator_match_levels",
}
JSON_COLS_CREATOR = {"category_tags"}


def parse_json_cols(d: dict, cols: set[str]) -> dict:
    for k in cols:
        if k in d and isinstance(d[k], str) and d[k]:
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                d[k] = []
        elif k in d and not d[k]:
            d[k] = []
    return d


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    # --- products.json ---
    products = []
    for r in con.execute(
        "SELECT p.*, c.code AS category_code, c.name_zh AS category_name "
        "FROM product p LEFT JOIN category c ON p.category_id=c.id ORDER BY p.id"
    ):
        d = parse_json_cols(dict(r), JSON_COLS_PRODUCT)
        d["images"] = [
            {"rel_path": ir["rel_path"], "kind": ir["kind"], "caption": ir["caption"]}
            for ir in con.execute(
                "SELECT rel_path, kind, caption FROM product_image "
                "WHERE product_id=? ORDER BY display_order, id", (d["id"],)
            )
        ]
        products.append(d)
    (OUT / "products.json").write_text(
        json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] products.json  {len(products)} rows")

    # --- tk_content_products.json (PRODUCT_LIBRARY shape) ---
    tk = {}
    for p in products:
        key = p.get("tk_content_key")
        if not key or key in tk:
            continue  # keep first SKU per key
        tk[key] = {
            "englishName": p.get("name_en") or "",
            "chineseName": p.get("name_zh") or "",
            "label": f'{p.get("name_en","")}（{p.get("name_zh","")}）',
            "category": p.get("series") or p.get("subcategory") or "",
            "audienceSummaryEn": p.get("target_audience_en") or "",
            "audienceSummaryZh": p.get("target_audience_zh") or "",
            "scenariosEn": p.get("scenarios_en") or [],
            "scenariosZh": p.get("scenarios_zh") or [],
            "keyPointsEn": p.get("selling_points_en") or [],
            "keyPointsZh": p.get("selling_points_zh") or [],
            "specs": f'{p.get("size_label","")} ({p.get("pcs_per_pack","")} count per pack)',
            "proof": p.get("proof") or "",
            "vocabulary": p.get("vocabulary_en") or [],
            "creativeAngles": p.get("creative_angles_en") or [],
            "safeScenes": p.get("safe_scenes_en") or [],
            "focus": "",
            "focusZh": p.get("focus_zh") or "",
            "x9_sku_codes": [p["sku_code"]],
        }
    # group all SKUs sharing the same tk_key
    for p in products:
        key = p.get("tk_content_key")
        if not key:
            continue
        if p["sku_code"] not in tk[key]["x9_sku_codes"]:
            tk[key]["x9_sku_codes"].append(p["sku_code"])
    (OUT / "tk_content_products.json").write_text(
        json.dumps(tk, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] tk_content_products.json  {len(tk)} entries")

    # --- creators.json ---
    creators = []
    for r in con.execute("SELECT * FROM creator ORDER BY id"):
        d = parse_json_cols(dict(r), JSON_COLS_CREATOR)
        creators.append(d)
    (OUT / "creators.json").write_text(
        json.dumps(creators, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] creators.json  {len(creators)} rows")

    # --- outreach.json ---
    outreach = []
    for r in con.execute(
        "SELECT o.*, c.handle AS creator_handle FROM outreach o "
        "JOIN creator c ON c.id=o.creator_id ORDER BY o.event_date, o.id"
    ):
        outreach.append(dict(r))
    (OUT / "outreach.json").write_text(
        json.dumps(outreach, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] outreach.json  {len(outreach)} rows")

    con.close()


if __name__ == "__main__":
    main()
