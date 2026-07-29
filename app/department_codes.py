"""Application-facing department-code rules.

The names exported here are a frozen V1 compatibility surface for Alembic
revisions ``0a1b2c3d4e5f`` and ``2b3c4d5e6f7a``. Do not change their meaning:
new policy needs a new versioned rule module and new consumers. This
indirection lets historical migrations keep their original deterministic rule
objects without modifying already-applied migration files.
"""
from __future__ import annotations

from .department_codes_v1 import (
    DEPARTMENT_CODE_BOUNDARY_WHITESPACE,
    DEPARTMENT_CODE_SLUG,
    normalise_department_code,
    normalised_department_code_expression,
    validate_department_code,
)


__all__ = [
    "DEPARTMENT_CODE_BOUNDARY_WHITESPACE",
    "DEPARTMENT_CODE_SLUG",
    "normalise_department_code",
    "normalised_department_code_expression",
    "validate_department_code",
]
