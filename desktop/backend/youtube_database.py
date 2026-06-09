from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATA_DIR


class YoutubeBase(DeclarativeBase):
    pass


YOUTUBE_DB_URL = os.getenv("YOUTUBE_DB_URL", f"sqlite:///{(DATA_DIR / 'youtube.sqlite').as_posix()}")
_connect_args = {"check_same_thread": False} if YOUTUBE_DB_URL.startswith("sqlite") else {}
_pool_kwargs: dict = {}
if not YOUTUBE_DB_URL.startswith("sqlite"):
    _pool_kwargs = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_timeout": 30,
    }

youtube_engine = create_engine(
    YOUTUBE_DB_URL,
    connect_args=_connect_args,
    future=True,
    **_pool_kwargs,
)

if YOUTUBE_DB_URL.startswith("sqlite"):
    @event.listens_for(youtube_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


YoutubeSessionLocal = sessionmaker(bind=youtube_engine, autoflush=False, autocommit=False, future=True)


def get_youtube_db() -> Generator[Session, None, None]:
    db = YoutubeSessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_youtube_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    from .models import youtube_lead  # noqa: F401
    from .services.youtube_import_service import clear_resolved_manual_review_leads

    YoutubeBase.metadata.create_all(bind=youtube_engine)
    with YoutubeSessionLocal() as db:
        if clear_resolved_manual_review_leads(db):
            db.commit()
