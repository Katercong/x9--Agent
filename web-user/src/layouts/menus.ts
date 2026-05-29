import {
  Home, BarChart3, Telescope, Sparkles,
  ArrowDownToLine, TrendingUp, Bot, Users, Store, Radar, FileSpreadsheet, MailCheck,
  type LucideIcon,
} from 'lucide-react';
import type { Language } from '@/lib/i18n';

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

type PageMeta = { title: string; subtitle: string };

const menuText: Record<Language, Record<string, string>> = {
  zh: {
    workbench: '工作台',
    business: '业务看板',
    creatorData: '达人数据采集',
    collection: '采集总览',
    collectShop: '采集 · TikTok Shop',
    collectLeads: '采集 · X9 线索',
    collectImport: '采集 · 表格导入',
    recommendations: '达人库',
    emails: '邮件存档',
    export: '数据工具',
    hotkw: 'TikTok 热搜',
    assistant: 'AI 助手',
  },
  en: {
    workbench: 'Workbench',
    business: 'Business Dashboard',
    creatorData: 'Creator Collection',
    collection: 'Collection Overview',
    collectShop: 'TikTok Shop',
    collectLeads: 'X9 Leads',
    collectImport: 'Table Import',
    recommendations: 'Creator Library',
    emails: 'Email Archive',
    export: 'Data Tools',
    hotkw: 'TikTok Trends',
    assistant: 'AI Assistant',
  },
};

function buildPortalMenu(language: Language): MenuEntry[] {
  const t = menuText[language];
  return [
    { key: 'workbench', label: t.workbench, to: '/', icon: Home },
    { key: 'business', label: t.business, to: '/business', icon: BarChart3 },
    {
      key: 'creator-data',
      label: t.creatorData,
      icon: Users,
      children: [
        { key: 'collection', label: t.collection, to: '/collection', icon: Telescope },
        { key: 'collect-shop', label: t.collectShop, to: '/collect-shop', icon: Store },
        { key: 'collect-leads', label: t.collectLeads, to: '/collect-leads', icon: Radar },
        { key: 'collect-import', label: t.collectImport, to: '/collect-import', icon: FileSpreadsheet },
      ],
    },
    { key: 'recommendations', label: t.recommendations, to: '/recommendations', icon: Sparkles },
    { key: 'emails', label: t.emails, to: '/emails', icon: MailCheck },
    { key: 'export', label: t.export, to: '/export', icon: ArrowDownToLine },
    { key: 'hotkw', label: t.hotkw, to: '/hotkw', icon: TrendingUp },
    { key: 'assistant', label: t.assistant, to: '/assistant', icon: Bot },
  ];
}

export const portalMenu: MenuEntry[] = buildPortalMenu('zh');

export function getPortalMenu(language: Language): MenuEntry[] {
  return buildPortalMenu(language);
}

const pageMetaByLanguage: Record<Language, Record<string, PageMeta>> = {
  zh: {
    '/': { title: '工作台', subtitle: '待处理事项、采集状态与常用入口' },
    '/business': { title: '业务看板', subtitle: '管理员看公司全量，部门账号看当前部门' },
    '/collection': { title: '采集总览', subtitle: '插件状态、任务进度与三类达人采集渠道统一入口' },
    '/collect-shop': { title: '采集 · TikTok Shop', subtitle: 'affiliate-us 全自动采集 · 漏斗 / 类目 / 点击达人看详情' },
    '/collect-leads': { title: '采集 · X9 线索', subtitle: 'www.tiktok.com 卡片流 · 联系方式覆盖与趋势' },
    '/collect-import': { title: '采集 · 表格导入', subtitle: 'CSV / XLSX 批量导入 · 国家 / Tier / 质量分布' },
    '/creators-info': { title: '达人库', subtitle: '已合并到推荐池与全部达人统一页面' },
    '/recommendations': { title: '达人库', subtitle: '推荐池 / 全部达人统一视图 · 点击达人进入详情与邮件建联' },
    '/emails': { title: '邮件存档', subtitle: '按部门复查已发送邮件正文、发件账号与达人记录' },
    '/export': { title: '数据工具', subtitle: '导出文件、下载模板，正式导入统一到表格导入页' },
    '/hotkw': { title: 'TikTok 热搜', subtitle: '热门关键词与增长趋势' },
    '/assistant': { title: 'AI 助手', subtitle: '智能问答与运维指引' },
  },
  en: {
    '/': { title: 'Workbench', subtitle: 'Open tasks, collection status, and common entry points' },
    '/business': { title: 'Business Dashboard', subtitle: 'Company-wide metrics for admins and department-scoped data for teams' },
    '/collection': { title: 'Collection Overview', subtitle: 'Extension status, task progress, and three creator collection channels' },
    '/collect-shop': { title: 'TikTok Shop Collection', subtitle: 'Automated affiliate-us collection with funnel, category, and detail views' },
    '/collect-leads': { title: 'X9 Leads Collection', subtitle: 'TikTok card feed, contact coverage, and trend monitoring' },
    '/collect-import': { title: 'Table Import', subtitle: 'CSV / XLSX batch import with country, tier, and quality distribution' },
    '/creators-info': { title: 'Creator Library', subtitle: 'Merged into the recommendation pool and unified creator page' },
    '/recommendations': { title: 'Creator Library', subtitle: 'Recommendation pool and all creators in one view with detail and email outreach' },
    '/emails': { title: 'Email Archive', subtitle: 'Review sent email bodies, sending accounts, and creator records by department' },
    '/export': { title: 'Data Tools', subtitle: 'Export files, download templates, and route formal imports to Table Import' },
    '/hotkw': { title: 'TikTok Trends', subtitle: 'Trending keywords and growth signals' },
    '/assistant': { title: 'AI Assistant', subtitle: 'Smart Q&A and operations guidance' },
  },
};

export const pageMeta: Record<string, PageMeta> = pageMetaByLanguage.zh;

export function getPageMeta(pathname: string, language: Language): PageMeta {
  if (pathname.startsWith('/recommendations/')) {
    return language === 'en'
      ? { title: 'Creator Detail', subtitle: 'Recommendation evidence, review signals, and email outreach' }
      : { title: '达人详情', subtitle: '推荐判断、证据复核与邮件建联' };
  }
  return pageMetaByLanguage[language][pathname]
    ?? (language === 'en' ? { title: 'Page', subtitle: '' } : { title: '页面', subtitle: '' });
}
