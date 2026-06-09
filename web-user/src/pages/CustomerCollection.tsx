import { useMemo, useState } from 'react';
import {
  ArrowRight,
  CalendarDays,
  Download,
  ExternalLink,
  Filter,
  Mail,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Tag,
  Users,
  Youtube,
} from 'lucide-react';
import { AsyncState } from '@/components/states/States';
import { PaginationControls } from '@/components/PaginationControls';
import {
  useYoutubeLeads,
  useYoutubeRuns,
  useYoutubeStats,
  type YoutubeLead,
} from '@/api/youtube';
import { maskEmail } from '@/lib/format';
import { num } from './collectShared';

const PAGE_SIZE = 10;
const SOURCE_FILTERS = [
  { key: '', label: '全部来源' },
  { key: 'creator_channel', label: '视频博主' },
  { key: 'comment_author_channel', label: '评论用户' },
] as const;

const CONTACT_FILTERS = [
  { key: 'all', label: '全部线索' },
  { key: 'email', label: '有邮箱' },
  { key: 'review', label: '人工审查' },
] as const;

type ContactFilter = (typeof CONTACT_FILTERS)[number]['key'];

function shortTime(value: string | null | undefined): string {
  if (!value) return '暂无';
  const ts = new Date(value).getTime();
  if (!Number.isFinite(ts)) return '暂无';
  const minutes = Math.floor((Date.now() - ts) / 60_000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  const date = new Date(ts);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function sourceLabel(value: string) {
  if (value === 'creator_channel') return '视频博主';
  if (value === 'comment_author_channel') return '评论用户';
  return 'YouTube';
}

function sourceColor(value: string) {
  if (value === 'comment_author_channel') return '#00a6c8';
  return '#ff0033';
}

function reviewReasonLabel(value: string) {
  if (value === 'captcha_required') return '验证码';
  if (value === 'hidden_email_button_present') return '隐藏邮箱';
  if (value === 'login_required') return '需要登录';
  return value || '人工审查';
}

function channelName(row: YoutubeLead) {
  return row.display_name || row.channel_handle || row.channel_key || row.channel_url || row.id;
}

function channelHandle(row: YoutubeLead) {
  if (row.channel_handle) return row.channel_handle.startsWith('@') ? row.channel_handle : `@${row.channel_handle}`;
  const key = row.channel_key.replace(/^handle:/, '');
  return key || '@youtube';
}

function firstLetter(row: YoutubeLead) {
  return channelName(row).replace(/^@/, '').slice(0, 1).toUpperCase() || 'Y';
}

function includesText(row: YoutubeLead, text: string) {
  const q = text.trim().toLowerCase();
  if (!q) return true;
  return [
    row.channel_key,
    row.channel_handle,
    row.channel_url,
    row.display_name,
    row.email,
    row.latest_keyword,
    row.latest_video_title,
  ].some((value) => String(value || '').toLowerCase().includes(q));
}

function csvCell(value: unknown) {
  return `"${String(value ?? '').replace(/"/g, '""')}"`;
}

function exportCsv(rows: YoutubeLead[]) {
  const columns = ['channel', 'email', 'source_type', 'keyword', 'video_title', 'video_url', 'manual_review', 'review_reasons'];
  const lines = [
    columns.join(','),
    ...rows.map((row) => [
      channelName(row),
      row.email,
      sourceLabel(row.latest_source_type),
      row.latest_keyword,
      row.latest_video_title,
      row.latest_video_url,
      row.needs_manual_review ? 'yes' : 'no',
      row.review_reasons.join('|'),
    ].map(csvCell).join(',')),
  ];
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `youtube-customer-collection-${Date.now()}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function CustomerCollection() {
  const [page, setPage] = useState(0);
  const [sourceType, setSourceType] = useState('');
  const [contactFilter, setContactFilter] = useState<ContactFilter>('all');
  const [search, setSearch] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);

  const stats = useYoutubeStats();
  const runs = useYoutubeRuns({ limit: 1, offset: 0 });
  const leads = useYoutubeLeads({
    source_type: sourceType || undefined,
    has_email: contactFilter === 'email' ? true : undefined,
    needs_manual_review: contactFilter === 'review' ? true : undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const rawItems = leads.data?.items ?? [];
  const items = useMemo(() => rawItems.filter((row) => includesText(row, search)), [rawItems, search]);
  const activeSourceLabel = SOURCE_FILTERS.find((item) => item.key === sourceType)?.label || '全部来源';
  const latestRun = stats.data?.latest_run || runs.data?.items?.[0] || null;

  function resetFilters() {
    setSourceType('');
    setContactFilter('all');
    setSearch('');
    setShowAdvanced(false);
    setPage(0);
  }

  function refreshAll() {
    stats.refetch();
    runs.refetch();
    leads.refetch();
  }

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-md border border-border bg-elev1 shadow-card">
        <div className="grid gap-3 border-b border-border p-3 xl:grid-cols-[220px_minmax(0,1fr)]">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="chip text-xxs"><Sparkles size={12} /> 客户采集</span>
              <span className="rounded-full bg-accent/15 px-2 py-1 text-[11px] font-bold text-accent">
                {num(stats.data?.has_email ?? 0)} / {num(stats.data?.leads ?? 0)}
              </span>
            </div>
            <h2 className="mt-2 text-lg font-black leading-tight text-text">YouTube 客户采集库</h2>
            <div className="mt-1 text-xs text-muted">当前来源: {activeSourceLabel}</div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <TopMetric label="有效 Leads" value={num(stats.data?.leads ?? 0)} icon={Users} />
            <TopMetric label="今日入库" value={num(stats.data?.today_runs ?? 0)} icon={CalendarDays} />
            <TopMetric label="人工审查" value={num(stats.data?.manual_review ?? 0)} icon={ShieldAlert} />
          </div>
        </div>

        <div className="p-3">
          <div className="grid gap-2 xl:grid-cols-[minmax(420px,0.95fr)_minmax(300px,1fr)_auto]">
            <div className="min-w-0 rounded-md border border-border bg-elev2/70 p-1">
              <div className="flex max-w-full gap-1 overflow-x-auto">
                {SOURCE_FILTERS.map((item) => (
                  <SegmentedButton
                    key={item.key}
                    active={sourceType === item.key}
                    onClick={() => {
                      setSourceType(item.key);
                      setPage(0);
                    }}
                  >
                    {item.label}
                  </SegmentedButton>
                ))}
              </div>
            </div>

            <label className="flex h-10 min-w-0 items-center gap-2 rounded-md border border-border bg-elev2/45 px-3 text-xs text-muted">
              <Search size={16} className="shrink-0" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索 handle / 邮箱 / 视频 / 关键词"
                className="h-full min-w-0 flex-1 bg-transparent text-text outline-none"
              />
            </label>

            <div className="flex items-center gap-2">
              <button type="button" className="btn" onClick={() => setShowAdvanced((value) => !value)}>
                <Filter size={14} /> 高级筛选
              </button>
              <button type="button" className="btn" onClick={() => exportCsv(items)}>
                <Download size={14} /> 导出
              </button>
              <button type="button" className="btn" onClick={resetFilters}>
                <RefreshCw size={14} /> 重置
              </button>
            </div>
          </div>

          <div className="mt-2 grid gap-2 md:grid-cols-[minmax(260px,0.7fr)_minmax(320px,1fr)]">
            <div className="flex flex-wrap items-center gap-1 rounded-md border border-border bg-elev2/45 p-1">
              {CONTACT_FILTERS.map((item) => (
                <SegmentedButton
                  key={item.key}
                  active={contactFilter === item.key}
                  onClick={() => {
                    setContactFilter(item.key);
                    setPage(0);
                  }}
                >
                  {item.label}
                </SegmentedButton>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-elev2/45 px-3 py-2 text-[11px] text-muted">
              <span>本地模式</span>
              <span className="chip text-xxs">desktop/data/youtube.sqlite</span>
              <span>最近批次: {latestRun?.filename || '暂无'}</span>
            </div>
          </div>

          {showAdvanced && (
            <div className="mt-3 rounded-md border border-border bg-elev2/40 p-3">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-xs font-bold text-text">
                  <Filter size={14} /> 高级条件
                </div>
                <span className="text-[11px] text-muted">当前只筛选本地 YouTube 清洗库，不连接 usx9.us</span>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <InfoBox label="Raw Rows" value={num(stats.data?.raw_rows ?? 0)} />
                <InfoBox label="丢弃空邮箱" value={num(stats.data?.dropped_no_contact ?? 0)} />
                <InfoBox label="数据库状态" value={stats.data?.db_status || 'unknown'} />
              </div>
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3 text-[11px] text-muted">
            <span>已启用</span>
            <span className="chip text-xxs">{activeSourceLabel}</span>
            <span className="chip text-xxs">{CONTACT_FILTERS.find((item) => item.key === contactFilter)?.label}</span>
            {search ? <span className="chip text-xxs">搜索: {search}</span> : <span className="chip text-xxs">无额外条件</span>}
          </div>
        </div>
      </section>

      <AsyncState
        loading={stats.isLoading || leads.isLoading}
        error={stats.error || leads.error}
        isEmpty={!leads.isLoading && items.length === 0}
        emptyMessage="暂无符合条件的 YouTube 客户"
        height={320}
      >
        <div className="grid gap-3">
          {items.map((lead) => (
            <LeadCard key={lead.id} lead={lead} />
          ))}
        </div>

        <PaginationControls
          page={page}
          pageSize={PAGE_SIZE}
          total={leads.data?.total ?? 0}
          currentCount={rawItems.length}
          loading={leads.isFetching}
          onPageChange={setPage}
        />
      </AsyncState>
    </div>
  );
}

function LeadCard({ lead }: { lead: YoutubeLead }) {
  const color = sourceColor(lead.latest_source_type);
  const reasons = lead.review_reasons.map(reviewReasonLabel);
  const statusTone = lead.has_email ? '可联系' : lead.needs_manual_review ? '待核验' : '待补充';
  const statusClass = lead.has_email
    ? 'bg-emerald-400/15 text-emerald-300 border-emerald-400/30'
    : lead.needs_manual_review
      ? 'bg-amber-400/15 text-amber-200 border-amber-300/40'
      : 'bg-slate-400/15 text-slate-300 border-slate-400/30';
  const email = lead.email || '';

  return (
    <article className="group grid overflow-hidden rounded-md border border-border bg-elev1 shadow-card transition-all hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-lg xl:grid-cols-[minmax(260px,0.9fr)_minmax(380px,1.35fr)_minmax(250px,0.75fr)_58px]">
      <div className="flex min-w-0 gap-3 p-3">
        <div className="relative flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-md text-xl font-black text-white shadow-sm" style={{ background: color }}>
          {firstLetter(lead)}
          <div className="absolute bottom-1 left-2 right-2 h-1 rounded-full bg-white/35" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <a className="truncate text-sm font-black text-text hover:text-accent" href={lead.channel_url || undefined} target="_blank" rel="noreferrer">
              {channelHandle(lead)}
            </a>
            <span className="rounded-full bg-elev2 px-2 py-0.5 text-[11px] font-bold text-text">
              {lead.needs_manual_review ? '核验' : 'Lead'}
            </span>
          </div>
          <div className="mt-1 truncate text-xs text-muted">{channelName(lead)}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <TagPill>{sourceLabel(lead.latest_source_type)}</TagPill>
            <TagPill>YouTube</TagPill>
            <TagPill>{lead.latest_keyword || '关键词未知'}</TagPill>
            {lead.has_email ? <TagPill tone="good">可联系</TagPill> : null}
          </div>
        </div>
      </div>

      <div className="border-y border-border p-3 xl:border-x xl:border-y-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-bold ${statusClass}`}>
            {lead.has_email ? <Mail size={12} /> : <ShieldAlert size={12} />} {statusTone}
          </span>
          <span className="rounded-full bg-elev2 px-2.5 py-1 text-xs text-muted">{shortTime(lead.updated_at || lead.last_seen_at)}</span>
        </div>
        <p className="mt-3 line-clamp-2 text-xs leading-5 text-text">
          {lead.latest_video_title || (lead.has_email ? '已从公开视频详情或频道 About 页面清洗出可用邮箱。' : '该频道需要人工核验或等待补充公开邮箱。')}
        </p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {lead.has_email ? <MetricPill>{maskEmail(email)}</MetricPill> : null}
          {reasons.length ? reasons.map((reason) => <MetricPill key={reason} tone="warn">{reason}</MetricPill>) : null}
          {lead.latest_video_id ? <MetricPill>video {lead.latest_video_id}</MetricPill> : null}
          {lead.source_types.map((item) => <MetricPill key={item}>{sourceLabel(item)}</MetricPill>)}
        </div>
      </div>

      <div className="grid gap-2 p-3">
        <div className="grid grid-cols-3 gap-2">
          <StatBox label="邮箱" value={lead.has_email ? '有' : '空'} />
          <StatBox label="来源" value={sourceLabel(lead.latest_source_type).replace('视频', '')} />
          <StatBox label="核验" value={lead.needs_manual_review ? '是' : '否'} />
        </div>
        <div className="rounded-md border border-border bg-elev2 p-2">
          <div className="truncate text-xs text-muted">{email ? maskEmail(email) : '暂无公开邮箱'}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {lead.has_email ? <MetricPill tone="good">有邮箱</MetricPill> : null}
            {lead.needs_manual_review ? <MetricPill tone="warn">人工审查</MetricPill> : null}
            {lead.manual_review_url ? <MetricPill>review url</MetricPill> : null}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-end border-t border-border bg-elev2/45 p-2 xl:flex-col xl:border-l xl:border-t-0">
        <IconLink href={lead.channel_url} title="打开频道" icon={<ExternalLink size={15} />} />
        <IconLink href={lead.manual_review_url || lead.latest_video_url} title="打开证据" icon={<Tag size={15} />} />
        <IconLink href={email ? `mailto:${email}` : ''} title="邮件建联" icon={<Mail size={15} />} primary />
        <IconLink href={lead.latest_video_url} title="打开来源视频" icon={<ArrowRight size={15} />} />
      </div>
    </article>
  );
}

