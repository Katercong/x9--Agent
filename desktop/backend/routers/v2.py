"""V2 dashboard API routes — backs the `/preview/*` UI.

Read-only endpoints. None of these write to the database; they only query
the existing tables (creators / creator / tk_creators / outreach_emails /
raw_observations / app_users) and the existing dashboard tables.

All endpoints require an authenticated user. Granular role checks are
deliberately loose here (any logged-in user can see the preview) since
the v2 UI is still being evaluated; production access control will come
when we drop the legacy pages.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import v2_service


router = APIRouter(prefix="/api/v2", tags=["v2"])


def _current_user_or_401(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    return user


@router.get("/pulse")
def pulse(
    request: Request,
    range: str = Query("week", regex="^(today|week|month)$"),
    db: Session = Depends(get_db),
) -> dict:
    _current_user_or_401(request)
    return v2_service.get_pulse(db, range_key=range)


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)) -> dict:
    user = _current_user_or_401(request)
    return v2_service.get_me(db, user)


@router.get("/creators")
def creators(
    request: Request,
    tab: str = Query("all", regex="^(all|mine|pool|pending|contacted|active)$"),
    q: str | None = None,
    platform: str | None = None,
    tier: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    user = _current_user_or_401(request)
    return v2_service.get_creators_unified(
        db,
        tab=tab,
        q=q,
        platform=platform,
        tier=tier,
        status=status,
        owner=owner,
        limit=limit,
        offset=offset,
        user=user,
    )


@router.get("/creators/{platform}/{handle}")
def creator_detail(
    request: Request,
    platform: str,
    handle: str,
    db: Session = Depends(get_db),
) -> dict:
    _current_user_or_401(request)
    result = v2_service.get_creator_360(db, platform, handle)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("detail", "not found"))
    return result
