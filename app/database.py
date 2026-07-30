from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import load_project_environment


load_project_environment()


def _normalise_database_url(url: str) -> str:
    """Convert legacy PostgreSQL schemes to SQLAlchemy's psycopg scheme."""

    if url.startswith("postgres://"):
        return f"postgresql+psycopg://{url.removeprefix('postgres://')}"
    if url.startswith("postgresql://"):
        return f"postgresql+psycopg://{url.removeprefix('postgresql://')}"
    return url


def _require_postgresql_url() -> str:
    raw_url = os.getenv("DATABASE_URL")
    if not raw_url:
        raise RuntimeError("DATABASE_URL must be configured with a PostgreSQL URL")
    database_url = _normalise_database_url(raw_url)
    if not database_url.startswith("postgresql"):
        raise RuntimeError("DATABASE_URL must use a PostgreSQL URL")
    return database_url


DATABASE_URL = _require_postgresql_url()
engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
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
    """Verify the Alembic-managed PostgreSQL schema is reachable."""

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