function TopMetric({ label, value, icon: Icon }: { label: string; value: string; icon: typeof Users }) {
  return (
    <div className="rounded-md border border-border bg-elev2/45 p-3">
      <div className="flex items-center gap-1.5 text-[11px] text-muted">
        <Icon size={12} /> {label}
      </div>
      <div className="mt-2 font-mono text-sm font-black text-text">{value}</div>
    </div>
  );
}

function SegmentedButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className={`shrink-0 rounded-md px-3 py-2 text-xs font-bold transition-colors ${active ? 'bg-accent text-white shadow-sm' : 'text-muted hover:bg-elev1 hover:text-text'}`}>
      {children}
    </button>
  );
}

function TagPill({ children, tone = 'muted' }: { children: React.ReactNode; tone?: 'muted' | 'good' }) {
  const cls = tone === 'good'
    ? 'border-emerald-400/30 bg-emerald-400/15 text-emerald-300'
    : 'border-border bg-elev2 text-muted';
  return <span className={`rounded-full border px-2 py-1 text-[11px] ${cls}`}>{children}</span>;
}

function MetricPill({ children, tone = 'muted' }: { children: React.ReactNode; tone?: 'muted' | 'good' | 'warn' }) {
  const cls = tone === 'good'
    ? 'border-emerald-400/30 bg-emerald-400/15 text-emerald-300'
    : tone === 'warn'
      ? 'border-amber-300/40 bg-amber-400/15 text-amber-200'
      : 'border-pink-500/25 bg-pink-500/10 text-pink-300';
  return <span className={`rounded-full border px-2 py-1 text-[11px] ${cls}`}>{children}</span>;
}

function StatBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-elev2 p-2">
      <div className="text-[11px] text-muted">{label}</div>
      <div className="mt-1 truncate font-mono text-lg font-black leading-none text-text">{value}</div>
    </div>
  );
}

function InfoBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-elev1 p-3">
      <div className="text-[11px] text-muted">{label}</div>
      <div className="mt-1 truncate text-sm font-bold text-text">{value}</div>
    </div>
  );
}

function IconLink({ href, title, icon, primary = false }: { href?: string; title: string; icon: React.ReactNode; primary?: boolean }) {
  const disabled = !href;
  const cls = primary
    ? 'bg-accent text-white hover:brightness-110'
    : 'border border-border bg-elev1 text-muted hover:bg-elev2 hover:text-text';
  if (disabled) {
    return (
      <span title={title} className="mb-2 flex h-9 w-9 items-center justify-center rounded-md border border-border bg-elev1 text-muted opacity-40">
        {icon}
      </span>
    );
  }
  return (
    <a title={title} href={href} target="_blank" rel="noreferrer" className={`mb-2 flex h-9 w-9 items-center justify-center rounded-md transition-colors ${cls}`}>
      {icon}
    </a>
  );
}
