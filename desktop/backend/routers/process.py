from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.departments import current_department_code
from ..services.pipeline import run_full_pipeline


router = APIRouter(prefix="/api/local/process", tags=["process"])


@router.post("/score-creators")
def score_creators(request: Request, body: dict | None = Body(default=None), db: Session = Depends(get_db)) -> dict:
    body = body or {}
    return run_full_pipeline(db, creator_id=body.get("creator_id"), limit=body.get("limit", 5000), department_code=current_department_code(request))


@router.post("/tag-creators")
def tag_creators(request: Request, body: dict | None = Body(default=None), db: Session = Depends(get_db)) -> dict:
    # Tag is part of the unified pipeline — calling this just re-runs it.
    body = body or {}
    return run_full_pipeline(db, creator_id=body.get("creator_id"), limit=body.get("limit", 5000), department_code=current_department_code(request))


@router.post("/recommend-creators")
def recommend_creators(request: Request, body: dict | None = Body(default=None), db: Session = Depends(get_db)) -> dict:
    body = body or {}
    return run_full_pipeline(db, creator_id=body.get("creator_id"), limit=body.get("limit", 5000), department_code=current_department_code(request))


@router.post("/run-full-pipeline")
def run_pipeline(request: Request, body: dict | None = Body(default=None), db: Session = Depends(get_db)) -> dict:
    body = body or {}
    return run_full_pipeline(db, creator_id=body.get("creator_id"), limit=body.get("limit", 5000), department_code=current_department_code(request))
