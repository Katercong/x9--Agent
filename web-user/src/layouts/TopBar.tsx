import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { RefreshCw, Moon, Sun, LogOut, Menu, KeyRound } from 'lucide-react';
import { useUiStore } from '@/stores/uiStore';
import { useMe } from '@/hooks/useApi';
import { endpoints } from '@/api/endpoints';
import { useQueryClient } from '@tanstack/react-query';
import { ChangePasswordDialog } from '@/components/account/ChangePasswordDialog';
import { getPageMeta } from './menus';

const topBarCopy = {
  zh: {
    refresh: '刷新',
    switchLanguage: '切换到 English',
    switchTheme: '切换主题',
    openMenu: '打开菜单',
    logout: '退出',
    changePassword: '修改密码',
    anonymous: '匿名',
    emptyRole: '--',
    languageTarget: 'EN',
  },
  en: {
    refresh: 'Refresh',
    switchLanguage: 'Switch to Chinese',
    switchTheme: 'Toggle theme',
    openMenu: 'Open menu',
    logout: 'Log out',
    changePassword: 'Change password',
    anonymous: 'Anonymous',
    emptyRole: '--',
    languageTarget: '中',
  },
};

export default function TopBar() {
  const { pathname } = useLocation();
  const { theme, toggleTheme, language, toggleLanguage, openMobileDrawer } = useUiStore();
  const meta = getPageMeta(pathname, language);
  const copy = topBarCopy[language];
  const { data: me } = useMe();
  const qc = useQueryClient();
  const [passwordOpen, setPasswordOpen] = useState(false);

  const onRefresh = () => qc.invalidateQueries();
  const onLogout = async () => {
    try { await endpoints.logout(); } catch { /* ignore */ }
    window.location.href = '/login';
  };

  const user = me?.user;
  const username = user?.display_name || user?.username || copy.anonymous;

  return (
    <>
      <header
        className="h-14 border-b border-border flex items-center px-3 md:px-5 gap-2 md:gap-4 shrink-0"
        style={{ background: 'rgb(var(--bg-elev-1))' }}
      >
        <button
          onClick={openMobileDrawer}
          className="md:hidden w-9 h-9 rounded flex items-center justify-center text-muted hover:text-text shrink-0"
          aria-label={copy.openMenu}
        >
          <Menu size={18} />
        </button>

        <div className="flex items-baseline gap-3 min-w-0 flex-1 md:flex-initial">
          <h1 className="text-sm md:text-base font-semibold truncate">{meta.title}</h1>
          <span className="text-xs text-muted truncate hidden md:block">{meta.subtitle}</span>
        </div>

        <div className="ml-auto flex items-center gap-1 md:gap-1.5 shrink-0">
          <button
            onClick={onRefresh}
            className="w-8 h-8 rounded flex items-center justify-center text-muted hover:text-text"
            title={copy.refresh}
            aria-label={copy.refresh}
          >
            <RefreshCw size={15} />
          </button>
          <button
            onClick={toggleLanguage}
            className="flex w-8 h-8 rounded items-center justify-center text-muted hover:text-text"
            title={copy.switchLanguage}
            aria-label={copy.switchLanguage}
          >
            <span className="text-xs font-medium">{copy.languageTarget}</span>
          </button>
          <button
            onClick={toggleTheme}
            className="w-8 h-8 rounded flex items-center justify-center text-muted hover:text-text"
            title={copy.switchTheme}
            aria-label={copy.switchTheme}
          >
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
          </button>
          <div className="hidden md:block w-px h-6 bg-border mx-1" />

          <div className="flex items-center gap-2 px-1 md:px-2 py-1 rounded">
            <div
              className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0"
              style={{ background: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)' }}
            >
              {username[0]?.toUpperCase() || 'U'}
            </div>
            <div className="hidden md:flex flex-col items-start leading-tight">
              <span className="text-xs font-medium">{username}</span>
              <span className="text-xxs text-muted">{user?.role || copy.emptyRole}</span>
            </div>
            <button
              onClick={() => setPasswordOpen(true)}
              className="w-7 h-7 rounded flex items-center justify-center text-muted hover:text-text"
              title={copy.changePassword}
              aria-label={copy.changePassword}
            >
              <KeyRound size={14} />
            </button>
            <button
              onClick={onLogout}
              className="w-7 h-7 rounded flex items-center justify-center text-muted hover:text-bad"
              title={copy.logout}
              aria-label={copy.logout}
            >
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </header>

      <ChangePasswordDialog
        open={passwordOpen}
        language={language}
        onClose={() => setPasswordOpen(false)}
      />
    </>
  );
}
