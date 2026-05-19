import {
  LayoutDashboard, BarChart3, Telescope, Sparkles, ClipboardCheck,
  ArrowDownToLine, TrendingUp, Bot, Users, Store, Radar, FileSpreadsheet,
  type LucideIcon,
} from 'lucide-react';

export type MenuItem = {
  key: string;
  label: string;
  to: string;
  icon: LucideIcon;
};

export type MenuGroup = {
  key: string;
  label: string;
  icon: LucideIcon;
  children: MenuItem[];
};

export type MenuEntry = MenuItem | MenuGroup;

// 严格镜像 desktop/backend/ui/index.html 侧边栏顺序
export const portalMenu: MenuEntry[] = [
  { key: 'business', label: '业务看板', to: '/business', icon: BarChart3 },
  { key: 'dashboard', label: '仪表盘', to: '/dashboard', icon: LayoutDashboard },
  { key: 'collection', label: '采集监控', to: '/collection', icon: Telescope },
  {
    key: 'creator-data',
    label: '达人数据采集',
    icon: Users,
    children: [
      { key: 'collect-shop', label: '采集 · TikTok Shop', to: '/collect-shop', icon: Store },
      { key: 'collect-leads', label: '采集 · X9 线索', to: '/collect-leads', icon: Radar },
      { key: 'collect-import', label: '采集 · 表格导入', to: '/collect-import', icon: FileSpreadsheet },
    ],
  },
  { key: 'creators-info', label: '达人信息', to: '/creators-info', icon: Users },
  { key: 'recommendations', label: '推荐列表', to: '/recommendations', icon: Sparkles },
  { key: 'review', label: '人工审核', to: '/review', icon: ClipboardCheck },
  { key: 'export', label: '导出/导入', to: '/export', icon: ArrowDownToLine },
  { key: 'hotkw', label: 'TikTok 热搜', to: '/hotkw', icon: TrendingUp },
  { key: 'assistant', label: 'AI 助手', to: '/assistant', icon: Bot },
];

export const pageMeta: Record<string, { title: string; subtitle: string }> = {
  '/business': { title: '业务看板', subtitle: '按当前部门数据实时汇总' },
  '/dashboard': { title: '仪表盘', subtitle: '系统状态与今日数据' },
  '/collection': { title: '采集监控', subtitle: '浏览器扩展实时上传创作者观察记录' },
  '/collect-shop': { title: '采集 · TikTok Shop', subtitle: 'affiliate-us 全自动采集 · 漏斗 / 类目 / 点击达人看详情' },
  '/collect-leads': { title: '采集 · X9 线索', subtitle: 'www.tiktok.com 卡片流 · 联系方式覆盖与趋势' },
  '/collect-import': { title: '采集 · 表格导入', subtitle: 'CSV / XLSX 批量导入 · 国家 / Tier / 质量分布' },
  '/creators-info': { title: '达人信息', subtitle: '三大来源达人统一视图 · 来源筛选与联系方式' },
  '/recommendations': { title: '推荐列表', subtitle: 'AI 评分后的高质量达人候选' },
  '/review': { title: '人工审核', subtitle: '低置信度推荐人工复审' },
  '/export': { title: '导出 / 导入', subtitle: 'CSV / Excel 数据导入导出' },
  '/hotkw': { title: 'TikTok 热搜', subtitle: '热门关键词与增长趋势' },
  '/assistant': { title: 'AI 助手', subtitle: '智能问答与运维指引' },
};
