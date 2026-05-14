import { useLocation } from 'react-router-dom';
import { Bell, Globe, Moon, Calendar, ChevronDown } from 'lucide-react';
import RoleSwitcher from '@/components/role/RoleSwitcher';
import { pageMeta } from './menus';

export default function TopBar() {
  const { pathname } = useLocation();
  const meta = pageMeta[pathname] || { title: '页面', subtitle: '' };

  return (
    <header className="h-14 bg-white border-b border-line flex items-center px-5 gap-4 shrink-0">
      <div className="flex items-baseline gap-3 min-w-0">
        <h1 className="text-base font-semibold text-gray-800 truncate">{meta.title}</h1>
        <span className="text-xs text-muted truncate hidden md:block">{meta.subtitle}</span>
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        <button className="w-8 h-8 rounded flex items-center justify-center text-muted hover:text-gray-700 hover:bg-soft">
          <Bell size={16} />
        </button>
        <button className="w-8 h-8 rounded flex items-center justify-center text-muted hover:text-gray-700 hover:bg-soft">
          <Globe size={16} />
        </button>
        <button className="w-8 h-8 rounded flex items-center justify-center text-muted hover:text-gray-700 hover:bg-soft">
          <Moon size={16} />
        </button>
        <div className="w-px h-6 bg-line mx-1" />
        <button className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs text-gray-700 hover:bg-soft border border-line">
          <Calendar size={14} className="text-muted" />
          <span>近 7 天</span>
          <ChevronDown size={12} className="text-muted" />
        </button>
        <div className="w-px h-6 bg-line mx-1" />
        <RoleSwitcher />
      </div>
    </header>
  );
}
