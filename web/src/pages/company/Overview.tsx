import { Wallet, ShoppingCart, Users, TrendingUp, Building2, Video, ArrowUpRight, AlertOctagon } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { overviewKpis, monthlyRevenue, departments, importantEvents } from '@/mock/company';
import { chartPalette } from '@/lib/colors';

const icons = [Wallet, ShoppingCart, Users, TrendingUp, Building2, Video, ArrowUpRight, AlertOctagon];
const bgs = ['#e0e7ff', '#d1fae5', '#cffafe', '#fed7aa', '#ede9fe', '#fce7f3', '#fef3c7', '#fee2e2'];
const fgs = ['#4f46e5', '#16a34a', '#0891b2', '#ea580c', '#7c3aed', '#db2777', '#ca8a04', '#dc2626'];

type Event = typeof importantEvents[number];

const eventColumns: Column<Event>[] = [
  { key: 'date', header: '日期', cell: (r) => <span className="text-xs text-muted">{r.date}</span>, width: '100px' },
  {
    key: 'type', header: '类型',
    cell: (r) => {
      const toneMap: Record<string, 'good' | 'warn' | 'bad' | 'info'> = {
        good: 'good', info: 'info', warn: 'warn', bad: 'bad',
      };
      return <Pill tone={toneMap[r.level]}>{r.type}</Pill>;
    },
  },
  { key: 'title', header: '事件', cell: (r) => <span className="text-xs">{r.title}</span> },
  { key: 'dept', header: '部门', cell: (r) => <span className="text-xs text-muted">{r.dept}</span> },
];

export default function Overview() {
  const revenueTrendOption = {
    grid: { top: 30, right: 20, bottom: 40, left: 50, containLabel: true },
    legend: { top: 0, textStyle: { color: '#86909c', fontSize: 11 } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: monthlyRevenue.months,
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 11, formatter: '{value}万' },
    },
    series: monthlyRevenue.departments.map((name, i) => ({
      name,
      type: 'bar',
      stack: 'rev',
      barWidth: 22,
      data: monthlyRevenue.series[i],
      itemStyle: { color: chartPalette.categorical[i] },
    })),
  };

  const deptContrib = departments.map((d, i) => ({
    name: d.name,
    value: d.revenue,
    itemStyle: { color: chartPalette.categorical[i] },
  }));

  const deptContribOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c}万 ({d}%)' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, textStyle: { fontSize: 11 } },
    series: [
      {
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: false,
        label: { show: false },
        labelLine: { show: false },
        data: deptContrib,
      },
    ],
  };

  const categoryOption = {
    grid: { top: 20, right: 30, bottom: 30, left: 80, containLabel: true },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } } },
    yAxis: { type: 'category', data: ['女性护理', '母婴', '家居护理', '成人护理', '宠物用品'].reverse(), axisLine: { show: false }, axisTick: { show: false } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [
      {
        type: 'bar',
        data: [292, 240, 200, 290, 450].reverse(),
        barWidth: 14,
        itemStyle: { color: '#3370ff', borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: 'right', color: '#4e5969', fontSize: 11, formatter: '{c}万' },
      },
    ],
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
        {overviewKpis.map((k, i) => (
          <KpiCard
            key={k.label}
            label={k.label}
            value={k.value}
            subLabel={k.subLabel}
            delta={k.delta}
            icon={icons[i]}
            iconBg={bgs[i]}
            iconColor={fgs[i]}
          />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <ChartCard title="近 7 月营收趋势 · 按部门" className="lg:col-span-2">
          <EChart option={revenueTrendOption} height={280} />
        </ChartCard>
        <ChartCard title="部门营收贡献">
          <EChart option={deptContribOption} height={280} />
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <ChartCard title="类目分布 · 30 日营收">
          <EChart option={categoryOption} height={260} />
        </ChartCard>
        <div className="card lg:col-span-2">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">最近重要事件</h3>
          </div>
          <DataTable columns={eventColumns} data={importantEvents.slice(0, 6)} compact />
        </div>
      </div>
    </div>
  );
}
