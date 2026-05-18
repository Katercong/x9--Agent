// 用户端 API 客户端 — 对接 desktop/backend 的 /api/local/*
// 使用 cookie 会话(credentials: 'include'),401 时自动跳 /login
import { matchMock } from './mock';

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

const API_BASE = '/api/local';

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

export async function apiFetch<T>(
  path: string,
  init?: RequestInit & { params?: Record<string, unknown> },
): Promise<T> {
  const url = API_BASE + path + qs(init?.params);
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init?.headers as Record<string, string>) || {}),
  };
  let res: Response;
  try {
    res = await fetch(url, { ...init, headers, credentials: 'include' });
  } catch (e) {
    // 网络错误 → dev 模式返回 mock
    if (import.meta.env.DEV) {
      const mock = matchMock(url);
      if (mock !== null) return mock as T;
    }
    throw e;
  }

  // Dev 模式下 401/404/5xx → 返回 mock(让 UI 用占位数据完整渲染)
  if (import.meta.env.DEV && !res.ok) {
    const mock = matchMock(url);
    if (mock !== null) return mock as T;
  }

  // 401 → 跳到登录页(仅生产构建,dev 预览不跳)
  if (res.status === 401) {
    if (import.meta.env.PROD && !window.location.pathname.startsWith('/login')) {
      window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
    }
    throw new ApiError(401, 'login required');
  }

  if (!res.ok) {
    let body: unknown = null;
    try { body = await res.json(); } catch {
      try { body = await res.text(); } catch { /* ignore */ }
    }
    const msg =
      (body && typeof body === 'object' && 'detail' in body && (body as any).detail) ||
      res.statusText ||
      `HTTP ${res.status}`;
    throw new ApiError(res.status, String(msg), body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get:  <T>(path: string, params?: Record<string, unknown>) =>
    apiFetch<T>(path, { method: 'GET', params }),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put:  <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'PUT',  body: body ? JSON.stringify(body) : undefined }),
  del:  <T>(path: string) => apiFetch<T>(path, { method: 'DELETE' }),
};
