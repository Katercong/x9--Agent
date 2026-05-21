# X9 PostgreSQL Database

This project now uses the local PostgreSQL database as its primary data source.

## Connection

The project-level `.env` contains:

```env
LOCAL_DB_URL=postgresql+psycopg://x9:***@localhost:15432/x9db
X9_PG_DSN=postgresql://x9:***@localhost:15432/x9db?connect_timeout=5
```

`LOCAL_DB_URL` is used by SQLAlchemy inside `backend/database/connection.py`.
`X9_PG_DSN` is available for direct `psycopg` scripts.

## Current Database

- Container: `x9-postgres`
- Database: `x9db`
- Host port: `15432`
- Driver: `psycopg`

## Verify

Run from this project folder:

```powershell
py -3.11 scripts\check_postgres_database.py
```

Expected output should show `dialect=postgresql` and row counts for `creators`,
`creator_tags`, `creator_recommendations`, `outreach_emails`, and
`outreach_templates`.

The old SQLite file remains in `data\creators.sqlite` as a backup and is no
longer the configured source of truth.
