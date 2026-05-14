import { Trophy } from 'lucide-react';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { departments, radarMetrics } from '@/mock/company';
import { chartPalette } from '@/lib/colors';
import { formatCurrency, formatPercent } from '@/lib/format';

type Dept = typeof departments[number];

// 归一化每个指标用于雷达图
const maxVals = {
  creators: Math.max(...departments.map((d) => d.creators)),
  conv: Math.max(...departments.map((d) => d.conv)),
  revenue: Math.max(...departments.map((d) => d.revenue)),
  video: Math.max(...departments.map((d) => d.video)),
  roi: Math.max(...departments.map((d) => d.roi)),
  aov: 100,
};

const deptColumns: Column<Dept>[] = [
  {
    key: 'rank', header: '#', align: 'center',
    cell: (_, i) => (
      <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xxs font-bold ${
        i < 3 ? 'bg-amber-100 text-amber-700' : 'bg-soft text-muted'
      }`}>
        {i + 1}
      </span>
    ),
    width: '50px',
  },
  { key: 'name', header: '部门', cell: (r) => <span className="text-xs font-medium">{r.name}</span> },
  { key: 'creators', header: '达人', align: 'right', cell: (r) => <span className="text-xs num">{r.creators}</span> },
  {
    key: 'conv', header: '转化率', align: 'right',
    cell: (r) => (
      <div className="flex items-center justify-end gap-2">
        <div className="w-16 h-1 rounded-full bg-soft overflow-hidden">
          <div className="h-full bg-brand-500 rounded-full" style={{ width: `${(r.conv / maxVals.conv) * 100}%` }} />
        </div>
        <span className="text-xs num">{formatPercent(r.conv, 1)}</span>
      </div>
    ),
  },
  { key: 'revenue', header: '营收(万)', align: 'right', cell: (r) => <span className="text-xs num font-medium">{r.revenue}</span> },
  { key: 'video', header: '视频数', align: 'right', cell: (r) => <span className="text-xs num">{r.video}</span> },
  {
    key: 'roi', header: 'ROI', align: 'right',
    cell: (r) => <span className={`text-xs num font-medium ${r.roi >= 3 ? 'text-good' : 'text-gray-700'}`}>{r.roi.toFixed(1)}x</span>,
  },
];

export default function Departments() {
  const radarOption = {
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, textStyle: { fontSize: 11 } },
    tooltip: {},
    radar: {
      indicator: radarMetrics.map((name) => ({ name, max: 100 })),
      shape: 'polygon',
      splitArea: { areaStyle: { color: ['rgba(247,247,249,0.4)', 'rgba(247,247,249,0.8)'] } },
      axisName: { color: '#4e5969', fontSize: 11 },
      splitLine: { lineStyle: { color: '#e5e6eb' } },
      axisLine: { lineStyle: { color: '#e5e6eb' } },
    },
    series: [
      {
        type: 'radar',
        symbol: 'circle',
        symbolSize: 4,
        data: departments.map((d, i) => ({
          name: d.name,
          value: [
            (d.creators / maxVals.creators) * 100,
            (d.conv / maxVals.conv) * 100,
            (d.revenue / maxVals.revenue) * 100,
            (d.video / maxVals.video) * 100,
            (d.roi / maxVals.roi) * 100,
            70 + i * 4,
          ],
          areaStyle: { opacity: 0.18, color: chartPalette.categorical[i] },
          lineStyle: { width: 2, color: chartPalette.categorical[i] },
          itemStyle: { color: chartPalette.categorical[i] },
        })),
      },
    ],
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <ChartCard title="部门多维绩效雷达" className="lg:col-span-2">
          <EChart option={radarOption} height={380} />
        </ChartCard>
        <div className="card">
          <div className="px-4 py-3 border-b border-line flex items-center gap-2">
            <Trophy size={16} className="text-amber-500" />
            <h3 className="text-sm font-semibold text-gray-800">Top 3 部门</h3>
          </div>
          <div className="p-3 space-y-2">
            {departments.slice(0, 3).map((d, i) => (
              <div key={d.name} className="border border-line rounded p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium">{d.name}</span>
                  <span className={`pill ${i === 0 ? 'bg-amber-100 text-amber-700' : 'pill-muted'}`}>#{i + 1}</span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-xxs">
                  <div>
                    <div className="text-muted">营收</div>
                    <div className="text-sm num font-semibold mt-0.5">{d.revenue}万</div>
                  </div>
                  <div>
                    <div className="text-muted">转化</div>
                    <div className="text-sm num font-semibold mt-0.5">{formatPercent(d.conv, 1)}</div>
                  </div>
                  <div>
                    <div className="text-muted">ROI</div>
                    <div className="text-sm num font-semibold mt-0.5">{d.roi}x</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="px-4 py-3 border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">部门绩效详表</h3>
        </div>
        <DataTable columns={deptColumns} data={departments} rowKey={(r) => r.name} />
      </div>
    </div>
  );
}
