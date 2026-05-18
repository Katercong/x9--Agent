import { Users, Trophy, Activity, Globe } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { TierPill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useCreators } from '@/hooks/useApi';
import { groupByTier, groupByCountry } from '@/lib/derive';
import { formatCompact } from '@/lib/format';
import type { Creator } from '@/api/types';

export default function Creators() {
  const { data, isLoading, error } = useCreators({ limit: 1000 });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  const tierDist = groupByTier(items);
  const countryDist = groupByCountry(items, 9);
  const active = items.filter((c) => c.current_status && !['prospect', 'dropped'].includes(c.current_status)).length;
  const high = tierDist.filter((d) => d.name === 'S 级' || d.name === 'A 级').reduce((s, d) => s + d.value, 0);

  const topCreators = [...items]
    .filter((c) => c.followers !== null)
    .sort((a, b) => (b.followers || 0) - (a.followers || 0))
    .slice(0, 20);

  const creatorColumns: Column<Creator>[] = [
    {
      key: 'rank', header: '#', align: 'center',
      cell: (_, i) => (
        <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xxs font-bold ${
          i < 3 ? 'bg-amber-100 text-amber-700' : 'bg-soft text-muted'
        }`}>{i + 1}</span>
      ),
      width: '50px',
    },
    {
      key: 'creator', header: '达人',
      cell: (r) => (
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center text-white text-xs font-medium">
            {r.handle[0]?.toUpperCase() || '?'}
          </div>
          <span className="text-xs font-medium">@{r.handle}</span>
        </div>
      ),
    },
    { key: 'tier', header: 'Tier', cell: (r) => r.tier ? <TierPill tier={r.tier} /> : <span className="text-xxs text-muted">—</span> },
    { key: 'followers', header: '粉丝', align: 'right', cell: (r) => <span className="text-xs num">{formatCompact(r.followers || 0)}</span> },
    { key: 'country', header: '国家', cell: (r) => <span className="text-xs">{r.country || '—'}</span> },
    { key: 'status', header: '状态', cell: (r) => <span className="text-xs">{r.current_status || '—'}</span> },
    { key: 'owner', header: 'BD', cell: (r) => <span className="text-xs">{r.owner_bd || '—'}</span> },
  ];

  const tierOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', right: 10, top: 'center', icon: 'circle', itemWidth: 8, textStyle: { fontSize: 11 } },
    series: [{
      type: 'pie', radius: ['45%', '70%'], center: ['35%', '50%'],
      label: { show: false },
      data: tierDist.map((d) => ({ name: d.name, value: d.value, itemStyle: { color: d.color } })),
    }],
  };

  const countryOption = {
    grid: { top: 20, right: 30, bottom: 20, left: 100, containLabel: true },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } } },
    yAxis: {
      type: 'category', data: countryDist.map((d) => d.name).reverse(),
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { fontSize: 11 },
    },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [{
      type: 'bar', data: countryDist.map((d) => d.value).reverse(),
      barWidth: 14, itemStyle: { color: '#3370ff', borderRadius: [0, 3, 3, 0] },
      label: { show: true, position: 'right', fontSize: 11, color: '#4e5969' },
    }],
  };

  return (
    <AsyncState loading={isLoading} error={error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard label="总达人数" value={total} icon={Users} iconBg="#e0e7ff" iconColor="#4f46e5" />
          <KpiCard label="S+A 头部" value={high} icon={Trophy} iconBg="#fef3c7" iconColor="#ca8a04" />
          <KpiCard label="活跃达人" value={active} icon={Activity} iconBg="#d1fae5" iconColor="#16a34a" />
          <KpiCard label="覆盖国家" value={countryDist.length} icon={Globe} iconBg="#cffafe" iconColor="#0891b2" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <ChartCard title="Tier 分布">
            <EChart option={tierOption} height={280} />
          </ChartCard>
          <ChartCard title="国家分布 Top 9" className="lg:col-span-2">
            <EChart option={countryOption} height={280} />
          </ChartCard>
        </div>

        <div className="card">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">头部达人 Top 20(按粉丝)</h3>
          </div>
          <DataTable columns={creatorColumns} data={topCreators} rowKey={(r) => r.id} />
        </div>
      </div>
    </AsyncState>
  );
}
