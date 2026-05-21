from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.departments import current_department_code, current_user, normalize_department_code
from ..services.post_processing import analytics_summary


router = APIRouter(prefix="/api/local/analytics", tags=["analytics"])


def _actor_id(user: dict) -> str:
    return str(user.get("id") or user.get("identity") or user.get("username") or "")


@router.get("/me")
def me(request: Request, days: int = Query(default=30, ge=1, le=120), db: Session = Depends(get_db)) -> dict:
    user = current_user(request)
    return analytics_summary(
        db,
        scope="user",
        department_code=user.get("department_code"),
        actor_user_id=_actor_id(user),
        days=days,
    )


@router.get("/department")
def department(
    request: Request,
    department_code: str | None = None,
    days: int = Query(default=30, ge=1, le=120),
    db: Session = Depends(get_db),
) -> dict:
    user = current_user(request)
    dept = department_code if user.get("role") in {"company_admin", "super_admin"} else current_department_code(request)
    return analytics_summary(
        db,
        scope="department",
        department_code=normalize_department_code(dept, default=None) if dept else current_department_code(request),
        days=days,
    )


@router.get("/company")
def company(request: Request, days: int = Query(default=30, ge=1, le=120), db: Session = Depends(get_db)) -> dict:
    user = current_user(request)
    if user.get("role") not in {"company_admin", "super_admin"}:
        raise HTTPException(status_code=403, detail="company analytics requires company admin")
    return analytics_summary(db, scope="company", department_code=None, days=days)


@router.get("/company-growth")
def company_growth(request: Request, days: int = Query(default=90, ge=1, le=120), db: Session = Depends(get_db)) -> dict:
    user = current_user(request)
    if user.get("role") not in {"company_admin", "super_admin"}:
        raise HTTPException(status_code=403, detail="company growth requires company admin")
    return analytics_summary(db, scope="company_growth", department_code=None, days=days)
