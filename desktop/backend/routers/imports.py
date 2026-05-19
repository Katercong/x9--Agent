from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.departments import current_department_code
from ..services.creator_table_import import import_creator_table, template_csv_bytes, template_xlsx_bytes


router = APIRouter(prefix="/api/local/import", tags=["import"])


@router.get("/creators/template.csv")
def creator_import_template() -> Response:
    return Response(
        content=template_csv_bytes(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="creator-import-template.csv"'},
    )


@router.get("/creators/template.xlsx")
def creator_import_template_xlsx() -> Response:
    return Response(
        content=template_xlsx_bytes(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="creator-import-template.xlsx"'},
    )


@router.post("/creators/table")
async def import_creators_table(
    request: Request,
    filename: str = Query(default=""),
    dry_run: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="empty table file")

    resolved_filename = filename or request.headers.get("X-Filename") or "creators.csv"
    try:
        return import_creator_table(
            db,
            content,
            filename=resolved_filename,
            dry_run=dry_run,
            department_code=current_department_code(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
