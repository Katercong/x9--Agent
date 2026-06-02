from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, func, select  # noqa: E402

from desktop.backend.database.connection import SessionLocal  # noqa: E402
from desktop.backend.models.social_lead import XhsAiJudgment, XhsUser  # noqa: E402
from desktop.backend.services.xhs_lead_service import (  # noqa: E402
    PROMPT_VERSION,
    count_unjudged_social_users,
    judge_users_with_gpt,
)


EXPORT_DIR = ROOT / "desktop" / "data" / "exports" / "social_score_backups"


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _backup_judgments(db, department_code: str, started_at: str) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / f"xhs_ai_judgments_before_chain_intent_{department_code}_{started_at}.jsonl"
    rows = db.scalars(
        select(XhsAiJudgment)
        .where(XhsAiJudgment.department_code == department_code)
        .order_by(XhsAiJudgment.created_at, XhsAiJudgment.id)
    ).all()
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            payload = {column.name: getattr(row, column.name) for column in XhsAiJudgment.__table__.columns}
            f.write(json.dumps(payload, ensure_ascii=False, default=_json_default) + "\n")
    return path


def _count_v5(db, department_code: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(XhsAiJudgment)
            .where(
                XhsAiJudgment.department_code == department_code,
                XhsAiJudgment.prompt_version == PROMPT_VERSION,
            )
        )
        or 0
    )


def _decision_counts(db, department_code: str) -> dict[str, int]:
    rows = db.execute(
        select(XhsAiJudgment.decision, func.count())
        .where(
            XhsAiJudgment.department_code == department_code,
            XhsAiJudgment.prompt_version == PROMPT_VERSION,
        )
        .group_by(XhsAiJudgment.decision)
        .order_by(func.count().desc())
    ).all()
    return {str(decision or "unknown"): int(count or 0) for decision, count in rows}


def _relationship_counts(db, department_code: str) -> dict[str, int]:
    rows = db.execute(
        select(XhsAiJudgment.judgment, XhsAiJudgment.id)
        .where(
            XhsAiJudgment.department_code == department_code,
            XhsAiJudgment.prompt_version == PROMPT_VERSION,
        )
    ).all()
    counts: dict[str, int] = {}
    for raw, _id in rows:
        relationship = "unknown"
        try:
            parsed = json.loads(raw or "{}")
            relationship = str(parsed.get("relationship_type") or "unknown")
        except Exception:
            relationship = "unknown"
        counts[relationship] = counts.get(relationship, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def _write_event(path: Path, event: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(), **event}, ensure_ascii=False, default=_json_default) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rerun X9 foreign-trade social GPT judgments with chain-intent prompt.")
    parser.add_argument("--department-code", default="foreign_trade")
    parser.add_argument("--batch-size", type=int, default=80)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--replace-current", action="store_true")
    parser.add_argument("--delete-old", action="store_true")
    parser.add_argument("--max-batches", type=int, default=0)
    args = parser.parse_args()

    os.environ["X9_FT_GPT_CONCURRENCY"] = str(max(1, min(args.concurrency, 12)))
    started_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    progress_path = EXPORT_DIR / f"xhs_chain_intent_rerun_{args.department_code}_{started_at}.jsonl"
    summary_path = EXPORT_DIR / f"xhs_chain_intent_rerun_{args.department_code}_{started_at}_summary.json"

    with SessionLocal() as db:
        total_users = int(
            db.scalar(
                select(func.count())
                .select_from(XhsUser)
                .where(XhsUser.department_code == args.department_code, XhsUser.has_contact == 1)
            )
            or 0
        )
        backup_path = _backup_judgments(db, args.department_code, started_at)

        if args.replace_current:
            deleted_current = db.execute(
                delete(XhsAiJudgment).where(
                    XhsAiJudgment.department_code == args.department_code,
                    XhsAiJudgment.prompt_version == PROMPT_VERSION,
                )
            ).rowcount
            db.commit()
        else:
            deleted_current = 0

        _write_event(progress_path, {
            "event": "started",
            "department_code": args.department_code,
            "prompt_version": PROMPT_VERSION,
            "total_users": total_users,
            "backup_path": str(backup_path),
            "deleted_current": int(deleted_current or 0),
        })

        batches = 0
        while True:
            pending = count_unjudged_social_users(db, args.department_code)
            saved = _count_v5(db, args.department_code)
            _write_event(progress_path, {"event": "progress", "pending": pending, "saved": saved, "total_users": total_users})
            print(json.dumps({"pending": pending, "saved": saved, "total_users": total_users}, ensure_ascii=False), flush=True)
            if pending <= 0:
                break
            if args.max_batches and batches >= args.max_batches:
                break
            result = judge_users_with_gpt(
                db,
                department_code=args.department_code,
                limit=min(args.batch_size, pending),
                force=False,
            )
            batches += 1
            _write_event(progress_path, {"event": "batch_done", "batch": batches, **result})

        deleted_old = 0
        final_pending = count_unjudged_social_users(db, args.department_code)
        if args.delete_old and final_pending <= 0:
            deleted_old = db.execute(
                delete(XhsAiJudgment).where(
                    XhsAiJudgment.department_code == args.department_code,
                    XhsAiJudgment.prompt_version != PROMPT_VERSION,
                )
            ).rowcount
            db.commit()

        summary = {
            "ok": final_pending <= 0,
            "department_code": args.department_code,
            "prompt_version": PROMPT_VERSION,
            "total_users": total_users,
            "saved": _count_v5(db, args.department_code),
            "pending": final_pending,
            "deleted_current": int(deleted_current or 0),
            "deleted_old": int(deleted_old or 0),
            "backup_path": str(backup_path),
            "progress_path": str(progress_path),
            "summary_path": str(summary_path),
            "decisions": _decision_counts(db, args.department_code),
            "relationships": _relationship_counts(db, args.department_code),
            "finished_at": datetime.now().isoformat(),
        }
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
        _write_event(progress_path, {"event": "finished", **summary})
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
