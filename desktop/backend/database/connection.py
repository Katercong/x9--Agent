from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..config import DATA_DIR, EXPORT_DIR, LOG_DIR, settings
from ..services.departments import DEFAULT_DEPARTMENT


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.db_url.startswith("sqlite") else {}
engine = create_engine(settings.db_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Import models so they register with Base.metadata.
    from .. import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_schema_columns()
    _seed_admin_users()
    _seed_default_outreach_templates()
    _migrate_legacy_gmail_token()


def _seed_admin_users() -> None:
    try:
        from ..services.auth_service import seed_admin_users  # noqa: WPS433
    except Exception:
        return
    seed_admin_users()


def _migrate_legacy_gmail_token() -> None:
    """Pull the old single-file Gmail token into the new gmail_accounts table."""
    try:
        from ..services.gmail_service import migrate_legacy_token_if_present  # noqa: WPS433
    except Exception:  # pragma: no cover - service deps unavailable
        return
    try:
        migrate_legacy_token_if_present()
    except Exception:  # pragma: no cover - never let a startup hiccup crash the app
        pass


def _ensure_schema_columns() -> None:
    department_tables = [
        "app_users",
        "app_sessions",
        "creators",
        "raw_observations",
        "creator_tags",
        "creator_recommendations",
        "review_tasks",
        "outreach_emails",
        "outreach_templates",
        "extension_sessions",
        "extension_commands",
        "extension_run_progress",
    ]
    with engine.begin() as conn:
        for table in department_tables:
            _ensure_column(conn, table, "department_code", "VARCHAR(40)")
            _ensure_index(conn, f"ix_{table}_department_code", table, "department_code")

        _ensure_column(conn, "app_sessions", "entry_scope", "VARCHAR(40)")
        _ensure_index(conn, "ix_app_sessions_entry_scope", "app_sessions", "entry_scope")
        _drop_not_null(conn, "app_sessions", "gmail_account_id")

        _ensure_column(conn, "app_users", "username", "VARCHAR(120)")
        _ensure_column(conn, "app_users", "password_hash", "VARCHAR(500)")
        _ensure_column(conn, "app_users", "approval_status", "VARCHAR(40)")
        _ensure_column(conn, "app_users", "must_change_password", "INTEGER")
        _ensure_column(conn, "app_users", "approved_by", "VARCHAR(120)")
        _ensure_column(conn, "app_users", "approved_at", "TIMESTAMP")
        _ensure_column(conn, "app_users", "last_password_at", "TIMESTAMP")
        _ensure_column(conn, "app_users", "failed_login_count", "INTEGER")
        _ensure_column(conn, "app_users", "locked_until", "TIMESTAMP")
        _ensure_index(conn, "ix_app_users_username", "app_users", "username")
        _ensure_index(conn, "ix_app_users_approval_status", "app_users", "approval_status")
        _ensure_index(conn, "ix_app_users_must_change_password", "app_users", "must_change_password")
        _drop_not_null(conn, "app_users", "email")

        _ensure_column(conn, "gmail_accounts", "user_id", "VARCHAR(120)")
        _ensure_column(conn, "gmail_accounts", "department_code", "VARCHAR(40)")
        _ensure_index(conn, "ix_gmail_accounts_user_id", "gmail_accounts", "user_id")
        _ensure_index(conn, "ix_gmail_accounts_department_code", "gmail_accounts", "department_code")

        _set_nulls(conn, "app_sessions", "entry_scope", "workspace")
        _set_nulls(conn, "app_users", "approval_status", "active")
        _set_nulls_typed(conn, "app_users", "must_change_password", 0)
        _set_nulls_typed(conn, "app_users", "failed_login_count", 0)
        for table in department_tables:
            if table not in {"outreach_templates", "app_users"}:
                _set_nulls(conn, table, "department_code", DEFAULT_DEPARTMENT)
        if "department_code" in _columns(conn, "app_users"):
            conn.execute(text("UPDATE app_users SET department_code = NULL WHERE role IN ('admin', 'company_admin', 'super_admin')"))
            conn.execute(
                text("""
                UPDATE app_users
                SET department_code = :value
                WHERE role NOT IN ('admin', 'company_admin', 'super_admin') AND (department_code IS NULL OR department_code = '')
                """),
                {"value": DEFAULT_DEPARTMENT},
            )
        if {"username", "email"} <= _columns(conn, "app_users"):
            if engine.dialect.name == "sqlite":
                conn.execute(
                    text("""
                    UPDATE app_users
                    SET username = lower(substr(email, 1, instr(email, '@') - 1))
                    WHERE (username IS NULL OR username = '') AND email IS NOT NULL AND instr(email, '@') > 1
                    """)
                )
            else:
                conn.execute(
                    text("""
                    UPDATE app_users
                    SET username = lower(split_part(email, '@', 1))
                    WHERE (username IS NULL OR username = '') AND email IS NOT NULL AND position('@' in email) > 1
                    """)
                )

        _ensure_remote_department_column(conn)

        creator_columns = _columns(conn, "creators")
        if "current_status" not in creator_columns:
            conn.execute(text("ALTER TABLE creators ADD COLUMN current_status VARCHAR(80)"))
        if "store_assigned" not in creator_columns:
            conn.execute(text("ALTER TABLE creators ADD COLUMN store_assigned VARCHAR(120)"))
        if "owner_bd" not in creator_columns:
            conn.execute(text("ALTER TABLE creators ADD COLUMN owner_bd VARCHAR(120)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_creators_current_status ON creators (current_status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_creators_store_assigned ON creators (store_assigned)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_creators_owner_bd ON creators (owner_bd)"))

        # Per-source attribution + TikTok Shop fields for the 3 collection dashboards.
        _ensure_column(conn, "creators", "source", "VARCHAR(60)")
        _ensure_column(conn, "creators", "avatar_url", "TEXT")
        _ensure_column(conn, "creators", "shop_profile_url", "TEXT")
        _ensure_column(conn, "creators", "lead_status", "VARCHAR(40)")
        _ensure_column(conn, "creators", "tiktok_shop_json", "TEXT")
        _ensure_column(conn, "creators", "profile_snapshot_json", "TEXT")
        _ensure_index(conn, "ix_creators_source", "creators", "source")
        _ensure_index(conn, "ix_creators_lead_status", "creators", "lead_status")
        # Backfill: only positively set what we can prove. raw_observations has
        # no handle column (handle lives inside raw_json) so a precise per-creator
        # join is infeasible; platform reliably identifies Shop. Legacy non-Shop
        # rows stay NULL ("unknown") rather than being mislabeled. New ingests
        # set the exact source (services/collector_service.py).
        conn.execute(text(
            "UPDATE creators SET source = 'tiktok_shop' "
            "WHERE source IS NULL AND platform = 'tiktok_shop'"
        ))

        # AI outreach upgrade — tone / language / length controls + multi-version drafts
        _ensure_column(conn, "outreach_templates", "tone", "VARCHAR(20)")
        _ensure_column(conn, "outreach_templates", "max_length", "INTEGER")
        _ensure_column(conn, "outreach_emails", "ai_versions_json", "TEXT")
        _ensure_column(conn, "outreach_emails", "parent_email_id", "VARCHAR(120)")
        _ensure_column(conn, "outreach_emails", "ai_tone", "VARCHAR(20)")
        _ensure_column(conn, "outreach_emails", "ai_language", "VARCHAR(10)")
        _ensure_index(conn, "ix_outreach_emails_parent_email_id", "outreach_emails", "parent_email_id")


def _columns(conn, table: str) -> set[str]:
    if engine.dialect.name == "sqlite":
        return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
    rows = conn.execute(
        text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :table
        """),
        {"table": table},
    )
    return {row[0] for row in rows}


def _ensure_column(conn, table: str, column: str, sql_type: str) -> None:
    if column in _columns(conn, table):
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))


def _ensure_index(conn, index_name: str, table: str, column: str) -> None:
    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({column})"))


def _set_nulls(conn, table: str, column: str, value: str) -> None:
    if column not in _columns(conn, table):
        return
    conn.execute(text(f"UPDATE {table} SET {column} = :value WHERE {column} IS NULL OR {column} = ''"), {"value": value})


def _set_nulls_typed(conn, table: str, column: str, value) -> None:
    if column not in _columns(conn, table):
        return
    conn.execute(text(f"UPDATE {table} SET {column} = :value WHERE {column} IS NULL"), {"value": value})


def _drop_not_null(conn, table: str, column: str) -> None:
    if engine.dialect.name == "sqlite":
        return
    if column not in _columns(conn, table):
        return
    try:
        conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL"))
    except Exception:
        pass


def _ensure_remote_department_column(conn) -> None:
    if not settings.db_url.startswith(("postgresql://", "postgresql+")):
        return
    table = settings.remote_table
    if not table.replace("_", "").isalnum():
        return
    if table not in {"creators"} and not _columns(conn, table):
        return
    _ensure_column(conn, table, "department_code", "VARCHAR(40)")
    _ensure_index(conn, f"ix_{table}_department_code", table, "department_code")
    _set_nulls(conn, table, "department_code", DEFAULT_DEPARTMENT)


def _seed_default_outreach_templates() -> None:
    """Insert built-in outreach templates if the table is empty.

    Templates are also rebuildable from
    :func:`backend.services.outreach_service.default_templates`; we seed
    here so the UI has something to show on first launch without requiring
    an admin import step.
    """
    try:
        from ..services.outreach_service import default_templates  # noqa: WPS433
    except Exception:  # pragma: no cover - service imports failed; bail.
        return
    from ..models.outreach_template import OutreachTemplate  # noqa: WPS433

    with SessionLocal() as session:
        existing = session.query(OutreachTemplate).count()
        if existing > 0:
            return
        for template in default_templates():
            session.add(OutreachTemplate(**template))
        session.commit()
