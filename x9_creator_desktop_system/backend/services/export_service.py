"""export_service.py — emits the recommended-creators CSV."""
from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import EXPORT_DIR
from ..models.creator import Creator
from .departments import department_where
from ..utils.contact_methods import contact_types_for, extract_contact_methods, methods_to_text
from ..utils.json_utils import loads_json_list


CREATOR_FIELDS = [
    "handle",
    "display_name",
    "profile_url",
    "followers_count",
    "email",
    "contact_types",
    "contact_methods",
    "recommended_product_type",
    "recommended_collab_type",
    "outreach_priority",
    "current_status",
    "recommendation_status",
    "recommendation_reason",
    "risk_tags",
    "next_action",
    "notes",
]


def export_recommended_csv(
    db: Session,
    status_filter: list[str] | None = None,
    department_code: str | None = None,
) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / "recommended-creators.csv"

    q = select(Creator)
    if status_filter:
        q = q.where(Creator.recommendation_status.in_(status_filter))
    where_department = department_where(Creator, department_code)
    if where_department is not None:
        q = q.where(where_department)
    q = q.order_by(Creator.outreach_priority.asc(), Creator.recommendation_score.desc())

    rows = list(db.scalars(q).all())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CREATOR_FIELDS)
        w.writeheader()
        for r in rows:
            risks = "; ".join(loads_json_list(r.risk_tags_json))
            contact_methods = extract_contact_methods(r.email, r.bio, r.external_links_json)
            w.writerow({
                "handle": r.handle,
                "display_name": r.display_name or "",
                "profile_url": r.profile_url or "",
                "followers_count": r.followers_count or "",
                "email": r.email or "",
                "contact_types": "; ".join(contact_types_for(r.email, r.bio, r.external_links_json)),
                "contact_methods": methods_to_text(contact_methods),
                "recommended_product_type": r.recommended_product_type or "",
                "recommended_collab_type": r.recommended_collab_type or "",
                "outreach_priority": r.outreach_priority or "",
                "current_status": r.current_status or "",
                "recommendation_status": r.recommendation_status or "",
                "recommendation_reason": r.recommendation_reason or "",
                "risk_tags": risks,
                "next_action": r.next_action or "",
                "notes": r.notes or "",
            })
    return path
