import {
  ArrowUpRight,
  Clock,
  Handshake,
  Inbox,
  ListChecks,
  MailCheck,
  MessageSquare,
  PackageCheck,
  UserCheck,
  UserPlus,
  Users,
  Video,
} from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { AsyncState, Empty } from '@/components/states/States';
import { useBusinessDashboard } from '@/hooks/useApi';

type CountRow = { key?: string; name?: string; label?: string; count?: number; value?: number };
type BdRow = {
  owner?: string;
  creator_count?: number;
  contacted?: number;
  confirmed?: number;
  samples?: number;
  videos?: number;
  authorized?: number;
};

const topKpiIcons = [Users, Inbox, Handshake, ListChecks];
const topKpiBg = ['#e0e7ff', '#d1fae5', '#cffafe', '#ede9fe'];
const topKpiFg = ['#4f46e5', '#16a34a', '#0891b2', '#7c3aed'];

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
  pending_followup: '#fbbf24',
  pending_reply: '#fbbf24',
  confirmed: '#3370ff',
  sample_shipped: '#8b5cf6',
  sample_delivered: '#a855f7',
  video_published: '#f59e0b',
  ad_authorized: '#10b981',
  ad_running: '#16a34a',
  dropped: '#ef4444',
};

function num(n: unknown): string {
  const v = typeof n === 'number' ? n : Number(n);
  return Number.isFinite(v) ? new Intl.NumberFormat('en-US').format(v) : '0';
}

function formatDay(value: string) {
  const parts = value.split('-');
  if (parts.length !== 3) return value;
  return `${Number(parts[1])}/${Number(parts[2])}`;
}

function countValue(row: CountRow) {
  return Number(row.count ?? row.value ?? 0) || 0;
}

