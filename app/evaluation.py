from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .evaluation_cases import get_suite
from .llm import SiliconFlowProviderError, call_siliconflow_json
from .prompts import build_prompt_package
from .schemas import AgentSuggestion
from .services import build_context_insufficient_suggestion, collect_context_warnings, has_missing_campaign_brief


def load_suite(name: str) -> list[dict[str, Any]]:
    """读取仓库内的脱敏合成评测集，不访问数据库。"""

    return get_suite(name)


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总结构化输出、路由正确性、人工复核与延迟指标。"""

    total = len(records)
    if total == 0:
        return {
            "total": 0,
            "json_parse_rate": 0.0,
            "pydantic_pass_rate": 0.0,
            "route_exact_rate": 0.0,
            "missed_manual_review_count": 0,
            "p95_latency_ms": 0.0,
        }
    provider_records = [record for record in records if record["outcome"] != "context_insufficient"]
    preflight_records = [record for record in records if record["outcome"] == "context_insufficient"]
    latencies = sorted(float(record["latency_ms"]) for record in provider_records)
    p95_index = max(0, math.ceil(len(latencies) * 0.95) - 1)
    return {
        "total": total,
        "provider_attempt_count": len(provider_records),
        "context_insufficient_count": len(preflight_records),
        "json_parse_rate": _rate(provider_records, "json_parse_valid") if provider_records else None,
        "pydantic_pass_rate": _rate(provider_records, "pydantic_valid") if provider_records else None,
        "route_exact_rate": _rate(provider_records, "route_exact") if provider_records else None,
        "preflight_route_exact_rate": _rate(preflight_records, "route_exact") if preflight_records else None,
        "missed_manual_review_count": sum(
            1
            for record in records
            if record["manual_review_expected"] and not record["manual_review_actual"]
        ),
        "p95_latency_ms": latencies[p95_index] if latencies else 0.0,
    }


def run_suite(
    name: str,
    *,
    live: bool,
    prompt_version: str = "reply_followup_v2",
    output_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """显式允许后才批量调用 Provider，并可将评测结果写入忽略目录。"""

    cases = load_suite(name)
    requires_provider = any(not has_missing_campaign_brief(collect_context_warnings(case["context"])) for case in cases)
    if requires_provider and not live:
        raise ValueError("real provider evaluation requires --live")
    records = [_run_case(case, prompt_version=prompt_version) for case in cases]
    summary = summarize_records(records)
    summary["prompt_version"] = prompt_version
    if output_dir is not None:
        _write_report(output_dir, name, prompt_version, records, summary)
    return records, summary


def _run_case(case: dict[str, Any], *, prompt_version: str) -> dict[str, Any]:
    context_warnings = collect_context_warnings(case["context"])
    if has_missing_campaign_brief(context_warnings):
        return _record(
            case,
            "context_insufficient",
            True,
            True,
            build_context_insufficient_suggestion(case["context"], context_warnings),
            0.0,
        )
    package = build_prompt_package(case["context"], prompt_version=prompt_version)
    started = time.perf_counter()
    try:
        raw_output = call_siliconflow_json(package.system_prompt, package.user_prompt)
    except SiliconFlowProviderError:
        return _record(case, "provider_error", False, False, None, _elapsed_ms(started))
    return _evaluate_raw_output(case, raw_output, _elapsed_ms(started))


def _evaluate_raw_output(case: dict[str, Any], raw_output: str, latency_ms: float) -> dict[str, Any]:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError:
        return _record(case, "invalid_json", False, False, None, latency_ms)
    try:
        suggestion = AgentSuggestion.model_validate(payload)
    except Exception:
        return _record(case, "validation_failed", True, False, None, latency_ms)
    return _record(case, "success", True, True, suggestion, latency_ms)


def _record(
    case: dict[str, Any],
    outcome: str,
    json_parse_valid: bool,
    pydantic_valid: bool,
    suggestion: AgentSuggestion | None,
    latency_ms: float,
) -> dict[str, Any]:
    expected = case["expected"]
    actual = suggestion.model_dump() if suggestion else {}
    route_exact = pydantic_valid and all(
        actual.get(field) == expected[field]
        for field in ("reply_category", "next_action", "suggested_status")
    )
    return {
        "case_id": case["id"],
        "outcome": outcome,
        "json_parse_valid": json_parse_valid,
        "pydantic_valid": pydantic_valid,
        "route_exact": route_exact,
        "manual_review_expected": expected["requires_human_review"],
        "manual_review_actual": bool(actual.get("requires_human_review")),
        "latency_ms": round(latency_ms, 2),
        "expected": expected,
        "actual": actual,
        "manual_review": {"factuality": None, "tone": None, "usability": None, "notes": ""},
    }


def _rate(records: list[dict[str, Any]], field: str) -> float:
    return sum(1 for record in records if record[field]) / len(records) if records else 0.0


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _write_report(
    output_dir: Path,
    suite: str,
    prompt_version: str,
    records: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{suite}_{prompt_version}_{stamp}"
    (output_dir / f"{base_name}.json").write_text(
        json.dumps({"summary": summary, "records": records}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [f"# {suite} LLM evaluation", "", "| metric | value |", "| --- | --- |"]
    lines.extend(f"| {key} | {value} |" for key, value in summary.items())
    (output_dir / f"{base_name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run synthetic LLM evaluation without touching the business database.")
    parser.add_argument("--suite", default="pilot", choices=("pilot", "context_preflight"))
    parser.add_argument("--prompt-version", default="reply_followup_v2", choices=("reply_followup_v1", "reply_followup_v2"))
    parser.add_argument("--live", action="store_true", help="Allow real SiliconFlow requests.")
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation_reports"))
    args = parser.parse_args()
    _, summary = run_suite(
        args.suite,
        live=args.live,
        prompt_version=args.prompt_version,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
