from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
EXPORT_DIR = DATA_DIR / "exports"
LOG_DIR = ROOT_DIR / "logs"
UI_DIR = Path(__file__).resolve().parent / "ui"

_PROCESS_ENV = dict(os.environ)
load_dotenv(ROOT_DIR.parent / ".env.shared")
load_dotenv(ROOT_DIR / ".env", override=True)
os.environ.update(_PROCESS_ENV)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    if raw is not None:
        return raw
    if os.name == "nt":
        try:
            import winreg  # type: ignore

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _value_type = winreg.QueryValueEx(key, name)
                return str(value)
        except Exception:
            return default
    return default


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "local")
    app_name: str = os.getenv("APP_NAME", "x9_creator_desktop_system")
    system_version: str = os.getenv("X9_SYSTEM_VERSION", "1.0")
    backend_port: int = int(os.getenv("BACKEND_PORT", "8000"))
    admin_emails: str = _env_str("X9_ADMIN_EMAILS", "")
    super_admin_username: str = _env_str("X9_SUPER_ADMIN_USERNAME", "superadmin")
    super_admin_password: str = _env_str("X9_SUPER_ADMIN_PASSWORD", "X9@2026")
    db_url: str = os.getenv(
        "LOCAL_DB_URL",
        f"sqlite:///{(DATA_DIR / 'creators.sqlite').as_posix()}",
    )
    # Extension heartbeats fire via chrome.alarms with a minimum period of
    # 30 seconds (browser-enforced for performance). Allow ~3x slack so a
    # single missed beat doesn't paint the dashboard "offline".
    extension_offline_seconds: int = int(os.getenv("EXTENSION_OFFLINE_SECONDS", "90"))
    score_version: str = "creator_score_v3.0"
    tag_version: str = "creator_tag_v3.0"
    rec_version: str = "recommendation_v3.0"

    # ---- Remote X9 backend (this app reads/writes the remote DB only) ----
    # Local SQLite is no longer the source of truth 鈥?it's only kept around
    # for tables that haven't been migrated yet (creator_tags etc.).
    remote_api_url: str = os.getenv("REMOTE_API_URL", "https://usx9.us")
    remote_api_key: str = os.getenv("REMOTE_API_KEY", "")
    remote_table: str = os.getenv("REMOTE_TABLE", "tk_creators")
    remote_timeout: float = float(os.getenv("REMOTE_TIMEOUT", "10"))

    # ----- Gmail OAuth client -----
    # The deployed server owns one Google OAuth Web client. Users authorize
    # their own Gmail accounts through Google, and the server exchanges the
    # authorization code for tokens bound to the logged-in local user.
    # Keep the client secret and token encryption key server-side only.
    # If a user drops their own ``data/gmail_client_secret.json`` it takes
    # precedence over these defaults.
    gmail_default_client_id: str = os.getenv("GMAIL_DEFAULT_CLIENT_ID", "")
    gmail_default_client_secret: str = os.getenv("GMAIL_DEFAULT_CLIENT_SECRET", "")
    gmail_default_project_id: str = os.getenv("GMAIL_DEFAULT_PROJECT_ID", "x9-creator-leads")
    gmail_token_encryption_key: str = _env_str("GMAIL_TOKEN_ENCRYPTION_KEY", "")

    # ----- Outreach AI writer -----
    # Keep API keys in .env / process env only; never hardcode them in source.
    openai_api_key: str = _env_str("OPENAI_API_KEY", "")
    openai_model: str = _env_str("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url: str = _env_str("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_timeout: float = float(_env_str("OPENAI_TIMEOUT", "30"))


settings = Settings()
