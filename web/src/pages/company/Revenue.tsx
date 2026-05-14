import { Wallet, TrendingUp, Percent, Trophy } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { monthlyRevenue, profitMargin, topSkus } from '@/mock/company';
import { chartPalette } from '@/lib/colors';
import { formatCurrency, formatPercent } from '@/lib/format';

type SkuRow = typeof topSkus[number];

const skuColumns: Column<SkuRow>[] = [
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
  { key: 'sku', header: 'SKU', cell: (r) => <span className="text-xs font-mono">{r.sku}</span> },
  { key: 'name', header: '产品名称', cell: (r) => <span className="text-xs">{r.name}</span> },
  { key: 'category', header: '类目', cell: (r) => <Pill tone="info">{r.category}</Pill> },
  { key: 'revenue', header: '营收', align: 'right', cell: (r) => <span className="text-xs num font-medium">{formatCurrency(r.revenue)}</span> },
  { key: 'qty', header: '销量', align: 'right', cell: (r) => <span className="text-xs num">{r.qty.toLocaleString()}</span> },
  {
    key: 'margin', header: '利润率', align: 'right',
    cell: (r) => (
      <div className="flex items-center justify-end gap-2">
        <div className="w-16 h-1 rounded-full bg-soft overflow-hidden">
          <div className="h-full bg-good rounded-full" style={{ width: `${r.margin}%` }} />
        </div>
        <span className="text-xs num">{formatPercent(r.margin, 0)}</span>
      </div>
    ),
  },
];

export default function Revenue() {
  const stackOption = {
    grid: { top: 36, right: 20, bottom: 40, left: 50, containLabel: true },
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
      barWidth: 28,
      data: monthlyRevenue.series[i],
      itemStyle: { color: chartPalette.categorical[i] },
    })),
  };

  const profitOption = {
    grid: { top: 20, right: 20, bottom: 30, left: 40, containLabel: true },
    tooltip: { trigger: 'axis', formatter: '{b}: {c}%' },
    xAxis: {
      type: 'category',
      data: profitMargin.months,
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      min: 25,
      max: 40,
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 11, formatter: '{value}%' },
    },
    series: [
      {
        type: 'line',
        data: profitMargin.values,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: '#16a34a', width: 2 },
        itemStyle: { color: '#16a34a' },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(22,163,74,0.2)' },
              { offset: 1, color: 'rgba(22,163,74,0)' },
            ],
          },
        },
      },
    ],
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="本月营收" value="¥ 2.12M" delta={12} icon={Wallet} iconBg="#e0e7ff" iconColor="#4f46e5" />
        <KpiCard label="同比增长" value="+18%" delta={18} icon={TrendingUp} iconBg="#d1fae5" iconColor="#16a34a" />
        <KpiCard label="利润率" value="35.1%" delta={3} icon={Percent} iconBg="#fef3c7" iconColor="#ca8a04" />
        <KpiCard label="Top 1 SKU" value="¥ 487K" delta={9} icon={Trophy} iconBg="#fed7aa" iconColor="#ea580c" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <ChartCard title="月度营收 · 按部门堆叠" className="lg:col-span-2">
          <EChart option={stackOption} height={300} />
        </ChartCard>
        <ChartCard title="利润率趋势">
          <EChart option={profitOption} height={300} />
        </ChartCard>
      </div>

      <div className="card">
        <div className="px-4 py-3 border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">Top 10 SKU 营收排行</h3>
        </div>
        <DataTable columns={skuColumns} data={topSkus} rowKey={(r) => r.sku} />
      </div>
    </div>
  );
}
