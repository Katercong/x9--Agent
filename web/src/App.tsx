import { useEffect } from 'react';
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import AppShell from './layouts/AppShell';
import { departmentRoutes } from './pages/department/routes';
import { companyRoutes } from './pages/company/routes';
import { superRoutes } from './pages/super/routes';
import { useAuthMe } from './hooks/useAuth';
import {
  useRoleStore, defaultRoleFor, allowedRolesFor, roleHome,
} from './stores/roleStore';

export default function App() {
  return <AuthGate />;
}

/**
 * Bootstraps the app:
 *  - Fetches current user from /api/local/auth/me on load
 *  - If not logged in → redirect to /login (existing vanilla page)
 *  - If logged in but visiting a role-locked path → redirect to user's home
 *  - Auto-sets currentRole + currentUser in zustand
 */
function AuthGate() {
  const { data, isLoading, error } = useAuthMe();
  const { setCurrentUser, switchRole, currentRole } = useRoleStore();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  // On user info arrival, sync to store
  useEffect(() => {
    if (!data) return;
    if (!data.logged_in || !data.user) {
      setCurrentUser(null);
      // Avoid infinite loop if user is on /login already (shouldn't happen — login is at desktop /login HTML)
      window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
      return;
    }
    setCurrentUser(data.user);

    // Compute default role for this user
    const defaultRole = defaultRoleFor(data.user);
    const allowed = allowedRolesFor(data.user);

    // If current path doesn't belong to an allowed role's area, redirect to user's home
    const inC = pathname.startsWith('/c/');
    const inD = pathname.startsWith('/d/');
    const inA = pathname.startsWith('/a/');
    const currentPathRole = inC ? 'company' : inD ? 'department' : inA ? 'super' : null;

    if (pathname === '/' || !currentPathRole) {
      // Landing at root or unknown path → redirect to user's primary home
      navigate(roleHome[defaultRole], { replace: true });
      switchRole(defaultRole);
    } else if (!allowed.includes(currentPathRole)) {
      // User tried to access a forbidden area (e.g. department_user → /c/overview)
      navigate(roleHome[defaultRole], { replace: true });
      switchRole(defaultRole);
    } else {
      // Path is allowed — keep zustand role in sync with URL
      if (currentRole !== currentPathRole) {
        switchRole(currentPathRole);
      }
    }
  }, [currentRole, data, navigate, pathname, setCurrentUser, switchRole]);

  if (isLoading) {
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
    // Already redirected via useEffect — show transient state
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
        <Route index element={<Navigate to={roleHome[defaultRoleFor(data.user!)]} replace />} />
        {departmentRoutes}
        {companyRoutes}
        {superRoutes}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

function NotFound() {
  return (
    <div className="flex items-center justify-center h-full text-muted">页面未找到</div>
  );
}
