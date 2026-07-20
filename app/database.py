from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import load_project_environment


DATA_DIR = Path("data")
DEFAULT_DB_URL = f"sqlite:///{(DATA_DIR / 'replychat_agent.sqlite').as_posix()}"
load_project_environment()


def _normalise_database_url(url: str) -> str:
    """Convert the legacy PostgreSQL scheme into SQLAlchemy's psycopg scheme."""

    if url.startswith("postgres://"):
        return f"postgresql+psycopg://{url.removeprefix('postgres://')}"
    if url.startswith("postgresql://"):
        return f"postgresql+psycopg://{url.removeprefix('postgresql://')}"
    return url


DATABASE_URL = _normalise_database_url(os.getenv("DATABASE_URL", DEFAULT_DB_URL))
IS_SQLITE = DATABASE_URL.startswith("sqlite")

connect_args = {"check_same_thread": False} if IS_SQLITE else {}
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    future=True,
    pool_pre_ping=not IS_SQLITE,
)


if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        """Keep local SQLite tests aligned with PostgreSQL foreign-key semantics."""

        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401

    if IS_SQLITE:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(bind=engine)
        return

    # Production schema changes are applied explicitly with Alembic before the
    # application is started. This makes multi-process deployments predictable.
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
