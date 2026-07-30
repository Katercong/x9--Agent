"""Create one disposable PostgreSQL database and run the complete backend suite.

The caller supplies an admin URL for the dedicated test PostgreSQL service.  This
script never reads .env, never uses the application/demo database, and removes
only the random database name it created itself.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_PREFIX = "x9_replychat_test_"


def _redact(value: str, *secrets: str) -> str:
    result = value
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[redacted]")
    return result


def _require_admin_url() -> URL:
    raw_url = os.getenv("POSTGRES_TEST_ADMIN_URL")
    if not raw_url:
        raise SystemExit("POSTGRES_TEST_ADMIN_URL is required; use only a dedicated PostgreSQL test service")
    url = make_url(raw_url)
    if not url.drivername.startswith("postgresql"):
        raise SystemExit("POSTGRES_TEST_ADMIN_URL must use a PostgreSQL SQLAlchemy URL")
    if url.database != "postgres":
        raise SystemExit("POSTGRES_TEST_ADMIN_URL must target the dedicated service's postgres control database")
    return url


def _database_url(admin_url: URL, database_name: str) -> str:
    return admin_url.set(database=database_name).render_as_string(hide_password=False)


def _run(command: list[str], *, environment: dict[str, str], secrets: tuple[str, ...]) -> int:
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.stdout:
        print(_redact(completed.stdout, *secrets), end="")
    if completed.stderr:
        print(_redact(completed.stderr, *secrets), end="", file=sys.stderr)
    return completed.returncode


def _drop_created_database(engine, database_name: str) -> None:
    with engine.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = :database_name AND pid <> pg_backend_pid()"
            ),
            {"database_name": database_name},
        )
        # database_name is generated internally from a fixed ASCII prefix and UUID.
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))


def main() -> int:
    admin_url = _require_admin_url()
    database_name = f"{TEST_DATABASE_PREFIX}{uuid.uuid4().hex}"
    database_url = _database_url(admin_url, database_name)
    admin_engine = create_engine(admin_url, future=True, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    created = False
    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        created = True

        environment = os.environ.copy()
        environment.update(
            {
                "DATABASE_URL": database_url,
                "POSTGRES_TEST_DATABASE_URL": database_url,
                "X9_TEST_ISOLATED": "1",
                "SILICONFLOW_API_KEY": "",
            }
        )
        secrets = (admin_url.render_as_string(hide_password=False), database_url)
        if _run([sys.executable, "-m", "alembic", "upgrade", "head"], environment=environment, secrets=secrets) != 0:
            return 1
        return _run(
            [sys.executable, "-m", "pytest", "-q", *sys.argv[1:]],
            environment=environment,
            secrets=secrets,
        )
    finally:
        if created:
            _drop_created_database(admin_engine, database_name)
        admin_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
