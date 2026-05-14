"""
x9_product_clone.py — 商品裂变 CLI 工具
-----------------------------------------
通过调用 Core API (POST /api/v1/ai/clone_product) 生成多角度商品文案变体。

OpenAI API Key 由管理员在前台 Settings → LLM → Features 里配置，
本脚本不需要也不应该持有密钥。

用法:
    python x9_product_clone.py --sku PP-SWIM-BLK-L --n 4 --dry-run
    python x9_product_clone.py --sku PP-SWIM-BLK-L --angles comfort,scenario,value,gift --out clones.json

环境变量:
    X9_API_KEY    X9 Core 认证 key（用 x9_key_permissions.py 确认权限）
    X9_CORE_URL   Core 地址，默认 http://192.168.1.168:18765
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib import error as urllib_error
from urllib import request as urllib_request

DEFAULT_CORE_URL = "http://192.168.1.168:18765"

VALID_ANGLES = [
    "comfort", "scenario", "value", "relief",
    "gift", "eco", "spec", "trust",
]


def _post(url: str, body: dict, x9_key: str) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if x9_key:
        headers["X-API-Key"] = x9_key
    req = urllib_request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib_error.HTTPError as e:
        body_text = e.read().decode("utf-8", "replace")
        print(f"ERROR: HTTP {e.code} — {body_text[:400]}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="X9 商品裂变工具（调用 Core API，Key 由管理员在前台配置）"
    )
    parser.add_argument("--sku",      required=True, help="源产品 SKU")
    parser.add_argument("--n",        type=int, default=4,
                        help="变体数量，默认 4，最多 8")
    parser.add_argument("--angles",   default="",
                        help=f"逗号分隔角度，留空=自动。可用: {', '.join(VALID_ANGLES)}")
    parser.add_argument("--dry-run",  action="store_true",
                        help="只返回预览，不写入数据库（默认开启保护）")
    parser.add_argument("--write",    action="store_true",
                        help="实际写入 Core 数据库（去掉 --dry-run 保护）")
    parser.add_argument("--core-url", default=os.environ.get("X9_CORE_URL", DEFAULT_CORE_URL))
    parser.add_argument("--x9-key",  default=os.environ.get("X9_API_KEY", ""))
    parser.add_argument("--out",      default="", help="额外保存结果为 JSON 文件")
    args = parser.parse_args()

    angles = [a.strip() for a in args.angles.split(",") if a.strip()] if args.angles else []
    invalid = [a for a in angles if a not in VALID_ANGLES]
    if invalid:
        print(f"ERROR: 未知角度 {invalid}。可用: {VALID_ANGLES}", file=sys.stderr)
        return 1

    dry_run = not args.write  # 默认 dry_run=True，需显式 --write 才写库

    payload: dict = {
        "sku":     args.sku,
        "n":       args.n,
        "dry_run": dry_run,
    }
    if angles:
        payload["angles"] = angles

    url = f"{args.core_url}/api/v1/ai/clone_product"
    print(f"调用 Core API: {url}")
    print(f"  SKU={args.sku}  n={args.n}  dry_run={dry_run}"
          + (f"  angles={angles}" if angles else ""))
    print()

    result = _post(url, payload, args.x9_key)

    # ── 打印预览 ──────────────────────────────────────────────────────────────
    src = result.get("source", {})
    clones = result.get("clones", [])
    print(f"源 SKU: {src.get('sku_code')}  ({src.get('name_en')})")
    print(f"Provider: {result.get('resolved_provider')}  "
          f"Model: {result.get('resolved_model')}  "
          f"Tokens: {result.get('tokens', {})}")
    print("─" * 70)

    for c in clones:
        sim_warn = "  ⚠ 相似度偏高" if c.get("similarity_warning") else ""
        print(f"\n【{c['variant_label']}】SKU: {c['sku_code']}{sim_warn}")
        print(f"  标题 ({c['title_chars']} 字符): {c['title']}")
        desc = c.get("description", "")
        print(f"  描述: {desc[:160]}{'…' if len(desc) > 160 else ''}")
        for sp in c.get("selling_points_en", []):
            print(f"    • {sp}")
        print(f"  图片建议: {c.get('image_hint', '')}")

    print("\n" + "─" * 70)

    platform = result.get("platform", {})
    print(f"平台规格: 主图 {platform.get('image_size_px')}px"
          f"，≤{platform.get('image_max_count')} 张"
          f"，格式 {'/'.join(platform.get('image_formats', []))}"
          f"，标题 ≤{platform.get('title_max_chars')} 字符")

    created = result.get("created_skus", [])
    if created:
        print(f"\n已写入 Core: {created}")
    elif dry_run:
        print("\n[dry-run] 未写入数据库。加 --write 参数即可正式创建。")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"结果已保存至: {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
