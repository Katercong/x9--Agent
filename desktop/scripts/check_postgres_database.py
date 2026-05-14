from __future__ import annotations

from pathlib import Path
import sys

from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import settings  # noqa: E402
from backend.database.connection import engine  # noqa: E402


def masked_url(url: str) -> str:
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    _auth, host = rest.split("@", 1)
    return f"{scheme}://***:***@{host}"


def main() -> None:
    print(f"db_url={masked_url(settings.db_url)}")
    print(f"dialect={engine.dialect.name}")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                  (SELECT COUNT(*) FROM creators) AS creators,
                  (SELECT COUNT(*) FROM creator_tags) AS creator_tags,
                  (SELECT COUNT(*) FROM creator_recommendations) AS creator_recommendations,
                  (SELECT COUNT(*) FROM outreach_emails) AS outreach_emails,
                  (SELECT COUNT(*) FROM outreach_templates) AS outreach_templates
                """
            )
        ).mappings().one()
    for key, value in rows.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
