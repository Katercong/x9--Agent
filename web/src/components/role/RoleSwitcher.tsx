import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Briefcase, Building, Shield, LogIn, LogOut, Loader2 } from 'lucide-react';
import {
  useRoleStore, backendRoleLabel,
  type Role,
} from '@/stores/roleStore';
import { useLogout } from '@/hooks/useAuth';

const roleIcon: Record<Role, typeof Briefcase> = {
  company: Briefcase,
  department: Building,
  super: Shield,
};

const roleColor: Record<Role, string> = {
  company: '#f97316',
  department: '#3370ff',
  super: '#8b5cf6',
};

export default function RoleSwitcher() {
  const { currentRole, currentUser } = useRoleStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const logout = useLogout();

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const username = currentUser?.display_name || currentUser?.username || '未登录';
  const userRoleLabel = currentUser ? backendRoleLabel[currentUser.role] : '未登录';
  const departmentName = currentUser?.department_name || currentUser?.department_code || '';
  const Icon = roleIcon[currentRole];

  const handleLogout = () => {
    if (!confirm('确定退出登录？')) return;
    logout.mutate(undefined, {
      onSettled: () => { window.location.href = '/login'; },
    });
  };

  const handleLogin = () => {
    window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-2.5 py-1.5 rounded hover:bg-soft transition-colors"
      >
        <span
          className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold"
          style={{ background: currentUser ? roleColor[currentRole] : '#86909c' }}
        >
          <Icon size={14} />
        </span>
        <div className="hidden md:flex flex-col items-start leading-tight">
          <span className="text-xs font-medium text-gray-800 truncate max-w-[160px]">{username}</span>
          <span className="text-xxs text-muted">{userRoleLabel}{departmentName ? ` · ${departmentName}` : ''}</span>
        </div>
        <ChevronDown size={14} className="text-muted" />
      </button>

      {open && (
        <div className="absolute right-0 mt-1 w-72 bg-white border border-line rounded-md shadow-soft py-1 z-50">
          <div className="px-3 py-3 border-b border-line">
            <div className="flex items-center gap-2.5">
              <span
                className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-bold shrink-0"
                style={{ background: currentUser ? roleColor[currentRole] : '#86909c' }}
              >
                {username[0]?.toUpperCase() || '?'}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-gray-800 truncate">{username}</div>
                <div className="text-xxs text-muted truncate">
                  {currentUser?.username && currentUser.username !== username && (
                    <span>@{currentUser.username} · </span>
                  )}
                  {userRoleLabel}
                </div>
                {departmentName && <div className="text-xxs text-muted truncate">部门：{departmentName}</div>}
              </div>
            </div>
          </div>

          <div className="px-3 py-2 text-xxs text-muted">
            角色由登录会话决定，不能在前端切换身份。
          </div>

          <div className="border-t border-line">
            {currentUser ? (
              <button
                onClick={handleLogout}
                disabled={logout.isPending}
                className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-soft text-left transition-colors text-xs text-bad disabled:opacity-50"
              >
                {logout.isPending ? <Loader2 size={14} className="animate-spin" /> : <LogOut size={14} />}
                <span>退出登录</span>
              </button>
            ) : (
              <button
                onClick={handleLogin}
                className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-soft text-left transition-colors text-xs text-brand-500"
              >
                <LogIn size={14} />
                <span>前往登录</span>
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
