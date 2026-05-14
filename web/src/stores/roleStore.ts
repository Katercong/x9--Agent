import { create } from 'zustand';

export type Role = 'company' | 'department' | 'super';

interface RoleState {
  currentRole: Role;
  switchRole: (role: Role) => void;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
}

export const useRoleStore = create<RoleState>((set) => ({
  currentRole: 'department',
  switchRole: (role) => set({ currentRole: role }),
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}));

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
  super: '/a/monitor',
};
