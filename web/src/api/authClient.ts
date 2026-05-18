// Auth uses desktop backend's /api/local/auth/* (cookie-based x9_session, path=/).
// This is separate from client.ts, which talks to /api/v1/* through desktop.
import type { AuthMeResponse, CurrentUser } from './types';

async function authFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch('/api/local/auth' + path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...((init?.headers as Record<string, string>) || {}) },
    ...init,
  });

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
