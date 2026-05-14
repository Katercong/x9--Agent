import { Users, Inbox, ThumbsUp, Clock, Handshake, ListChecks, MessageSquare, ArrowUpRight, MailCheck, PackageCheck, Video, UserCheck, UserMinus, UserPlus } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { PriorityBar } from '@/components/progress/PriorityBar';
import { DataTable, type Column } from '@/components/table/DataTable';
import { dashboardKpis, trend7d, statusDistribution, productDirection, priorityDistribution, bdFollowUp } from '@/mock/department';

const topKpiIcons = [Users, Inbox, ThumbsUp, Clock, Handshake];
const topKpiBg = ['#e0e7ff', '#d1fae5', '#cffafe', '#fed7aa', '#ede9fe'];
const topKpiFg = ['#4f46e5', '#16a34a', '#0891b2', '#ea580c', '#7c3aed'];

const overviewIcons = [
  ArrowUpRight, MessageSquare, ListChecks, Clock, UserPlus,
  UserMinus, MailCheck, PackageCheck, Video, UserCheck,
];
const overviewBg = [
  '#fce7f3', '#dcfce7', '#dbeafe', '#fef3c7', '#cffafe',
  '#fee2e2', '#dbeafe', '#dcfce7', '#fef3c7', '#ede9fe',
];
const overviewFg = [
  '#db2777', '#16a34a', '#2563eb', '#a16207', '#0891b2',
  '#dc2626', '#2563eb', '#16a34a', '#ca8a04', '#7c3aed',
];

type BdRow = (typeof bdFollowUp)[number];

const bdColumns: Column<BdRow>[] = [
  { key: 'owner', header: '负责人', cell: (r) => <span className="text-xs">{r.owner}</span> },
  { key: 'recommend', header: '推荐', align: 'right', cell: (r) => <span className="text-xs num">{r.recommend}</span> },
  { key: 'contact', header: '待联系', align: 'right', cell: (r) => <span className="text-xs num">{r.contact}</span> },
  { key: 'advance', header: '已推进', align: 'right', cell: (r) => <span className="text-xs num">{r.advance}</span> },
];

export default function Dashboard() {
  // ECharts options
  const trendOption = {
    grid: { top: 30, right: 16, bottom: 30, left: 36, containLabel: true },
    xAxis: {
      type: 'category',
      data: trend7d.dates,
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      max: 40,
      splitNumber: 4,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    tooltip: { trigger: 'axis' },
    series: [
      {
        type: 'line',
        data: trend7d.values,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: '#3370ff', width: 2 },
        itemStyle: { color: '#3370ff', borderColor: '#fff', borderWidth: 2 },
        label: { show: true, position: 'top', color: '#3370ff', fontSize: 11, fontWeight: 600 },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(51,112,255,0.18)' },
              { offset: 1, color: 'rgba(51,112,255,0)' },
            ],
          },
        },
      },
    ],
  };

  const donutOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: {
      orient: 'vertical',
      right: '4%',
      top: 'center',
      icon: 'circle',
      itemWidth: 8,
      itemGap: 12,
      textStyle: { color: '#4e5969', fontSize: 12 },
      formatter: (name: string) => {
        const item = statusDistribution.data.find((d) => d.name === name);
        if (!item) return name;
        const pct = ((item.value / statusDistribution.total) * 100).toFixed(1);
        return `${name}  ${item.value} (${pct}%)`;
      },
    },
    series: [
      {
        type: 'pie',
        radius: ['58%', '78%'],
        center: ['32%', '50%'],
        avoidLabelOverlap: false,
        label: { show: false },
        labelLine: { show: false },
        data: statusDistribution.data.map((d) => ({ name: d.name, value: d.value, itemStyle: { color: d.color } })),
      },
    ],
    graphic: [
      {
        type: 'text',
        left: '32%',
        top: '42%',
        style: {
          text: '总计',
          textAlign: 'center',
          fontSize: 12,
          fill: '#86909c',
        },
      },
      {
        type: 'text',
        left: '32%',
        top: '52%',
        style: {
          text: String(statusDistribution.total),
          textAlign: 'center',
          fontSize: 22,
          fontWeight: 700,
          fill: '#1f2329',
        },
      },
    ],
  };

  const directionOption = {
    grid: { top: 10, right: 24, bottom: 30, left: 80, containLabel: true },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLabel: { color: '#86909c', fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'category',
      data: productDirection.map((d) => d.name).reverse(),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#4e5969', fontSize: 12 },
    },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [
      {
        type: 'bar',
        data: productDirection.map((d) => d.value).reverse(),
        barWidth: 14,
        itemStyle: { color: '#3370ff', borderRadius: [0, 3, 3, 0] },
        label: {
          show: true,
          position: 'right',
          color: '#4e5969',
          fontSize: 11,
          fontWeight: 500,
        },
      },
    ],
  };

  return (
    <div className="space-y-4">
      {/* 顶部 5 KPI */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {dashboardKpis.topRow.map((k, i) => (
          <KpiCard
            key={k.label}
            label={k.label}
            value={k.value}
            subLabel={k.subLabel}
            delta={k.delta}
            icon={topKpiIcons[i]}
            iconBg={topKpiBg[i]}
            iconColor={topKpiFg[i]}
          />
        ))}
      </div>

      {/* 业务概览标题 */}
      <div className="pt-1">
        <h3 className="sec-title">业务概览</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {dashboardKpis.overview.map((k, i) => (
            <KpiCard
              key={k.label}
              label={k.label}
              value={k.value}
              delta={k.delta}
              icon={overviewIcons[i]}
              iconBg={overviewBg[i]}
              iconColor={overviewFg[i]}
              compact
            />
          ))}
        </div>
      </div>

      {/* 三栏图表 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <ChartCard title="近 7 天新增趋势">
          <EChart option={trendOption} height={240} />
        </ChartCard>
        <ChartCard title="业务状态分布">
          <EChart option={donutOption} height={240} />
        </ChartCard>
        <ChartCard title="产品方向分布">
          <EChart option={directionOption} height={240} />
        </ChartCard>
      </div>

      {/* 底部:优先级 + BD 表 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="card lg:col-span-1">
          <div className="px-4 pt-3 pb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-800">优先级分布</h3>
          </div>
          <div className="px-2 pb-3">
            <PriorityBar rows={priorityDistribution} />
          </div>
        </div>
        <div className="card lg:col-span-2">
          <div className="px-4 pt-3 pb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-800">BD 跟进明细</h3>
          </div>
          <div className="px-2 pb-3">
            <DataTable columns={bdColumns} data={bdFollowUp} rowKey={(r) => r.owner} />
          </div>
        </div>
      </div>
    </div>
  );
}
