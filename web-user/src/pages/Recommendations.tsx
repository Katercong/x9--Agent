import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight, CalendarDays, CheckCircle2, Clock, Download, ExternalLink, Filter, Handshake, Mail,
  RotateCcw, Search, ShieldAlert, SlidersHorizontal, Sparkles, Star, Tag, UserCheck, Users, X,
} from 'lucide-react';
import { AsyncState } from '@/components/states/States';
import { OutreachDrawer } from '@/components/outreach/OutreachDrawer';
import { PaginationControls } from '@/components/PaginationControls';
import { useAcquireOutreachLock, useCreators } from '@/hooks/useApi';
import { formatCompact, maskEmail } from '@/lib/format';
import type { Language } from '@/lib/i18n';
import { pickItems, type Creator, type CreatorOutreachLock } from '@/api/types';
import { useUiStore } from '@/stores/uiStore';


type SourceFilter = 'all' | 'tiktok_shop' | 'x9_leads' | 'table_import' | 'other';
type PriorityFilter = 'all' | 'P1' | 'P2' | 'P3' | 'P4';
type ContactFilter = 'all' | 'contactable' | 'email' | 'none';
type ScoreFilter = 'all' | 'gte85' | '70_84' | '50_69' | 'lt50';

type DateFilter = 'all' | '1d' | '7d' | '30d';
type ReviewFilter = 'all' | 'need_review' | 'has_risk' | 'clean';
type OwnerFilter = 'all' | 'assigned' | 'unassigned';
type SortFilter = 'recommended' | 'score' | 'followers' | 'fit' | 'priority' | 'recent' | 'contactable' | 'micro';

type SelectOption = { value: string; label: string };
type ActiveFilterBadge = { key: string; label: string; onClear: () => void };
type CreatorTag = { label: string; tone?: 'shop' | 'good' | 'warn' | 'muted' };
type LocalizedOption<T extends string> = { key: T; zh: string; en: string };

const PAGE_SIZE = 10;

const SOURCE_META: Record<Exclude<SourceFilter, 'all'>, { zh: string; en: string; color: string }> = {
  tiktok_shop: { zh: 'TikTok Shop', en: 'TikTok Shop', color: '#ff3b63' },
  x9_leads: { zh: 'X9 线索', en: 'X9 Leads', color: '#00a6c8' },
  table_import: { zh: '表格导入', en: 'Table Import', color: '#c88415' },
  other: { zh: '其他来源', en: 'Other Sources', color: '#687284' },
};

const SOURCE_FILTERS: Array<LocalizedOption<SourceFilter>> = [
  { key: 'all', zh: '全部来源', en: 'All Sources' },
  { key: 'tiktok_shop', zh: 'TikTok Shop', en: 'TikTok Shop' },
  { key: 'x9_leads', zh: 'X9 线索', en: 'X9 Leads' },
  { key: 'table_import', zh: '表格导入', en: 'Table Import' },
  { key: 'other', zh: '其他', en: 'Other' },
];

const SCORE_FILTERS: Array<LocalizedOption<ScoreFilter>> = [
  { key: 'all', zh: '全部评分', en: 'All Scores' },
  { key: 'gte85', zh: '85+ 强推荐', en: '85+ Strong Fit' },
  { key: '70_84', zh: '70-84 可测试', en: '70-84 Testable' },
  { key: '50_69', zh: '50-69 观察', en: '50-69 Watch' },
  { key: 'lt50', zh: '<50 低分', en: '<50 Low Score' },
];

const PRIORITY_FILTERS: Array<LocalizedOption<PriorityFilter>> = [
  { key: 'all', zh: '全部优先级', en: 'All Priorities' },
  { key: 'P1', zh: 'P1', en: 'P1' },
  { key: 'P2', zh: 'P2', en: 'P2' },
  { key: 'P3', zh: 'P3', en: 'P3' },
  { key: 'P4', zh: 'P4', en: 'P4' },
];

const CONTACT_FILTERS: Array<LocalizedOption<ContactFilter>> = [
  { key: 'all', zh: '全部联系', en: 'All Contact' },
  { key: 'contactable', zh: '可联系', en: 'Contactable' },
  { key: 'email', zh: '有邮箱', en: 'Has Email' },
  { key: 'none', zh: '无联系方式', en: 'No Contact' },
];


const DATE_FILTERS: Array<LocalizedOption<DateFilter>> = [
  { key: 'all', zh: '全部入库时间', en: 'All Dates' },
  { key: '1d', zh: '近 24 小时', en: 'Last 24 Hours' },
  { key: '7d', zh: '近 7 天', en: 'Last 7 Days' },
  { key: '30d', zh: '近 30 天', en: 'Last 30 Days' },
];

const REVIEW_FILTERS: Array<LocalizedOption<ReviewFilter>> = [
  { key: 'all', zh: '全部复核状态', en: 'All Review States' },
  { key: 'need_review', zh: '需要复核', en: 'Needs Review' },
  { key: 'has_risk', zh: '有风险提示', en: 'Has Risk' },
  { key: 'clean', zh: '无复核/风险', en: 'Clean' },
];

const OWNER_FILTERS: Array<LocalizedOption<OwnerFilter>> = [
  { key: 'all', zh: '全部归属', en: 'All Owners' },
  { key: 'assigned', zh: '已分配 BD', en: 'Assigned BD' },
  { key: 'unassigned', zh: '未分配 BD', en: 'Unassigned' },
];

const SORT_FILTERS: Array<LocalizedOption<SortFilter>> = [
  { key: 'recommended', zh: '综合推荐排序', en: 'Recommended' },
  { key: 'score', zh: '评分从高到低', en: 'Score High to Low' },
  { key: 'followers', zh: '粉丝从高到低', en: 'Followers High to Low' },
  { key: 'fit', zh: '产品匹配优先', en: 'Product Fit First' },
  { key: 'priority', zh: '优先级 P1 优先', en: 'Priority P1 First' },
  { key: 'recent', zh: '最近入库优先', en: 'Newest First' },
  { key: 'contactable', zh: '可联系优先', en: 'Contactable First' },
  { key: 'micro', zh: '小达人优先', en: 'Micro Creators First' },
];

