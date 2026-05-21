from __future__ import annotations

import json
from typing import Any


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads_json_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return parsed if isinstance(parsed, list) else [parsed]
    return [value]


def parse_followers_count(raw: str | None) -> int | None:
    """Parse '844.5K', '1.2M', '12,300', '1.2万 followers' into an int."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    s = str(raw).strip().lower().replace(",", "")
    if not s:
        return None
    import re

    m = re.search(r"([\d.]+)\s*([kmb]|万|萬|亿|億)?", s)
    if not m:
        try:
            return int(float(s))
        except ValueError:
            return None
    n = float(m.group(1))
    suffix = m.group(2) or ""
    mult = {
        "k": 1_000,
        "m": 1_000_000,
        "b": 1_000_000_000,
        "万": 10_000,
        "萬": 10_000,
        "亿": 100_000_000,
        "億": 100_000_000,
    }.get(suffix, 1)
    return int(n * mult)
