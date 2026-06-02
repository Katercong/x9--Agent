from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, update

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from desktop.backend.database.connection import SessionLocal  # noqa: E402
from desktop.backend.models.social_lead import (  # noqa: E402
    XhsAiJudgment,
    XhsComment,
    XhsExtractedContact,
    XhsNote,
    XhsUser,
    XhsUserHistoryPost,
    XhsUserSource,
)


EXPORT_ROOT = ROOT / "desktop" / "data" / "exports" / "social_dedupe"


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _identity_expr():
    return func.lower(func.coalesce(XhsUser.account_clean, XhsUser.external_user_id, XhsUser.xhs_user_id))


def _row_dict(row: Any) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _backup_users(db, users: list[XhsUser], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for user in users:
            f.write(json.dumps(_row_dict(user), ensure_ascii=False, default=_json_default) + "\n")


def _evidence_count(db, user_id: str) -> int:
    return int(db.scalar(select(func.count()).select_from(XhsComment).where(XhsComment.user_id == user_id)) or 0) + int(
        db.scalar(select(func.count()).select_from(XhsUserSource).where(XhsUserSource.user_id == user_id)) or 0
    ) + int(db.scalar(select(func.count()).select_from(XhsExtractedContact).where(XhsExtractedContact.user_id == user_id)) or 0)


def _choose_keeper(db, users: list[XhsUser]) -> XhsUser:
    return sorted(
        users,
        key=lambda user: (
            _evidence_count(db, user.id),
            int(user.has_contact or 0),
            user.last_seen_at or user.created_at or datetime.min,
        ),
        reverse=True,
    )[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge duplicate foreign-trade social users by platform account.")
    parser.add_argument("--department-code", default="foreign_trade")
    parser.add_argument("--clear-judgments", action="store_true")
    args = parser.parse_args()

    started_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = EXPORT_ROOT / f"duplicate_users_before_merge_{args.department_code}_{started_at}.jsonl"
    summary_path = EXPORT_ROOT / f"dedupe_summary_{args.department_code}_{started_at}.json"

    with SessionLocal() as db:
        groups = db.execute(
            select(XhsUser.platform, _identity_expr().label("identity_key"), func.count())
            .where(XhsUser.department_code == args.department_code, _identity_expr() != "")
            .group_by(XhsUser.platform, _identity_expr())
            .having(func.count() > 1)
            .order_by(func.count().desc())
        ).all()

        duplicate_users: list[XhsUser] = []
        merges: list[dict[str, Any]] = []
        for platform, identity_key, count in groups:
            users = list(
                db.scalars(
                    select(XhsUser)
                    .where(
                        XhsUser.department_code == args.department_code,
                        XhsUser.platform == platform,
                        _identity_expr() == identity_key,
                    )
                    .order_by(XhsUser.created_at.asc(), XhsUser.id.asc())
                ).all()
            )
            duplicate_users.extend(users)
            keeper = _choose_keeper(db, users)
            loser_ids = [user.id for user in users if user.id != keeper.id]
            if not loser_ids:
                continue

            # Remove duplicate contacts that would violate the owner/value unique key after reassignment.
            keeper_contact_keys = {
                (c.owner_type, c.contact_type, c.value_norm)
                for c in db.scalars(
                    select(XhsExtractedContact).where(
                        (XhsExtractedContact.user_id == keeper.id)
                        | (XhsExtractedContact.owner_id == keeper.id)
                    )
                ).all()
            }
            loser_contacts = db.scalars(
                select(XhsExtractedContact).where(
                    (XhsExtractedContact.user_id.in_(loser_ids))
                    | (XhsExtractedContact.owner_id.in_(loser_ids))
                )
            ).all()
            for contact in loser_contacts:
                if (contact.owner_type, contact.contact_type, contact.value_norm) in keeper_contact_keys:
                    db.delete(contact)
            db.flush()

            for model, column in (
                (XhsComment, XhsComment.user_id),
                (XhsUserSource, XhsUserSource.user_id),
                (XhsUserHistoryPost, XhsUserHistoryPost.user_id),
                (XhsNote, XhsNote.author_user_id),
                (XhsExtractedContact, XhsExtractedContact.user_id),
            ):
                db.execute(update(model).where(column.in_(loser_ids)).values({column.key: keeper.id}))

            db.execute(
                update(XhsExtractedContact)
                .where(XhsExtractedContact.owner_type == "user", XhsExtractedContact.owner_id.in_(loser_ids))
                .values(owner_id=keeper.id)
            )
            db.execute(delete(XhsAiJudgment).where(XhsAiJudgment.user_id.in_(loser_ids)))
            deleted_users = db.execute(delete(XhsUser).where(XhsUser.id.in_(loser_ids))).rowcount or 0
            merges.append({
                "platform": platform,
                "identity_key": identity_key,
                "count": int(count or 0),
                "keeper_id": keeper.id,
                "deleted_user_ids": loser_ids,
                "deleted_users": int(deleted_users),
            })
        if duplicate_users:
            _backup_users(db, duplicate_users, backup_path)
        if args.clear_judgments:
            cleared = db.execute(delete(XhsAiJudgment).where(XhsAiJudgment.department_code == args.department_code)).rowcount or 0
        else:
            cleared = 0
        db.commit()

        remaining_groups = db.execute(
            select(XhsUser.platform, _identity_expr().label("identity_key"), func.count())
            .where(XhsUser.department_code == args.department_code, _identity_expr() != "")
            .group_by(XhsUser.platform, _identity_expr())
            .having(func.count() > 1)
        ).all()
        user_total = int(db.scalar(select(func.count()).select_from(XhsUser).where(XhsUser.department_code == args.department_code)) or 0)
        judgment_total = int(db.scalar(select(func.count()).select_from(XhsAiJudgment).where(XhsAiJudgment.department_code == args.department_code)) or 0)

    summary = {
        "ok": len(remaining_groups) == 0,
        "department_code": args.department_code,
        "backup_path": str(backup_path) if duplicate_users else None,
        "summary_path": str(summary_path),
        "merged_groups": len(merges),
        "merges": merges,
        "cleared_judgments": int(cleared),
        "remaining_duplicate_groups": len(remaining_groups),
        "user_total": user_total,
        "judgment_total": judgment_total,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default))
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
