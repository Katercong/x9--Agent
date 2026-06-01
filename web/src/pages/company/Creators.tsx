import { useMemo, useState } from 'react';
import { Users, Trophy, Activity, Globe } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { PaginationControls } from '@/components/PaginationControls';
import { TierPill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useCreators } from '@/hooks/useApi';
import { groupByTier, groupByCountry } from '@/lib/derive';
import { formatCompact } from '@/lib/format';
import { countHeadTierCreators, isActiveCreator } from '@/lib/creatorMetrics';
import type { Creator } from '@/api/types';

const PAGE_SIZE = 10;
const KPI_FETCH_LIMIT = 10000;

export default function Creators() {
  const [page, setPage] = useState(0);
  const tableParams = useMemo(
    () => ({ limit: PAGE_SIZE, offset: page * PAGE_SIZE, order_by: 'followers', desc: true }),
    [page],
  );
  const kpiParams = useMemo(
    () => ({ limit: KPI_FETCH_LIMIT, offset: 0, order_by: 'followers', desc: true }),
    [],
  );
  const { data, isLoading, error } = useCreators(tableParams);
  const { data: kpiData } = useCreators(kpiParams);
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const kpiItems = kpiData?.items ?? items;

  const tierDist = groupByTier(kpiItems);
  const countryDist = groupByCountry(kpiItems, 9);
  const active = kpiItems.filter((c) => isActiveCreator(c.current_status)).length;
  const high = countHeadTierCreators(kpiItems);

  const topCreators = [...items]
    .filter((c) => c.followers !== null)
    .sort((a, b) => (b.followers || 0) - (a.followers || 0))
    .slice(0, PAGE_SIZE);

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
          <ChartCard title="当前页 Tier 分布">
            <EChart option={tierOption} height={280} />
          </ChartCard>
          <ChartCard title="当前页国家分布 Top 9" className="lg:col-span-2">
            <EChart option={countryOption} height={280} />
          </ChartCard>
        </div>

        <div className="card">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">头部达人 Top 10(按粉丝)</h3>
          </div>
          <DataTable columns={creatorColumns} data={topCreators} rowKey={(r) => r.id} />
          <PaginationControls
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            currentCount={items.length}
            loading={isLoading}
            onPageChange={setPage}
          />
        </div>
      </div>
    </AsyncState>
  );
}
