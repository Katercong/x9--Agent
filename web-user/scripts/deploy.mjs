#!/usr/bin/env node
// Copies dist-deploy/ → desktop/backend/ui/portal/
// Run via: npm run deploy   (after `npm run build:deploy`)
import { existsSync, rmSync, mkdirSync, readdirSync, statSync, copyFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const SRC = resolve(__dirname, '..', 'dist-deploy');
const DEST = resolve(__dirname, '..', '..', 'desktop', 'backend', 'ui', 'portal');

if (!existsSync(SRC)) {
  console.error('[deploy] Source not found:', SRC);
  console.error('[deploy] Run `npm run build:deploy` first.');
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
  console.log('[deploy] Cleaning', DEST);
  rmSync(DEST, { recursive: true, force: true });
}
console.log('[deploy] Copying', SRC, '→', DEST);
copyDir(SRC, DEST);
console.log('[deploy] Done. Mount path: /portal/');
console.log('[deploy] Reachable at: http://localhost:8000/portal/');
