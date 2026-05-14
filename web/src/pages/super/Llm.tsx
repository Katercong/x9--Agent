import { Plus, Zap, CheckCircle2, AlertTriangle, HelpCircle, Star } from 'lucide-react';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { llmProviders, llmFeatures, tokenUsage } from '@/mock/super';

type Feature = typeof llmFeatures[number];

const featureColumns: Column<Feature>[] = [
  { key: 'feature', header: '功能', cell: (r) => <span className="text-xs font-mono">{r.feature}</span> },
  { key: 'label', header: '说明', cell: (r) => <span className="text-xs">{r.label}</span> },
  { key: 'provider', header: 'Provider', cell: (r) => <Pill tone="info">{r.provider}</Pill> },
  { key: 'model', header: 'Model', cell: (r) => <span className="text-xs font-mono text-muted">{r.model}</span> },
  { key: 'action', header: '', align: 'right', cell: () => <button className="chip text-xxs">改绑定</button> },
];

const testIcon: Record<string, { icon: typeof CheckCircle2; color: string }> = {
  ok: { icon: CheckCircle2, color: '#16a34a' },
  warn: { icon: AlertTriangle, color: '#f5a623' },
  unknown: { icon: HelpCircle, color: '#86909c' },
};

export default function Llm() {
  const usageOption = {
    grid: { top: 30, right: 20, bottom: 30, left: 50, containLabel: true },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: tokenUsage.days,
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 11, formatter: (v: number) => (v / 1000).toFixed(0) + 'K' },
    },
    series: [
      {
        name: '输入 token',
        type: 'bar',
        stack: 't',
        data: tokenUsage.input,
        barWidth: 18,
        itemStyle: { color: '#3370ff' },
      },
      {
        name: '输出 token',
        type: 'bar',
        stack: 't',
        data: tokenUsage.output,
        itemStyle: { color: '#94b1ff' },
      },
    ],
  };

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">Provider 管理</h3>
          <span className="text-xxs text-muted">{llmProviders.length} 个 Provider</span>
          <div className="ml-auto">
            <button className="btn btn-primary"><Plus size={12} />新增 Provider</button>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-4">
          {llmProviders.map((p) => {
            const meta = testIcon[p.testStatus] || testIcon.unknown;
            const TestIcon = meta.icon;
            return (
              <div
                key={p.code}
                className={`border rounded-lg p-4 ${
                  p.active ? 'border-brand-500 bg-brand-50/30' : 'border-line'
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="w-9 h-9 rounded-md bg-soft flex items-center justify-center">
                      <Zap size={16} className="text-brand-500" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold">{p.name}</span>
                        {p.active && (
                          <span className="pill bg-amber-100 text-amber-700 text-xxs">
                            <Star size={9} className="inline mr-0.5" />当前活跃
                          </span>
                        )}
                      </div>
                      <div className="text-xxs text-muted font-mono mt-0.5">{p.code} · {p.type}</div>
                    </div>
                  </div>
                  <TestIcon size={16} style={{ color: meta.color }} />
                </div>
                <div className="space-y-1.5 text-xs">
                  <div className="flex gap-2">
                    <span className="text-muted w-16">Base URL</span>
                    <span className="font-mono truncate">{p.baseUrl}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="text-muted w-16">默认模型</span>
                    <span className="font-mono">{p.model}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="text-muted w-16">API Key</span>
                    <span className="font-mono text-muted">{p.keyMask}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-3 pt-3 border-t border-line">
                  <button className="chip text-xxs">编辑</button>
                  <button className="chip text-xxs">测试</button>
                  {!p.active && <button className="chip text-xxs text-brand-500">激活</button>}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="card">
        <div className="px-4 py-3 border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">Feature 绑定</h3>
        </div>
        <DataTable columns={featureColumns} data={llmFeatures} rowKey={(r) => r.feature} />
      </div>

      <ChartCard title="近 14 天 Token 用量">
        <EChart option={usageOption} height={240} />
      </ChartCard>
    </div>
  );
}
