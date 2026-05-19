import { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { ChevronDown, ChevronsLeft, ChevronsRight, Download, X } from 'lucide-react';
import { useUiStore } from '@/stores/uiStore';
import { portalMenu, type MenuEntry, type MenuItem } from './menus';
import { cn } from '@/lib/cn';

function isMenuGroup(entry: MenuEntry): entry is Extract<MenuEntry, { children: MenuItem[] }> {
  return 'children' in entry;
}

export default function Sidebar() {
  const { sidebarCollapsed, toggleSidebar, mobileDrawerOpen, closeMobileDrawer } = useUiStore();
  const { pathname } = useLocation();
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const activeGroupKey = portalMenu.find(
    (entry) => isMenuGroup(entry) && entry.children.some((item) => pathname === item.to),
  )?.key;

  const toggleGroup = (key: string) => {
    setOpenGroups((current) => ({ ...current, [key]: !(current[key] ?? true) }));
  };

  useEffect(() => {
    if (!activeGroupKey) return;
    setOpenGroups((current) => {
      if (current[activeGroupKey] === true || current[activeGroupKey] === undefined) {
        return current;
      }
      return { ...current, [activeGroupKey]: true };
    });
  }, [activeGroupKey, pathname]);

  // 路由变化时自动关闭移动抽屉
  useEffect(() => {
  useEffect(() => {
    closeMobileDrawer();
  }, [pathname, closeMobileDrawer]);

  // 抽屉打开时锁定 body 滚动
  useEffect(() => {
    if (mobileDrawerOpen) {
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = ''; };
    }
  }, [mobileDrawerOpen]);

  return (
    <>
      {/* Scrim — 仅移动端抽屉打开时显示 */}
      {mobileDrawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={closeMobileDrawer}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          'flex flex-col shrink-0 border-r border-border transition-transform duration-300',
          // 桌面端:固定占位、收起 68px / 展开 220px、永远可见
          'md:relative md:translate-x-0',
          sidebarCollapsed ? 'md:w-[68px]' : 'md:w-[220px]',
          // 移动端:fixed 抽屉、宽 240px、根据状态滑入/滑出
          'fixed inset-y-0 left-0 z-50 w-[240px]',
          mobileDrawerOpen ? 'translate-x-0' : '-translate-x-full',
        )}
        style={{ background: 'rgb(var(--bg-elev-1))' }}
      >
        {/* Brand */}
        <div className="h-14 flex items-center px-4 gap-2.5 shrink-0 border-b border-border">
          <div
            className="w-8 h-8 rounded-md flex items-center justify-center font-bold text-white text-sm shrink-0"
            style={{ background: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)' }}
          >X9</div>
          {/* 在桌面收起态隐藏文字;移动抽屉永远显示 */}
          <div
            className={cn(
              'text-text text-sm font-semibold leading-tight whitespace-nowrap truncate flex-1',
              sidebarCollapsed && 'md:hidden',
            )}
          >
            X9 达人线索后台
          </div>
          {/* 移动端关闭按钮 */}
          <button
            onClick={closeMobileDrawer}
            className="md:hidden text-muted hover:text-text"
            aria-label="关闭菜单"
          >
            <X size={18} />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto px-2 py-2">
          {portalMenu.map((entry) => (
            isMenuGroup(entry) ? (
              <div key={entry.key} className="my-1">
                <button
                  type="button"
                  onClick={() => toggleGroup(entry.key)}
                  title={entry.label}
                  aria-expanded={openGroups[entry.key] ?? true}
                  className={cn(
                    'w-full relative flex items-center gap-3 px-3 py-2 my-0.5 rounded text-xs transition-colors',
                    entry.children.some((item) => pathname === item.to)
                      ? 'text-white font-semibold'
                      : 'text-text/75 hover:text-text hover:bg-white/5',
                  )}
                >
                  <entry.icon size={16} className="shrink-0" />
                  <span className={cn('whitespace-nowrap flex-1 text-left', sidebarCollapsed && 'md:hidden')}>
                    {entry.label}
                  </span>
                  <ChevronDown
                    size={14}
                    className={cn(
                      'shrink-0 transition-transform text-muted',
                      !(openGroups[entry.key] ?? true) && '-rotate-90',
                      sidebarCollapsed && 'md:hidden',
                    )}
                  />
                </button>
                {(openGroups[entry.key] ?? true) && (
                  <div className={cn(!sidebarCollapsed && 'md:pl-4')}>
                    {entry.children.map((item) => (
                      <SidebarLink key={item.key} item={item} sidebarCollapsed={sidebarCollapsed} nested />
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <SidebarLink key={entry.key} item={entry} sidebarCollapsed={sidebarCollapsed} />
            )
          ))}
        </nav>

        {/* Foot */}
        <div className="border-t border-border">
          <a
            href="/api/local/extension/download"
            className="flex items-center gap-3 px-4 py-2.5 text-xs text-muted hover:text-text"
          >
            <Download size={14} className="shrink-0" />
            <span className={cn(sidebarCollapsed && 'md:hidden')}>下载插件</span>
          </a>
          {/* 桌面端折叠按钮 — 移动端隐藏(移动端有专门的 X 关闭) */}
          <button
            onClick={toggleSidebar}
            className="hidden md:flex w-full h-10 items-center gap-2 px-4 text-xs text-muted hover:text-text border-t border-border"
          >
            {sidebarCollapsed ? <ChevronsRight size={14} /> : <ChevronsLeft size={14} />}
            <span className={cn(sidebarCollapsed && 'md:hidden')}>收起菜单</span>
          </button>
        </div>
      </aside>
    </>
  );
}

function SidebarLink({ item, sidebarCollapsed, nested = false }: { item: MenuItem; sidebarCollapsed: boolean; nested?: boolean }) {
  return (
    <NavLink
      to={item.to}
      title={item.label}
      aria-label={item.label}
      className={({ isActive }) =>
        cn(
          'relative flex items-center gap-3 px-3 py-2 my-0.5 rounded text-xs transition-colors',
          nested && !sidebarCollapsed && 'md:py-1.5',
          isActive ? 'text-white font-semibold' : 'text-text/75 hover:text-text hover:bg-white/5',
        )
      }
      style={({ isActive }) =>
        isActive ? { background: 'rgb(var(--accent) / 0.18)' } : undefined
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <span
              className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r"
              style={{ background: 'rgb(var(--accent))' }}
            />
          )}
          <item.icon size={16} className="shrink-0" />
          {/* 桌面收起态隐藏文字;移动端永远显示 */}
          <span className={cn('whitespace-nowrap', sidebarCollapsed && 'md:hidden')}>
            {item.label}
          </span>
        </>
      )}
    </NavLink>
  );
}
