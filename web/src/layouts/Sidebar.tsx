import { useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { ChevronsLeft, ChevronsRight, X } from 'lucide-react';
import { useRoleStore } from '@/stores/roleStore';
import { departmentMenu, companyMenu, superMenu, type MenuItem } from './menus';
import { cn } from '@/lib/cn';

export default function Sidebar() {
  const { currentRole, sidebarCollapsed, toggleSidebar, mobileDrawerOpen, closeMobileDrawer } = useRoleStore();
  const { pathname } = useLocation();

  const menu: MenuItem[] =
    currentRole === 'company' ? companyMenu : currentRole === 'super' ? superMenu : departmentMenu;

  useEffect(() => { closeMobileDrawer(); }, [pathname, closeMobileDrawer]);
  useEffect(() => {
    if (mobileDrawerOpen) {
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = ''; };
    }
  }, [mobileDrawerOpen]);

  return (
    <>
      {mobileDrawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={closeMobileDrawer}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          'flex flex-col text-sidebar-text transition-transform duration-300 shrink-0',
          'md:relative md:translate-x-0',
          sidebarCollapsed ? 'md:w-[68px]' : 'md:w-[220px]',
          'fixed inset-y-0 left-0 z-50 w-[240px]',
          mobileDrawerOpen ? 'translate-x-0' : '-translate-x-full',
        )}
        style={{ background: '#1f1f2e' }}
      >
        {/* Logo */}
        <div className="h-14 flex items-center px-4 gap-2.5 shrink-0">
          <div className="w-8 h-8 rounded-md flex items-center justify-center font-bold text-white text-sm shrink-0"
               style={{ background: 'linear-gradient(135deg, #f97316 0%, #dc2626 100%)' }}>
            X9
          </div>
          <div className={cn(
            'text-white text-sm font-medium leading-tight whitespace-nowrap flex-1',
            sidebarCollapsed && 'md:hidden',
          )}>
            X9 管理员
          </div>
          <button
            onClick={closeMobileDrawer}
            className="md:hidden text-[#b8b8c4] hover:text-white"
            aria-label="关闭菜单"
          >
            <X size={18} />
          </button>
        </div>

        {/* Menu */}
        <nav className="flex-1 overflow-y-auto px-2 py-2">
          {menu.map((item) => (
            <NavLink
              key={item.key}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'relative flex items-center gap-3 px-3 py-2 my-0.5 rounded text-xs transition-colors',
                  isActive
                    ? 'text-[#d97706] font-medium'
                    : 'text-[#b8b8c4] hover:text-white hover:bg-[#2a2a3d]',
                )
              }
              style={({ isActive }) =>
                isActive ? { background: '#fef3eb' } : undefined
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span
                      className="absolute left-0 top-1 bottom-1 w-[3px] rounded-r"
                      style={{ background: '#f97316' }}
                    />
                  )}
                  <item.icon size={16} className="shrink-0" />
                  <span className={cn('whitespace-nowrap', sidebarCollapsed && 'md:hidden')}>
                    {item.label}
                  </span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Collapse (desktop only) */}
        <button
          onClick={toggleSidebar}
          className="hidden md:flex h-10 items-center gap-2 px-4 text-xs text-[#b8b8c4] hover:text-white border-t border-[#2a2a3d] shrink-0"
        >
          {sidebarCollapsed ? <ChevronsRight size={14} /> : <ChevronsLeft size={14} />}
          <span className={cn(sidebarCollapsed && 'md:hidden')}>收起菜单</span>
        </button>
      </aside>
    </>
  );
}
