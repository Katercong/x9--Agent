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
import { useAcquireOutreachLock, useBusinessDashboard, useCreators, useRecommended } from '@/hooks/useApi';
import { formatCompact, maskEmail } from '@/lib/format';
import { pickItems, type Creator, type CreatorOutreachLock } from '@/api/types';


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

const PAGE_SIZE = 10;

const SOURCE_META: Record<Exclude<SourceFilter, 'all'>, { label: string; color: string }> = {
  tiktok_shop: { label: 'TikTok Shop', color: '#ff3b63' },
  x9_leads: { label: 'X9 线索', color: '#00a6c8' },
  table_import: { label: '表格导入', color: '#c88415' },
  other: { label: '其他来源', color: '#687284' },
};

const SOURCE_FILTERS: Array<{ key: SourceFilter; label: string }> = [
  { key: 'all', label: '全部来源' },
  { key: 'tiktok_shop', label: 'TikTok Shop' },
  { key: 'x9_leads', label: 'X9 线索' },
  { key: 'table_import', label: '表格导入' },
  { key: 'other', label: '其他' },
];

const SCORE_FILTERS: Array<{ key: ScoreFilter; label: string }> = [
  { key: 'all', label: '全部评分' },
  { key: 'gte85', label: '85+ 强推荐' },
  { key: '70_84', label: '70-84 可测试' },
  { key: '50_69', label: '50-69 观察' },
  { key: 'lt50', label: '<50 低分' },
];

const PRIORITY_FILTERS: Array<{ key: PriorityFilter; label: string }> = [
  { key: 'all', label: '全部优先级' },
  { key: 'P1', label: 'P1' },
  { key: 'P2', label: 'P2' },
  { key: 'P3', label: 'P3' },
  { key: 'P4', label: 'P4' },
];

const CONTACT_FILTERS: Array<{ key: ContactFilter; label: string }> = [
  { key: 'all', label: '全部联系' },
  { key: 'contactable', label: '可联系' },
  { key: 'email', label: '有邮箱' },
  { key: 'none', label: '无联系方式' },
];


const DATE_FILTERS: Array<{ key: DateFilter; label: string }> = [
  { key: 'all', label: '全部入库时间' },
  { key: '1d', label: '近 24 小时' },
  { key: '7d', label: '近 7 天' },
  { key: '30d', label: '近 30 天' },
];

const REVIEW_FILTERS: Array<{ key: ReviewFilter; label: string }> = [
  { key: 'all', label: '全部复核状态' },
  { key: 'need_review', label: '需要复核' },
  { key: 'has_risk', label: '有风险提示' },
  { key: 'clean', label: '无复核/风险' },
];

const OWNER_FILTERS: Array<{ key: OwnerFilter; label: string }> = [
  { key: 'all', label: '全部归属' },
  { key: 'assigned', label: '已分配 BD' },
  { key: 'unassigned', label: '未分配 BD' },
];

const SORT_FILTERS: Array<{ key: SortFilter; label: string }> = [
  { key: 'recommended', label: '综合推荐排序' },
  { key: 'score', label: '评分从高到低' },
  { key: 'followers', label: '粉丝从高到低' },
  { key: 'fit', label: '产品匹配优先' },
  { key: 'priority', label: '优先级 P1 优先' },
  { key: 'recent', label: '最近入库优先' },
  { key: 'contactable', label: '可联系优先' },
  { key: 'micro', label: '小达人优先' },
];

const filterControlClass = 'h-9 w-full rounded-md border border-border bg-elev1 px-3 text-xs text-text outline-none transition-colors focus:border-accent';

