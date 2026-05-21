import { TrendingUp, Hash, RefreshCw, ArrowUp } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { AsyncState, Empty } from '@/components/states/States';
import { useKeywordsDashboard } from '@/hooks/useApi';
import { shortRelative, formatPercent } from '@/lib/format';
import type { KeywordRow } from '@/api/types';

export default function HotKeywords() {
  const { data, isLoading, error } = useKeywordsDashboard();
  const d = data || {};

  const total = (d as any).total ?? 0;
  const new24 = (d as any).new_24h ?? 0;
  const pending = (d as any).pending_classify ?? 0;
  const lastAt = (d as any).last_captured_at;
  const topGrowth: KeywordRow[] = (d as any).top_growth || [];
  const topVolume: KeywordRow[] = (d as any).top_volume || [];
  const items: KeywordRow[] = (d as any).items || [];

  const cols: Column<KeywordRow>[] = [
    { key: 'kw', header: '关键词', cell: (r) => <div className="flex items-center gap-1.5"><Hash size={12} className="text-accent" /><span className="text-xs font-medium">{r.keyword}</span></div> },
    { key: 'vol', header: '搜索量', align: 'right', cell: (r) => <span className="text-xs num">{r.search_volume?.toLocaleString() ?? '—'}</span> },
    {
      key: 'growth', header: '增长', align: 'right',
      cell: (r) => {
        const g = r.growth_rate;
        if (g === null || g === undefined) return <span className="text-xxs text-muted">—</span>;
        const pct = (g * 100);
        return (
          <span className={`text-xs num font-medium ${pct > 0 ? 'text-good' : pct < 0 ? 'text-bad' : 'text-muted'}`}>
            {pct > 0 ? '↑' : pct < 0 ? '↓' : '—'} {formatPercent(Math.abs(pct), 0)}
          </span>
        );
      },
    },
    { key: 'rank', header: '排名', align: 'right', cell: (r) => <span className="text-xs num">{r.rank_position ?? '—'}</span> },
    { key: 'category', header: '类目', cell: (r) => r.category ? <span className="pill pill-muted">{r.category}</span> : <span className="text-xxs text-muted">—</span> },
  ];

  const growthOption = topGrowth.length > 0
    ? {
        grid: { top: 20, right: 30, bottom: 30, left: 90, containLabel: true },
        xAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(38,47,64,0.5)', type: 'dashed' } } },
        yAxis: { type: 'category', data: topGrowth.slice(0, 8).map((r) => r.keyword).reverse(), axisLine: { show: false }, axisTick: { show: false } },
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        series: [{
          type: 'bar',
          data: topGrowth.slice(0, 8).map((r) => (r.growth_rate || 0) * 100).reverse(),
          barWidth: 16, itemStyle: { color: '#22c55e', borderRadius: [0, 3, 3, 0] },
          label: { show: true, position: 'right', fontSize: 11, color: '#8691a2', formatter: (p: any) => `${p.value.toFixed(0)}%` },
        }],
      }
    : null;

  const volumeOption = topVolume.length > 0
    ? {
        grid: { top: 20, right: 30, bottom: 30, left: 90, containLabel: true },
        xAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(38,47,64,0.5)', type: 'dashed' } } },
        yAxis: { type: 'category', data: topVolume.slice(0, 8).map((r) => r.keyword).reverse(), axisLine: { show: false }, axisTick: { show: false } },
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        series: [{
          type: 'bar', data: topVolume.slice(0, 8).map((r) => r.search_volume || 0).reverse(),
          barWidth: 16, itemStyle: { color: '#06b6d4', borderRadius: [0, 3, 3, 0] },
          label: { show: true, position: 'right', fontSize: 11, color: '#8691a2' },
        }],
      }
    : null;

  return (
    <AsyncState loading={isLoading} error={error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard label="关键词总数" value={total} icon={Hash} iconBg="rgb(6 182 212 / 0.18)" iconColor="#22d3ee" />
          <KpiCard label="24h 新增" value={new24} icon={ArrowUp} iconBg="rgb(34 197 94 / 0.18)" iconColor="#4ade80" />
          <KpiCard label="待分类" value={pending} icon={TrendingUp} iconBg="rgb(245 158 11 / 0.18)" iconColor="#fbbf24" />
          <KpiCard label="最近抓取" value={lastAt ? shortRelative(lastAt) : '—'} icon={RefreshCw} iconBg="rgb(139 92 246 / 0.18)" iconColor="#a78bfa" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {growthOption ? (
            <ChartCard title="增长 Top 8">
              <EChart option={growthOption} height={260} />
            </ChartCard>
          ) : <div className="card"><div className="px-4 py-3 border-b border-border"><h3 className="text-sm font-semibold">增长 Top 8</h3></div><Empty height={200} /></div>}
          {volumeOption ? (
            <ChartCard title="搜索量 Top 8">
              <EChart option={volumeOption} height={260} />
            </ChartCard>
          ) : <div className="card"><div className="px-4 py-3 border-b border-border"><h3 className="text-sm font-semibold">搜索量 Top 8</h3></div><Empty height={200} /></div>}
        </div>

        <div className="card">
          <div className="px-4 py-3 border-b border-border">
            <h3 className="text-sm font-semibold">全量关键词列表</h3>
            <div className="text-xxs text-muted mt-0.5">数据源:/api/local/shared/keywords/dashboard</div>
          </div>
          {items.length === 0
            ? <Empty height={200} message="后端尚未返回 items 数组" />
            : <DataTable columns={cols} data={items} rowKey={(r) => r.id || r.keyword} />
          }
        </div>
      </div>
    </AsyncState>
  );
}
