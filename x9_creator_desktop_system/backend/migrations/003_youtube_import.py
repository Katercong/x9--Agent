"""003_youtube_import: create YouTube import and cleaned lead tables.

Safe to run multiple times. SQLAlchemy metadata owns the table definitions.

Usage:
  py -3.11 -m x9_creator_desktop_system.backend.migrations.003_youtube_import
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from x9_creator_desktop_system.backend.youtube_database import init_youtube_db, youtube_engine  # noqa: E402


def main() -> int:
    init_youtube_db()
    print(f"[003_youtube_import] complete. db={youtube_engine.url} dialect={youtube_engine.dialect.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
