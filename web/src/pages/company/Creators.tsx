import { Users, Trophy, Activity, Globe } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { TierPill } from '@/components/Pill';
import { tierDistribution, countryDistribution, topCreators } from '@/mock/company';
import { formatCompact, formatCurrency, formatPercent } from '@/lib/format';

type Creator = typeof topCreators[number];

const creatorColumns: Column<Creator>[] = [
  {
    key: 'rank', header: '#', align: 'center',
    cell: (r) => (
      <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xxs font-bold ${
        r.rank <= 3 ? 'bg-amber-100 text-amber-700' : 'bg-soft text-muted'
      }`}>
        {r.rank}
      </span>
    ),
    width: '50px',
  },
  {
    key: 'creator', header: '达人',
    cell: (r) => (
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center text-white text-xs font-medium">
          {r.handle[0].toUpperCase()}
        </div>
        <span className="text-xs font-medium">@{r.handle}</span>
      </div>
    ),
  },
  { key: 'tier', header: 'Tier', cell: (r) => <TierPill tier={r.tier} /> },
  { key: 'followers', header: '粉丝', align: 'right', cell: (r) => <span className="text-xs num">{formatCompact(r.followers)}</span> },
  { key: 'videos', header: '视频数', align: 'right', cell: (r) => <span className="text-xs num">{r.videos}</span> },
  { key: 'gmv', header: '30d GMV', align: 'right', cell: (r) => <span className="text-xs num font-medium">{formatCurrency(r.gmv30d)}</span> },
  {
    key: 'conv', header: '转化率', align: 'right',
    cell: (r) => (
      <div className="flex items-center justify-end gap-2">
        <div className="w-16 h-1 rounded-full bg-soft overflow-hidden">
          <div className="h-full bg-good rounded-full" style={{ width: `${r.conv * 4}%` }} />
        </div>
        <span className="text-xs num">{formatPercent(r.conv, 1)}</span>
      </div>
    ),
  },
];

export default function Creators() {
  const tierOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', right: 10, top: 'center', icon: 'circle', itemWidth: 8, textStyle: { fontSize: 11 } },
    series: [
      {
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['35%', '50%'],
        label: { show: false },
        data: tierDistribution.map((d) => ({ name: d.name, value: d.value, itemStyle: { color: d.color } })),
      },
    ],
  };

  const countryOption = {
    grid: { top: 20, right: 30, bottom: 20, left: 100, containLabel: true },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } } },
    yAxis: {
      type: 'category',
      data: countryDistribution.map((d) => d.name).reverse(),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { fontSize: 11 },
    },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [
      {
        type: 'bar',
        data: countryDistribution.map((d) => d.value).reverse(),
        barWidth: 14,
        itemStyle: { color: '#3370ff', borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: 'right', fontSize: 11, color: '#4e5969' },
      },
    ],
  };

  const histogramData = Array.from({ length: 10 }, (_, i) => {
    const center = (i + 1) * 2;
    return { range: `${center - 2}-${center}%`, count: Math.floor(300 * Math.exp(-Math.pow(i - 4, 2) / 8)) };
  });

  const histogramOption = {
    grid: { top: 20, right: 20, bottom: 40, left: 40, containLabel: true },
    xAxis: {
      type: 'category',
      data: histogramData.map((d) => d.range),
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 10, rotate: 30 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    tooltip: { trigger: 'axis' },
    series: [
      {
        type: 'bar',
        data: histogramData.map((d) => d.count),
        barWidth: '70%',
        itemStyle: { color: '#3370ff', borderRadius: [3, 3, 0, 0] },
      },
    ],
  };

  const total = tierDistribution.reduce((s, d) => s + d.value, 0);
  const high = tierDistribution.filter((d) => d.name === 'S 级' || d.name === 'A 级').reduce((s, d) => s + d.value, 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="总达人数" value={total} delta={5} icon={Users} iconBg="#e0e7ff" iconColor="#4f46e5" />
        <KpiCard label="S/A 占比" value={formatPercent((high / total) * 100, 1)} delta={2} icon={Trophy} iconBg="#fef3c7" iconColor="#ca8a04" />
        <KpiCard label="30d 活跃" value={188} delta={12} icon={Activity} iconBg="#d1fae5" iconColor="#16a34a" />
        <KpiCard label="覆盖国家" value={countryDistribution.length} delta={0} icon={Globe} iconBg="#cffafe" iconColor="#0891b2" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <ChartCard title="Tier 分布">
          <EChart option={tierOption} height={280} />
        </ChartCard>
        <ChartCard title="国家分布 Top 9" className="lg:col-span-2">
          <EChart option={countryOption} height={280} />
        </ChartCard>
      </div>

      <ChartCard title="互动率分布直方图">
        <EChart option={histogramOption} height={240} />
      </ChartCard>

      <div className="card">
        <div className="px-4 py-3 border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">头部达人 Top 20</h3>
        </div>
        <DataTable columns={creatorColumns} data={topCreators} rowKey={(r) => r.handle} />
      </div>
    </div>
  );
}
