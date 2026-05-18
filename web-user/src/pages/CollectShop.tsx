import { useMemo, useState } from 'react';
import { Store, Users, ScanLine, DollarSign, Tag } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useSourceStats, useObservationsFeed, type ObservationItem } from '@/api/collector';
import { ACCENTS, CollectHeader, Reveal, dailyAreaOption, num } from './collectShared';
import { CreatorDetailDrawer } from './CreatorDetailDrawer';

const A = ACCENTS.shop;

export default function CollectShop() {
  const stats = useSourceStats();
  const feed = useObservationsFeed({ source: 'tiktok_shop', limit: 300 });
  const [openHandle, setOpenHandle] = useState<string | null>(null);

  const shop = stats.data?.sources?.tiktok_shop;
  const items = feed.data?.items ?? [];

  const derived = useMemo(() => {
    const handles = new Set(items.map((i) => i.handle).filter(Boolean));
    const withGmv = items.filter((i) => i.shop?.gmv_raw).length;
    const cat = new Map<string, number>();
    for (const it of items) {
      const c = it.shop?.category_text;
      if (c) cat.set(c, (cat.get(c) ?? 0) + 1);
    }
    const categories = [...cat.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
    return { creators: handles.size, withGmv, categories, topCategory: categories[0]?.[0] ?? '—' };
  }, [items]);

  const funnel = shop?.funnel ?? { shop_list_seen: 0, shop_profile_collected: 0 };

  const funnelOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c}' },
    series: [
      {
        type: 'funnel',
        left: '6%', right: '6%', top: 10, bottom: 10,
        minSize: '30%', gap: 4,
        label: { show: true, position: 'inside', color: '#fff', fontSize: 12, fontWeight: 600 },
        data: [
          { value: Math.max(funnel.shop_list_seen, funnel.shop_profile_collected, 1), name: `列表发现 ${funnel.shop_list_seen}`, itemStyle: { color: '#7a1733' } },
          { value: Math.max(funnel.shop_profile_collected, 0.0001), name: `详情采集 ${funnel.shop_profile_collected}`, itemStyle: { color: A.key } },
        ],
      },
    ],
  };

  const categoryOption = {
    grid: { top: 10, right: 24, bottom: 20, left: 90, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.07)' } }, axisLabel: { fontSize: 11, color: 'rgba(255,255,255,0.55)' } },
    yAxis: {
      type: 'category',
      data: derived.categories.map((c) => c[0]).reverse(),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { fontSize: 11, color: 'rgba(255,255,255,0.7)' },
    },
    series: [
      {
        type: 'bar',
        data: derived.categories.map((c) => c[1]).reverse(),
        barWidth: 14,
        itemStyle: { color: A.key, borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: 'right', fontSize: 11, color: 'rgba(255,255,255,0.7)' },
      },
    ],
  };

  const columns: Column<ObservationItem>[] = [
    {
      key: 'creator',
      header: '达人',
      cell: (r) => (
        <button
          type="button"
          onClick={() => setOpenHandle(r.handle)}
          className="flex items-center gap-2.5 text-left group"
        >
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0" style={{ background: A.key }}>
            {(r.handle[0] || '?').toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="text-xs font-medium text-text truncate group-hover:underline" style={{ textDecorationColor: A.key }}>@{r.handle}</div>
            <div className="text-xxs text-muted truncate">{r.display_name || '—'}</div>
          </div>
        </button>
      ),
      width: '220px',
    },
    { key: 'followers', header: '粉丝', align: 'right', cell: (r) => <span className="text-xs num text-text">{r.followers_raw || '—'}</span> },
    { key: 'gmv', header: 'GMV', align: 'right', cell: (r) => <span className="text-xs num font-medium" style={{ color: r.shop?.gmv_raw ? A.key : 'rgb(var(--muted))' }}>{r.shop?.gmv_raw || '—'}</span> },
    { key: 'gpm', header: 'GPM', align: 'right', cell: (r) => <span className="text-xs num text-text">{r.shop?.gpm_raw || '—'}</span> },
    { key: 'comm', header: '佣金', align: 'right', cell: (r) => <span className="text-xs num text-text">{r.shop?.avg_commission_rate_raw || '—'}</span> },
    { key: 'cat', header: '类目', cell: (r) => <span className="text-xs text-text">{r.shop?.category_text || '—'}</span> },
    {
      key: 'stage',
      header: '阶段',
      cell: (r) =>
        r.shop?.lead_status === 'shop_profile_collected' ? <Pill tone="good">详情已采</Pill> : <Pill tone="muted">仅列表</Pill>,
    },
  ];

  const drawerRows = openHandle ? items.filter((i) => i.handle === openHandle) : [];

  return (
    <div className="space-y-4">
      <CollectHeader accent={A} icon={Store} title="采集 · TikTok Shop" subtitle="affiliate-us 全自动达人采集 · 点击达人查看详情" />

      <AsyncState
        loading={stats.isLoading || feed.isLoading}
        error={stats.error || feed.error}
        isEmpty={!feed.isLoading && items.length === 0}
        emptyMessage="还没有 TikTok Shop 采集数据"
        height={420}
      >
        <Reveal i={1}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard label="采集达人" value={num(derived.creators)} icon={Users} iconBg={A.dim} iconColor={A.key} />
            <KpiCard label="详情已采" value={num(funnel.shop_profile_collected)} icon={ScanLine} iconBg="rgba(6,182,212,0.14)" iconColor="#06b6d4" />
            <KpiCard label="含 GMV" value={num(derived.withGmv)} icon={DollarSign} iconBg="rgba(16,185,129,0.14)" iconColor="#10b981" />
            <KpiCard label="主类目" value={derived.topCategory} icon={Tag} iconBg="rgba(245,158,11,0.14)" iconColor="#f59e0b" />
          </div>
        </Reveal>

        <Reveal i={2}>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-4">
            <ChartCard title="列表 → 详情 漏斗">
              <EChart option={funnelOption} height={260} />
            </ChartCard>
            <ChartCard title="近 7 天采集量" className="lg:col-span-2">
              <EChart option={dailyAreaOption(shop?.daily ?? [], A.key)} height={260} />
            </ChartCard>
          </div>
        </Reveal>

        <Reveal i={3}>
          <div className="mt-4">
            <ChartCard title="类目分布 Top 8">
              <EChart option={categoryOption} height={Math.max(220, derived.categories.length * 34 + 40)} />
            </ChartCard>
          </div>
        </Reveal>

        <Reveal i={4}>
          <div className="card mt-4">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-text">采集明细 · {num(items.length)} 条观测</h3>
              <span className="text-xxs text-muted">点击达人进入详情</span>
            </div>
            <div className="p-2">
              <DataTable columns={columns} data={items} rowKey={(r) => r.id} emptyText="还没有 TikTok Shop 采集数据" />
            </div>
          </div>
        </Reveal>
      </AsyncState>

      <CreatorDetailDrawer handle={openHandle} rows={drawerRows} onClose={() => setOpenHandle(null)} />
    </div>
  );
}
