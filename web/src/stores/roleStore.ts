import { create } from 'zustand';
import type { BackendRole, CurrentUser } from '@/api/types';

export type Role = 'company' | 'department' | 'super';

interface RoleState {
  // ---------- UI state ----------
  currentRole: Role;
  switchRole: (role: Role) => void;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  mobileDrawerOpen: boolean;
  openMobileDrawer: () => void;
  closeMobileDrawer: () => void;

  // ---------- Real user state ----------
  currentUser: CurrentUser | null;
  setCurrentUser: (u: CurrentUser | null) => void;
}

export const useRoleStore = create<RoleState>((set) => ({
  currentRole: 'department',
  switchRole: (role) => set({ currentRole: role }),
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  mobileDrawerOpen: false,
  openMobileDrawer: () => set({ mobileDrawerOpen: true }),
  closeMobileDrawer: () => set({ mobileDrawerOpen: false }),
  currentUser: null,
  setCurrentUser: (u) => set({ currentUser: u }),
}));

// ---------- Display labels ----------
export const roleLabel: Record<Role, string> = {
  company: '公司管理员',
  department: '部门管理员',
  super: '超级管理员',
};

export const roleSubtitle: Record<Role, string> = {
  company: '老板视角 · 全公司业绩',
  department: '部门内部业务运营',
  super: '系统配置 · 全局运维',
};

export const roleHome: Record<Role, string> = {
  company: '/c/overview',
  department: '/d/dashboard',
  super: '/a/dashboard',
};

// ---------- Backend role mapping ----------
// 后端 4 种角色 → 前端 3 种视图域 + 允许的访问范围
const BACKEND_PRIMARY: Record<BackendRole, Role> = {
  super_admin: 'super',
  company_admin: 'company',
  department_admin: 'department',
  department_user: 'department',
};

const BACKEND_ALLOWED: Record<BackendRole, Role[]> = {
  super_admin: ['super'],
  company_admin: ['company'],
  department_admin: ['department'],
  department_user: [],
};

/** 后端角色对应的默认前端入口角色。 */
export function defaultRoleFor(user: CurrentUser | null): Role {
  if (!user) return 'department';
  return BACKEND_PRIMARY[user.role] ?? 'department';
}

/** 后端角色允许访问的所有前端视图域。 */
export function allowedRolesFor(user: CurrentUser | null): Role[] {
  if (!user) return [];
  return BACKEND_ALLOWED[user.role] ?? [];
}

/** Backend user home. Workspace users live in /portal/, outside this admin SPA. */
export function homeForUser(user: CurrentUser | null): string {
  if (!user) return '/login';
  if (user.role === 'department_user' || user.entry_scope !== 'admin') {
    return '/portal/';
  }
  return roleHome[defaultRoleFor(user)];
}

/** 中文角色名(展示用)。 */
export const backendRoleLabel: Record<BackendRole, string> = {
  super_admin: '超级管理员',
  company_admin: '公司管理员',
  department_admin: '部门管理员',
  department_user: '部门成员',
};
