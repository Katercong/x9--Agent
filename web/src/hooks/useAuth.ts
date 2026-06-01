import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { authApi } from '@/api/authClient';
import type { AuthMeResponse } from '@/api/types';

const AUTH_KEY = ['auth', 'me'];
const CACHE_KEY = 'x9.auth.me.v1';

// Stale-while-revalidate: cache the last `/me` response in localStorage so a
// hard refresh paints the dashboard immediately (no white flash), and we
// re-validate in the background. If the background fetch comes back 401, the
// AuthGate effect redirects to /login as before.
function readCachedAuthMe(): AuthMeResponse | undefined {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as AuthMeResponse & { _cachedAt?: number };
    // Discard caches older than 12h — if someone hasn't opened the dashboard
    // in half a day, their session is probably gone anyway.
    if (parsed._cachedAt && Date.now() - parsed._cachedAt > 12 * 3600 * 1000) {
      localStorage.removeItem(CACHE_KEY);
      return undefined;
    }
    return parsed;
  } catch {
    return undefined;
  }
}

function writeCachedAuthMe(data: AuthMeResponse | null): void {
  try {
    if (!data || !data.logged_in) {
      localStorage.removeItem(CACHE_KEY);
      return;
    }
    localStorage.setItem(CACHE_KEY, JSON.stringify({ ...data, _cachedAt: Date.now() }));
  } catch {
    /* localStorage full or disabled — fall through */
  }
}

export function useAuthMe() {
  return useQuery({
    queryKey: AUTH_KEY,
    queryFn: async () => {
      const data = await authApi.me();
      writeCachedAuthMe(data);
      return data;
    },
    staleTime: 60_000,
    retry: false,
    // Render instantly from cache on first mount; React Query still fires
    // the queryFn in the background to revalidate.
    placeholderData: readCachedAuthMe,
  });
}

export function useLogin() {
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      authApi.login(username, password),
  });
}

export function useLogout() {
  return useMutation({
    mutationFn: async () => {
      const result = await authApi.logout();
      // Logout: nuke the SWR cache so the next mount doesn't briefly render
      // the just-logged-out user from localStorage.
      writeCachedAuthMe(null);
      return result;
    },
  });
}

export function useChangePassword() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ oldPassword, newPassword }: { oldPassword: string; newPassword: string }) =>
      authApi.changePassword(oldPassword, newPassword),
    onSuccess: async () => {
      localStorage.removeItem(CACHE_KEY);
      await qc.invalidateQueries({ queryKey: AUTH_KEY });
    },
  });
}
