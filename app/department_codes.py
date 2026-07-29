"""Canonical department-code rules shared by API queries and data migrations."""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement


# Department codes preserve internal whitespace, but all boundary ASCII
# whitespace is ignored.  Keeping this explicit (rather than Python's broader
# default ``str.strip()`` set) makes the persisted SQL representation portable
# between SQLite and PostgreSQL.
DEPARTMENT_CODE_BOUNDARY_WHITESPACE = " \t\n\r\v\f"


def normalise_department_code(value: str) -> str:
    """Return the canonical department code used for authorization scope."""

    return value.strip(DEPARTMENT_CODE_BOUNDARY_WHITESPACE).lower()


def normalised_department_code_expression(
    column: ColumnElement[str],
    *,
    dialect_name: str,
) -> ColumnElement[str]:
    """Build the SQL equivalent of :func:`normalise_department_code`.

    SQLite exposes ``trim(value, characters)`` while PostgreSQL exposes the
    equivalent ``btrim(value, characters)`` function.  Both remove exactly
    the declared boundary character set and preserve internal whitespace.
    """

    if dialect_name == "postgresql":
        trimmed = func.btrim(column, DEPARTMENT_CODE_BOUNDARY_WHITESPACE)
    else:
        trimmed = func.trim(column, DEPARTMENT_CODE_BOUNDARY_WHITESPACE)
    return func.lower(trimmed)