const filterControlClass = 'h-9 w-full rounded-md border border-border bg-elev1 px-3 text-xs text-text outline-none transition-colors focus:border-accent';

const copy = {
  zh: {
    title: '新达人推荐库',
    sourcePrefix: '当前来源',
    newCreators: '新达人',
    todayAdded: '今日入库',
    highScore: '高分 ≥80',
    searchPlaceholder: '搜索 handle / 邮箱 / 商品 / 推荐理由',
    advancedFilters: '高级筛选',
    exportCsv: '导出',
    reset: '重置',
    advancedTitle: '高级条件',
    enabled: '已启用',
    noExtraFilters: '无额外条件',
    empty: '暂无符合条件的达人',
    score: '评分',
    followers: '粉丝',
    fit: '匹配',
    commission: '佣金',
    detailCaptured: '详情已采集',
    strong: '强推荐',
    testable: '可测试',
    watch: '观察',
    unknownRegion: '地区未知',
    contactable: '可联系',
    noReason: '暂无推荐理由，进入详情页补充查看达人画像与外联建议。',
    noTags: '暂无标签',
    noEmail: '暂无邮箱',
    noShopMetrics: '暂无 Shop 指标',
    profileTitle: '达人主页',
    shopTitle: 'Shop 详情',
    outreachTitle: '邮件建联',
    allProduct: '全部品类 / 商品类型',
    allCollab: '全部合作方式',
    allStatus: '全部状态',
    min: '最低',
    max: '最高',
    filters: {
      source: '来源',
      search: '搜索',
      priority: '优先级',
      contact: '联系',
      score: '评分',
      followers: '粉丝',
      time: '时间',
      review: '复核',
      owner: '归属',
      product: '品类',
      collab: '合作',
      status: '状态',
      sort: '排序',
    },
    field: {
      score: '评分',
      followers: '粉丝范围',
      product: '品类 / 商品',
      collab: '合作方式',
      status: '状态',
      review: '复核 / 风险',
      owner: 'BD 归属',
      date: '入库时间',
      sort: '排序',
    },
    status: {
      contacted: '待建联',
      followup: '待跟进',
    },
    noLimit: '不限',
    lockBusy: '达人已被其他用户占用，请刷新后再试',
  },
  en: {
    title: 'New Creator Recommendations',
    sourcePrefix: 'Source',
    newCreators: 'New Creators',
    todayAdded: 'Added Today',
    highScore: 'Score ≥80',
    searchPlaceholder: 'Search handle / email / product / reason',
    advancedFilters: 'Advanced Filters',
    exportCsv: 'Export',
    reset: 'Reset',
    advancedTitle: 'Advanced Conditions',
    enabled: 'Active',
    noExtraFilters: 'No extra filters',
    empty: 'No matching creators',
    score: 'Score',
    followers: 'Followers',
    fit: 'Fit',
    commission: 'Commission',
    detailCaptured: 'Details Captured',
    strong: 'Strong Fit',
    testable: 'Testable',
    watch: 'Watch',
    unknownRegion: 'Unknown Region',
    contactable: 'Contactable',
    noReason: 'No recommendation reason yet. Open the detail page to review the creator profile and outreach suggestions.',
    noTags: 'No tags',
    noEmail: 'No email',
    noShopMetrics: 'No Shop metrics',
    profileTitle: 'Creator Profile',
    shopTitle: 'Shop Details',
    outreachTitle: 'Email Outreach',
    allProduct: 'All Categories / Product Types',
    allCollab: 'All Collaboration Types',
    allStatus: 'All Statuses',
    min: 'Min',
    max: 'Max',
    filters: {
      source: 'Source',
      search: 'Search',
      priority: 'Priority',
      contact: 'Contact',
      score: 'Score',
      followers: 'Followers',
      time: 'Time',
      review: 'Review',
      owner: 'Owner',
      product: 'Product',
      collab: 'Collab',
      status: 'Status',
      sort: 'Sort',
    },
    field: {
      score: 'Score',
      followers: 'Follower Range',
      product: 'Category / Product',
      collab: 'Collaboration Type',
      status: 'Status',
      review: 'Review / Risk',
      owner: 'BD Owner',
      date: 'Added Date',
      sort: 'Sort',
    },
    status: {
      contacted: 'To Contact',
      followup: 'Follow Up',
    },
    noLimit: 'No limit',
    lockBusy: 'This creator is currently locked by another user. Refresh and try again.',
  },
} satisfies Record<Language, Record<string, any>>;

function optionLabel<T extends string>(items: Array<LocalizedOption<T>>, key: T, language: Language) {
  return items.find((item) => item.key === key)?.[language] || key;
}

function compactByLanguage(value: number | null | undefined, language: Language) {
  if (language === 'zh') return formatCompact(value);
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}

