import {
  Users,
  Inbox,
  ThumbsUp,
  Clock,
  Handshake,
  ListChecks,
  MessageSquare,
  ArrowUpRight,
  MailCheck,
  PackageCheck,
  Video,
  UserCheck,
  UserPlus,
} from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { PriorityBar } from '@/components/progress/PriorityBar';
import { DataTable, type Column } from '@/components/table/DataTable';
import { AsyncState } from '@/components/states/States';
import { useDepartmentDashboardSummary, useStaff, useUnifiedDashboard } from '@/hooks/useApi';
import { staffStats } from '@/lib/derive';
import type { AnalyticsMemberRow } from '@/api/types';

const topKpiIcons = [Users, UserCheck, Inbox, ThumbsUp, UserPlus, Clock, Handshake];
const topKpiBg = ['#e0e7ff', '#dcfce7', '#d1fae5', '#cffafe', '#fee2e2', '#fed7aa', '#ede9fe'];
const topKpiFg = ['#4f46e5', '#16a34a', '#16a34a', '#0891b2', '#dc2626', '#ea580c', '#7c3aed'];

const overviewIcons = [
  ArrowUpRight, MessageSquare, ListChecks, Clock, UserPlus,
  PackageCheck, MailCheck, Video, UserCheck, Handshake,
];
const overviewBg = [
  '#fce7f3', '#dcfce7', '#dbeafe', '#fef3c7', '#cffafe',
  '#dcfce7', '#dbeafe', '#fef3c7', '#ede9fe', '#f3e8ff',
];
const overviewFg = [
  '#db2777', '#16a34a', '#2563eb', '#a16207', '#0891b2',
  '#16a34a', '#2563eb', '#ca8a04', '#7c3aed', '#9333ea',
];

const stageColors: Record<string, string> = {
  discovered: '#94a3b8',
  recommended: '#38bdf8',
  pending_contact: '#22c55e',
  prospect: '#94a3b8',
  contacted: '#60a5fa',
  pending_reply: '#fbbf24',
  communicating: '#3370ff',
  confirmed: '#3370ff',
  sample_shipped: '#8b5cf6',
  sample_delivered: '#a855f7',
  video_published: '#f59e0b',
  ad_authorized: '#10b981',
  ad_running: '#16a34a',
  dropped: '#ef4444',
};

type BdRow = ReturnType<typeof staffStats>[number];

const bdColumns: Column<BdRow>[] = [
  { key: 'owner', header: '负责人', cell: (r) => <span className="text-xs">{r.name}</span> },
  { key: 'contacted', header: '已建联', align: 'right', cell: (r) => <span className="text-xs num">{r.contacted}</span> },
  { key: 'confirmed', header: '已确认', align: 'right', cell: (r) => <span className="text-xs num">{r.confirmed}</span> },
  { key: 'samples', header: '已寄样', align: 'right', cell: (r) => <span className="text-xs num">{r.samples}</span> },
  { key: 'videos', header: '已发视频', align: 'right', cell: (r) => <span className="text-xs num">{r.videos}</span> },
];

const memberColumns: Column<AnalyticsMemberRow>[] = [
  { key: 'member', header: '成员', cell: (r) => <span className="text-xs">{r.member || '未分配'}</span> },
  { key: 'shop', header: 'Shop入库', align: 'right', cell: (r) => <span className="text-xs num">{r.tiktok_shop_processed ?? 0}</span> },
  { key: 'video', header: '视频入库', align: 'right', cell: (r) => <span className="text-xs num">{r.tiktok_video_processed ?? 0}</span> },
  { key: 'bd', header: 'BD入库', align: 'right', cell: (r) => <span className="text-xs num">{r.bd_processed ?? 0}</span> },
  { key: 'recommended', header: '推荐', align: 'right', cell: (r) => <span className="text-xs num">{r.recommended ?? 0}</span> },
  { key: 'sent', header: '已发送', align: 'right', cell: (r) => <span className="text-xs num">{r.sent ?? 0}</span> },
  { key: 'replied', header: '已回复', align: 'right', cell: (r) => <span className="text-xs num">{r.replied ?? 0}</span> },
  { key: 'sample_shipped', header: '已寄样', align: 'right', cell: (r) => <span className="text-xs num">{r.sample_shipped ?? 0}</span> },
  { key: 'partnered', header: '已合作', align: 'right', cell: (r) => <span className="text-xs num">{r.partnered ?? 0}</span> },
];

const sourceLabels: Record<string, string> = {
  tiktok_shop: 'TikTok Shop',
  tiktok_video: 'TikTok视频',
  bd: 'BD达人',
};

function formatDay(value: string) {
  const parts = value.split('-');
  if (parts.length !== 3) return value;
  return `${Number(parts[1])}/${Number(parts[2])}`;
}

