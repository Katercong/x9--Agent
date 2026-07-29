"""Frozen V1 department-code rules used by already-released Alembic revisions.

Do not edit this module. A new department-code policy must be added in a new
versioned module and adopted by new application code and migrations. Existing
migrations import the compatibility exports in :mod:`app.department_codes`,
which deliberately point at these V1 objects.
"""
from __future__ import annotations

import re

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement


DEPARTMENT_CODE_BOUNDARY_WHITESPACE = " \t\n\r\v\f"
DEPARTMENT_CODE_SLUG = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")


def normalise_department_code(value: str) -> str:
    """Return the V1 canonical department code used for authorization scope."""

    return value.strip(DEPARTMENT_CODE_BOUNDARY_WHITESPACE).lower()


def validate_department_code(value: str) -> str:
    """Validate and canonicalize the V1 portable ASCII department namespace."""

    code = normalise_department_code(value)
    if not code:
        raise ValueError("department code must not be empty")
    if not DEPARTMENT_CODE_SLUG.fullmatch(code):
        raise ValueError("department code must be an ASCII slug")
    return code


def normalised_department_code_expression(
    column: ColumnElement[str],
    *,
    dialect_name: str,
) -> ColumnElement[str]:
    """Build the V1 SQL equivalent of :func:`normalise_department_code`."""

    if dialect_name == "postgresql":
        trimmed = func.btrim(column, DEPARTMENT_CODE_BOUNDARY_WHITESPACE)
    else:
        trimmed = func.trim(column, DEPARTMENT_CODE_BOUNDARY_WHITESPACE)
    return func.lower(trimmed)