function SegmentedButton({
  active,
  children,
  onClick,
  accent = 'rgb(var(--accent))',
}: {
  active: boolean;
  children: ReactNode;
  onClick: () => void;
  accent?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex h-8 items-center justify-center gap-1.5 whitespace-nowrap rounded px-2.5 text-xs font-semibold transition-colors ${
        active ? 'text-white shadow-sm' : 'text-muted hover:bg-elev1 hover:text-text'
      }`}
      style={active ? { background: accent } : undefined}
    >
      {children}
    </button>
  );
}

function FilterField({ label, icon, children, className = '' }: { label: string; icon: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={`min-w-0 space-y-1 ${className}`}>
      <span className="flex items-center gap-1.5 text-[11px] font-semibold text-muted">
        {icon}
        {label}
      </span>
      {children}
    </label>
  );
}

function scoreTone(score: number | null | undefined, language: Language) {
  const t = copy[language];
  if ((score ?? 0) >= 85) return { fg: '#05343b', bg: '#c8f7ff', label: t.strong };
  if ((score ?? 0) >= 70) return { fg: '#6f4700', bg: '#fff1c6', label: t.testable };
  return { fg: '#4b5563', bg: '#eef2f7', label: t.watch };
}

function creatorInitial(c: Creator) {
  return (c.handle || c.display_name || '?').slice(0, 1).toUpperCase();
}

function creatorName(c: Creator, language: Language) {
  return c.display_name || c.handle || `${language === 'zh' ? '达人' : 'Creator'} ${c.id}`;
}

function followers(c: Creator) {
  return c.followers_count ?? c.followers ?? null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function compactText(value: unknown) {
  const text = String(value ?? '').trim();
  return text && text !== 'null' && text !== 'undefined' ? text : '';
}

function numberValue(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function shopValue(c: Creator, ...keys: string[]) {
  const shop = asRecord(c.tiktok_shop);
  for (const key of keys) {
    const value = compactText(shop?.[key] ?? c[key]);
    if (value) return value;
  }
  return '';
}

function recordSearchValues(value: unknown): string[] {
  const record = asRecord(value);
  if (!record) return [];
  return Object.values(record)
    .flatMap((item) => Array.isArray(item) ? item : [item])
    .filter((item) => typeof item === 'string' || typeof item === 'number')
    .map((item) => String(item));
}

function creatorDate(c: Creator) {
  return c.collected_at || c.created_at || c.updated_at || null;
}

function dateMs(value?: string | null) {
  if (!value) return 0;
  const time = new Date(value).getTime();
  return Number.isFinite(time) ? time : 0;
}

function valueList(...values: unknown[]) {
  const out: string[] = [];
  for (const value of values) {
    if (Array.isArray(value)) {
      out.push(...value.map((item) => String(item ?? '').trim()).filter(Boolean));
    } else {
      const text = String(value ?? '').trim();
      if (text) out.push(text);
    }
  }
  return out;
}

function canonicalStatus(value?: string | null) {
  const text = String(value || '').trim();
  if (!text) return '待建联';
  const key = text.toLowerCase().replace(/[-\s]+/g, '_');
  if (text === '未建联' || text === '待联系' || key === 'to_be_contacted' || key === 'pending_contact' || key === 'prospect' || key === 'recommended') return '待建联';
  if (text === '\u5f85\u56de\u590d' || text === '\u7b49\u5f85\u56de\u590d' || key === 'pending_reply' || key === 'pending_followup' || key === 'pending_follow_up' || key === 'needs_followup' || key === 'needs_follow_up') return '待跟进';
  return text;
}

function displayStatus(value: string | null | undefined, language: Language) {
  const status = canonicalStatus(value);
  if (status === '待建联') return copy[language].status.contacted;
  if (status === '待跟进') return copy[language].status.followup;
  return status;
}

function outreachStatusValue(creator: Creator) {
  return canonicalStatus(creator.current_status);
}

function isNewRecommendationCreator(creator: Creator) {
  const sentCount = Number(creator.outreach_count ?? 0);
  return outreachStatusValue(creator) === '待建联' && sentCount <= 0 && !creator.last_outreach_at;
}

function uniqueOptions(items: Creator[], getValues: (creator: Creator) => unknown | unknown[], limit = 24): SelectOption[] {
  const seen = new Set<string>();
  const options: SelectOption[] = [];
  for (const creator of items) {
    for (const value of valueList(getValues(creator))) {
      if (seen.has(value)) continue;
      seen.add(value);
      options.push({ value, label: value });
    }
  }
  return options.sort((a, b) => a.label.localeCompare(b.label, 'zh-Hans')).slice(0, limit);
}

function sourceKey(c: Creator): Exclude<SourceFilter, 'all'> {
  const key = String(c.source || '').trim();
  return key in SOURCE_META ? key as Exclude<SourceFilter, 'all'> : 'other';
}

function sourceMeta(c: Creator, language: Language) {
  const key = sourceKey(c);
  return { key, label: SOURCE_META[key][language] || c.source_label || key, color: SOURCE_META[key].color };
}

function hasContact(c: Creator) {
  const methods = c.contact_methods;
  const methodCount = Array.isArray(methods) ? methods.length : methods && typeof methods === 'object' ? Object.keys(methods).length : 0;
  return Boolean(c.email || c.has_contact || methodCount > 0 || (c.external_links?.length ?? 0) > 0);
}

function isToday(value?: string | null) {
  if (!value) return false;
  const day = new Date(value);
  if (Number.isNaN(day.getTime())) return false;
  const now = new Date();
  return day.getFullYear() === now.getFullYear()
    && day.getMonth() === now.getMonth()
    && day.getDate() === now.getDate();
}

function pushTag(tags: CreatorTag[], seen: Set<string>, label: unknown, tone: CreatorTag['tone'] = 'muted') {
  const text = compactText(label);
  if (!text || seen.has(text)) return;
  seen.add(text);
  tags.push({ label: text, tone });
}

function tagsFor(c: Creator, language: Language) {
  const t = copy[language];
  const tags: CreatorTag[] = [];
  const seen = new Set<string>();
  const gmv = shopValue(c, 'gmv_raw', 'gmv');
  const gpm = shopValue(c, 'gpm_raw', 'gpm');
  const commission = shopValue(c, 'avg_commission_rate_raw', 'commission_rate_raw', 'commission_rate');
  const shopCategory = shopValue(c, 'category_text', 'category', 'primary_category');
  const detailCapturedAt = shopValue(c, 'detail_captured_at');

  if (sourceKey(c) === 'tiktok_shop' || c.shop_profile_url || asRecord(c.tiktok_shop)) {
    pushTag(tags, seen, 'TikTok Shop', 'shop');
  }
  pushTag(tags, seen, gmv ? `GMV ${gmv}` : '', 'shop');
  pushTag(tags, seen, gpm ? `GPM ${gpm}` : '', 'shop');
  pushTag(tags, seen, commission ? `${t.commission} ${commission}` : '', 'shop');
  pushTag(tags, seen, shopCategory, 'shop');
  pushTag(tags, seen, detailCapturedAt ? t.detailCaptured : '', 'good');
  pushTag(tags, seen, c.lead_status, 'warn');
  pushTag(tags, seen, c.primary_product_category, 'good');
  pushTag(tags, seen, c.recommended_product_type, 'good');
  for (const tag of c.category_tags || []) pushTag(tags, seen, tag, 'muted');
  for (const tag of c.positive_tags || []) pushTag(tags, seen, tag, 'good');
  return tags.slice(0, 9);
}

function tagClass(tone: CreatorTag['tone']) {
  if (tone === 'shop') return 'border-pink-500/20 bg-pink-500/10 text-pink-700';
  if (tone === 'good') return 'border-emerald-500/20 bg-emerald-500/10 text-good';
  if (tone === 'warn') return 'border-amber-500/25 bg-amber-500/10 text-amber-700';
  return 'border-border bg-elev1 text-muted';
}

function scoreMatches(c: Creator, filter: ScoreFilter) {
  const score = c.recommendation_score ?? 0;
  if (filter === 'gte85') return score >= 85;
  if (filter === '70_84') return score >= 70 && score < 85;
  if (filter === '50_69') return score >= 50 && score < 70;
  if (filter === 'lt50') return score < 50;
  return true;
}

function followerRangeMatches(c: Creator, minText: string, maxText: string) {
  const min = minText.trim() ? numberValue(minText) : null;
  const max = maxText.trim() ? numberValue(maxText) : null;
  if (min === null && max === null) return true;
  const value = numberValue(followers(c));
  if (value === null) return false;
  if (min !== null && value < min) return false;
  if (max !== null && value > max) return false;
  return true;
}

function dateMatches(c: Creator, filter: DateFilter) {
  if (filter === 'all') return true;
  const time = dateMs(creatorDate(c));
  if (!time) return false;
  const days = filter === '1d' ? 1 : filter === '7d' ? 7 : 30;
  return time >= Date.now() - days * 24 * 60 * 60 * 1000;
}

function reviewMatches(c: Creator, filter: ReviewFilter) {
  const hasRisk = Boolean(c.risk_summary || (c.risk_tags?.length ?? 0) > 0);
  if (filter === 'need_review') return Boolean(c.review_required || c.review_status === 'pending');
  if (filter === 'has_risk') return hasRisk;
  if (filter === 'clean') return !c.review_required && !hasRisk;
  return true;
}

function ownerMatches(c: Creator, filter: OwnerFilter) {
  const assigned = Boolean(String(c.owner_bd || c.bd_owner || '').trim());
  if (filter === 'assigned') return assigned;
  if (filter === 'unassigned') return !assigned;
  return true;
}

function priorityRank(c: Creator) {
  return { P1: 1, P2: 2, P3: 3, P4: 4 }[String(c.outreach_priority || c.priority_level || '')] ?? 9;
}

function sortCreators(rows: Creator[], sort: SortFilter) {
  if (sort === 'recommended') return rows;
  return [...rows].sort((a, b) => {
    if (sort === 'score') return (b.recommendation_score ?? 0) - (a.recommendation_score ?? 0);
    if (sort === 'followers') return (numberValue(followers(b)) ?? -1) - (numberValue(followers(a)) ?? -1);
    if (sort === 'fit') return (b.primary_product_fit_score ?? 0) - (a.primary_product_fit_score ?? 0);
    if (sort === 'priority') return priorityRank(a) - priorityRank(b) || (b.recommendation_score ?? 0) - (a.recommendation_score ?? 0);
    if (sort === 'recent') return dateMs(creatorDate(b)) - dateMs(creatorDate(a));
    if (sort === 'contactable') return Number(hasContact(b)) - Number(hasContact(a)) || Number(Boolean(b.email)) - Number(Boolean(a.email));
    if (sort === 'micro') return (numberValue(followers(a)) ?? Number.MAX_SAFE_INTEGER) - (numberValue(followers(b)) ?? Number.MAX_SAFE_INTEGER);
    return 0;
  });
}

function RecommendationCard({
  creator,
  language,
  onOpen,
  onMail,
  mailPending,
}: {
  creator: Creator;
  language: Language;
  onOpen: (creator: Creator) => void;
  onMail: (creator: Creator) => void;
  mailPending?: boolean;
}) {
  const t = copy[language];
  const tone = scoreTone(creator.recommendation_score, language);
  const tags = tagsFor(creator, language);
  const priority = creator.outreach_priority || creator.priority_level || 'P?';
  const status = displayStatus(creator.current_status, language);
  const source = sourceMeta(creator, language);
  const gmv = shopValue(creator, 'gmv_raw', 'gmv');
  const gpm = shopValue(creator, 'gpm_raw', 'gpm');
  const commission = shopValue(creator, 'avg_commission_rate_raw', 'commission_rate_raw', 'commission_rate');
  const shopMetrics = [
    ['GMV', gmv],
    ['GPM', gpm],
    [t.commission, commission],
  ].filter(([, value]) => Boolean(value));

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onOpen(creator)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') onOpen(creator);
      }}
      className="group grid cursor-pointer grid-cols-1 overflow-hidden rounded-md border border-border bg-elev1 shadow-card transition-all hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-lg xl:grid-cols-[minmax(260px,0.9fr)_minmax(380px,1.35fr)_minmax(250px,0.75fr)_58px]"
    >
      <div className="flex min-w-0 gap-3 p-3">
        <div className="relative flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-md text-xl font-black text-white shadow-sm" style={{ background: source.color }}>
          <span>{creatorInitial(creator)}</span>
          <span className="absolute inset-x-2 bottom-1 h-1 rounded-full bg-white/25" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <h3 className="truncate text-base font-black leading-tight">@{creator.handle || 'unknown'}</h3>
            <span className="rounded-full bg-elev2 px-2 py-0.5 text-[11px] font-semibold text-text">{priority}</span>
          </div>
          <div className="mt-1 truncate text-xs text-muted">{creatorName(creator, language)}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="rounded-full border border-border bg-elev2 px-2 py-0.5 text-[11px] text-muted">
              {creator.platform || 'tiktok'}
            </span>
            <span
              className="rounded-full border px-2 py-0.5 text-[11px]"
              style={{ borderColor: `${source.color}33`, background: `${source.color}12`, color: source.color }}
            >
              {source.label}
            </span>
            <span className="rounded-full border border-border bg-elev2 px-2 py-0.5 text-[11px] text-muted">
              {creator.country || creator.language || t.unknownRegion}
            </span>
            {hasContact(creator) && (
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[11px] text-good">
                {t.contactable}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="min-w-0 border-y border-border/70 p-3 xl:border-x xl:border-y-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-bold" style={{ color: tone.fg, background: tone.bg }}>
            <Star size={12} /> {tone.label}
          </span>
          <span className="rounded-full bg-elev2 px-2.5 py-1 text-[11px] text-muted">{status}</span>
        </div>
        <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-text/80">
          {creator.recommendation_reason || creator.next_action || t.noReason}
        </p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {tags.length > 0 ? tags.map((tag) => (
            <span key={tag.label} className={`rounded-full border px-2 py-0.5 text-[11px] ${tagClass(tag.tone)}`}>{tag.label}</span>
          )) : (
            <span className="text-[11px] text-muted">{t.noTags}</span>
          )}
        </div>
      </div>

      <div className="grid gap-2 p-3">
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-md border border-border bg-elev2 p-2">
            <div className="text-[11px] text-muted">{t.score}</div>
            <div className="mt-1 font-mono text-xl font-black leading-none">{Math.round(creator.recommendation_score ?? 0)}</div>
          </div>
          <div className="rounded-md border border-border bg-elev2 p-2">
            <div className="text-[11px] text-muted">{t.followers}</div>
            <div className="mt-1 text-sm font-black">{compactByLanguage(followers(creator), language)}</div>
          </div>
          <div className="rounded-md border border-border bg-elev2 p-2">
            <div className="text-[11px] text-muted">{t.fit}</div>
            <div className="mt-1 text-sm font-black">{creator.primary_product_fit_score ?? '-'}</div>
          </div>
        </div>
        <div className="min-w-0 rounded-md border border-border bg-elev2 px-2 py-1.5">
          <div className="truncate text-[11px] text-muted">{creator.email ? maskEmail(creator.email) : t.noEmail}</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {shopMetrics.length > 0 ? shopMetrics.map(([label, value]) => (
              <span key={label} className="rounded-full bg-pink-500/10 px-2 py-0.5 text-[10px] font-semibold text-pink-700">
                {label} {value}
              </span>
            )) : (
              <span className="text-[11px] text-muted">{t.noShopMetrics}</span>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 border-t border-border/70 bg-elev2/45 p-3 xl:flex-col xl:border-l xl:border-t-0 xl:p-2">
        {creator.profile_url && (
          <a
            href={creator.profile_url}
            target="_blank"
            rel="noreferrer"
            title={t.profileTitle}
            onClick={(event) => event.stopPropagation()}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-elev1 text-muted transition-colors hover:border-accent hover:text-accent"
          >
            <ExternalLink size={14} />
          </a>
        )}
        {creator.shop_profile_url && (
          <a
            href={creator.shop_profile_url}
            target="_blank"
            rel="noreferrer"
            title={t.shopTitle}
            onClick={(event) => event.stopPropagation()}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-elev1 text-muted transition-colors hover:border-accent hover:text-accent"
          >
            <Tag size={14} />
          </a>
        )}
        <button
          type="button"
          title={t.outreachTitle}
          onClick={(event) => {
            event.stopPropagation();
            onMail(creator);
          }}
          disabled={mailPending}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-accent bg-accent text-white transition-transform hover:scale-[1.02] disabled:opacity-60"
        >
          <Mail size={14} />
        </button>
        <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-elev1 text-accent transition-transform group-hover:translate-x-0.5">
          <ArrowRight size={15} />
        </span>
      </div>
    </article>
  );
}

export default function Recommendations() {
  const navigate = useNavigate();
  const { language } = useUiStore();
  const t = copy[language];

  const [source, setSource] = useState<SourceFilter>('all');
  const [q, setQ] = useState('');
  const [priority, setPriority] = useState<PriorityFilter>('all');
  const [contact, setContact] = useState<ContactFilter>('all');
  const [scoreFilter, setScoreFilter] = useState<ScoreFilter>('all');
  const [minFollowers, setMinFollowers] = useState('');
  const [maxFollowers, setMaxFollowers] = useState('');
  const [dateRange, setDateRange] = useState<DateFilter>('all');
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>('all');
  const [ownerFilter, setOwnerFilter] = useState<OwnerFilter>('all');
  const [productFilter, setProductFilter] = useState('all');
  const [collabFilter, setCollabFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sort, setSort] = useState<SortFilter>('recommended');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [drawerCreator, setDrawerCreator] = useState<Creator | null>(null);
  const [drawerLock, setDrawerLock] = useState<CreatorOutreachLock | null>(null);
  const [lockingCreatorId, setLockingCreatorId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const acquireOutreachLock = useAcquireOutreachLock();

  const sourceParams = source === 'all' ? {} : { source };
  const dateParams = dateRange === 'all' ? {} : { collected_range: dateRange };
  const backendSortBy = sort === 'recent'
    ? 'collected_at'
    : sort === 'followers'
      ? 'followers'
      : sort === 'score'
        ? 'score'
        : sort === 'fit'
          ? 'fit'
          : sort === 'priority'
            ? 'priority'
            : sort === 'contactable'
              ? 'contactable'
              : sort === 'micro'
                ? 'micro'
                : 'recommended';
  const offset = page * PAGE_SIZE;
  const queryParams = { limit: PAGE_SIZE, ...sourceParams, ...dateParams };
  const newCreatorParams = { ...queryParams, uncontacted: true, outreach_sent: false };
  const creatorsQ = useCreators({ ...newCreatorParams, offset, sort_by: backendSortBy });
  const activeQ = creatorsQ;
  const items = pickItems<Creator>(activeQ.data as any);
  const newAllItems = useMemo(() => items.filter(isNewRecommendationCreator), [items]);

  const optionItems = useMemo(() => {
    const seen = new Map<string, Creator>();
    newAllItems.forEach((creator) => {
      seen.set(String(creator.id ?? `${creator.source || ''}:${creator.handle || ''}`), creator);
    });
    return [...seen.values()];
  }, [newAllItems]);
  const productOptions = useMemo(
    () => uniqueOptions(optionItems, (creator) => [
      creator.primary_product_category,
      creator.recommended_product_type,
      ...(creator.category_tags || []),
      ...(creator.positive_tags || []),
    ]),
    [optionItems],
  );
  const collabOptions = useMemo(
    () => uniqueOptions(optionItems, (creator) => creator.recommended_collab_type),
    [optionItems],
  );
  const statusOptions = useMemo(
    () => uniqueOptions(optionItems, outreachStatusValue),
    [optionItems],
  );

  useEffect(() => {
    setPage(0);
  }, [collabFilter, contact, dateRange, maxFollowers, minFollowers, ownerFilter, priority, productFilter, q, reviewFilter, scoreFilter, sort, source, statusFilter]);

  const filtered = useMemo(() => {
    const text = q.trim().toLowerCase();
    const rows = newAllItems.filter((creator) => {
      const hay = [
        creator.handle,
        creator.display_name,
        creator.email,
        creator.recommendation_reason,
        creator.next_action,
        creator.risk_summary,
        creator.bio,
        creator.search_keyword,
        creator.primary_product_category,
        creator.recommended_product_type,
        creator.recommended_collab_type,
        creator.source_label,
        creator.source,
        creator.shop_profile_url,
        creator.lead_status,
        creator.followers_raw,
        creator.country,
        creator.language,
        creator.tier,
        creator.current_status,
        creator.recommendation_status,
        creator.owner_bd,
        creator.store_assigned,
        ...(creator.category_tags || []),
        ...(creator.positive_tags || []),
        ...(creator.matched_keywords || []),
        ...(creator.contact_types || []),
        ...recordSearchValues(creator.tiktok_shop),
      ].filter(Boolean).join(' ').toLowerCase();
      if (text && !hay.includes(text)) return false;
      if (source !== 'all' && sourceKey(creator) !== source) return false;
      if (priority !== 'all' && (creator.outreach_priority || creator.priority_level) !== priority) return false;
      if (contact === 'email' && !creator.email) return false;
      if (contact === 'contactable' && !hasContact(creator)) return false;
      if (contact === 'none' && hasContact(creator)) return false;
      if (!scoreMatches(creator, scoreFilter)) return false;
      if (!followerRangeMatches(creator, minFollowers, maxFollowers)) return false;
      if (!dateMatches(creator, dateRange)) return false;
      if (!reviewMatches(creator, reviewFilter)) return false;
      if (!ownerMatches(creator, ownerFilter)) return false;
      if (productFilter !== 'all' && !valueList(
        creator.primary_product_category,
        creator.recommended_product_type,
        ...(creator.category_tags || []),
        ...(creator.positive_tags || []),
      ).includes(productFilter)) return false;
      if (collabFilter !== 'all' && creator.recommended_collab_type !== collabFilter) return false;
      if (statusFilter !== 'all' && outreachStatusValue(creator) !== statusFilter) return false;
      return true;
    });
    return sortCreators(rows, sort);
  }, [collabFilter, contact, dateRange, maxFollowers, minFollowers, newAllItems, ownerFilter, priority, productFilter, q, reviewFilter, scoreFilter, sort, source, statusFilter]);
  const pagedItems = filtered;

  const resetFilters = () => {
    setSource('all');
    setQ('');
    setPriority('all');
    setContact('all');
    setScoreFilter('all');
    setMinFollowers('');
    setMaxFollowers('');
    setDateRange('all');
    setReviewFilter('all');
    setOwnerFilter('all');
    setProductFilter('all');
    setCollabFilter('all');
    setStatusFilter('all');
    setSort('recommended');
  };

  const activeFilterCount = [
    source !== 'all',
    Boolean(q.trim()),
    priority !== 'all',
    contact !== 'all',
    scoreFilter !== 'all',
    Boolean(minFollowers.trim() || maxFollowers.trim()),
    dateRange !== 'all',
    reviewFilter !== 'all',
    ownerFilter !== 'all',
    productFilter !== 'all',
    collabFilter !== 'all',
    statusFilter !== 'all',
    sort !== 'recommended',
  ].filter(Boolean).length;

  const highScore = newAllItems.filter((c) => (c.recommendation_score ?? 0) >= 80).length;
  const localTodayAdded = newAllItems.filter((c) => isToday(c.collected_at || c.created_at)).length;
  const endpointAllTotal = (creatorsQ.data as any)?.total ?? newAllItems.length;
  const allTotal = endpointAllTotal;
  const todayAdded = localTodayAdded;
  const activeSourceLabel = optionLabel(SOURCE_FILTERS, source, language);
  const activeFilterBadges: ActiveFilterBadge[] = [
    source !== 'all' && { key: 'source', label: `${t.filters.source}: ${activeSourceLabel}`, onClear: () => setSource('all') },
    Boolean(q.trim()) && { key: 'q', label: `${t.filters.search}: ${q.trim()}`, onClear: () => setQ('') },
    priority !== 'all' && { key: 'priority', label: `${t.filters.priority}: ${priority}`, onClear: () => setPriority('all') },
    contact !== 'all' && { key: 'contact', label: `${t.filters.contact}: ${optionLabel(CONTACT_FILTERS, contact, language)}`, onClear: () => setContact('all') },
    scoreFilter !== 'all' && { key: 'score', label: `${t.filters.score}: ${optionLabel(SCORE_FILTERS, scoreFilter, language)}`, onClear: () => setScoreFilter('all') },
    Boolean(minFollowers.trim() || maxFollowers.trim()) && {
      key: 'followers',
      label: `${t.filters.followers}: ${minFollowers.trim() || '0'}-${maxFollowers.trim() || t.noLimit}`,
      onClear: () => { setMinFollowers(''); setMaxFollowers(''); },
    },
    dateRange !== 'all' && { key: 'date', label: `${t.filters.time}: ${optionLabel(DATE_FILTERS, dateRange, language)}`, onClear: () => setDateRange('all') },
    reviewFilter !== 'all' && { key: 'review', label: `${t.filters.review}: ${optionLabel(REVIEW_FILTERS, reviewFilter, language)}`, onClear: () => setReviewFilter('all') },
    ownerFilter !== 'all' && { key: 'owner', label: `${t.filters.owner}: ${optionLabel(OWNER_FILTERS, ownerFilter, language)}`, onClear: () => setOwnerFilter('all') },
    productFilter !== 'all' && { key: 'product', label: `${t.filters.product}: ${productFilter}`, onClear: () => setProductFilter('all') },
    collabFilter !== 'all' && { key: 'collab', label: `${t.filters.collab}: ${collabFilter}`, onClear: () => setCollabFilter('all') },
    statusFilter !== 'all' && { key: 'status', label: `${t.filters.status}: ${displayStatus(statusFilter, language)}`, onClear: () => setStatusFilter('all') },
    sort !== 'recommended' && { key: 'sort', label: `${t.filters.sort}: ${optionLabel(SORT_FILTERS, sort, language)}`, onClear: () => setSort('recommended') },
  ].filter(Boolean) as ActiveFilterBadge[];

  const openOutreach = async (creator: Creator) => {
    const creatorId = String(creator.id);
    setLockingCreatorId(creatorId);
    try {
      const result = await acquireOutreachLock.mutateAsync({ creator_id: creator.id });
      setDrawerLock(result.lock);
      setDrawerCreator(creator);
    } catch (error: any) {
      const detail = error?.response?.data?.detail || error?.message || t.lockBusy;
      alert(String(detail));
    } finally {
      setLockingCreatorId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-md border border-border bg-elev1 shadow-card">
        <div className="grid gap-3 border-b border-border p-3 xl:grid-cols-[220px_minmax(0,1fr)]">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="chip text-xxs"><Sparkles size={12} /> {t.title}</span>
              <span className="rounded-full bg-accent/10 px-2 py-1 text-[11px] font-semibold text-accent">
                {pagedItems.length} / {compactByLanguage(endpointAllTotal, language)}
              </span>
            </div>
            <h2 className="mt-2 text-lg font-black leading-tight text-text">{t.title}</h2>
            <div className="mt-1 text-xs text-muted">{t.sourcePrefix}: {activeSourceLabel}</div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: t.newCreators, value: compactByLanguage(allTotal, language), icon: Users },
              { label: t.todayAdded, value: compactByLanguage(todayAdded, language), icon: CalendarDays },
              { label: t.highScore, value: compactByLanguage(highScore, language), icon: Star },
            ].map((kpi) => {
              const Icon = kpi.icon;
              return (
                <div key={kpi.label} className="rounded-md border border-border bg-elev2/70 px-3 py-2">
                  <div className="flex items-center gap-1.5 text-[10px] text-muted"><Icon size={11} />{kpi.label}</div>
                  <div className="mt-1 font-mono text-base font-black text-text">{kpi.value}</div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="p-3">
          <div className="grid gap-2 xl:grid-cols-[minmax(420px,0.95fr)_minmax(300px,1fr)_auto]">
            <div className="min-w-0 rounded-md border border-border bg-elev2/70 p-1">
              <div className="flex max-w-full gap-1 overflow-x-auto">
                {SOURCE_FILTERS.map((item) => {
                  const meta = item.key === 'all' ? null : SOURCE_META[item.key];
                  return (
                    <SegmentedButton
                      key={item.key}
                      active={source === item.key}
                      onClick={() => setSource(item.key)}
                      accent={meta?.color || 'rgb(var(--accent))'}
                    >
                      {meta && <span className="h-1.5 w-1.5 rounded-full bg-current opacity-90" />}
                      {item[language]}
                    </SegmentedButton>
                  );
                })}
              </div>
            </div>

            <div className="flex h-10 min-w-0 items-center gap-2 rounded-md border border-border bg-elev1 px-3 shadow-sm focus-within:border-accent">
              <Search size={15} className="shrink-0 text-muted" />
              <input
                value={q}
                onChange={(event) => setQ(event.target.value)}
                placeholder={t.searchPlaceholder}
                className="min-w-0 flex-1 bg-transparent text-xs text-text outline-none placeholder:text-muted"
              />
              {q.trim() && (
                <button type="button" onClick={() => setQ('')} className="inline-flex h-6 w-6 items-center justify-center rounded text-muted hover:bg-elev2 hover:text-text">
                  <X size={13} />
                </button>
              )}
            </div>

            <div className="flex flex-wrap items-center justify-end gap-2">
              <button type="button" onClick={() => setShowAdvanced((value) => !value)} className="btn !h-10 shrink-0 text-xs">
                <Filter size={13} /> {t.advancedFilters}
                {activeFilterCount > 0 && <span className="rounded-full bg-accent px-1.5 py-0.5 text-[10px] text-white">{activeFilterCount}</span>}
              </button>
              <a href="/api/local/export/recommended-creators.csv" className="btn btn-ghost !h-10 shrink-0 text-xs" title="Export CSV">
                <Download size={13} /> {t.exportCsv}
              </a>
              <button type="button" onClick={resetFilters} className="btn btn-ghost !h-10 shrink-0 text-xs" title={t.reset}>
                <RotateCcw size={13} /> {t.reset}
              </button>
            </div>
          </div>

          <div className="mt-2 grid gap-2 md:grid-cols-[minmax(260px,0.7fr)_minmax(320px,1fr)]">
            <div className="flex flex-wrap items-center gap-1 rounded-md border border-border bg-elev2/45 p-1">
              {PRIORITY_FILTERS.map((item) => (
                <SegmentedButton key={item.key} active={priority === item.key} onClick={() => setPriority(item.key)}>
                  {item[language]}
                </SegmentedButton>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-1 rounded-md border border-border bg-elev2/45 p-1">
              {CONTACT_FILTERS.map((item) => (
                <SegmentedButton key={item.key} active={contact === item.key} onClick={() => setContact(item.key)}>
                  {item.key === 'contactable' && <CheckCircle2 size={12} />}
                  {item[language]}
                </SegmentedButton>
              ))}
            </div>
          </div>

          {showAdvanced && (
            <div className="mt-3 rounded-md border border-border bg-elev2/40 p-3">
              <div className="mb-3 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-text">
                  <SlidersHorizontal size={14} className="text-accent" />
                  <span>{t.advancedTitle}</span>
              </div>
                <span className="text-[11px] text-muted">{t.sourcePrefix}: {activeSourceLabel}</span>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
                <FilterField label={t.field.score} icon={<Star size={12} />}>
                  <select value={scoreFilter} onChange={(event) => setScoreFilter(event.target.value as ScoreFilter)} className={filterControlClass}>
                    {SCORE_FILTERS.map((item) => <option key={item.key} value={item.key}>{item[language]}</option>)}
                  </select>
                </FilterField>
                <FilterField label={t.field.followers} icon={<Users size={12} />}>
                  <div className="grid grid-cols-2 gap-2">
                    <input value={minFollowers} onChange={(event) => setMinFollowers(event.target.value.replace(/[^0-9]/g, ''))} inputMode="numeric" placeholder={t.min} className={filterControlClass} />
                    <input value={maxFollowers} onChange={(event) => setMaxFollowers(event.target.value.replace(/[^0-9]/g, ''))} inputMode="numeric" placeholder={t.max} className={filterControlClass} />
                  </div>
                </FilterField>
                <FilterField label={t.field.product} icon={<Tag size={12} />}>
                  <select value={productFilter} onChange={(event) => setProductFilter(event.target.value)} className={filterControlClass}>
                    <option value="all">{t.allProduct}</option>
                    {productOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                </FilterField>
                <FilterField label={t.field.collab} icon={<Handshake size={12} />}>
                  <select value={collabFilter} onChange={(event) => setCollabFilter(event.target.value)} className={filterControlClass}>
                    <option value="all">{t.allCollab}</option>
                    {collabOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                </FilterField>
                <FilterField label={t.field.status} icon={<ShieldAlert size={12} />}>
                  <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className={filterControlClass}>
                    <option value="all">{t.allStatus}</option>
                    {statusOptions.map((item) => <option key={item.value} value={item.value}>{displayStatus(item.label, language)}</option>)}
                  </select>
                </FilterField>
                <FilterField label={t.field.review} icon={<ShieldAlert size={12} />}>
                  <select value={reviewFilter} onChange={(event) => setReviewFilter(event.target.value as ReviewFilter)} className={filterControlClass}>
                    {REVIEW_FILTERS.map((item) => <option key={item.key} value={item.key}>{item[language]}</option>)}
                  </select>
                </FilterField>
                <FilterField label={t.field.owner} icon={<UserCheck size={12} />}>
                  <select value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value as OwnerFilter)} className={filterControlClass}>
                    {OWNER_FILTERS.map((item) => <option key={item.key} value={item.key}>{item[language]}</option>)}
                  </select>
                </FilterField>
                <FilterField label={t.field.date} icon={<Clock size={12} />}>
                  <select value={dateRange} onChange={(event) => setDateRange(event.target.value as DateFilter)} className={filterControlClass}>
                    {DATE_FILTERS.map((item) => <option key={item.key} value={item.key}>{item[language]}</option>)}
                  </select>
                </FilterField>
                <FilterField label={t.field.sort} icon={<SlidersHorizontal size={12} />} className="xl:col-span-2">
                  <select value={sort} onChange={(event) => setSort(event.target.value as SortFilter)} className={filterControlClass}>
                    {SORT_FILTERS.map((item) => <option key={item.key} value={item.key}>{item[language]}</option>)}
                  </select>
                </FilterField>
              </div>
            </div>
          )}

          <div className="mt-3 flex min-h-9 flex-wrap items-center gap-2 border-t border-border pt-2">
            <span className="text-[11px] font-semibold text-muted">{t.enabled}</span>
            {activeFilterBadges.length === 0 ? (
              <span className="rounded-full bg-elev2 px-2 py-1 text-[11px] text-muted">{t.noExtraFilters}</span>
            ) : activeFilterBadges.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={item.onClear}
                className="inline-flex max-w-[220px] items-center gap-1 rounded-full border border-border bg-elev1 px-2 py-1 text-[11px] text-text transition-colors hover:border-accent"
              >
                <span className="truncate">{item.label}</span>
                <X size={11} className="shrink-0 text-muted" />
              </button>
            ))}
          </div>
        </div>
      </div>

      <AsyncState
        loading={activeQ.isLoading}
        error={activeQ.error}
        isEmpty={filtered.length === 0}
        loadingMessage={language === 'zh' ? '加载中...' : 'Loading...'}
        errorTitle={language === 'zh' ? '加载失败' : 'Failed to load'}
        emptyMessage={t.empty}
        height={320}
      >
        <div className="grid gap-3">
          {pagedItems.map((creator, index) => (
            <RecommendationCard
              key={`${String(creator.id ?? 'creator')}:${sourceKey(creator)}:${creator.handle || 'handle'}:${offset + index}`}
              creator={creator}
              language={language}
              onOpen={(c) => navigate(`/recommendations/${encodeURIComponent(String(c.id))}`)}
              onMail={openOutreach}
              mailPending={lockingCreatorId === String(creator.id)}
            />
          ))}
        </div>
      </AsyncState>

      <PaginationControls
        page={page}
        pageSize={PAGE_SIZE}
        total={endpointAllTotal}
        currentCount={pagedItems.length}
        loading={activeQ.isFetching}
        language={language}
        onPageChange={setPage}
      />

      <OutreachDrawer
        creator={drawerCreator}
        open={!!drawerCreator}
        initialLock={drawerLock}
        onClose={() => {
          setDrawerCreator(null);
          setDrawerLock(null);
          activeQ.refetch();
        }}
      />
    </div>
  );
}
