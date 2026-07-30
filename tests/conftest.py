"""Test-process database selection before application modules are imported."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest


_SQLITE_TEST_PATH: Path | None = None


def _configure_test_database() -> None:
    """Keep ordinary tests isolated from .env while allowing the explicit PG runner."""

    global _SQLITE_TEST_PATH

    backend = os.getenv("X9_TEST_DATABASE_BACKEND", "sqlite")
    if backend == "sqlite":
        database_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        database_file.close()
        _SQLITE_TEST_PATH = Path(database_file.name)
        os.environ["DATABASE_URL"] = f"sqlite:///{_SQLITE_TEST_PATH.as_posix()}"
    elif backend == "postgres":
        database_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
        if not database_url:
            raise pytest.UsageError(
                "X9_TEST_DATABASE_BACKEND=postgres requires POSTGRES_TEST_DATABASE_URL from the isolated test runner"
            )
        os.environ["DATABASE_URL"] = database_url
    else:
        raise pytest.UsageError("X9_TEST_DATABASE_BACKEND must be either 'sqlite' or 'postgres'")

    # Tests must never load a developer's real model credential from .env.
    os.environ["SILICONFLOW_API_KEY"] = ""


_configure_test_database()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Remove the per-process SQLite file; PostgreSQL cleanup belongs to its runner."""

    del session, exitstatus
    if _SQLITE_TEST_PATH is not None:
        database_module = sys.modules.get("app.database")
        if database_module is not None:
            database_module.engine.dispose()
        _SQLITE_TEST_PATH.unlink(missing_ok=True)
