"""Link product images to products.

Two image sources:
  1. TK_Content reference-images (21 PNGs) - copied to assets/reference-images/
     Mapped to products via tk_content_key.
  2. F:\\实习生\\A社媒\\... (hundreds of jpg/png organized by category & view)
     Heuristic: directory name contains 女性/成人/宠物/母婴 -> category;
                directory name contains 内容物/场景/外包装/包装 -> kind;
                fallback: assigned to all SKUs of the same series in that category.

Stored in product_image as relative paths under Database/.
Re-runnable: rebuilds product_image rows; existing rows for the same path are kept (UNIQUE constraint).
"""
from __future__ import annotations
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"
ASSETS = ROOT / "assets"
REF_DIR_DST = ASSETS / "reference-images"

REF_DIR_SRC = Path(r"D:\Backup\Downloads\TK_Content_Workbench_Delivery\app\assets\reference-images")
INTERN_A = Path(r"F:\实习生\A社媒")

# tk_content_key -> reference image filename (from TK_Content)
TK_REF_MAP = {
    "adult_tabs": "adult_tabs.png",
    "disposable_briefs": "disposable_briefs.png",
    "men_pads": "men_pads.png",
    "postpartum_pads": "postpartum_pads_compare.png",
    "calabash_postpartum_pads": "postpartum_pads_compare.png",
    "women_pads": "women_pads.png",
    "activated_charcoal_underpads": "activated_charcoal_underpads.png",
    "disposable_male_wraps": "disposable_male_wraps.png",
    "disposable_diapers": "disposable_diapers_tail_hole.png",
    "training_pads": "training_pads.png",
    "regular_underpads": "regular_underpads.png",
    "lavender_underpads": "lavender_underpads.png",
    "ultra_thin_baby_diapers": "ultra_thin_baby_diapers.png",
    "t_shape_training_pants": "t_shape_training_pants.png",
    "q_shape_diaper_pants": "q_shape_diaper_pants.png",
    "nursing_pads": "nursing_pads.png",
    "cloud_period_underwear": "cloud_period_underwear.png",
    "cotton_cover_panty_liners": "cotton_cover_line.png",
    "cotton_cover_pads": "cotton_cover_line.png",
    "ultra_thin_pads": "ultra_thin_pads.png",
    "micro_panty_liners": "micro_panty_liners.png",
    "period_underwear": "period_underwear.png",
    "male_wraps_size": "male_wraps_size_guide.png",
}

# Folder name segment -> category code
CATEGORY_HINT = {
    "女性": "female_care",
    "成人": "adult_care",
    "宠物": "pet",
    "母婴": "baby",
    "陈崎银母婴": "baby",
    "吴莹莹母婴": "baby",
}
KIND_HINT = {
    "内容物": "content",
    "内容展示": "content",
    "场景": "scene",
    "场景展示": "scene",
    "外包装": "package",
    "外包装展示": "package",
    "包装展示": "package",
    "产品分类": "package",
}

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def copy_reference_images() -> None:
    REF_DIR_DST.mkdir(parents=True, exist_ok=True)
    if not REF_DIR_SRC.exists():
        print(f"[import_images] WARN: reference src not found: {REF_DIR_SRC}")
        return
    n = 0
    for src in REF_DIR_SRC.iterdir():
        if src.suffix.lower() not in IMG_EXTS:
            continue
        dst = REF_DIR_DST / src.name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
        n += 1
    print(f"[import_images] copied/verified {n} reference images")


def link_reference_images(con: sqlite3.Connection) -> int:
    """For each product with tk_content_key, link the matching reference image."""
    cur = con.cursor()
    rows = cur.execute(
        "SELECT id, tk_content_key FROM product WHERE tk_content_key IS NOT NULL"
    ).fetchall()
    n = 0
    for pid, key in rows:
        fname = TK_REF_MAP.get(key)
        if not fname:
            continue
        rel = f"assets/reference-images/{fname}"
        cur.execute(
            "INSERT OR IGNORE INTO product_image(product_id, rel_path, kind, caption, display_order) "
            "VALUES(?,?,?,?,?)",
            (pid, rel, "reference", f"TK_Content reference: {fname}", 0),
        )
        n += cur.rowcount
    con.commit()
    return n


def categorize_intern_image(p: Path) -> tuple[str | None, str | None, str | None]:
    """Return (category_code, kind, hint_series) based on path."""
    parts = [s.lower() for s in p.parts]
    cat = None
    kind = None
    full = "/".join(p.parts)
    for k, v in CATEGORY_HINT.items():
        if k in full:
            cat = v
            break
    for k, v in KIND_HINT.items():
        if k in full:
            kind = v
            break
    return cat, kind, None


def link_intern_images(con: sqlite3.Connection) -> int:
    """Walk F:\\实习生\\A社媒 and link each image to ALL products of the matching category.

    This is intentionally coarse: one image often illustrates a whole series
    (e.g. all 3 sizes of cotton-cover pads). The viewer can prune later via UI.
    """
    if not INTERN_A.exists():
        print(f"[import_images] WARN: intern src not found: {INTERN_A}")
        return 0

    cur = con.cursor()
    cat_to_pids = {}
    for code in ("female_care", "adult_care", "pet", "baby", "home_care"):
        pids = [r[0] for r in cur.execute(
            "SELECT p.id FROM product p JOIN category c ON c.id=p.category_id WHERE c.code=?",
            (code,)).fetchall()]
        cat_to_pids[code] = pids

    n_imgs = 0
    n_links = 0
    for img in INTERN_A.rglob("*"):
        if img.is_dir() or img.suffix.lower() not in IMG_EXTS:
            continue
        cat, kind, _ = categorize_intern_image(img.relative_to(INTERN_A))
        if not cat:
            continue
        pids = cat_to_pids.get(cat, [])
        if not pids:
            continue

        # Store as relative path *from project root* so frontend can serve it.
        # We don't copy -- we keep the file in 实习生 and reference it absolutely
        # via a special prefix the FastAPI server can resolve.
        rel = "intern://" + img.relative_to(INTERN_A).as_posix()
        n_imgs += 1
        for pid in pids:
            cur.execute(
                "INSERT OR IGNORE INTO product_image(product_id, rel_path, kind, caption, display_order) "
                "VALUES(?,?,?,?,?)",
                (pid, rel, kind or "package", img.name, 5),
            )
            n_links += cur.rowcount
    con.commit()
    print(f"[import_images] intern images scanned={n_imgs}, new links={n_links}")
    return n_links


def main() -> None:
    copy_reference_images()
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys=ON")
    n_ref = link_reference_images(con)
    print(f"[import_images] reference image links: +{n_ref}")
    link_intern_images(con)

    total = con.execute("SELECT COUNT(*) FROM product_image").fetchone()[0]
    by_kind = con.execute("SELECT kind, COUNT(*) FROM product_image GROUP BY kind").fetchall()
    print(f"[import_images] total product_image rows: {total}")
    for k, c in by_kind:
        print(f"   {k}: {c}")
    con.close()


if __name__ == "__main__":
    main()
