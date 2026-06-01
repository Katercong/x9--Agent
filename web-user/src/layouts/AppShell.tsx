import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useMe } from '@/hooks/useApi';
import { GmailOAuthFeedback } from '@/components/outreach/GmailOAuthFeedback';
import Sidebar from './Sidebar';
import TopBar from './TopBar';

export default function AppShell() {
  const meQ = useMe();
  const location = useLocation();

  useEffect(() => {
    if (location.pathname !== '/') return;
    const role = meQ.data?.user?.role;
    const adminHome =
      role === 'super_admin' ? '/a/dashboard' :
      role === 'company_admin' ? '/c/overview' :
      role === 'department_admin' ? '/d/dashboard' :
      '';
    if (!adminHome) return;
    window.location.replace(adminHome + (location.search || ''));
  }, [location.pathname, location.search, meQ.data?.user?.role]);

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'rgb(var(--bg))' }}>
      <GmailOAuthFeedback />
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 overflow-y-auto">
          <div className="p-3 md:p-5">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
