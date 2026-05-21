import { create } from 'zustand';

type Theme = 'dark' | 'light';

interface UiState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  // 移动端抽屉(独立于桌面端折叠)
  mobileDrawerOpen: boolean;
  openMobileDrawer: () => void;
  closeMobileDrawer: () => void;
  theme: Theme;
  toggleTheme: () => void;
  language: 'zh' | 'en';
  toggleLanguage: () => void;
}

function initialTheme(): Theme {
  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem('x9-theme');
    if (stored === 'dark' || stored === 'light') return stored;
  }
  return 'dark';
}

export const useUiStore = create<UiState>((set) => ({
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  mobileDrawerOpen: false,
  openMobileDrawer: () => set({ mobileDrawerOpen: true }),
  closeMobileDrawer: () => set({ mobileDrawerOpen: false }),
  theme: initialTheme(),
  toggleTheme: () =>
    set((s) => {
      const next: Theme = s.theme === 'dark' ? 'light' : 'dark';
      localStorage.setItem('x9-theme', next);
      document.documentElement.setAttribute('data-theme', next);
      return { theme: next };
    }),
  language: (typeof localStorage !== 'undefined' && (localStorage.getItem('x9_ui_language') as 'zh' | 'en')) || 'zh',
  toggleLanguage: () =>
    set((s) => {
      const next: 'zh' | 'en' = s.language === 'zh' ? 'en' : 'zh';
      localStorage.setItem('x9_ui_language', next);
      return { language: next };
    }),
}));
