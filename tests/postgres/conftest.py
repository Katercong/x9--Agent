"""Shared fixtures for real PostgreSQL integration tests.

The parent runner creates the primary disposable database before pytest imports
the application.  Migration-specific tests may create additional databases
through the same dedicated PostgreSQL control connection.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Callable

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app import models  # noqa: F401
from app.database import Base


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_PREFIX = "x9_replychat_test_"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Keep default SQLite regression fast, but reject a misconfigured explicit PG run."""

    if os.getenv("X9_TEST_DATABASE_BACKEND") == "postgres":
        return
    if config.option.markexpr.strip() == "postgres_integration":
        raise pytest.UsageError(
            "postgres_integration tests require scripts/run-postgres-tests.ps1 or scripts/run_postgres_tests.py"
        )
    skip_marker = pytest.mark.skip(reason="run PostgreSQL integration tests through scripts/run-postgres-tests.ps1")
    for item in items:
        if item.get_closest_marker("postgres_integration"):
            item.add_marker(skip_marker)


def _admin_url() -> URL:
    raw_url = os.getenv("POSTGRES_TEST_ADMIN_URL")
    if not raw_url:
        raise pytest.UsageError("POSTGRES_TEST_ADMIN_URL is required for postgres_integration tests")
    url = make_url(raw_url)
    if not url.drivername.startswith("postgresql") or url.database != "postgres":
        raise pytest.UsageError("POSTGRES_TEST_ADMIN_URL must target the dedicated PostgreSQL postgres database")
    return url


def _head_revision() -> str:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    return ScriptDirectory.from_config(config).get_current_head()


def _drop_database(engine: Engine, database_name: str) -> None:
    with engine.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = :database_name AND pid <> pg_backend_pid()"
            ),
            {"database_name": database_name},
        )
        # The name is generated locally from a fixed ASCII prefix and UUID.
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))


@pytest.fixture(scope="session")
def postgres_database_url() -> str:
    database_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not database_url:
        raise pytest.UsageError("POSTGRES_TEST_DATABASE_URL must be supplied by scripts/run_postgres_tests.py")
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql") or not (url.database or "").startswith(TEST_DATABASE_PREFIX):
        raise pytest.UsageError("POSTGRES_TEST_DATABASE_URL must name a runner-created x9_replychat_test_* database")
    return database_url


@pytest.fixture(scope="session")
def postgres_engine(postgres_database_url: str) -> Engine:
    engine = create_engine(postgres_database_url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            current_revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert current_revision == _head_revision()
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def postgres_sessions(postgres_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=postgres_engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(autouse=True)
def reset_postgres_data(postgres_engine: Engine) -> None:
    """Keep core integration cases independent without bypassing Alembic schema."""

    table_names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with postgres_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
    yield
    with postgres_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def temporary_postgres_database() -> str:
    """Provide an empty child database for a migration path, then remove it."""

    admin_url = _admin_url()
    database_name = f"{TEST_DATABASE_PREFIX}migration_{uuid.uuid4().hex}"
    database_url = admin_url.set(database=database_name).render_as_string(hide_password=False)
    admin_engine = create_engine(admin_url, future=True, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    created = False
    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        created = True
        yield database_url
    finally:
        if created:
            _drop_database(admin_engine, database_name)
        admin_engine.dispose()


@pytest.fixture
def run_alembic() -> Callable[..., subprocess.CompletedProcess[str]]:
    def invoke(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["DATABASE_URL"] = database_url
        environment["SILICONFLOW_API_KEY"] = ""
        return subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    return invoke
