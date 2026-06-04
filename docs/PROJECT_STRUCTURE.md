# Project Structure

This repository is now organized around a few active roots plus an archive area.

The current runtime mainline is `desktop/` plus two React source roots:
`web/` for the admin/global UI and `web-user/` for the department portal.
`core/` still provides the product/AI/data center and the proxied `/api/v1`
surface. See `docs/system_boundary_and_acceptance.md` for the operational
boundary and verification checklist.

## Active Roots

| Path | Role | Notes |
|---|---|---|
| `desktop/` | Main backend/runtime | Port `8000`; active FastAPI backend, auth, role routing, Chrome extension bridge, Gmail outreach, recommendation pipeline, foreign-trade leads, and static host. |
| `web/` | Admin/global frontend source | React/Vite source for `/`, `/a/*`, `/c/*`, `/d/*`, and `/preview/*`; deploys to `desktop/backend/ui/admin/`. |
| `web-user/` | Portal frontend source | React/Vite source for `/portal/*`; deploys to `desktop/backend/ui/portal/`. |
| `core/` | Core API and shared business data services | Port `18765`; product catalog, legacy data center, LLM/AI routes, and `/api/v1` resources proxied by desktop. |
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

Source changes should be made in `web-user/src`, `web/src`, or backend code,
then rebuilt and deployed by scripts:

- `web`: `npm run build:root` then `npm run deploy:root`
- `web-user`: `npm run build:deploy` then `npm run deploy`
- backend code: restart the desktop backend after deploying

Markdown-only documentation changes do not require frontend rebuilds or backend restart.

## Data and Secrets Policy

Local databases, Gmail OAuth files, tokens, tunnel binaries, logs, and machine-specific config stay out of git. Use `.env.example` or documentation for shape, not real values.

`x9_creator_desktop_system/data/creators.sqlite` is tracked today as legacy data. The target state is to remove runtime databases from git after any needed migration/backup is verified.

## Cleanup Backlog

1. Migrate tests and deployment scripts from `x9_creator_desktop_system.backend.*` imports to `desktop.backend.*` or add a small compatibility shim.
2. Remove tracked build bundles from git history/current index after confirming deployment scripts rebuild them reliably.
3. Replace mojibake README sections with clean UTF-8 Chinese docs.
4. Move temporary screenshots and ad-hoc previews into `docs/screenshots/` when they are still useful; otherwise delete them.
5. Audit `.env.shared` because it is ignored now but still appears in repository history.
