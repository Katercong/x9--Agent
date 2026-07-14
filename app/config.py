from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


PROJECT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_project_environment() -> bool:
    """加载项目根目录的本地 .env，已存在的系统环境变量保持优先。"""

    return load_dotenv(PROJECT_ENV_FILE, override=False)
