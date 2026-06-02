from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, or_, select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from desktop.backend.database.connection import SessionLocal  # noqa: E402
from desktop.backend.models.social_lead import (  # noqa: E402
    XhsAiJudgment,
    XhsCollectionRun,
    XhsComment,
    XhsExtractedContact,
    XhsNote,
    XhsNoteMedia,
    XhsRawSnapshot,
    XhsUser,
    XhsUserHistoryPost,
    XhsUserSource,
)


EXPORT_ROOT = ROOT / "desktop" / "data" / "exports" / "social_test_samples"
OLD_PROMPT = "xhs-b2b-us-dropship-fit-v6"

TABLES = [
    XhsCollectionRun,
    XhsRawSnapshot,
    XhsUser,
    XhsNote,
    XhsComment,
    XhsNoteMedia,
    XhsUserSource,
    XhsUserHistoryPost,
    XhsExtractedContact,
    XhsAiJudgment,
]


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _row_dict(row: Any) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _backup_table(db, model, backup_dir: Path, department_code: str) -> int:
    path = backup_dir / f"{model.__tablename__}.jsonl"
    rows = db.scalars(
        select(model)
        .where(model.department_code == department_code)
        .order_by(getattr(model, "created_at", getattr(model, "id")))
    ).all()
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(_row_dict(row), ensure_ascii=False, default=_json_default) + "\n")
    return len(rows)


def _select_latest(db, department_code: str, limit: int, exclude: set[str]) -> list[str]:
    ids: list[str] = []
    rows = db.scalars(
        select(XhsUser)
        .where(XhsUser.department_code == department_code)
        .order_by(func.coalesce(XhsUser.last_seen_at, XhsUser.first_seen_at, XhsUser.created_at).desc())
        .limit(max(limit * 3, limit))
    ).all()
    for user in rows:
        if user.id in exclude:
            continue
        ids.append(user.id)
        exclude.add(user.id)
        if len(ids) >= limit:
            break
    return ids


def _select_by_old_decisions(
    db,
    department_code: str,
    decisions: tuple[str, ...],
    limit: int,
    exclude: set[str],
) -> list[str]:
    ids: list[str] = []
    rows = db.execute(
        select(XhsUser.id, XhsAiJudgment.fit_score, XhsAiJudgment.decision)
        .join(XhsAiJudgment, XhsAiJudgment.user_id == XhsUser.id)
        .where(
            XhsUser.department_code == department_code,
            XhsAiJudgment.department_code == department_code,
            XhsAiJudgment.prompt_version == OLD_PROMPT,
            XhsAiJudgment.decision.in_(decisions),
        )
        .order_by(XhsAiJudgment.fit_score.desc(), XhsAiJudgment.created_at.desc())
        .limit(max(limit * 4, limit))
    ).all()
    for user_id, _score, _decision in rows:
        if user_id in exclude:
            continue
        ids.append(user_id)
        exclude.add(user_id)
        if len(ids) >= limit:
            break
    return ids


def _counts(db, department_code: str) -> dict[str, int]:
    return {
        model.__tablename__: int(
            db.scalar(select(func.count()).select_from(model).where(model.department_code == department_code)) or 0
        )
        for model in TABLES
    }


def _platform_counts(db, user_ids: set[str]) -> dict[str, int]:
    if not user_ids:
        return {}
    rows = db.execute(
        select(XhsUser.platform, func.count())
        .where(XhsUser.id.in_(user_ids))
        .group_by(XhsUser.platform)
        .order_by(XhsUser.platform)
    ).all()
    return {str(platform or "unknown"): int(count or 0) for platform, count in rows}


