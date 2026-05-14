import { Activity, AlertTriangle, Users, Zap } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { apiStats, topUsers, requestVolume } from '@/mock/super';
import { formatPercent } from '@/lib/format';
import { chartPalette } from '@/lib/colors';

type Stat = typeof apiStats[number];
type TopU = typeof topUsers[number];

const statColumns: Column<Stat>[] = [
  { key: 'endpoint', header: '端点', cell: (r) => <span className="text-xs font-mono">{r.endpoint}</span> },
  {
    key: 'count', header: '调用量', align: 'right',
    cell: (r) => (
      <div className="flex items-center justify-end gap-2">
        <div className="w-20 h-1 rounded-full bg-soft overflow-hidden">
          <div className="h-full bg-brand-500 rounded-full" style={{ width: `${(r.count / 12840) * 100}%` }} />
        </div>
        <span className="text-xs num">{r.count.toLocaleString()}</span>
      </div>
    ),
  },
  { key: 'avg', header: '平均耗时', align: 'right', cell: (r) => <span className={`text-xs num ${r.avgMs > 500 ? 'text-warn' : 'text-good'}`}>{r.avgMs} ms</span> },
  {
    key: 'err', header: '错误率', align: 'right',
    cell: (r) => (
      <Pill tone={r.errorRate > 0.02 ? 'bad' : r.errorRate > 0.005 ? 'warn' : 'good'}>
        {formatPercent(r.errorRate * 100, 2)}
      </Pill>
    ),
  },
];

const userColumns: Column<TopU>[] = [
  { key: 'user', header: '调用方', cell: (r) => <span className="text-xs font-medium">{r.user}</span> },
  {
    key: 'calls', header: '调用量', align: 'right',
    cell: (r) => (
      <div className="flex items-center justify-end gap-2">
        <div className="w-20 h-1 rounded-full bg-soft overflow-hidden">
          <div className="h-full bg-brand-500 rounded-full" style={{ width: `${r.percent}%` }} />
        </div>
        <span className="text-xs num">{r.calls.toLocaleString()}</span>
      </div>
    ),
  },
  { key: 'pct', header: '占比', align: 'right', cell: (r) => <span className="text-xs num font-medium">{r.percent}%</span> },
];

export default function ApiStats() {
  const trendOption = {
    grid: { top: 30, right: 20, bottom: 30, left: 50, containLabel: true },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: requestVolume.hours,
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 10, interval: 2 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: 'line',
        data: requestVolume.values,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#3370ff', width: 2 },
        areaStyle: {
          color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: 'rgba(51,112,255,0.18)' }, { offset: 1, color: 'rgba(51,112,255,0)' }] },
        },
      },
    ],
  };

  const userPieOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, textStyle: { fontSize: 11 } },
    series: [
      {
        type: 'pie',
        radius: ['50%', '70%'],
        center: ['50%', '42%'],
        label: { show: false },
        data: topUsers.map((u, i) => ({
          name: u.user,
          value: u.calls,
          itemStyle: { color: chartPalette.categorical[i] },
        })),
      },
    ],
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="24h 调用量" value="51.6K" delta={12} icon={Activity} iconBg="#dbeafe" iconColor="#2563eb" />
        <KpiCard label="平均响应" value="142ms" delta={-8} icon={Zap} iconBg="#d1fae5" iconColor="#16a34a" />
        <KpiCard label="错误率" value="0.32%" delta={-15} icon={AlertTriangle} iconBg="#fef3c7" iconColor="#ca8a04" />
        <KpiCard label="活跃调用方" value={topUsers.length} delta={0} icon={Users} iconBg="#ede9fe" iconColor="#7c3aed" />
      </div>

      <ChartCard title="24h 调用趋势">
        <EChart option={trendOption} height={220} />
      </ChartCard>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-3">
        <div className="card lg:col-span-3">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">端点性能排行</h3>
          </div>
          <DataTable columns={statColumns} data={apiStats} rowKey={(r) => r.endpoint} />
        </div>
        <div className="card lg:col-span-2">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">Top 调用方</h3>
          </div>
          <DataTable columns={userColumns} data={topUsers} rowKey={(r) => r.user} />
          <EChart option={userPieOption} height={200} />
        </div>
      </div>
    </div>
  );
}
