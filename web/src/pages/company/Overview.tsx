import { Wallet, ShoppingCart, Users, TrendingUp, Building2, Video, ArrowUpRight, AlertOctagon, UserCheck, UserPlus } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { OutreachStatsTable } from '@/components/dashboard/OutreachStatsTable';
import { useCreators, useOutreach, useProducts, useUnifiedDashboard, useAnalyticsCompany } from '@/hooks/useApi';
import { trendByDay } from '@/lib/derive';
import { formatDate } from '@/lib/format';

interface RecentEvent {
  id: string;
  date: string;
  sortAt: number;
  source: string;
  type: string;
  level: 'good' | 'info' | 'warn' | 'bad';
  title: string;
  dept: string;
}

const eventColumns: Column<RecentEvent>[] = [
  { key: 'date', header: '日期', cell: (r) => <span className="text-xs text-muted">{r.date}</span>, width: '100px' },
  { key: 'source', header: '来源', cell: (r) => <span className="text-xs text-muted">{r.source}</span>, width: '120px' },
  {
    key: 'type',
    header: '类型',
    width: '92px',
    cell: (r) => <Pill tone={r.level} className="min-w-[64px] justify-center whitespace-nowrap">{r.type}</Pill>,
  },
  { key: 'title', header: '事件', cell: (r) => <span className="text-xs">{r.title}</span> },
  { key: 'dept', header: '部门', cell: (r) => <span className="text-xs text-muted">{r.dept}</span> },
];

const EVENT_TYPE_LABELS: Record<string, string> = {
  recommended: '推荐',
  assigned: '分配',
  sent: '已发送',
  email_sent: '已发送',
  queued: '邮件排队',
  email_queued: '邮件排队',
  failed: '邮件失败',
  email_failed: '邮件失败',
  pending_reply: '待回复',
  contacted: '已建联',
  replied: '已回复',
  communicating: '沟通中',
  confirmed: '已确认',
  sample_shipped: '已寄样',
  sample_delivered: '样品签收',
  video_published: '视频已发',
  partnered: '已合作',
  ad_authorized: '已授权',
  ad_running: '投放中',
  dropped: '已放弃',
};

function eventLevel(type: string): RecentEvent['level'] {
  if (['ad_running', 'ad_authorized', 'partnered', 'email_sent'].includes(type)) return 'good';
  if (['dropped', 'failed', 'email_failed'].includes(type)) return 'bad';
  if (['video_published', 'sample_shipped', 'sample_delivered'].includes(type)) return 'warn';
  return 'info';
}

function eventTime(value: string | null | undefined) {
  const time = value ? Date.parse(value) : 0;
  return Number.isFinite(time) ? time : 0;
}

function eventLabel(type: string | null | undefined, fallback?: string | null) {
  const normalized = String(type || '').trim().toLowerCase();
  const mapped = EVENT_TYPE_LABELS[normalized];
  if (mapped) return mapped;
  if (fallback === '邮件已发') return '已发送';
  return fallback || normalized || '事件';
}

