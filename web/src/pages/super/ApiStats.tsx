import { Activity, AlertTriangle, Users, Zap } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { AsyncState } from '@/components/states/States';
import { useResources, useNamedQueries } from '@/hooks/useApi';

interface EndpointRow {
  endpoint: string;
  desc: string;
  type: '资源' | '命名查询' | 'LLM' | '元信息';
}

export default function ApiStats() {
  const resources = useResources();
  const queries = useNamedQueries();

  const resList = resources.data?.items ?? [];
  const qList = queries.data?.items ?? [];

  // 构造端点清单(后端没有实时调用统计 metrics 端点,显示静态清单)
  const endpoints: EndpointRow[] = [
    ...resList.map((r) => ({
      endpoint: `/api/v1/data/${r.name}`,
      desc: r.description || r.table,
      type: '资源' as const,
    })),
    ...qList.map((q) => ({
      endpoint: q.url,
      desc: q.description,
      type: '命名查询' as const,
    })),
    { endpoint: '/api/v1/llm/complete', desc: '统一 LLM 调用入口', type: 'LLM' },
    { endpoint: '/api/v1/llm/providers', desc: 'LLM Provider 列表', type: 'LLM' },
    { endpoint: '/api/v1/version', desc: '服务版本信息', type: '元信息' },
    { endpoint: '/api/v1/resources', desc: '全部资源元信息', type: '元信息' },
  ];

  const columns: Column<EndpointRow>[] = [
    { key: 'endpoint', header: '端点', cell: (r) => <span className="text-xs font-mono">{r.endpoint}</span> },
    { key: 'desc', header: '说明', cell: (r) => <span className="text-xs">{r.desc || '—'}</span> },
    {
      key: 'type', header: '类型',
      cell: (r) => {
        const tone = r.type === '资源' ? 'good' : r.type === '命名查询' ? 'info' : r.type === 'LLM' ? 'warn' : 'muted';
        return <span className={`pill pill-${tone === 'good' ? 'info' : tone === 'info' ? 'good' : 'warn'}`}>{r.type}</span>;
      },
    },
  ];

  // 类型分布柱图
  const counts = {
    '资源': resList.length,
    '命名查询': qList.length,
    'LLM': 2,
    '元信息': 2,
  };
  const distOption = {
    grid: { top: 20, right: 30, bottom: 30, left: 60, containLabel: true },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } } },
    yAxis: { type: 'category', data: Object.keys(counts).reverse(), axisLine: { show: false }, axisTick: { show: false } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [{
      type: 'bar', data: Object.values(counts).reverse(),
      barWidth: 14, itemStyle: { color: '#3370ff', borderRadius: [0, 3, 3, 0] },
      label: { show: true, position: 'right', fontSize: 11, color: '#4e5969', formatter: '{c} 个' },
    }],
  };

  return (
    <AsyncState loading={resources.isLoading || queries.isLoading} error={resources.error || queries.error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard label="端点总数" value={endpoints.length} icon={Activity} iconBg="#dbeafe" iconColor="#2563eb" />
          <KpiCard label="资源端点" value={resList.length} icon={Zap} iconBg="#d1fae5" iconColor="#16a34a" />
          <KpiCard label="命名查询" value={qList.length} icon={Users} iconBg="#fef3c7" iconColor="#ca8a04" />
          <KpiCard label="实时统计" value="—" icon={AlertTriangle} iconBg="#fee2e2" iconColor="#dc2626" />
        </div>

        <ChartCard title="端点类型分布">
          <EChart option={distOption} height={220} />
        </ChartCard>

        <div className="card">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">全量 API 端点清单</h3>
            <div className="text-xxs text-muted mt-0.5">注:调用量/耗时/错误率统计需后端 metrics 端点(当前未提供)</div>
          </div>
          <DataTable columns={columns} data={endpoints} rowKey={(r) => r.endpoint} compact />
        </div>
      </div>
    </AsyncState>
  );
}
