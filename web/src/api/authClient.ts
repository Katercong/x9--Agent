// Auth uses desktop backend's /api/local/auth/* (cookie-based x9_session, path=/).
// This is separate from client.ts, which talks to /api/v1/* through desktop.
import type { AuthMeResponse, CurrentUser } from './types';

// Same retry policy as client.ts apiFetch: 502/503/504 + network errors get
// retried twice with backoff for idempotent methods. /me is the most-called
// endpoint on the dashboard, so a transient gateway hiccup shouldn't bounce
// the user out to /login.
const TRANSIENT_STATUSES = new Set([502, 503, 504]);
const RETRY_DELAYS_MS = [200, 800];

function isIdempotent(method: string | undefined): boolean {
  const m = (method || 'GET').toUpperCase();
  return m === 'GET' || m === 'HEAD';
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

async function authFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = '/api/local/auth' + path;
  const idempotent = isIdempotent(init?.method);
  let attempt = 0;

  while (true) {
    let res: Response;
    try {
      res = await fetch(url, {
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...((init?.headers as Record<string, string>) || {}) },
        ...init,
      });
    } catch (networkErr) {
      if (idempotent && attempt < RETRY_DELAYS_MS.length) {
        console.warn(`[authFetch] network error on ${url}, retry ${attempt + 1}`);
        await sleep(RETRY_DELAYS_MS[attempt]);
        attempt += 1;
        continue;
      }
      throw networkErr;
    }

    if (!res.ok && idempotent && TRANSIENT_STATUSES.has(res.status) && attempt < RETRY_DELAYS_MS.length) {
      console.warn(`[authFetch] ${res.status} on ${url}, retry ${attempt + 1}`);
      await sleep(RETRY_DELAYS_MS[attempt]);
      attempt += 1;
      continue;
    }

    if (!res.ok) {
      let body: unknown = null;
      try { body = await res.json(); } catch { /* ignore */ }
      const detail = (body && typeof body === 'object' && 'detail' in body && (body as any).detail) || res.statusText;
      throw new Error(String(detail));
    }

    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('application/json')) {
      throw new Error('non-JSON response from auth API');
    }
    return (await res.json()) as T;
  }
}

export interface AuthUserStats {
  collection: { scope: 'company' | 'department'; total: number; today: number };
  creators: { owned: number; pending_contact: number; contacted: number };
  outreach: { total: number; drafts: number; queued: number; sent: number; failed: number; cancelled: number; last_at?: string | null };
}

export interface AuthUserRow {
  id: string;
  username: string;
  email: string | null;
  display_name: string | null;
  role: string;
  base_role?: string;
  approval_status: string; // active | pending | rejected | disabled
  is_active: boolean;
  department_name?: string | null;
  stats?: AuthUserStats;
}

export const authApi = {
  me: () => authFetch<AuthMeResponse>('/me'),
  login: (username: string, password: string) =>
    authFetch<{ ok: boolean; user: CurrentUser }>('/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  logout: () => authFetch<{ ok: boolean }>('/logout', { method: 'POST' }),

  // Desktop-backend user management (registration approval lives here).
  users: () => authFetch<{ ok: boolean; items: AuthUserRow[] }>('/users'),
  approveUser: (key: string) =>
    authFetch<{ ok: boolean }>(`/users/${encodeURIComponent(key)}/approve`, { method: 'POST' }),
  rejectUser: (key: string) =>
    authFetch<{ ok: boolean }>(`/users/${encodeURIComponent(key)}/reject`, { method: 'POST' }),
  patchUser: (
    key: string,
    body: Partial<{
      role: string;
      department_code: string;
      display_name: string;
      is_active: boolean;
      approval_status: string;
    }>,
  ) =>
    authFetch<{ ok: boolean; user: AuthUserRow }>(`/users/${encodeURIComponent(key)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
};
