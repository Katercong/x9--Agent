from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.creator import Creator
from ..services.collector_service import reprocess_raw_observations
from ..services.departments import current_department_code, current_user
from ..services.post_processing import (
    create_outreach_event,
    import_bd_creators,
    migrate_staff_note_bd_stats,
    normalize_creators,
    record_creator_source,
    SOURCE_BD,
    backfill_creator_sources,
    backfill_legacy_creator_tables,
)


process_router = APIRouter(prefix="/api/local/process", tags=["process"])
outreach_router = APIRouter(prefix="/api/local/outreach", tags=["outreach"])
creators_router = APIRouter(prefix="/api/local/creators", tags=["creators"])


def _actor_id(user: dict) -> str:
    return str(user.get("id") or user.get("identity") or user.get("username") or "")


@process_router.post("/replay-raw")
def replay_raw(request: Request, body: dict[str, Any] | None = Body(default=None), db: Session = Depends(get_db)) -> dict:
    body = body or {}
    return reprocess_raw_observations(
        db,
        limit=body.get("limit", 1000),
        platform=body.get("platform", "all"),
        department_code=current_department_code(request),
        skip_invalid_handle_repairs=body.get("skip_invalid_handle_repairs", True) is not False,
        auto_process=body.get("auto_process", True) is not False,
    )


@process_router.post("/normalize-creators")
def normalize_creator_records(
    _request: Request,
    body: dict[str, Any] | None = Body(default=None),
    db: Session = Depends(get_db),
) -> dict:
    body = body or {}
    out = {
        "normalize": normalize_creators(db, dry_run=body.get("dry_run", False) is True, limit=body.get("limit", 5000)),
    }
    if body.get("backfill_sources", True) is not False:
        out["sources"] = backfill_creator_sources(db, limit=body.get("limit", 50000))
    if body.get("backfill_legacy_tables", True) is not False:
        out["legacy_tables"] = backfill_legacy_creator_tables(db, limit=body.get("limit", 200000))
    if body.get("migrate_bd_stats", True) is not False:
        out["bd_monthly_stats"] = migrate_staff_note_bd_stats(db)
    return {"ok": True, **out}


@outreach_router.post("/events")
def create_event(request: Request, body: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict:
    user = current_user(request)
    creator_id = str(body.get("creator_id") or "")
    event_type = str(body.get("event_type") or "")
    creator = db.get(Creator, creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="creator not found")
    if user.get("role") not in {"company_admin", "super_admin"} and not creator.department_code == user.get("department_code"):
        raise HTTPException(status_code=404, detail="creator not found")
    event = create_outreach_event(
        db,
        creator,
        event_type=event_type,
        actor_user_id=_actor_id(user),
        owner_bd=body.get("owner_bd"),
        note=body.get("note"),
        metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else None,
        event_at=body.get("event_at"),
    )
    db.commit()
    return {"ok": True, "event": {"id": event.id, "creator_id": event.creator_id, "event_type": event.event_type}}


@creators_router.post("/import-bd")
def import_bd(request: Request, body: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict:
    user = current_user(request)
    rows = body.get("items") or body.get("rows") or []
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="items must be a list")
    result = import_bd_creators(
        db,
        rows,
        actor_user_id=_actor_id(user),
        department_code=body.get("department_code") or user.get("department_code") or current_department_code(request),
    )
    for creator_id in body.get("source_creator_ids") or []:
        creator = db.get(Creator, str(creator_id))
        if creator is not None:
            record_creator_source(
                db,
                creator,
                source_type=SOURCE_BD,
                actor_user_id=_actor_id(user),
                metadata={"source": "bd_import_marker"},
            )
    db.commit()
    return result
