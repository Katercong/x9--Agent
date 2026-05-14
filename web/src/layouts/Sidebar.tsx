import { NavLink } from 'react-router-dom';
import { ChevronsLeft, ChevronsRight } from 'lucide-react';
import { useRoleStore } from '@/stores/roleStore';
import { departmentMenu, companyMenu, superMenu, type MenuItem } from './menus';
import { cn } from '@/lib/cn';

export default function Sidebar() {
  const { currentRole, sidebarCollapsed, toggleSidebar } = useRoleStore();

  const menu: MenuItem[] =
    currentRole === 'company' ? companyMenu : currentRole === 'super' ? superMenu : departmentMenu;

  return (
    <aside
      className={cn(
        'flex flex-col text-sidebar-text transition-all duration-200 shrink-0',
        sidebarCollapsed ? 'w-[68px]' : 'w-[220px]',
      )}
      style={{ background: '#1f1f2e' }}
    >
      {/* Logo */}
      <div className="h-14 flex items-center px-4 gap-2.5 shrink-0">
        <div className="w-8 h-8 rounded-md flex items-center justify-center font-bold text-white text-sm shrink-0"
             style={{ background: 'linear-gradient(135deg, #f97316 0%, #dc2626 100%)' }}>
          X9
        </div>
        {!sidebarCollapsed && (
          <div className="text-white text-sm font-medium leading-tight whitespace-nowrap">
            X9 管理员
          </div>
        )}
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
              isActive
                ? { background: '#fef3eb' }
                : undefined
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
                {!sidebarCollapsed && <span className="whitespace-nowrap">{item.label}</span>}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Collapse */}
      <button
        onClick={toggleSidebar}
        className="h-10 flex items-center gap-2 px-4 text-xs text-[#b8b8c4] hover:text-white border-t border-[#2a2a3d] shrink-0"
      >
        {sidebarCollapsed ? <ChevronsRight size={14} /> : <ChevronsLeft size={14} />}
        {!sidebarCollapsed && <span>收起菜单</span>}
      </button>
    </aside>
  );
}
