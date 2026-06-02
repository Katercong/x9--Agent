"""Compatibility ingest routes for the merged foreign-trade browser extension
(Phase 4).

The vendored recruitment + XHS collectors POST to their original paths
(`/api/companies/ingest`, `/api/talents/ingest`, `/api/xhs/ingest`,
`/api/douyin/ingest`). Rather than editing every collector, we expose those
exact paths here and forward to the X9 ingest services. Department attribution
comes from the payload (the extension's ft_actor.js bakes `department_code` at
download time and ft_api_config.js injects it into every ingest body), falling
back to the session department, then the default.

These endpoints are intentionally unauthenticated (the extension pushes
cross-origin without a session cookie), matching the original standalone
backends' open ingest contract.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.company_lead_service import ingest_company, ingest_talent
from ..services.upload_queue_cleanup import attach_queue_cleanup
from ..services.xhs_lead_service import ingest_snapshot

router = APIRouter(prefix="/api", tags=["extension-ingest-compat"])


def _dept(request: Request, payload: dict[str, Any]) -> str:
    # These compat routes are intentionally UNAUTHENTICATED (extension/helper push
    # cross-origin without a session cookie). Therefore we must NOT call
    # current_department_code()/current_user(), which raise HTTPException(401)
    # when there is no session — that 401 was the root cause of the batch-collect
    # "login required" failures (payload without department_code → 401).
    # Order: payload department (baked into the extension) → session if present
    # (read safely, never raising) → foreign_trade default.
    dept = payload.get("department_code")
    if dept:
        return dept
    user = getattr(request.state, "current_user", None)
    if user and user.get("department_code"):
        return user["department_code"]
    return "foreign_trade"


@router.post("/companies/ingest")
def companies_ingest(request: Request, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    department_code = _dept(request, payload)
    try:
        lead = ingest_company(db, payload, department_code=department_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return attach_queue_cleanup(
        {
            "ok": True,
            "id": lead.id,
            "department_code": lead.department_code or department_code,
            "tier": lead.tier,
            "score": lead.score,
            "llm_score_status": lead.llm_score_status,
        },
        payload,
        entity="company_lead",
        lead_id=lead.id,
    )


@router.post("/talents/ingest")
def talents_ingest(request: Request, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    department_code = _dept(request, payload)
    try:
        lead = ingest_talent(db, payload, department_code=department_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return attach_queue_cleanup(
        {
            "ok": True,
            "id": lead.id,
            "department_code": lead.department_code or department_code,
            "tier": lead.tier,
            "score": lead.score,
            "llm_score_status": lead.llm_score_status,
        },
        payload,
        entity="talent_lead",
        lead_id=lead.id,
    )


@router.post("/xhs/ingest")
def xhs_ingest_compat(request: Request, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ingest_snapshot(db, payload, platform="xhs", department_code=_dept(request, payload))


@router.post("/douyin/ingest")
def douyin_ingest_compat(request: Request, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ingest_snapshot(db, payload, platform="douyin", department_code=_dept(request, payload))
