#!/usr/bin/env node
// Deploy the root-base React build to desktop/backend/ui/_react/
// (Mounted at "/" by desktop/backend/main.py, becomes the default usx9.us face.)
// /portal/ keeps working independently via the other deploy script.
import { existsSync, rmSync, mkdirSync, readdirSync, statSync, copyFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const SRC = resolve(__dirname, '..', 'dist-root');
const DEST = resolve(__dirname, '..', '..', 'desktop', 'backend', 'ui', '_react');

if (!existsSync(SRC)) {
  console.error('[deploy-root] Source not found:', SRC);
  console.error('[deploy-root] Run `npm run build:root` first.');
  process.exit(1);
}

function copyDir(src, dest) {
  mkdirSync(dest, { recursive: true });
  for (const entry of readdirSync(src)) {
    const s = join(src, entry);
    const d = join(dest, entry);
    if (statSync(s).isDirectory()) copyDir(s, d);
    else copyFileSync(s, d);
  }
}

if (existsSync(DEST)) {
  console.log('[deploy-root] Cleaning', DEST);
  rmSync(DEST, { recursive: true, force: true });
}
console.log('[deploy-root] Copying', SRC, '→', DEST);
copyDir(SRC, DEST);
console.log('[deploy-root] Done. Mount point: / (replaces landing.html)');
console.log('[deploy-root] Old /portal/ still works for legacy URLs.');
