"""Current PostgreSQL-only department-code rules for application code.

Released Alembic revisions continue to import ``app.department_codes`` and its
frozen V1 compatibility exports. Runtime callers use this module so future
application policy changes cannot alter historical migration behavior.
"""
from __future__ import annotations

import re

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement


DEPARTMENT_CODE_BOUNDARY_WHITESPACE = " \t\n\r\v\f"
DEPARTMENT_CODE_SLUG = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")


def normalise_department_code(value: str) -> str:
    return value.strip(DEPARTMENT_CODE_BOUNDARY_WHITESPACE).lower()


def validate_department_code(value: str) -> str:
    code = normalise_department_code(value)
    if not code:
        raise ValueError("department code must not be empty")
    if not DEPARTMENT_CODE_SLUG.fullmatch(code):
        raise ValueError("department code must be an ASCII slug")
    return code


def normalised_postgresql_department_code_expression(column: ColumnElement[str]) -> ColumnElement[str]:
    """Return the PostgreSQL SQL equivalent of current code canonicalization."""

    return func.lower(func.btrim(column, DEPARTMENT_CODE_BOUNDARY_WHITESPACE))
