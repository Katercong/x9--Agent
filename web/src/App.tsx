import { useEffect, useRef } from 'react';
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import AppShell from './layouts/AppShell';
import { departmentRoutes } from './pages/department/routes';
import { companyRoutes } from './pages/company/routes';
import { superRoutes } from './pages/super/routes';
import { previewRoutes } from './pages/preview/routes';
import { useAuthMe } from './hooks/useAuth';
import {
  useRoleStore, defaultRoleFor, allowedRolesFor, homeForUser, type Role,
} from './stores/roleStore';
import type { CurrentUser } from './api/types';

export default function App() {
  return <AuthGate />;
}

/**
 * Bootstraps the app:
 *  - Fetches current user from /api/local/auth/me on load (with localStorage SWR placeholder)
 *  - If not logged in → redirect to /login (existing vanilla page)
 *  - If logged in but visiting a role-locked path → redirect to user's home
 *  - Syncs zustand role state with the URL
 *
 * Flicker fix:
 *  - `useAuthMe` returns `placeholderData` from localStorage, so the first paint
 *    after refresh already has user info — no white loading flash.
 *  - The path-role sync effect tracks its last computed role in a ref so it
 *    no longer depends on `currentRole`, killing the
 *    useEffect → switchRole → useEffect re-entry loop that caused the
 *    rapid super↔department visual flip.
 *  - While the *initial* fetch is in flight with no cache, we render the
 *    loading state instead of `<Routes>` so a forbidden URL never flashes
 *    its content for a frame before the redirect lands.
 */
function AuthGate() {
  const { data, isLoading, error } = useAuthMe();
  const setCurrentUser = useRoleStore((s) => s.setCurrentUser);
  const switchRole = useRoleStore((s) => s.switchRole);
  const navigate = useNavigate();
  const { pathname } = useLocation();

  // Track the last path-role we synced to the store. This breaks the cycle
  // where `switchRole(...)` would update store state, re-fire the effect,
  // and (depending on timing) cause a second navigate(). Now the effect
  // only acts when the URL or user *actually* changes.
  const lastSyncedRoleRef = useRef<Role | null>(null);

  useEffect(() => {
    if (!data) return;
    if (!data.logged_in || !data.user) {
      setCurrentUser(null);
      lastSyncedRoleRef.current = null;
      // Already on the dashboard surface — bounce to /login (a vanilla page
      // served by the desktop backend, outside React Router).
      window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
      return;
    }
    setCurrentUser(data.user);

    const defaultRole = defaultRoleFor(data.user);
    const allowed = allowedRolesFor(data.user);

    const inC = pathname.startsWith('/c/');
    const inD = pathname.startsWith('/d/');
    const inA = pathname.startsWith('/a/');
    const inPreview = pathname.startsWith('/preview');
    const currentPathRole: Role | null = inC ? 'company' : inD ? 'department' : inA ? 'super' : null;

    // Preview pages are open to all roles — don't redirect away from them.
    if (inPreview) {
      return;
    }

    if (data.user.role === 'department_user' || data.user.entry_scope !== 'admin') {
      window.location.href = homeForUser(data.user);
      return;
    }

    if (pathname === '/' || !currentPathRole) {
      if (lastSyncedRoleRef.current !== defaultRole) {
        navigate(homeForUser(data.user), { replace: true });
        switchRole(defaultRole);
        lastSyncedRoleRef.current = defaultRole;
      }
      return;
    }

    if (!allowed.includes(currentPathRole)) {
      // User tried to access a forbidden area (e.g. department_user → /c/overview)
      if (lastSyncedRoleRef.current !== defaultRole) {
        navigate(homeForUser(data.user), { replace: true });
        switchRole(defaultRole);
        lastSyncedRoleRef.current = defaultRole;
      }
      return;
    }

    // Path is allowed — keep zustand role in sync, but only when it actually changed.
    if (lastSyncedRoleRef.current !== currentPathRole) {
      switchRole(currentPathRole);
      lastSyncedRoleRef.current = currentPathRole;
    }
    // Intentionally NOT depending on `currentRole` — the ref guards against
    // the re-entry that would otherwise cause flicker on hard refresh.
  }, [data, navigate, pathname, setCurrentUser, switchRole]);

  // No cache and the fetch is still pending → show loading, do NOT render
  // any role-locked routes. Without this, the first paint can briefly show a
  // route the user isn't allowed on before the effect's navigate() lands.
  if (isLoading && !data) {
    return (
      <div className="flex h-screen items-center justify-center gap-2 text-muted text-sm">
        <Loader2 size={16} className="animate-spin" />
        正在验证身份…
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex h-screen items-center justify-center text-sm">
        <div className="card card-body max-w-md">
          <div className="text-bad mb-2">无法连接到登录服务</div>
          <div className="text-xxs text-muted">{(error as any)?.message || 'unknown'}</div>
          <a href="/login" className="btn btn-primary mt-3 inline-flex">前往登录页</a>
        </div>
      </div>
    );
  }
  if (!data?.logged_in) {
    return (
      <div className="flex h-screen items-center justify-center text-muted text-sm gap-2">
        <Loader2 size={16} className="animate-spin" />
        跳转登录…
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<HomeRedirect user={data.user!} />} />
        {departmentRoutes}
        {companyRoutes}
        {superRoutes}
        {previewRoutes}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

function HomeRedirect({ user }: { user: CurrentUser }) {
  const home = homeForUser(user);
  if (home.startsWith('/portal/')) {
    window.location.href = home;
    return (
      <div className="flex h-screen items-center justify-center gap-2 text-muted text-sm">
        <Loader2 size={16} className="animate-spin" />
        跳转工作台…
      </div>
    );
  }
  return <Navigate to={home} replace />;
}

function NotFound() {
  return (
    <div className="flex items-center justify-center h-full text-muted">页面未找到</div>
  );
}
