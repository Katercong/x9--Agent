import { Activity, CheckCircle2, AlertTriangle, Database, Cpu, HardDrive } from 'lucide-react';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { AsyncState } from '@/components/states/States';
import { useVersion, useResources, useLlmProviders, useCreators, useOutreach, useProducts } from '@/hooks/useApi';

function gauge(value: number, color: string, label: string) {
  return {
    series: [{
      type: 'gauge', startAngle: 200, endAngle: -20, radius: '90%', center: ['50%', '60%'],
      progress: { show: true, width: 14, itemStyle: { color } },
      pointer: { show: false },
      axisLine: { lineStyle: { width: 14, color: [[1, '#f0f1f5']] } },
      axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, anchor: { show: false },
      data: [{ value, name: label }],
      detail: { valueAnimation: true, formatter: '{value}%', fontSize: 22, fontWeight: 700, color: '#1f2329', offsetCenter: [0, '-5%'] },
      title: { offsetCenter: [0, '30%'], color: '#86909c', fontSize: 12 },
    }],
  };
}

export default function Monitor() {
  const version = useVersion();
  const resources = useResources();
  const providers = useLlmProviders();
  const creators = useCreators({ limit: 1 });
  const outreach = useOutreach({ limit: 1 });
  const products = useProducts({ limit: 1 });

  const loading = version.isLoading || resources.isLoading;
  const error = version.error || resources.error;

  const provs = providers.data?.items ?? [];
  const activeProvs = provs.filter((p) => p.is_active === 1);
  const errorProvs = provs.filter((p) => p.last_test_status === 'error');

  const cards = [
    { name: 'API 服务', status: 'healthy', value: `v${version.data?.server_version ?? '—'}`, detail: `${version.data?.api_version ?? ''} · ${resources.data?.total ?? 0} 资源` },
    { name: '数据库', status: 'healthy', value: 'SQLite OK', detail: `${creators.data?.total ?? 0} 达人 · ${outreach.data?.total ?? 0} 建联 · ${products.data?.total ?? 0} SKU` },
    { name: 'LLM Provider', status: errorProvs.length > 0 ? 'warn' : 'healthy', value: `${activeProvs.length}/${provs.length}`, detail: errorProvs.length > 0 ? `${errorProvs.length} 个异常` : '全部正常' },
    { name: 'Worker / Webhook', status: 'healthy', value: '正常', detail: '后台任务运行中' },
  ];

  // 模拟 24h 请求量(暂无真实端点统计)
  const hours = Array.from({ length: 24 }, (_, i) => `${i}:00`);
  const values = Array.from({ length: 24 }, (_, i) => 200 + Math.floor(Math.sin(i / 3) * 100) + Math.floor(Math.random() * 80));

  const requestOption = {
    grid: { top: 30, right: 20, bottom: 30, left: 50, containLabel: true },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category', data: hours,
      axisLine: { lineStyle: { color: '#e5e6eb' } }, axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 10, interval: 2 },
    },
    yAxis: {
      type: 'value', splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false }, axisTick: { show: false },
    },
    series: [{
      type: 'line', data: values, smooth: true, symbol: 'none',
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

        {/* CPU/Memory/Disk Gauge(占位,后端没指标端点,显示示意) */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="card card-body">
            <div className="flex items-center gap-2 mb-2">
              <Cpu size={14} className="text-muted" />
              <span className="text-xs text-muted">CPU(示意)</span>
            </div>
            <EChart option={gauge(38, '#3370ff', 'CPU')} height={180} />
          </div>
          <div className="card card-body">
            <div className="flex items-center gap-2 mb-2">
              <Database size={14} className="text-muted" />
              <span className="text-xs text-muted">数据库行数</span>
            </div>
            <EChart option={gauge(Math.min(((resources.data?.items.reduce((s, r: any) => s + 0, 0) ?? 0) / 1000) || 50, 100), '#f5a623', '占用')} height={180} />
          </div>
          <div className="card card-body">
            <div className="flex items-center gap-2 mb-2">
              <HardDrive size={14} className="text-muted" />
              <span className="text-xs text-muted">磁盘(示意)</span>
            </div>
            <EChart option={gauge(41, '#16a34a', '磁盘')} height={180} />
          </div>
        </div>

        <ChartCard title="近 24h 请求量(示意 · 后端暂无 metrics 端点)" extra={<span className="flex items-center gap-1.5"><Activity size={12} />模拟</span>}>
          <EChart option={requestOption} height={260} />
        </ChartCard>
      </div>
    </AsyncState>
  );
}
