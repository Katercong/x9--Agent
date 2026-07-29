"""Canonical department-code rules shared by API queries and data migrations."""
from __future__ import annotations

import re

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement


# Department codes preserve internal whitespace, but all boundary ASCII
# whitespace is ignored.  Keeping this explicit (rather than Python's broader
# default ``str.strip()`` set) makes the persisted SQL representation portable
# between SQLite and PostgreSQL.
DEPARTMENT_CODE_BOUNDARY_WHITESPACE = " \t\n\r\v\f"
DEPARTMENT_CODE_SLUG = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")


def normalise_department_code(value: str) -> str:
    """Return the canonical department code used for authorization scope."""

    return value.strip(DEPARTMENT_CODE_BOUNDARY_WHITESPACE).lower()


def validate_department_code(value: str) -> str:
    """Validate and canonicalize the portable ASCII department-code namespace.

    Only ASCII slugs with ``-``/``_`` separators are persisted.  This makes
    Python and both supported database engines agree on case conversion and
    prevents authorization scope from depending on Unicode collation rules.
    """

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
    """Build the SQL equivalent of :func:`normalise_department_code`.

    This expression is called only after :func:`validate_department_code` has
    restricted persisted values to ASCII. SQLite exposes ``trim(value,
    characters)`` while PostgreSQL exposes the equivalent ``btrim(value,
    characters)`` function, so both engines now have identical semantics.
    """

    if dialect_name == "postgresql":
        trimmed = func.btrim(column, DEPARTMENT_CODE_BOUNDARY_WHITESPACE)
    else:
        trimmed = func.trim(column, DEPARTMENT_CODE_BOUNDARY_WHITESPACE)
    return func.lower(trimmed)