export default function Dashboard() {
  const dashboardQ = useUnifiedDashboard();
  const legacyDashboardQ = useDepartmentDashboardSummary();
  const staffQ = useStaff({ limit: 10 });
  const data = dashboardQ.data;
  const legacyData = legacyDashboardQ.data;
  const summary = data?.summary ?? {
    total_discovered: 0,
    total_collected: 0,
    today_discovered: 0,
    today_collected: 0,
    today_duplicate_creators: 0,
    total_recommended: 0,
    pending_contact: 0,
    pending_reply: 0,
    communicating: 0,
    sample_shipped: 0,
    sample_delivered: 0,
    video_published: 0,
    ad_authorized: 0,
    ad_running: 0,
  };
  const overviewCounts = Object.fromEntries((data?.stage_rows ?? []).map((row) => [row.key, row.count]));
  const analytics = legacyData?.analytics;
  const sourceCounts = Object.fromEntries((analytics?.source_counts ?? []).map((row) => [row.name, row.count]));
  const memberRows = analytics?.members?.slice(0, 8) ?? [];
  const trend7 = legacyData?.trend_7d ?? [];
  const recent7 = trend7.reduce((sum, row) => sum + row.count, 0);
  const categoryCounts = legacyData?.category_counts?.length ? legacyData.category_counts : [{ name: '未填写', value: 0 }];
  const ownerRows = (legacyData?.owner_counts ?? []).map((row) => ({ label: row.name, value: row.count }));
  const bdRows = staffStats(staffQ.data?.items ?? [])
    .sort((a, b) => b.contacted - a.contacted)
    .slice(0, 8);

  const topRow = [
    { label: '总发现', value: summary.total_discovered, subLabel: '当前达人主队列总量', delta: null as number | null },
    { label: '总采集', value: summary.total_collected, subLabel: '去除队列标记后的采集量', delta: null },
    { label: '今日发现', value: summary.today_discovered, subLabel: '今天入队总量', delta: null },
    { label: '今日采集', value: summary.today_collected, subLabel: '今天新增有效采集', delta: null },
    { label: '今日重复达人', value: summary.today_duplicate_creators, subLabel: '今天重复出现的达人', delta: null },
    { label: '总达人推荐', value: summary.total_recommended, delta: null },
    { label: '待建联', value: summary.pending_contact, delta: null },
  ];

  const sourceRow = [
    { key: 'tiktok_shop', value: sourceCounts.tiktok_shop || 0, icon: Inbox, bg: '#fce7f3', fg: '#db2777' },
    { key: 'tiktok_video', value: sourceCounts.tiktok_video || 0, icon: Video, bg: '#dbeafe', fg: '#2563eb' },
    { key: 'bd', value: sourceCounts.bd || 0, icon: UserCheck, bg: '#dcfce7', fg: '#16a34a' },
  ];

  const overview = [
    { label: '待回复', value: overviewCounts.pending_reply || 0 },
    { label: '沟通中', value: overviewCounts.communicating || 0 },
    { label: '近 7 天新增', value: recent7 },
    { label: '跟进逾期', value: data?.followups.overdue ?? 0 },
    { label: '今日跟进', value: data?.followups.due_today ?? 0 },
    { label: '已寄样', value: overviewCounts.sample_shipped || 0 },
    { label: '样品签收', value: overviewCounts.sample_delivered || 0 },
    { label: '视频已发', value: overviewCounts.video_published || 0 },
    { label: '已授权', value: overviewCounts.ad_authorized || 0 },
    { label: '广告投放中', value: overviewCounts.ad_running || 0 },
  ];

  const donutData = (data?.stage_rows ?? [])
    .filter((row) => row.count > 0)
    .map((row) => ({
      name: row.name,
      value: row.count,
      color: stageColors[row.key] || '#94a3b8',
    }));
  const donutTotal = summary.total_discovered;

  const trendOption = {
    grid: { top: 30, right: 16, bottom: 30, left: 36, containLabel: true },
    xAxis: {
      type: 'category', data: trend7.map((d) => formatDay(d.date)),
      axisLine: { lineStyle: { color: '#e5e6eb' } }, axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    yAxis: {
      type: 'value', splitNumber: 4,
      axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    tooltip: { trigger: 'axis' },
    series: [{
      type: 'line', data: trend7.map((d) => d.count), smooth: true,
      symbol: 'circle', symbolSize: 6,
      lineStyle: { color: '#3370ff', width: 2 },
      itemStyle: { color: '#3370ff', borderColor: '#fff', borderWidth: 2 },
      label: { show: true, position: 'top', color: '#3370ff', fontSize: 11, fontWeight: 600 },
      areaStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: 'rgba(51,112,255,0.18)' }, { offset: 1, color: 'rgba(51,112,255,0)' }] },
      },
    }],
  };

  const donutOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: {
      orient: 'vertical', right: '2%', top: 'center', icon: 'circle',
      itemWidth: 8, itemGap: 10, textStyle: { color: '#4e5969', fontSize: 11 },
      formatter: (name: string) => {
        const item = donutData.find((d) => d.name === name);
        if (!item || !donutTotal) return name;
        const pct = ((item.value / donutTotal) * 100).toFixed(1);
        return `${name}  ${item.value} (${pct}%)`;
      },
    },
    series: [{
      type: 'pie', radius: ['58%', '78%'], center: ['28%', '50%'],
      label: { show: false }, labelLine: { show: false },
      data: donutData.map((d) => ({ name: d.name, value: d.value, itemStyle: { color: d.color } })),
    }],
    graphic: [
      { type: 'text', left: '28%', top: '42%', style: { text: '总计', textAlign: 'center', fontSize: 12, fill: '#86909c' } },
      { type: 'text', left: '28%', top: '52%', style: { text: String(donutTotal), textAlign: 'center', fontSize: 22, fontWeight: 700, fill: '#1f2329' } },
    ],
  };

  const directionOption = {
    grid: { top: 10, right: 24, bottom: 30, left: 80, containLabel: true },
    xAxis: {
      type: 'value', splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLabel: { color: '#86909c', fontSize: 11 }, axisLine: { show: false }, axisTick: { show: false },
    },
    yAxis: {
      type: 'category', data: categoryCounts.map((d) => d.name).reverse(),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: '#4e5969', fontSize: 12 },
    },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [{
      type: 'bar', data: categoryCounts.map((d) => d.value).reverse(),
      barWidth: 14,
      itemStyle: { color: '#3370ff', borderRadius: [0, 3, 3, 0] },
      label: { show: true, position: 'right', color: '#4e5969', fontSize: 11, fontWeight: 500 },
    }],
  };

  return (
    <AsyncState loading={dashboardQ.isLoading} error={dashboardQ.error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-7 gap-3">
          {topRow.map((k, i) => (
            <KpiCard
              key={k.label}
              label={k.label}
              value={k.value}
              subLabel={k.subLabel}
              icon={topKpiIcons[i]}
              iconBg={topKpiBg[i]}
              iconColor={topKpiFg[i]}
            />
          ))}
        </div>

        <div className="pt-1">
          <h3 className="sec-title">业务概览</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            {overview.map((k, i) => (
              <KpiCard
                key={k.label}
                label={k.label}
                value={k.value}
                icon={overviewIcons[i]}
                iconBg={overviewBg[i]}
                iconColor={overviewFg[i]}
                compact
              />
            ))}
          </div>
        </div>

        <div className="pt-1">
          <h3 className="sec-title">处理后来源拆分</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {sourceRow.map((item) => (
              <KpiCard
                key={item.key}
                label={sourceLabels[item.key]}
                value={item.value}
                subLabel="按去重主档来源记录统计"
                icon={item.icon}
                iconBg={item.bg}
                iconColor={item.fg}
                compact
              />
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <ChartCard title="近 7 天达人新增">
            <EChart option={trendOption} height={240} />
          </ChartCard>
          <ChartCard title="达人阶段分布">
            <EChart option={donutOption} height={240} />
          </ChartCard>
          <ChartCard title="达人品类分布">
            <EChart option={directionOption} height={240} />
          </ChartCard>
        </div>

        <div className="card">
          <div className="px-4 pt-3 pb-2">
            <h3 className="text-sm font-semibold text-gray-800">成员入库与建联进度</h3>
            <div className="text-xxs text-muted mt-0.5">只统计采集后处理入库、推荐和建联事件，不使用 raw 回传量作为达人数量</div>
          </div>
          <div className="px-2 pb-3">
            <DataTable
              columns={memberColumns}
              data={memberRows}
              rowKey={(r) => r.member}
              emptyText="暂无成员维度处理数据"
              compact
            />
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="card lg:col-span-1">
            <div className="px-4 pt-3 pb-2">
              <h3 className="text-sm font-semibold text-gray-800">对接人达人占比 Top 8</h3>
            </div>
            <div className="px-2 pb-3">
              <PriorityBar rows={ownerRows} labelHeader="对接人" valueHeader="达人数" />
            </div>
          </div>
          <div className="card lg:col-span-2">
            <div className="px-4 pt-3 pb-2">
              <h3 className="text-sm font-semibold text-gray-800">BD 历史跟进数据</h3>
              <div className="text-xxs text-muted mt-0.5">来自 staff.note 月度统计，已并入上方全平台统计口径</div>
            </div>
            <div className="px-2 pb-3">
              <DataTable
                columns={bdColumns}
                data={bdRows}
                rowKey={(r) => r.name}
                emptyText={staffQ.isLoading ? 'BD 数据加载中...' : staffQ.error ? 'BD 历史数据暂不可用' : '暂无 BD 历史数据'}
                compact
              />
            </div>
          </div>
        </div>
      </div>
    </AsyncState>
  );
}
