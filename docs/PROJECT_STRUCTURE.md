# Project Structure

This repository is now organized around a few active roots plus an archive area.

## Active Roots

| Path | Role | Notes |
|---|---|---|
| `core/` | Core API and shared business data services | Port `18765`; this should hold shared product, creator, AI, and central data logic. |
| `desktop/` | Desktop/backend portal runtime | Port `8000`; active FastAPI backend, Chrome extension bridge, Gmail outreach, and portal static host. |
| `web-user/` | Portal frontend source | React/Vite source for `/portal/*`; build output is generated and should not be edited manually. |
| `web/` | Admin/global frontend source | React/Vite source for admin/global dashboards where applicable. |
| `scrapers/` | Collection utilities | CLI and helper tools that collect or normalize source platform data. |
| `infra/` | Infrastructure and deployment scripts | Docker, local/remote startup, database setup, tunnel scripts. |
| `tools/` | One-off maintenance tools | Diagnostics, sync, smoke tests, data checks. |
| `docs/` | Product, architecture, deployment, and cleanup docs | Keep decisions and migration notes here. |
| `archive/` | Historical reference artifacts | Not imported by runtime code. |

## Compatibility Roots

| Path | Status | Next Step |
|---|---|---|
| `x9_creator_desktop_system/` | Legacy compatibility package | Keep in place until tests and scripts stop importing `x9_creator_desktop_system.backend.*`. |

## Generated Files Policy

Generated frontend bundles are ignored going forward:

- `web-user/dist-deploy/`
- `web-user/dist-root/`
- `web/dist*`
- `desktop/backend/ui/portal/`
- `desktop/backend/ui/admin/`
- `desktop/backend/ui/_react/`
- matching generated UI folders under `x9_creator_desktop_system/`

Source changes should be made in `web-user/src`, `web/src`, or backend code, then rebuilt and deployed by scripts.

## Data and Secrets Policy

Local databases, Gmail OAuth files, tokens, tunnel binaries, logs, and machine-specific config stay out of git. Use `.env.example` or documentation for shape, not real values.

`x9_creator_desktop_system/data/creators.sqlite` is tracked today as legacy data. The target state is to remove runtime databases from git after any needed migration/backup is verified.

## Cleanup Backlog

1. Migrate tests and deployment scripts from `x9_creator_desktop_system.backend.*` imports to `desktop.backend.*` or add a small compatibility shim.
2. Remove tracked build bundles from git history/current index after confirming deployment scripts rebuild them reliably.
3. Replace mojibake README sections with clean UTF-8 Chinese docs.
4. Move temporary screenshots and ad-hoc previews into `docs/screenshots/` when they are still useful; otherwise delete them.
5. Audit `.env.shared` because it is ignored now but still appears in repository history.
