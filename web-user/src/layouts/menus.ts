import {
  Home, BarChart3, Telescope, Sparkles,
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
  { key: 'workbench', label: '工作台', to: '/', icon: Home },
  { key: 'business', label: '业务看板', to: '/business', icon: BarChart3 },
  {
    key: 'creator-data',
    label: '达人数据采集',
    icon: Users,
    children: [
      { key: 'collection', label: '采集总览', to: '/collection', icon: Telescope },
      { key: 'collect-shop', label: '采集 · TikTok Shop', to: '/collect-shop', icon: Store },
      { key: 'collect-leads', label: '采集 · X9 线索', to: '/collect-leads', icon: Radar },
      { key: 'collect-import', label: '采集 · 表格导入', to: '/collect-import', icon: FileSpreadsheet },
    ],
  },
  { key: 'recommendations', label: '达人库', to: '/recommendations', icon: Sparkles },
  { key: 'export', label: '数据工具', to: '/export', icon: ArrowDownToLine },
  { key: 'hotkw', label: 'TikTok 热搜', to: '/hotkw', icon: TrendingUp },
  { key: 'assistant', label: 'AI 助手', to: '/assistant', icon: Bot },
];

export const pageMeta: Record<string, { title: string; subtitle: string }> = {
  '/': { title: '工作台', subtitle: '待处理事项、采集状态与常用入口' },
  '/business': { title: '业务看板', subtitle: '管理员看公司全量，部门账号看当前部门' },
  '/collection': { title: '采集总览', subtitle: '插件状态、任务进度与三类达人采集渠道统一入口' },
  '/collect-shop': { title: '采集 · TikTok Shop', subtitle: 'affiliate-us 全自动采集 · 漏斗 / 类目 / 点击达人看详情' },
  '/collect-leads': { title: '采集 · X9 线索', subtitle: 'www.tiktok.com 卡片流 · 联系方式覆盖与趋势' },
  '/collect-import': { title: '采集 · 表格导入', subtitle: 'CSV / XLSX 批量导入 · 国家 / Tier / 质量分布' },
  '/creators-info': { title: '达人库', subtitle: '已合并到推荐池与全部达人统一页面' },
  '/recommendations': { title: '达人库', subtitle: '推荐池 / 全部达人统一视图 · 点击达人进入详情与邮件建联' },
  '/export': { title: '数据工具', subtitle: '导出文件、下载模板，正式导入统一到表格导入页' },
  '/hotkw': { title: 'TikTok 热搜', subtitle: '热门关键词与增长趋势' },
  '/assistant': { title: 'AI 助手', subtitle: '智能问答与运维指引' },
};