def _delete_not_in_sample(db, department_code: str, keep_ids: set[str]) -> dict[str, int]:
    deleted: dict[str, int] = {}

    # Clear every old or temporary score. The next step reruns GPT only for the sample.
    deleted["xhs_ai_judgments"] = int(
        db.execute(delete(XhsAiJudgment).where(XhsAiJudgment.department_code == department_code)).rowcount or 0
    )
    db.commit()

    keep_note_ids = {
        note_id
        for (note_id,) in db.execute(
            select(XhsNote.id).where(
                XhsNote.department_code == department_code,
                XhsNote.author_user_id.in_(keep_ids),
            )
        ).all()
    }
    keep_note_ids.update(
        note_id
        for (note_id,) in db.execute(
            select(XhsComment.note_id).where(
                XhsComment.department_code == department_code,
                XhsComment.user_id.in_(keep_ids),
                XhsComment.note_id.isnot(None),
            )
        ).all()
        if note_id
    )

    deleted["xhs_extracted_contacts"] = int(
        db.execute(
            delete(XhsExtractedContact).where(
                XhsExtractedContact.department_code == department_code,
                ~or_(
                    XhsExtractedContact.user_id.in_(keep_ids),
                    XhsExtractedContact.owner_id.in_(keep_ids),
                ),
            )
        ).rowcount
        or 0
    )
    deleted["xhs_user_sources"] = int(
        db.execute(
            delete(XhsUserSource).where(
                XhsUserSource.department_code == department_code,
                XhsUserSource.user_id.not_in(keep_ids),
            )
        ).rowcount
        or 0
    )
    deleted["xhs_user_history_posts"] = int(
        db.execute(
            delete(XhsUserHistoryPost).where(
                XhsUserHistoryPost.department_code == department_code,
                XhsUserHistoryPost.user_id.not_in(keep_ids),
            )
        ).rowcount
        or 0
    )
    deleted["xhs_comments"] = int(
        db.execute(
            delete(XhsComment).where(
                XhsComment.department_code == department_code,
                XhsComment.user_id.not_in(keep_ids),
            )
        ).rowcount
        or 0
    )
    deleted["xhs_note_media"] = int(
        db.execute(
            delete(XhsNoteMedia).where(
                XhsNoteMedia.department_code == department_code,
                XhsNoteMedia.note_id.not_in(keep_note_ids or {"__none__"}),
            )
        ).rowcount
        or 0
    )
    deleted["xhs_notes"] = int(
        db.execute(
            delete(XhsNote).where(
                XhsNote.department_code == department_code,
                XhsNote.id.not_in(keep_note_ids or {"__none__"}),
            )
        ).rowcount
        or 0
    )
    deleted["xhs_users"] = int(
        db.execute(
            delete(XhsUser).where(
                XhsUser.department_code == department_code,
                XhsUser.id.not_in(keep_ids),
            )
        ).rowcount
        or 0
    )
    db.commit()

    keep_snapshot_ids = set()
    for model, column_name in (
        (XhsUser, "raw_snapshot_id"),
        (XhsNote, "raw_snapshot_id"),
        (XhsComment, "raw_snapshot_id"),
        (XhsNoteMedia, "raw_snapshot_id"),
        (XhsUserHistoryPost, "raw_snapshot_id"),
    ):
        column = getattr(model, column_name)
        keep_snapshot_ids.update(
            value
            for (value,) in db.execute(
                select(column).where(model.department_code == department_code, column.isnot(None))
            ).all()
            if value
        )
    deleted["xhs_raw_snapshots"] = int(
        db.execute(
            delete(XhsRawSnapshot).where(
                XhsRawSnapshot.department_code == department_code,
                XhsRawSnapshot.id.not_in(keep_snapshot_ids or {"__none__"}),
            )
        ).rowcount
        or 0
    )
    db.commit()

    keep_run_ids = set()
    for model, column_name in (
        (XhsUser, "first_seen_run_id"),
        (XhsNote, "first_run_id"),
        (XhsComment, "first_run_id"),
        (XhsRawSnapshot, "run_id"),
        (XhsUserSource, "run_id"),
    ):
        column = getattr(model, column_name)
        keep_run_ids.update(
            value
            for (value,) in db.execute(
                select(column).where(model.department_code == department_code, column.isnot(None))
            ).all()
            if value
        )
    deleted["xhs_collection_runs"] = int(
        db.execute(
            delete(XhsCollectionRun).where(
                XhsCollectionRun.department_code == department_code,
                XhsCollectionRun.id.not_in(keep_run_ids or {"__none__"}),
            )
        ).rowcount
        or 0
    )
    db.commit()
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="Trim X9 foreign-trade social data to a small manual-review sample.")
    parser.add_argument("--department-code", default="foreign_trade")
    parser.add_argument("--latest", type=int, default=40)
    parser.add_argument("--positive", type=int, default=30)
    parser.add_argument("--negative", type=int, default=30)
    args = parser.parse_args()

    started_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = EXPORT_ROOT / f"before_trim_{args.department_code}_{started_at}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        before = _counts(db, args.department_code)
        backup_counts = {model.__tablename__: _backup_table(db, model, backup_dir, args.department_code) for model in TABLES}

        selected: set[str] = set()
        buckets = {
            "latest": _select_latest(db, args.department_code, args.latest, selected),
            "old_positive": _select_by_old_decisions(
                db,
                args.department_code,
                ("target_customer", "experienced_seller", "high_priority", "follow_up"),
                args.positive,
                selected,
            ),
            "old_negative": _select_by_old_decisions(
                db,
                args.department_code,
                ("supplier_peer", "logistics_partner", "irrelevant", "potential", "error", "consumer"),
                args.negative,
                selected,
            ),
        }
        if len(selected) < args.latest + args.positive + args.negative:
            needed = args.latest + args.positive + args.negative - len(selected)
            buckets["filler"] = _select_latest(db, args.department_code, needed, selected)

        deleted = _delete_not_in_sample(db, args.department_code, selected)
        after = _counts(db, args.department_code)
        sample_path = backup_dir / "kept_sample_user_ids.json"
        sample_payload = {
            "department_code": args.department_code,
            "selected_total": len(selected),
            "buckets": buckets,
            "platform_counts": _platform_counts(db, selected),
        }
        sample_path.write_text(json.dumps(sample_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "ok": True,
        "backup_dir": str(backup_dir),
        "sample_path": str(sample_path),
        "backup_counts": backup_counts,
        "before": before,
        "deleted": deleted,
        "after": after,
        **sample_payload,
    }
    summary_path = backup_dir / "trim_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
