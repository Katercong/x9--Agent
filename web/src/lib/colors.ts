export const colors = {
  brand: '#3370ff',
  good: '#16a34a',
  warn: '#f5a623',
  bad: '#ef4444',
  muted: '#86909c',
  sidebar: {
    bg: '#1f1f2e',
    hover: '#2a2a3d',
    textMuted: '#b8b8c4',
    textActive: '#ffffff',
  },
  sidebarSel: {
    bg: '#fef3eb',
    bar: '#f97316',
    text: '#d97706',
  },
  // 状态机 9 色
  status: {
    prospect: '#94a3b8',
    contacted: '#60a5fa',
    confirmed: '#3370ff',
    sample_shipped: '#8b5cf6',
    sample_delivered: '#a855f7',
    video_published: '#f59e0b',
    ad_authorized: '#10b981',
    ad_running: '#16a34a',
    dropped: '#ef4444',
  } as Record<string, string>,
  tier: {
    S: '#dc2626',
    A: '#ea580c',
    B: '#3370ff',
    C: '#16a34a',
    D: '#86909c',
  } as Record<string, string>,
  kpiIconBg: [
    '#e0e7ff',
    '#d1fae5',
    '#cffafe',
    '#fed7aa',
    '#ede9fe',
    '#fce7f3',
    '#fef3c7',
    '#dbeafe',
    '#fef9c3',
    '#fee2e2',
  ],
  kpiIconFg: [
    '#4f46e5',
    '#16a34a',
    '#0891b2',
    '#ea580c',
    '#7c3aed',
    '#db2777',
    '#ca8a04',
    '#2563eb',
    '#a16207',
    '#dc2626',
  ],
};

export const chartPalette = {
  sequential: [
    '#eff5ff', '#dbe7ff', '#bed1ff', '#94b1ff', '#6087ff', '#3370ff',
    '#2c5fd9', '#2050d4', '#1a3fa8', '#162f80', '#101f55', '#0a142c',
  ],
  diverging: [
    '#dc2626', '#ef4444', '#f97316', '#f5a623', '#fbbf24',
    '#86909c', '#a3e635', '#84cc16', '#22c55e', '#16a34a', '#15803d',
  ],
  categorical: [
    '#3370ff', '#f5a623', '#16a34a', '#ef4444', '#8b5cf6',
    '#06b6d4', '#ec4899', '#84cc16', '#f97316', '#0ea5e9',
    '#a855f7', '#14b8a6',
  ],
};

export const statusLabel: Record<string, string> = {
  prospect: '潜在',
  contacted: '已联系',
  confirmed: '已确认',
  sample_shipped: '样品已寄',
  sample_delivered: '样品签收',
  video_published: '视频已发',
  ad_authorized: '已授权',
  ad_running: '广告投放中',
  dropped: '已放弃',
};
