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
import { useDepartmentDashboardSummary } from '@/hooks/useApi';
import type { DepartmentDashboardBdRow } from '@/api/types';

const topKpiIcons = [Users, Inbox, ThumbsUp, Clock, Handshake];
const topKpiBg = ['#e0e7ff', '#d1fae5', '#cffafe', '#fed7aa', '#ede9fe'];
const topKpiFg = ['#4f46e5', '#16a34a', '#0891b2', '#ea580c', '#7c3aed'];

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
  prospect: '#94a3b8',
  contacted: '#60a5fa',
  pending_reply: '#fbbf24',
  confirmed: '#3370ff',
  sample_shipped: '#8b5cf6',
  sample_delivered: '#a855f7',
  video_published: '#f59e0b',
  ad_authorized: '#10b981',
  ad_running: '#16a34a',
  dropped: '#ef4444',
};

type BdRow = DepartmentDashboardBdRow;

const bdColumns: Column<BdRow>[] = [
  { key: 'owner', header: '负责人', cell: (r) => <span className="text-xs">{r.owner}</span> },
  { key: 'creator_count', header: '达人数', align: 'right', cell: (r) => <span className="text-xs num">{r.creator_count}</span> },
  { key: 'contacted', header: '已建联', align: 'right', cell: (r) => <span className="text-xs num">{r.contacted}</span> },
  { key: 'confirmed', header: '已确认', align: 'right', cell: (r) => <span className="text-xs num">{r.confirmed}</span> },
  { key: 'samples', header: '已寄样', align: 'right', cell: (r) => <span className="text-xs num">{r.samples}</span> },
  { key: 'videos', header: '已发视频', align: 'right', cell: (r) => <span className="text-xs num">{r.videos}</span> },
  { key: 'authorized', header: '已授权', align: 'right', cell: (r) => <span className="text-xs num">{r.authorized}</span> },
];

function formatDay(value: string) {
  const parts = value.split('-');
  if (parts.length !== 3) return value;
  return `${Number(parts[1])}/${Number(parts[2])}`;
}

export default function Dashboard() {
  const dashboardQ = useDepartmentDashboardSummary();
  const data = dashboardQ.data;
  const summary = data?.summary ?? {
    total_creators: 0,
    today_collected: 0,
    contacted: 0,
    review_pending: 0,
    progressed: 0,
  };
  const stageCounts = data?.stage_counts ?? {};
  const trend7 = data?.trend_7d ?? [];
  const recent7 = trend7.reduce((sum, row) => sum + row.count, 0);
  const categoryCounts = data?.category_counts?.length ? data.category_counts : [{ name: '未填写', value: 0 }];
  const ownerRows = (data?.owner_counts ?? []).map((row) => ({ label: row.name, value: row.count }));
  const bdRows = data?.bd_rows ?? [];

  const topRow = [
    { label: '总达人', value: summary.total_creators, subLabel: '全部达人去重数', delta: null as number | null },
    { label: '今日采集', value: summary.today_collected, delta: null },
    { label: '已建联', value: summary.contacted, delta: null },
    { label: '待审核', value: summary.review_pending, delta: null },
    { label: '已推进', value: summary.progressed, delta: null },
  ];

  const overview = [
    { label: '潜在线索', value: stageCounts.prospect || 0 },
    { label: '已联系', value: stageCounts.contacted || 0 },
    { label: '已确认', value: stageCounts.confirmed || 0 },
    { label: '待回复', value: stageCounts.pending_reply || 0 },
    { label: '近 7 天新增', value: recent7 },
    { label: '已寄样', value: stageCounts.sample_shipped || 0 },
    { label: '样品签收', value: stageCounts.sample_delivered || 0 },
    { label: '视频已发', value: stageCounts.video_published || 0 },
    { label: '已授权', value: stageCounts.ad_authorized || 0 },
    { label: '广告投放中', value: stageCounts.ad_running || 0 },
  ];

  const donutData = (data?.stage_rows ?? [])
    .filter((row) => row.count > 0)
    .map((row) => ({
      name: row.name,
      value: row.count,
      color: stageColors[row.key] || '#94a3b8',
    }));
  const donutTotal = summary.total_creators;

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
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
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
              <h3 className="text-sm font-semibold text-gray-800">BD 跟进明细</h3>
              <div className="text-xxs text-muted mt-0.5">基于全部达人去重后的负责人阶段统计</div>
            </div>
            <div className="px-2 pb-3">
              <DataTable
                columns={bdColumns}
                data={bdRows}
                rowKey={(r) => r.owner}
                emptyText="暂无 BD 统计数据"
                compact
              />
            </div>
          </div>
        </div>
      </div>
    </AsyncState>
  );
}
