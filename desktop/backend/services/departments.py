from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import or_


DEFAULT_DEPARTMENT = "cross_border"

DEPARTMENTS: dict[str, dict[str, str]] = {
    "cross_border": {
        "code": "cross_border",
        "slug": "cross-border",
        "name": "跨境部",
    },
    "foreign_trade": {
        "code": "foreign_trade",
        "slug": "foreign-trade",
        "name": "外贸部",
    },
}

SLUG_TO_CODE = {item["slug"]: code for code, item in DEPARTMENTS.items()}


def normalize_department_code(value: str | None, *, default: str | None = DEFAULT_DEPARTMENT) -> str | None:
    raw = (value or "").strip().lower().replace("-", "_")
    if not raw:
        return default
    if raw in DEPARTMENTS:
        return raw
    if raw in SLUG_TO_CODE:
        return SLUG_TO_CODE[raw]
    raise HTTPException(status_code=400, detail=f"unknown department: {value}")


def department_slug(code: str | None) -> str:
    code = normalize_department_code(code)
    return DEPARTMENTS[code or DEFAULT_DEPARTMENT]["slug"]


def department_name(code: str | None) -> str:
    code = normalize_department_code(code)
    return DEPARTMENTS[code or DEFAULT_DEPARTMENT]["name"]


def current_user(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    return user


def current_department_code(request: Request) -> str | None:
    user = current_user(request)
    if user.get("role") in {"company_admin", "super_admin"} and user.get("entry_scope") == "admin":
        return None
    return normalize_department_code(user.get("department_code"))


def require_admin(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user.get("role") not in {"department_admin", "company_admin", "super_admin"} or user.get("entry_scope") != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return user


def require_super_admin(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user.get("role") != "super_admin" or user.get("entry_scope") != "admin":
        raise HTTPException(status_code=403, detail="super admin only")
    return user


def effective_row_department(row: dict[str, Any] | Any) -> str:
    if isinstance(row, dict):
        value = row.get("department_code")
    else:
        value = getattr(row, "department_code", None)
    return normalize_department_code(value)


def row_in_department(row: dict[str, Any] | Any, department_code: str | None) -> bool:
    if department_code is None:
        return True
    return effective_row_department(row) == department_code


def filter_rows_for_department(rows: list[dict[str, Any]], department_code: str | None) -> list[dict[str, Any]]:
    if department_code is None:
        return rows
    return [row for row in rows if row_in_department(row, department_code)]


def department_where(model, department_code: str | None):
    if department_code is None:
        return None
    column = getattr(model, "department_code")
    if department_code == DEFAULT_DEPARTMENT:
        return or_(column == department_code, column.is_(None))
    return column == department_code
