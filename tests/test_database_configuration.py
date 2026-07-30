"""PostgreSQL-only runtime configuration checks."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _import_with_environment(module: str, database_url: str | None) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["X9_TEST_ISOLATED"] = "1"
    environment["SILICONFLOW_API_KEY"] = ""
    environment.pop("POSTGRES_TEST_DATABASE_URL", None)
    if database_url is None:
        environment.pop("DATABASE_URL", None)
    else:
        environment["DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("module", ("app.main", "app.worker"))
@pytest.mark.parametrize(
    ("database_url", "expected_message"),
    (
        (None, "DATABASE_URL must be configured with a PostgreSQL URL"),
        ("sql" + "ite:///not-supported.db", "DATABASE_URL must use a PostgreSQL URL"),
    ),
)
def test_api_and_worker_fail_fast_without_a_postgresql_url(module: str, database_url: str | None, expected_message: str):
    result = _import_with_environment(module, database_url)

    assert result.returncode != 0
    assert expected_message in result.stderr


def test_postgresql_runtime_import_succeeds_with_runner_database(postgres_database_url: str):
    result = _import_with_environment("app.database", postgres_database_url)

    assert result.returncode == 0, result.stderr
