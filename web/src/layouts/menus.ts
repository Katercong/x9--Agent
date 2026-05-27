import {
  LayoutDashboard,
  Users,
  Search,
  Mail,
  Package,
  Video,
  ShoppingBag,
  Settings,
  TrendingUp,
  Wallet,
  Building2,
  Sparkles,
  Filter,
  Trophy,
  Globe,
  CalendarClock,
  Activity,
  KeyRound,
  Brain,
  Webhook,
  ScrollText,
  Database,
  FileCode,
  Gauge,
  Store,
  Radar,
  FileSpreadsheet,
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

export const departmentMenu: MenuEntry[] = [
  { key: 'd-dashboard', label: '数据看板', to: '/d/dashboard', icon: LayoutDashboard },
  {
    key: 'd-creator-data',
    label: '达人数据采集',
    icon: Users,
    children: [
      { key: 'd-collect-shop', label: '采集 · TikTok Shop', to: '/d/collect-shop', icon: Store },
      { key: 'd-collect-leads', label: '采集 · X9 线索', to: '/d/collect-leads', icon: Radar },
      { key: 'd-collect-import', label: '采集 · 表格导入', to: '/d/collect-import', icon: FileSpreadsheet },
    ],
  },
  { key: 'd-creators', label: '达人管理', to: '/d/creators', icon: Users },
  { key: 'd-leads', label: '线索管理', to: '/d/leads', icon: Search },
  { key: 'd-emails', label: '邮件管理', to: '/d/emails', icon: Mail },
  { key: 'd-samples', label: '样品管理', to: '/d/samples', icon: Package },
  { key: 'd-videos', label: '视频管理', to: '/d/videos', icon: Video },
  { key: 'd-products', label: '产品管理', to: '/d/products', icon: ShoppingBag },
  { key: 'd-settings', label: '设置中心', to: '/d/settings', icon: Settings },
];

export const companyMenu: MenuEntry[] = [
  { key: 'c-overview', label: '业绩总览', to: '/c/overview', icon: LayoutDashboard },
  { key: 'c-revenue', label: '营收与利润', to: '/c/revenue', icon: Wallet },
  { key: 'c-departments', label: '部门绩效', to: '/c/departments', icon: Building2 },
  { key: 'c-growth', label: '增长趋势', to: '/c/growth', icon: TrendingUp },
  { key: 'c-funnel', label: '转化漏斗', to: '/c/funnel', icon: Filter },
  { key: 'c-products', label: 'SKU 价值地图', to: '/c/products', icon: Trophy },
  { key: 'c-creators', label: '达人资产', to: '/c/creators', icon: Globe },
  { key: 'c-events', label: '重要事件', to: '/c/events', icon: CalendarClock },
];

export const superMenu: MenuEntry[] = [
  { key: 'a-dashboard', label: '数据看板', to: '/a/dashboard', icon: LayoutDashboard },
  { key: 'a-monitor', label: '系统监控', to: '/a/monitor', icon: Activity },
  {
    key: 'a-creator-data',
    label: '达人数据采集',
    icon: Users,
    children: [
      { key: 'a-collect-shop', label: '采集 · TikTok Shop', to: '/a/collect-shop', icon: Store },
      { key: 'a-collect-leads', label: '采集 · X9 线索', to: '/a/collect-leads', icon: Radar },
      { key: 'a-collect-import', label: '采集 · 表格导入', to: '/a/collect-import', icon: FileSpreadsheet },
    ],
  },
  { key: 'a-emails', label: '邮件管理', to: '/a/emails', icon: Mail },
  { key: 'a-users', label: '用户与权限', to: '/a/users', icon: KeyRound },
  { key: 'a-llm', label: 'LLM 配置', to: '/a/llm', icon: Brain },
  { key: 'a-webhooks', label: 'Webhook 集成', to: '/a/webhooks', icon: Webhook },
  { key: 'a-audit', label: '审计日志', to: '/a/audit', icon: ScrollText },
  { key: 'a-resources', label: '资源浏览器', to: '/a/resources', icon: Database },
  { key: 'a-queries', label: '命名查询', to: '/a/queries', icon: FileCode },
  { key: 'a-api-stats', label: 'API 统计', to: '/a/api-stats', icon: Gauge },
];

export const pageMeta: Record<string, { title: string; subtitle: string }> = {
  '/d/dashboard': { title: '数据看板', subtitle: '全面掌握业务运营情况,驱动高效增长' },
  '/d/collect-shop': { title: '采集 · TikTok Shop', subtitle: 'affiliate-us 全自动采集 · 列表→详情漏斗与运行状态' },
  '/d/collect-leads': { title: '采集 · X9 线索', subtitle: 'www.tiktok.com 卡片流 · 联系方式覆盖与趋势' },
  '/d/collect-import': { title: '采集 · 表格导入', subtitle: 'CSV / XLSX 批量导入 · 国家 / Tier / 质量分布' },
  '/d/creators': { title: '达人管理', subtitle: '管辖范围内达人的全生命周期管理' },
  '/d/leads': { title: '线索管理', subtitle: '从爬虫池筛选高质量达人候选' },
  '/d/emails': { title: '邮件管理', subtitle: 'AI 辅助邮件外联与跟进' },
  '/d/samples': { title: '样品管理', subtitle: '寄样物流、签收跟踪与异常预警' },
  '/d/videos': { title: '视频管理', subtitle: '在投视频实时表现监控' },
  '/d/products': { title: '产品管理', subtitle: 'SKU 主数据维护与文案生成' },
  '/d/settings': { title: '设置中心', subtitle: '部门成员、权限与偏好配置' },

  '/c/overview': { title: '公司业绩总览', subtitle: '高级 KPI · 营收 · 增长 · 异常' },
  '/c/revenue': { title: '营收与利润', subtitle: '月度营收、利润率与 SKU 贡献' },
  '/c/departments': { title: '部门绩效对比', subtitle: '多维度部门绩效雷达对比' },
  '/c/growth': { title: '增长趋势', subtitle: '达人 / SKU / 订单的增长曲线' },
  '/c/funnel': { title: '全公司转化漏斗', subtitle: '8 阶段转化、流失分析、阶段时长' },
  '/c/products': { title: 'SKU 价值地图', subtitle: '类目分布与营收热力' },
  '/c/creators': { title: '达人资产总览', subtitle: 'Tier 结构、地理分布、头部达人' },
  '/c/events': { title: '重要事件时间线', subtitle: '公司级里程碑与异常事件' },

  '/a/dashboard': { title: '数据看板', subtitle: '全公司业绩总览 · 全局视角' },
  '/a/monitor': { title: '系统监控', subtitle: '服务状态、性能指标与资源消耗' },
  '/a/collect-shop': { title: '采集 · TikTok Shop（全局）', subtitle: '全部门 TikTok Shop 采集 · 列表→详情漏斗' },
  '/a/collect-leads': { title: '采集 · X9 线索（全局）', subtitle: '全部门 X9 卡片流线索 · 联系方式覆盖' },
  '/a/collect-import': { title: '采集 · 表格导入（全局）', subtitle: '全部门 CSV / XLSX 导入 · 国家 / Tier 分布' },
  '/a/emails': { title: '邮件管理（全局）', subtitle: '全部门邮件外联事件、模板与近期发送队列' },
  '/a/users': { title: '用户与权限', subtitle: '全公司用户管理与 API Key 签发' },
  '/a/llm': { title: 'LLM 配置中心', subtitle: 'Provider 管理、Feature 绑定与用量' },
  '/a/webhooks': { title: 'Webhook 集成', subtitle: '钉钉、企微、Slack 等外部通知' },
  '/a/audit': { title: '审计日志', subtitle: '全量操作追溯与异常告警' },
  '/a/resources': { title: '资源浏览器', subtitle: '数据库表结构与通用 CRUD' },
  '/a/queries': { title: '命名查询', subtitle: '预定义业务查询管理与运行' },
  '/a/api-stats': { title: 'API 调用统计', subtitle: '端点级性能、错误率与调用排行' },
};
