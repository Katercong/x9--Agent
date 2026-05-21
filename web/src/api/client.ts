// Lightweight fetch wrapper for the FastAPI backend.
// /api/v1 is authenticated through the desktop proxy and must never fall back to mock data.

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

// Set this from app init if you need to attach an API key.
let API_KEY: string | null = null;
export function setApiKey(key: string | null) {
  API_KEY = key;
}

function qs(params?: Record<string, unknown>): string {
  if (!params) return '';
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.append(k, String(v));
  }
  const s = sp.toString();
  return s ? '?' + s : '';
}

// Statuses worth retrying once. Network errors (TypeError on fetch) and
// gateway-level failures from Cloudflare Tunnel / upstream restarts often
// resolve themselves on a quick retry. 502/503/504 are idempotent-safe for
// GET; we deliberately don't retry POST/PUT/DELETE to avoid duplicating writes.
const TRANSIENT_STATUSES = new Set([502, 503, 504]);
const RETRY_DELAYS_MS = [200, 800]; // 2 retries → 3 attempts total

function isIdempotent(method: string | undefined): boolean {
  const m = (method || 'GET').toUpperCase();
  return m === 'GET' || m === 'HEAD';
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit & { params?: Record<string, unknown> },
): Promise<T> {
  const url = path + qs(init?.params);
  const { params: _params, ...fetchInit } = init ?? {};
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((fetchInit.headers as Record<string, string>) || {}),
  };
  if (API_KEY) headers['X-API-Key'] = API_KEY;

  const idempotent = isIdempotent(fetchInit.method);
  let attempt = 0;
  let lastError: unknown = null;

  while (true) {
    let res: Response;
    try {
      res = await fetch(url, {
        ...fetchInit,
        credentials: fetchInit.credentials ?? 'same-origin',
        headers,
      });
    } catch (networkErr) {
      // Network-level failure (DNS, TLS, connection reset, offline).
      lastError = networkErr;
      if (idempotent && attempt < RETRY_DELAYS_MS.length) {
        console.warn(`[apiFetch] network error on ${url}, retry ${attempt + 1}`, networkErr);
        await sleep(RETRY_DELAYS_MS[attempt]);
        attempt += 1;
        continue;
      }
      throw networkErr;
    }

    // Retry transient 5xx for safe methods only.
    if (!res.ok && idempotent && TRANSIENT_STATUSES.has(res.status) && attempt < RETRY_DELAYS_MS.length) {
      console.warn(`[apiFetch] ${res.status} on ${url}, retry ${attempt + 1}`);
      await sleep(RETRY_DELAYS_MS[attempt]);
      attempt += 1;
      continue;
    }

    if (!res.ok) {
      let body: unknown = null;
      try {
        body = await res.json();
      } catch {
        try {
          body = await res.text();
        } catch {
          /* ignore */
        }
      }
      const msg =
        (body && typeof body === 'object' && 'detail' in body && (body as any).detail) ||
        res.statusText ||
        `HTTP ${res.status}`;
      throw new ApiError(res.status, String(msg), body);
    }
    if (res.status === 204) return undefined as T;

    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('application/json')) {
      throw new ApiError(res.status, 'Expected JSON response, got ' + ct);
    }
    return (await res.json()) as T;
  }
  // Unreachable, but keeps TS happy.
  void lastError;
}

export const api = {
  get: <T>(path: string, params?: Record<string, unknown>) =>
    apiFetch<T>(path, { method: 'GET', params }),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  del: <T>(path: string) => apiFetch<T>(path, { method: 'DELETE' }),
};