function optionLabel<T extends string>(items: Array<{ key: T; label: string }>, key: T) {
  return items.find((item) => item.key === key)?.label || key;
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

function scoreTone(score?: number | null) {
  if ((score ?? 0) >= 85) return { fg: '#05343b', bg: '#c8f7ff', label: '强推荐' };
  if ((score ?? 0) >= 70) return { fg: '#6f4700', bg: '#fff1c6', label: '可测试' };
  return { fg: '#4b5563', bg: '#eef2f7', label: '观察' };
}

function creatorInitial(c: Creator) {
  return (c.handle || c.display_name || '?').slice(0, 1).toUpperCase();
}

function creatorName(c: Creator) {
  return c.display_name || c.handle || `达人 ${c.id}`;
}

function followers(c: Creator) {
  return c.followers_count ?? c.followers ?? null;
}

function numberValue(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
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

function sourceMeta(c: Creator) {
  const key = sourceKey(c);
  return { key, label: c.source_label || SOURCE_META[key].label, color: SOURCE_META[key].color };
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

function tagsFor(c: Creator) {
  return [
    c.primary_product_category,
    c.recommended_product_type,
    ...(c.category_tags || []),
    ...(c.positive_tags || []),
  ].filter(Boolean).slice(0, 4) as string[];
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
  onOpen,
  onMail,
  mailPending,
}: {
  creator: Creator;
  onOpen: (creator: Creator) => void;
  onMail: (creator: Creator) => void;
  mailPending?: boolean;
}) {
  const tone = scoreTone(creator.recommendation_score);
  const tags = tagsFor(creator);
  const priority = creator.outreach_priority || creator.priority_level || 'P?';
  const status = creator.recommendation_status || creator.current_status || '待处理';
  const source = sourceMeta(creator);

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onOpen(creator)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') onOpen(creator);
      }}
      className="card card-body group grid cursor-pointer grid-cols-1 gap-3 transition-all hover:-translate-y-0.5 hover:shadow-lg lg:grid-cols-[minmax(280px,1.2fr)_minmax(320px,1fr)_220px]"
    >
      <div className="flex min-w-0 gap-3">
        <div className="relative flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-md text-xl font-black text-white shadow-sm" style={{ background: source.color }}>
          <span>{creatorInitial(creator)}</span>
          <span className="absolute inset-x-2 bottom-1 h-1 rounded-full bg-white/25" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <h3 className="truncate text-base font-black leading-tight">@{creator.handle || 'unknown'}</h3>
            <span className="rounded-full bg-elev2 px-2 py-0.5 text-[11px] font-semibold text-text">{priority}</span>
          </div>
          <div className="mt-1 truncate text-xs text-muted">{creatorName(creator)}</div>
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
              {creator.country || creator.language || '地区未知'}
            </span>
            {hasContact(creator) && (
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[11px] text-good">
                可联系
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-bold" style={{ color: tone.fg, background: tone.bg }}>
            <Star size={12} /> {tone.label}
          </span>
          <span className="rounded-full bg-elev2 px-2.5 py-1 text-[11px] text-muted">{status}</span>
        </div>
        <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-text/80">
          {creator.recommendation_reason || creator.next_action || '暂无推荐理由，进入详情页补充查看达人画像与外联建议。'}
        </p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {tags.length > 0 ? tags.map((tag) => (
            <span key={tag} className="rounded-full border border-border bg-elev1 px-2 py-0.5 text-[11px] text-muted">{tag}</span>
          )) : (
            <span className="text-[11px] text-muted">暂无标签</span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-[76px_1fr]">
        <div className="rounded-md border border-border bg-elev2 p-2">
          <div className="text-[11px] text-muted">评分</div>
          <div className="mt-1 font-mono text-2xl font-black leading-none">{Math.round(creator.recommendation_score ?? 0)}</div>
        </div>
        <div className="rounded-md border border-border bg-elev2 p-2">
          <div className="text-[11px] text-muted">粉丝 / 联系</div>
          <div className="mt-1 text-sm font-black">{formatCompact(followers(creator))}</div>
          <div className="mt-0.5 truncate text-[11px] text-muted">{creator.email ? maskEmail(creator.email) : '暂无邮箱'}</div>
        </div>
        <div className="col-span-2 flex items-center justify-end gap-2">
          {creator.profile_url && (
            <a
              href={creator.profile_url}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => event.stopPropagation()}
              className="btn btn-ghost !h-8 !px-2.5 text-xs"
            >
              <ExternalLink size={13} /> 主页
            </a>
          )}
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onMail(creator);
            }}
            disabled={mailPending}
            className="btn btn-primary !h-8 !px-3 text-xs disabled:opacity-60"
          >
            <Mail size={13} /> {mailPending ? '占用中' : '邮件建联'}
          </button>
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-elev2 text-accent transition-transform group-hover:translate-x-0.5">
            <ArrowRight size={15} />
          </span>
        </div>
      </div>
    </article>
  );
}

