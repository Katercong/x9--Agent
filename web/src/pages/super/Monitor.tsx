import { Activity, CheckCircle2, AlertTriangle, Database, Cpu, HardDrive, Gauge as GaugeIcon } from 'lucide-react';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { AsyncState } from '@/components/states/States';
import { useVersion, useResources, useLlmProviders, useSystemMetrics } from '@/hooks/useApi';
import { formatCompact } from '@/lib/format';

function gauge(value: number, color: string, label: string, formatter: string | ((v: number) => string) = '{value}%') {
  return {
    series: [{
      type: 'gauge', startAngle: 200, endAngle: -20, radius: '90%', center: ['50%', '60%'],
      progress: { show: true, width: 14, itemStyle: { color } },
      pointer: { show: false },
      axisLine: { lineStyle: { width: 14, color: [[1, '#f0f1f5']] } },
      axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, anchor: { show: false },
      data: [{ value, name: label }],
      detail: { valueAnimation: true, formatter, fontSize: 22, fontWeight: 700, color: '#1f2329', offsetCenter: [0, '-5%'] },
      title: { offsetCenter: [0, '30%'], color: '#86909c', fontSize: 12 },
    }],
  };
}

function formatBytes(value?: number | null) {
  const n = Number(value || 0);
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1);
  return `${(n / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export default function Monitor() {
  const version = useVersion();
  const resources = useResources();
  const providers = useLlmProviders();
  const metrics = useSystemMetrics();

  const loading = version.isLoading || resources.isLoading || metrics.isLoading;
  const error = version.error || resources.error || metrics.error;

  const provs = providers.data?.items ?? [];
  const activeProvs = provs.filter((p) => p.is_active === 1);
  const errorProvs = provs.filter((p) => p.last_test_status === 'error');
  const m = metrics.data;
  const dbRows = Number(m?.database?.row_count ?? 0);
  const dbGauge = dbRows > 0 ? Math.min(100, Math.max(6, Math.round(Math.log10(dbRows + 1) * 18))) : 0;
  const cpuValue = typeof m?.cpu_percent === 'number' ? m.cpu_percent : 0;
  const diskPercent = Number(m?.disk?.percent ?? 0);
  const requests = m?.requests_24h ?? [];

  const cards = [
    { name: 'API 服务', status: 'healthy', value: `v${version.data?.server_version ?? '-'}`, detail: `${version.data?.api_version ?? ''} · ${resources.data?.total ?? 0} 资源` },
    { name: '数据库行数', status: 'healthy', value: formatCompact(dbRows), detail: `${m?.database?.tables?.length ?? 0} 张表纳入监控` },
    { name: 'LLM Provider', status: errorProvs.length > 0 ? 'warn' : 'healthy', value: `${activeProvs.length}/${provs.length}`, detail: errorProvs.length > 0 ? `${errorProvs.length} 个异常` : '全部正常' },
    { name: '24h 请求', status: (m?.error_count_24h ?? 0) > 0 ? 'warn' : 'healthy', value: formatCompact(m?.request_total_24h ?? 0), detail: `平均 ${m?.avg_duration_ms_24h ?? 0}ms · 5xx ${m?.error_count_24h ?? 0}` },
  ];

  const requestOption = {
    grid: { top: 30, right: 20, bottom: 30, left: 50, containLabel: true },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category', data: requests.map((item) => item.hour),
      axisLine: { lineStyle: { color: '#e5e6eb' } }, axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 10, interval: 2 },
    },
    yAxis: {
      type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false }, axisTick: { show: false },
    },
    series: [{
      type: 'line', data: requests.map((item) => item.count), smooth: true, symbol: 'none',
      lineStyle: { color: '#3370ff', width: 2 },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: 'rgba(51,112,255,0.18)' }, { offset: 1, color: 'rgba(51,112,255,0)' }] } },
    }],
  };

  return (
    <AsyncState loading={loading} error={error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {cards.map((s) => {
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

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="card card-body">
            <div className="flex items-center gap-2 mb-2">
              <Cpu size={14} className="text-muted" />
              <span className="text-xs text-muted">CPU</span>
            </div>
            <EChart option={gauge(cpuValue, '#3370ff', typeof m?.cpu_percent === 'number' ? 'CPU' : '未取到')} height={180} />
          </div>
          <div className="card card-body">
            <div className="flex items-center gap-2 mb-2">
              <Database size={14} className="text-muted" />
              <span className="text-xs text-muted">数据库行数</span>
            </div>
            <EChart option={gauge(dbGauge, '#f5a623', '行数', () => formatCompact(dbRows))} height={180} />
          </div>
          <div className="card card-body">
            <div className="flex items-center gap-2 mb-2">
              <HardDrive size={14} className="text-muted" />
              <span className="text-xs text-muted">磁盘</span>
            </div>
            <EChart option={gauge(diskPercent, '#16a34a', `${formatBytes(m?.disk?.free)} 可用`)} height={180} />
          </div>
        </div>

        <ChartCard title="近 24h 请求量" extra={<span className="flex items-center gap-1.5"><Activity size={12} />真实日志</span>}>
          <EChart option={requestOption} height={260} />
        </ChartCard>

        <div className="card card-body">
          <div className="flex items-center gap-2 mb-3">
            <GaugeIcon size={14} className="text-muted" />
            <h3 className="text-sm font-semibold text-gray-800">数据库表行数</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {(m?.database?.tables ?? []).map((row) => (
              <div key={row.name} className="rounded border border-line px-3 py-2">
                <div className="text-xxs text-muted truncate">{row.name}</div>
                <div className="num text-sm font-semibold text-gray-800 mt-1">{formatCompact(row.count)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AsyncState>
  );
}
