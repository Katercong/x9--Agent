# Archive

This folder is for project artifacts that are useful for reference but should not be treated as active runtime code.

## Current Buckets

- `extensions/`: historical Chrome extension packages and snapshots.

## Rules

- Do not import runtime code from this folder.
- Do not store live database files, OAuth tokens, or production secrets here.
- If an archived item is needed by an install script, copy the exact files into the active package first and document that dependency.

## Legacy Note

`x9_creator_desktop_system/` is still at the repository root for now because tests, deployment scripts, and compatibility imports still reference `x9_creator_desktop_system.backend.*`. Move it only after those imports are migrated or a compatibility shim is added.