export default function Recommendations() {
  const navigate = useNavigate();

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
  const recommendedQ = useRecommended(queryParams);
  const creatorsQ = useCreators({ ...queryParams, offset, sort_by: backendSortBy });
  const businessQ = useBusinessDashboard();
  const activeQ = creatorsQ;
  const items = pickItems<Creator>(activeQ.data as any);
  const recommendedItems = pickItems<Creator>(recommendedQ.data as any);
  const allItems = pickItems<Creator>(creatorsQ.data as any);

  const optionItems = useMemo(() => {
    const seen = new Map<string, Creator>();
    [...allItems, ...recommendedItems].forEach((creator) => {
      seen.set(String(creator.id ?? `${creator.source || ''}:${creator.handle || ''}`), creator);
    });
    return [...seen.values()];
  }, [allItems, recommendedItems]);
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
    () => uniqueOptions(optionItems, (creator) => [creator.current_status, creator.recommendation_status]),
    [optionItems],
  );

  useEffect(() => {
    setPage(0);
  }, [collabFilter, contact, dateRange, maxFollowers, minFollowers, ownerFilter, priority, productFilter, q, reviewFilter, scoreFilter, sort, source, statusFilter]);

  const filtered = useMemo(() => {
    const text = q.trim().toLowerCase();
    const rows = items.filter((creator) => {
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
      if (statusFilter !== 'all' && !valueList(creator.current_status, creator.recommendation_status).includes(statusFilter)) return false;
      return true;
    });
    return sortCreators(rows, sort);
  }, [collabFilter, contact, dateRange, items, maxFollowers, minFollowers, ownerFilter, priority, productFilter, q, reviewFilter, scoreFilter, sort, source, statusFilter]);

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

  const highScore = recommendedItems.filter((c) => (c.recommendation_score ?? 0) >= 80).length;
  const needReview = recommendedItems.filter((c) => c.review_required || c.risk_summary).length;
  const contactable = allItems.filter(hasContact).length;
  const localTodayAdded = allItems.filter((c) => isToday(c.collected_at || c.created_at)).length;
  const recommendedTotal = (recommendedQ.data as any)?.total ?? recommendedItems.length;
  const endpointAllTotal = (creatorsQ.data as any)?.total ?? allItems.length;
  const summary = businessQ.data?.summary || {};
  const summaryAllTotal = Number(summary.total_creators);
  const allTotal = source === 'all' && Number.isFinite(summaryAllTotal) ? summaryAllTotal : endpointAllTotal;
  const summaryToday = Number(summary.today_new_creators ?? summary.today_collected);
  const todayAdded = source === 'all' && Number.isFinite(summaryToday) ? summaryToday : localTodayAdded;
  const activeSourceLabel = SOURCE_FILTERS.find((item) => item.key === source)?.label || '全部来源';
  const activeFilterBadges: ActiveFilterBadge[] = [
    source !== 'all' && { key: 'source', label: `来源: ${activeSourceLabel}`, onClear: () => setSource('all') },
    Boolean(q.trim()) && { key: 'q', label: `搜索: ${q.trim()}`, onClear: () => setQ('') },
    priority !== 'all' && { key: 'priority', label: `优先级: ${priority}`, onClear: () => setPriority('all') },
    contact !== 'all' && { key: 'contact', label: `联系: ${optionLabel(CONTACT_FILTERS, contact)}`, onClear: () => setContact('all') },
    scoreFilter !== 'all' && { key: 'score', label: `评分: ${optionLabel(SCORE_FILTERS, scoreFilter)}`, onClear: () => setScoreFilter('all') },
    Boolean(minFollowers.trim() || maxFollowers.trim()) && {
      key: 'followers',
      label: `粉丝: ${minFollowers.trim() || '0'}-${maxFollowers.trim() || '不限'}`,
      onClear: () => { setMinFollowers(''); setMaxFollowers(''); },
    },
    dateRange !== 'all' && { key: 'date', label: `时间: ${optionLabel(DATE_FILTERS, dateRange)}`, onClear: () => setDateRange('all') },
    reviewFilter !== 'all' && { key: 'review', label: `复核: ${optionLabel(REVIEW_FILTERS, reviewFilter)}`, onClear: () => setReviewFilter('all') },
    ownerFilter !== 'all' && { key: 'owner', label: `归属: ${optionLabel(OWNER_FILTERS, ownerFilter)}`, onClear: () => setOwnerFilter('all') },
    productFilter !== 'all' && { key: 'product', label: `品类: ${productFilter}`, onClear: () => setProductFilter('all') },
    collabFilter !== 'all' && { key: 'collab', label: `合作: ${collabFilter}`, onClear: () => setCollabFilter('all') },
    statusFilter !== 'all' && { key: 'status', label: `状态: ${statusFilter}`, onClear: () => setStatusFilter('all') },
    sort !== 'recommended' && { key: 'sort', label: `排序: ${optionLabel(SORT_FILTERS, sort)}`, onClear: () => setSort('recommended') },
  ].filter(Boolean) as ActiveFilterBadge[];

  const openOutreach = async (creator: Creator) => {
    const creatorId = String(creator.id);
    setLockingCreatorId(creatorId);
    try {
      const result = await acquireOutreachLock.mutateAsync({ creator_id: creator.id });
      setDrawerLock(result.lock);
      setDrawerCreator(creator);
    } catch (error: any) {
      const detail = error?.response?.data?.detail || error?.message || '达人已被其他用户占用，请刷新后再试';
      alert(String(detail));
    } finally {
      setLockingCreatorId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="card overflow-hidden">
        <div className="grid gap-4 p-4 lg:grid-cols-[minmax(320px,1fr)_auto]">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className="chip text-xxs">
                <Sparkles size={12} /> 达人库
              </span>
              <span className="chip text-xxs">推荐池和达人信息已合并</span>
            </div>
            <h2 className="text-xl font-semibold leading-tight text-text">达人库</h2>
            <div className="mt-2 text-xs text-muted">当前来源：{activeSourceLabel}</div>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:min-w-[660px] lg:grid-cols-6">
            {[
              { label: '全部达人', value: formatCompact(allTotal), icon: Users },
              { label: '推荐池', value: formatCompact(recommendedTotal), icon: Sparkles },
              { label: '可联系', value: contactable, icon: Mail },
              { label: '今日入库', value: todayAdded, icon: CalendarDays },
              { label: '高分 ≥80', value: highScore, icon: Star },
              { label: '需复核', value: needReview, icon: ShieldAlert },
            ].map((kpi) => {
              const Icon = kpi.icon;
              return (
                <div key={kpi.label} className="rounded-md border border-border bg-elev2 p-3">
                  <div className="flex items-center gap-1.5 text-[11px] text-muted"><Icon size={12} />{kpi.label}</div>
                  <div className="mt-2 font-mono text-xl font-semibold text-text">{kpi.value}</div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="border-t border-border">
          <div className="grid gap-3 p-3 xl:grid-cols-[minmax(420px,1.05fr)_minmax(360px,0.95fr)]">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-text">
                  <SlidersHorizontal size={14} className="text-accent" />
                  <span>筛选工作台</span>
                  <span className="rounded-full bg-elev2 px-2 py-0.5 text-[11px] font-medium text-muted">
                    {filtered.length} / {formatCompact(items.length)}
                  </span>
                  {activeFilterCount > 0 && (
                    <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[11px] font-semibold text-accent">
                      {activeFilterCount} 项启用
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <a href="/api/local/export/recommended-creators.csv" className="btn btn-ghost !h-8 text-xs">
                    <Download size={13} /> 导出 CSV
                  </a>
                  <button type="button" onClick={resetFilters} className="btn btn-ghost !h-8 text-xs">
                    <RotateCcw size={13} /> 重置
                  </button>
                </div>
              </div>

              <div className="grid gap-2 lg:grid-cols-[minmax(300px,1fr)_minmax(280px,0.85fr)]">
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
                          {item.label}
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
                    placeholder="搜索 handle / 邮箱 / 商品 / 推荐理由"
                    className="min-w-0 flex-1 bg-transparent text-xs text-text outline-none placeholder:text-muted"
                  />
                  {q.trim() && (
                    <button type="button" onClick={() => setQ('')} className="inline-flex h-6 w-6 items-center justify-center rounded text-muted hover:bg-elev2 hover:text-text">
                      <X size={13} />
                    </button>
                  )}
                </div>
              </div>

              <div className="grid gap-2 md:grid-cols-2">
                <div className="rounded-md border border-border bg-elev2/50 p-2">
                  <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold text-muted">
                    <Star size={12} /> 优先级
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {PRIORITY_FILTERS.map((item) => (
                      <SegmentedButton key={item.key} active={priority === item.key} onClick={() => setPriority(item.key)}>
                        {item.label}
                      </SegmentedButton>
                    ))}
                  </div>
                </div>
                <div className="rounded-md border border-border bg-elev2/50 p-2">
                  <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold text-muted">
                    <Mail size={12} /> 联系方式
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {CONTACT_FILTERS.map((item) => (
                      <SegmentedButton key={item.key} active={contact === item.key} onClick={() => setContact(item.key)}>
                        {item.key === 'contactable' && <CheckCircle2 size={12} />}
                        {item.label}
                      </SegmentedButton>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-3 rounded-md border border-border bg-elev2/40 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-text">
                  <Filter size={14} className="text-muted" />
                  <span>高级条件</span>
                </div>
                <span className="text-[11px] text-muted">当前来源: {activeSourceLabel}</span>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <FilterField label="评分" icon={<Star size={12} />}>
                  <select value={scoreFilter} onChange={(event) => setScoreFilter(event.target.value as ScoreFilter)} className={filterControlClass}>
                    {SCORE_FILTERS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                  </select>
                </FilterField>
                <FilterField label="粉丝范围" icon={<Users size={12} />}>
                  <div className="grid grid-cols-2 gap-2">
                    <input value={minFollowers} onChange={(event) => setMinFollowers(event.target.value.replace(/[^0-9]/g, ''))} inputMode="numeric" placeholder="最低" className={filterControlClass} />
                    <input value={maxFollowers} onChange={(event) => setMaxFollowers(event.target.value.replace(/[^0-9]/g, ''))} inputMode="numeric" placeholder="最高" className={filterControlClass} />
                  </div>
                </FilterField>
                <FilterField label="品类 / 商品" icon={<Tag size={12} />}>
                  <select value={productFilter} onChange={(event) => setProductFilter(event.target.value)} className={filterControlClass}>
                    <option value="all">全部品类 / 商品类型</option>
                    {productOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                </FilterField>
                <FilterField label="合作方式" icon={<Handshake size={12} />}>
                  <select value={collabFilter} onChange={(event) => setCollabFilter(event.target.value)} className={filterControlClass}>
                    <option value="all">全部合作方式</option>
                    {collabOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                </FilterField>
                <FilterField label="状态" icon={<ShieldAlert size={12} />}>
                  <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className={filterControlClass}>
                    <option value="all">全部状态</option>
                    {statusOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                </FilterField>
                <FilterField label="复核 / 风险" icon={<ShieldAlert size={12} />}>
                  <select value={reviewFilter} onChange={(event) => setReviewFilter(event.target.value as ReviewFilter)} className={filterControlClass}>
                    {REVIEW_FILTERS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                  </select>
                </FilterField>
                <FilterField label="BD 归属" icon={<UserCheck size={12} />}>
                  <select value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value as OwnerFilter)} className={filterControlClass}>
                    {OWNER_FILTERS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                  </select>
                </FilterField>
                <FilterField label="入库时间" icon={<Clock size={12} />}>
                  <select value={dateRange} onChange={(event) => setDateRange(event.target.value as DateFilter)} className={filterControlClass}>
                    {DATE_FILTERS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                  </select>
                </FilterField>
                <FilterField label="排序" icon={<SlidersHorizontal size={12} />} className="md:col-span-2">
                  <select value={sort} onChange={(event) => setSort(event.target.value as SortFilter)} className={filterControlClass}>
                    {SORT_FILTERS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                  </select>
                </FilterField>
              </div>
            </div>
          </div>

          <div className="flex min-h-11 flex-wrap items-center gap-2 border-t border-border bg-elev2/30 px-3 py-2">
            <span className="text-[11px] font-semibold text-muted">已启用</span>
            {activeFilterBadges.length === 0 ? (
              <span className="rounded-full bg-elev1 px-2 py-1 text-[11px] text-muted">无额外条件</span>
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

      <PaginationControls
        page={page}
        pageSize={PAGE_SIZE}
        total={endpointAllTotal}
        currentCount={items.length}
        loading={activeQ.isFetching}
        onPageChange={setPage}
      />

      <AsyncState loading={activeQ.isLoading} error={activeQ.error} isEmpty={filtered.length === 0} emptyMessage="暂无符合条件的达人" height={320}>
        <div className="grid gap-3">
          {filtered.map((creator) => (
            <RecommendationCard
              key={creator.id}
              creator={creator}
              onOpen={(c) => navigate(`/recommendations/${encodeURIComponent(String(c.id))}`)}
              onMail={openOutreach}
              mailPending={lockingCreatorId === String(creator.id)}
            />
          ))}
        </div>
      </AsyncState>

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
