import { Activity, AlertTriangle, CheckCircle2, Cpu, HardDrive, MemoryStick } from 'lucide-react';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { systemStatus, requestVolume, slowQueries, resourceGauge } from '@/mock/super';

type Status = typeof systemStatus[number];
type SlowQ = typeof slowQueries[number];

const statusColumns: Column<SlowQ>[] = [
  { key: 'endpoint', header: '端点', cell: (r) => <span className="text-xs font-mono">{r.endpoint}</span> },
  { key: 'avg', header: '平均', align: 'right', cell: (r) => <span className="text-xs num">{r.avgMs} ms</span> },
  { key: 'p99', header: 'P99', align: 'right', cell: (r) => <span className={`text-xs num ${r.p99Ms > 3000 ? 'text-bad' : 'text-gray-700'}`}>{r.p99Ms} ms</span> },
  { key: 'count', header: '次数', align: 'right', cell: (r) => <span className="text-xs num">{r.count}</span> },
];

function gauge(value: number, color: string, label: string) {
  return {
    series: [
      {
        type: 'gauge',
        startAngle: 200,
        endAngle: -20,
        radius: '90%',
        center: ['50%', '60%'],
        progress: { show: true, width: 14, itemStyle: { color } },
        pointer: { show: false },
        axisLine: { lineStyle: { width: 14, color: [[1, '#f0f1f5']] } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        anchor: { show: false },
        data: [{ value, name: label }],
        detail: { valueAnimation: true, formatter: '{value}%', fontSize: 22, fontWeight: 700, color: '#1f2329', offsetCenter: [0, '-5%'] },
        title: { offsetCenter: [0, '30%'], color: '#86909c', fontSize: 12 },
      },
    ],
  };
}

export default function Monitor() {
  const requestOption = {
    grid: { top: 30, right: 20, bottom: 40, left: 50, containLabel: true },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: requestVolume.hours,
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 10, interval: 2 },
    },
    yAxis: [
      {
        type: 'value',
        name: 'QPS',
        nameTextStyle: { color: '#86909c', fontSize: 11 },
        splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      {
        type: 'value',
        name: '错误',
        nameTextStyle: { color: '#86909c', fontSize: 11 },
        splitLine: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
      },
    ],
    series: [
      {
        name: '请求量',
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
      {
        name: '错误数',
        type: 'bar',
        yAxisIndex: 1,
        data: requestVolume.errors,
        barWidth: 6,
        itemStyle: { color: '#ef4444' },
      },
    ],
  };

  return (
    <div className="space-y-4">
      {/* 服务状态 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {systemStatus.map((s) => {
          const ok = s.status === 'healthy';
          return (
            <div key={s.name} className="card card-body">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-muted">{s.name}</span>
                {ok ? <CheckCircle2 size={14} className="text-good" /> : <AlertTriangle size={14} className="text-warn" />}
              </div>
              <div className="text-base font-semibold text-gray-800">{s.value}</div>
              <div className="text-xxs text-muted mt-1">{s.detail}</div>
            </div>
          );
        })}
      </div>

      {/* 资源仪表盘 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="card card-body">
          <div className="flex items-center gap-2 mb-2">
            <Cpu size={14} className="text-muted" />
            <span className="text-xs text-muted">CPU</span>
          </div>
          <EChart option={gauge(resourceGauge.cpu, '#3370ff', 'CPU 使用率')} height={180} />
        </div>
        <div className="card card-body">
          <div className="flex items-center gap-2 mb-2">
            <MemoryStick size={14} className="text-muted" />
            <span className="text-xs text-muted">内存</span>
          </div>
          <EChart option={gauge(resourceGauge.memory, '#f5a623', '内存使用率')} height={180} />
        </div>
        <div className="card card-body">
          <div className="flex items-center gap-2 mb-2">
            <HardDrive size={14} className="text-muted" />
            <span className="text-xs text-muted">磁盘</span>
          </div>
          <EChart option={gauge(resourceGauge.disk, '#16a34a', '磁盘使用率')} height={180} />
        </div>
      </div>

      <ChartCard title="近 24h 请求量 / 错误分布" extra={<span className="flex items-center gap-1.5"><Activity size={12} />实时</span>}>
        <EChart option={requestOption} height={260} />
      </ChartCard>

      <div className="card">
        <div className="px-4 py-3 border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">慢查询 Top 8</h3>
        </div>
        <DataTable columns={statusColumns} data={slowQueries} rowKey={(r) => r.endpoint} />
      </div>
    </div>
  );
}