export default function Overview() {
  const creators = useCreators({ limit: 10 });
  const outreach = useOutreach({ limit: 10, order_by: 'created_at:desc' });
  const products = useProducts({ limit: 1 });
  const unifiedDashboard = useUnifiedDashboard();
  const companyAnalytics = useAnalyticsCompany(30);

  const loading = creators.isLoading || outreach.isLoading || products.isLoading || unifiedDashboard.isLoading || companyAnalytics.isLoading;
  const error = creators.error || outreach.error || products.error || unifiedDashboard.error || companyAnalytics.error;

  const creatorList = creators.data?.items ?? [];
  const outreachList = outreach.data?.items ?? [];
  const unifiedSummary = unifiedDashboard.data?.summary;
  const company = companyAnalytics.data;
  const progressRows = company?.members?.slice(0, 12) ?? [];

  const trend30 = company?.trend?.length
    ? company.trend.map((d) => ({
        date: d.date.slice(5),
        collected: d.collected ?? 0,
        processed: d.processed,
        recommended: d.recommended,
        sent: d.sent,
        partnered: d.partnered,
      }))
    : trendByDay(creatorList as any, 30).map((d) => ({ date: d.date, collected: 0, processed: d.count, recommended: 0, sent: 0, partnered: 0 }));

  // 近期事件(从 outreach 取最近的)
  const platformEvents: RecentEvent[] = (company?.recent_events ?? []).map((event) => ({
    id: event.id,
    date: formatDate(event.occurred_at),
    sortAt: eventTime(event.occurred_at),
    source: event.source === 'outreach_emails' ? '邮件系统' : '建联事件',
    type: eventLabel(event.event_type, event.event_label),
    level: eventLevel(event.event_type),
    title: event.title || `${event.actor || '-'} 对 ${event.creator || event.creator_id || '-'} ${eventLabel(event.event_type, event.event_label)}`,
    dept: event.department_code || '全平台',
  }));
  const legacyEvents: RecentEvent[] = outreachList.map((o) => {
    const type = eventLabel(o.status || o.action, o.action || o.status || '事件');
    return {
      id: `legacy_outreach:${o.id}`,
      date: formatDate(o.event_date || o.created_at),
      sortAt: eventTime(o.event_date || o.created_at),
      source: '历史BD',
      type,
      level: eventLevel(o.status || o.action || ''),
      title: o.message ? o.message.slice(0, 30) + (o.message.length > 30 ? '...' : '') :
        `BD ${o.bd_owner || '-'} 对 #${o.creator_id} ${type}`,
      dept: o.store_name || '—',
    };
  });
  const recentEvents: RecentEvent[] = [...platformEvents, ...legacyEvents]
    .sort((a, b) => b.sortAt - a.sortAt)
    .slice(0, 8);

  const overviewKpis = [
    { label: '总发现', value: unifiedSummary?.total_discovered ?? 0, icon: Users, bg: '#e0e7ff', fg: '#4f46e5' },
    { label: '总采集', value: unifiedSummary?.total_collected ?? 0, icon: UserCheck, bg: '#dcfce7', fg: '#16a34a' },
    { label: '近24小时建联', value: unifiedSummary?.today_contacted ?? 0, icon: ShoppingCart, bg: '#d1fae5', fg: '#16a34a' },
    { label: '今日采集', value: unifiedSummary?.today_collected ?? 0, icon: Wallet, bg: '#cffafe', fg: '#0891b2' },
    { label: '今日重复达人', value: unifiedSummary?.today_duplicate_creators ?? 0, icon: UserPlus, bg: '#fee2e2', fg: '#dc2626' },
    { label: '总达人推荐', value: unifiedSummary?.total_recommended ?? 0, icon: TrendingUp, bg: '#fed7aa', fg: '#ea580c' },
    { label: '总建联', value: unifiedSummary?.total_contacted ?? 0, icon: Building2, bg: '#ede9fe', fg: '#7c3aed' },
    { label: '待回复', value: unifiedSummary?.pending_reply ?? 0, icon: Video, bg: '#fce7f3', fg: '#db2777' },
    { label: '沟通中', value: unifiedSummary?.communicating ?? 0, icon: ArrowUpRight, bg: '#fef3c7', fg: '#ca8a04' },
    { label: '广告投放中', value: unifiedSummary?.ad_running ?? 0, icon: AlertOctagon, bg: '#fee2e2', fg: '#dc2626' },
  ];

  // 趋势图
  const trendOption = {
    grid: { top: 30, right: 16, bottom: 30, left: 36, containLabel: true },
    xAxis: {
      type: 'category', data: trend30.map((d) => d.date),
      axisLine: { lineStyle: { color: '#e5e6eb' } }, axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 10, interval: 4 },
    },
    yAxis: {
      type: 'value', axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    tooltip: { trigger: 'axis' },
    legend: { top: 4, textStyle: { fontSize: 11 } },
    series: [
      { name: '总采集达人', type: 'line', data: trend30.map((d) => d.collected ?? 0), smooth: true, symbol: 'none', lineStyle: { color: '#0891b2', width: 2 } },
      {
        name: '处理入库', type: 'line', data: trend30.map((d) => d.processed), smooth: true, symbol: 'none',
        lineStyle: { color: '#3370ff', width: 2 },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: 'rgba(51,112,255,0.18)' }, { offset: 1, color: 'rgba(51,112,255,0)' }] } },
      },
      { name: '推荐', type: 'line', data: trend30.map((d) => d.recommended), smooth: true, symbol: 'none', lineStyle: { color: '#8b5cf6', width: 2 } },
      { name: '已发送', type: 'line', data: trend30.map((d) => d.sent), smooth: true, symbol: 'none', lineStyle: { color: '#16a34a', width: 2 } },
      { name: '合作', type: 'line', data: trend30.map((d) => d.partnered), smooth: true, symbol: 'none', lineStyle: { color: '#f59e0b', width: 2 } },
    ],
  };

  return (
    <AsyncState loading={loading} error={error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
          {overviewKpis.map((k) => (
            <KpiCard key={k.label} label={k.label} value={k.value} icon={k.icon} iconBg={k.bg} iconColor={k.fg} />
          ))}
        </div>

        <div>
          <ChartCard title="近 30 天达人新增">
            <EChart option={trendOption} height={280} />
          </ChartCard>
        </div>

        <OutreachStatsTable rows={progressRows} />

        <div className="card">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">最近事件流水</h3>
            <div className="text-xxs text-muted mt-0.5">数据源：全平台建联事件、邮件系统、历史 BD 流水，按事件时间倒序合并</div>
          </div>
          <DataTable columns={eventColumns} data={recentEvents} rowKey={(r) => r.id} compact />
        </div>
      </div>
    </AsyncState>
  );
}
