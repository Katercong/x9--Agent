// Defense-in-depth route guard.
//
// AuthGate (App.tsx) already redirects users into their default area on initial
// load, but a determined user could still navigate by URL inside the SPA after
// load. RoleGuard wraps each role's route subtree (super/company/department)
// and bounces unauthorized users back to their home — so even if AuthGate's
// effect fires late or is bypassed, the wrong UI never renders.
//
// We pair this with the backend `_admin_spa_role` check in
// `desktop/backend/main.py:103-112`, so a hard refresh on a forbidden URL is
// caught server-side (303 redirect), and an in-app navigation is caught here.
import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useRoleStore, allowedRolesFor, homeForUser, type Role } from '@/stores/roleStore';

interface RoleGuardProps {
  required: Role;
  children: ReactNode;
}

export function RoleGuard({ required, children }: RoleGuardProps) {
  const user = useRoleStore((s) => s.currentUser);
  // No user means AuthGate is still resolving — render nothing rather than
  // flashing the unauthorized UI for a frame. AuthGate's loading state is
  // already showing somewhere up the tree.
  if (!user) return null;

  const allowed = allowedRolesFor(user);
  if (!allowed.includes(required)) {
    const home = homeForUser(user);
    if (home.startsWith('/portal/')) {
      window.location.href = home;
      return null;
    }
    return <Navigate to={home} replace />;
  }
  return <>{children}</>;
}