function MiniTable({ title, rows, empty = '暂无数据' }: { title: string; rows: CountRow[]; empty?: string }) {
  const visibleRows = rows.filter((row) => countValue(row) > 0);
  return (
    <div className="card">
      <div className="px-4 py-3 border-b border-border">
        <h3 className="text-sm font-semibold text-text">{title}</h3>
      </div>
      <div className="p-2">
        {visibleRows.length === 0 ? (
          <Empty height={120} message={empty} />
        ) : (
          <table className="table-x9">
            <tbody>
              {visibleRows.map((row, i) => (
                <tr key={`${row.key || row.name || row.label || i}`}>
                  <td className="text-xs text-text">{row.name || row.label || row.key || '-'}</td>
                  <td className="text-xs text-right num text-text">{num(countValue(row))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default function Business() {
  const dashboardQ = useBusinessDashboard();
  const data: any = dashboardQ.data || {};
  const summary = data.summary || {};
  const overviewCounts = Object.fromEntries((data.overview || []).map((row: CountRow) => [row.key, row.count]));
  const trend7 = data.trend_7d || [];
  const recent7 = trend7.reduce((sum: number, row: CountRow) => sum + countValue(row), 0);
  const categoryRows: CountRow[] = data.category_counts || [];
  const ownerRows: CountRow[] = data.owner_counts || [];
  const stageRows: CountRow[] = data.stage_rows || [];
  const bdRows: BdRow[] = data.bd_rows || [];
  const sourceRows: CountRow[] = data.source_counts || [];
  const todayNewCreators = summary.today_new_creators ?? summary.today_collected ?? 0;
  const processedUnique = summary.unique_creators ?? 0;
  const processedRows = summary.processed_rows_total ?? 0;
  const rawRows = summary.raw_observations_total ?? 0;
  const bdHistoryCreators = summary.bd_history_creators ?? summary.legacy_staff_contacted ?? 0;

  const topRow = [
    { label: '总达人', value: summary.total_creators || 0, subLabel: `业务表 ${num(processedRows || processedUnique)} + raw ${num(rawRows)} + BD ${num(bdHistoryCreators)}` },
    { label: '今日新增', value: todayNewCreators, subLabel: '所有渠道累计' },
    { label: '业务已触达', value: summary.contacted || 0, subLabel: bdHistoryCreators ? `含 BD 历史 ${num(bdHistoryCreators)}` : undefined },
    { label: '业务已推进', value: summary.progressed || 0, subLabel: '确认及以上，不重复累加' },
  ];

  const overview = [
    { label: '潜在线索', value: overviewCounts.prospect || 0 },
    { label: '已联系', value: overviewCounts.contacted || 0 },
    { label: '已确认', value: overviewCounts.confirmed || 0 },
    { label: '待跟进', value: overviewCounts.pending_followup || overviewCounts.pending_reply || 0 },
    { label: '近 7 天新增', value: recent7 },
    { label: '已寄样', value: overviewCounts.sample_shipped || 0 },
    { label: '样品签收', value: overviewCounts.sample_delivered || 0 },
    { label: '视频已发', value: overviewCounts.video_published || 0 },
    { label: '已授权', value: overviewCounts.ad_authorized || 0 },
    { label: '广告投放中', value: overviewCounts.ad_running || 0 },
  ];

  const trendOption = {
    grid: { top: 30, right: 16, bottom: 30, left: 36, containLabel: true },
    xAxis: {
      type: 'category',
      data: trend7.map((row: any) => formatDay(String(row.date || ''))),
      axisLine: { lineStyle: { color: 'rgba(134,145,162,0.35)' } },
      axisTick: { show: false },
      axisLabel: { color: 'rgba(255,255,255,0.58)', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      splitNumber: 4,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: 'rgba(134,145,162,0.18)', type: 'dashed' } },
      axisLabel: { color: 'rgba(255,255,255,0.58)', fontSize: 11 },
    },
    tooltip: { trigger: 'axis' },
    series: [{
      type: 'line',
      data: trend7.map((row: CountRow) => countValue(row)),
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { color: '#22d3ee', width: 2 },
      itemStyle: { color: '#22d3ee', borderColor: '#0f172a', borderWidth: 2 },
      label: { show: true, position: 'top', color: '#22d3ee', fontSize: 11, fontWeight: 600 },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(34,211,238,0.20)' },
            { offset: 1, color: 'rgba(34,211,238,0)' },
          ],
        },
      },
    }],
  };

  const donutTotal = Number(summary.total_creators || 0);
  const donutData = stageRows
    .filter((row) => countValue(row) > 0)
    .map((row) => ({
      name: row.name || row.label || row.key || '-',
      value: countValue(row),
      color: stageColors[String(row.key || '')] || '#94a3b8',
    }));
  const donutOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: {
      type: 'scroll',
      orient: 'vertical',
      right: '2%',
      top: 'center',
      icon: 'circle',
      itemWidth: 8,
      itemGap: 10,
      textStyle: { color: 'rgba(255,255,255,0.72)', fontSize: 11 },
    },
    series: [{
      type: 'pie',
      radius: ['58%', '78%'],
      center: ['28%', '50%'],
      label: { show: false },
      labelLine: { show: false },
      data: donutData.map((row) => ({ name: row.name, value: row.value, itemStyle: { color: row.color } })),
    }],
    graphic: [
      { type: 'text', left: '28%', top: '42%', style: { text: '总计', textAlign: 'center', fontSize: 12, fill: 'rgba(255,255,255,0.58)' } },
      { type: 'text', left: '28%', top: '52%', style: { text: String(donutTotal), textAlign: 'center', fontSize: 22, fontWeight: 700, fill: '#fff' } },
    ],
  };

  const categoryOption = {
    grid: { top: 10, right: 24, bottom: 30, left: 88, containLabel: true },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: 'rgba(134,145,162,0.18)', type: 'dashed' } },
      axisLabel: { color: 'rgba(255,255,255,0.58)', fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'category',
      data: categoryRows.map((row) => row.name || row.label || '-').reverse(),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: 'rgba(255,255,255,0.72)', fontSize: 12 },
    },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [{
      type: 'bar',
      data: categoryRows.map((row) => countValue(row)).reverse(),
      barWidth: 14,
      itemStyle: { color: '#3b82f6', borderRadius: [0, 3, 3, 0] },
      label: { show: true, position: 'right', color: 'rgba(255,255,255,0.72)', fontSize: 11, fontWeight: 500 },
    }],
  };

  return (
    <AsyncState loading={dashboardQ.isLoading} error={dashboardQ.error} height={420}>
      <div className="space-y-4">
        <div className="text-xs text-muted">
          范围: {data.scope?.name || '当前部门'} · 数据源: /api/local/dashboard/department-summary ·
          业务去重口径 · 生成时间: {data.generated_at ? new Date(data.generated_at).toLocaleString() : '-'}
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {topRow.map((item, i) => (
            <KpiCard
              key={item.label}
              label={item.label}
              value={num(item.value)}
              subLabel={item.subLabel}
              icon={topKpiIcons[i]}
              iconBg={topKpiBg[i]}
              iconColor={topKpiFg[i]}
            />
          ))}
        </div>

        <div className="pt-1">
          <h3 className="sec-title">业务概览</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            {overview.map((item, i) => (
              <KpiCard
                key={item.label}
                label={item.label}
                value={num(item.value)}
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
            {donutData.length ? <EChart option={donutOption} height={240} /> : <Empty height={240} message="暂无阶段数据" />}
          </ChartCard>
          <ChartCard title="达人品类分布">
            {categoryRows.length ? <EChart option={categoryOption} height={240} /> : <Empty height={240} message="暂无品类数据" />}
          </ChartCard>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <MiniTable title="对接人达人占比 Top 8" rows={ownerRows} empty="暂无对接人数据" />
          <MiniTable title="业务来源分布" rows={sourceRows} empty="暂无来源数据" />
          <div className="card">
            <div className="px-4 py-3 border-b border-border">
              <h3 className="text-sm font-semibold text-text">BD 跟进数据</h3>
              <div className="text-xxs text-muted mt-0.5">业务表跟进 + BD 历史汇总，采集 raw 不进入这里</div>
            </div>
            <div className="p-2">
              {bdRows.length === 0 ? (
                <Empty height={140} message="暂无 BD 跟进数据" />
              ) : (
                <table className="table-x9">
                  <thead>
                    <tr>
                      <th className="text-left">BD</th>
                      <th className="text-right">达人</th>
                      <th className="text-right">已联系</th>
                      <th className="text-right">已确认</th>
                      <th className="text-right">已寄样</th>
                      <th className="text-right">视频</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bdRows.map((row, i) => (
                      <tr key={`${row.owner || i}`}>
                        <td className="text-xs text-text">{row.owner || '未分配'}</td>
                        <td className="text-xs text-right num text-text">{num(row.creator_count)}</td>
                        <td className="text-xs text-right num text-text">{num(row.contacted)}</td>
                        <td className="text-xs text-right num text-text">{num(row.confirmed)}</td>
                        <td className="text-xs text-right num text-text">{num(row.samples)}</td>
                        <td className="text-xs text-right num text-text">{num(row.videos)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      </div>
    </AsyncState>
  );
}
