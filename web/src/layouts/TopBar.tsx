import { useLocation } from 'react-router-dom';
import { Bell, Globe, Moon, Calendar, ChevronDown, Menu } from 'lucide-react';
import RoleSwitcher from '@/components/role/RoleSwitcher';
import { useRoleStore } from '@/stores/roleStore';
import { pageMeta } from './menus';

export default function TopBar() {
  const { pathname } = useLocation();
  const meta = pageMeta[pathname] || { title: '页面', subtitle: '' };
  const { openMobileDrawer } = useRoleStore();

  return (
    <header className="h-14 bg-white border-b border-line flex items-center px-3 md:px-5 gap-2 md:gap-4 shrink-0">
      <button
        onClick={openMobileDrawer}
        className="md:hidden w-9 h-9 rounded flex items-center justify-center text-muted hover:text-gray-700 shrink-0"
        aria-label="打开菜单"
      >
        <Menu size={18} />
      </button>

      <div className="flex items-baseline gap-3 min-w-0 flex-1 md:flex-initial">
        <h1 className="text-sm md:text-base font-semibold text-gray-800 truncate">{meta.title}</h1>
        <span className="text-xs text-muted truncate hidden md:block">{meta.subtitle}</span>
      </div>

      <div className="ml-auto flex items-center gap-1 md:gap-1.5">
        <button className="hidden md:flex w-8 h-8 rounded items-center justify-center text-muted hover:text-gray-700 hover:bg-soft">
          <Bell size={16} />
        </button>
        <button className="hidden md:flex w-8 h-8 rounded items-center justify-center text-muted hover:text-gray-700 hover:bg-soft">
          <Globe size={16} />
        </button>
        <button className="w-8 h-8 rounded flex items-center justify-center text-muted hover:text-gray-700 hover:bg-soft">
          <Moon size={16} />
        </button>
        <div className="hidden md:block w-px h-6 bg-line mx-1" />
        <button className="hidden md:flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs text-gray-700 hover:bg-soft border border-line">
          <Calendar size={14} className="text-muted" />
          <span>近 7 天</span>
          <ChevronDown size={12} className="text-muted" />
        </button>
        <div className="hidden md:block w-px h-6 bg-line mx-1" />
        <RoleSwitcher />
      </div>
    </header>
  );
}
