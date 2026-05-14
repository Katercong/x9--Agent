from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.departments import current_department_code
from ..services.export_service import export_recommended_csv


router = APIRouter(prefix="/api/local/export", tags=["export"])


@router.get("/recommended-creators.csv")
def recommended_csv(
    request: Request,
    only_p1_p2: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    statuses = None
    if only_p1_p2:
        statuses = ["recommended", "recommended_after_review"]
    path = export_recommended_csv(db, status_filter=statuses, department_code=current_department_code(request))
    return FileResponse(path, media_type="text/csv", filename=path.name)
