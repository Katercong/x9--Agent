import { useMemo } from 'react';
import { Store, Users, ScanLine, DollarSign, Tag, Radio } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useSourceStats, useObservationsFeed, useRunProgress, type ObservationItem } from '@/api/collector';
import { ACCENTS, CollectHeader, Reveal, dailyAreaOption, num } from './collectShared';

const A = ACCENTS.shop;

function pickRunRow(rp: unknown): Record<string, unknown> | null {
  if (!rp || typeof rp !== 'object') return null;
  const obj = rp as Record<string, unknown>;
  if (Array.isArray(obj.items) && obj.items.length) return obj.items[0] as Record<string, unknown>;
  if (obj.progress && typeof obj.progress === 'object') return obj.progress as Record<string, unknown>;
  if ('step' in obj || 'running' in obj || 'current_handle' in obj) return obj;
  return null;
}

export default function CollectShop() {
  const stats = useSourceStats();
  const feed = useObservationsFeed({ source: 'tiktok_shop', limit: 300 });
  const run = useRunProgress();

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
    // Prefer the contacts block from /source-stats (counts from `creators`
    // table, accurate even when raw_json was wiped).
    const fromContacts = shop?.contacts
      ? { creators: shop.contacts.today_total, withGmv: shop.contacts.today_total }
      : null;
    return {
      creators: fromContacts ? fromContacts.creators : handles.size,
      withGmv: fromContacts ? fromContacts.withGmv : withGmv,
      categories,
      topCategory: categories[0]?.[0] ?? '—',
    };
  }, [items, shop]);

  const funnel = shop?.funnel ?? { shop_list_seen: 0, shop_profile_collected: 0 };

  const funnelOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c}' },
    series: [
      {
        type: 'funnel',
        left: '6%',
        right: '6%',
        top: 10,
        bottom: 10,
        minSize: '28%',
        gap: 4,
        label: { show: true, position: 'inside', color: '#fff', fontSize: 12, fontWeight: 600 },
        data: [
          { value: Math.max(funnel.shop_list_seen, funnel.shop_profile_collected, 1), name: `列表发现 ${funnel.shop_list_seen}`, itemStyle: { color: A.ink } },
          { value: Math.max(funnel.shop_profile_collected, 0.0001), name: `详情采集 ${funnel.shop_profile_collected}`, itemStyle: { color: A.key } },
        ],
      },
    ],
  };

  const categoryOption = {
    grid: { top: 10, right: 24, bottom: 20, left: 90, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } }, axisLabel: { fontSize: 11, color: '#86909c' } },
    yAxis: {
      type: 'category',
      data: derived.categories.map((c) => c[0]).reverse(),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { fontSize: 11, color: '#4e5969' },
    },
    series: [
      {
        type: 'bar',
        data: derived.categories.map((c) => c[1]).reverse(),
        barWidth: 14,
        itemStyle: { color: A.key, borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: 'right', fontSize: 11, color: '#4e5969' },
      },
    ],
  };

  const runRow = pickRunRow(run.data);
  const running = !!(runRow && (runRow.running === true || runRow.running === 1));
  const runPanel = (
    <div className="flex items-center gap-2 text-xs">
      <span
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-medium"
        style={{ background: running ? '#dcfce7' : '#f3f4f6', color: running ? '#15803d' : '#6b7280' }}
      >
        <Radio size={12} className={running ? 'animate-pulse' : ''} />
        {running ? '采集运行中' : '空闲'}
      </span>
      {runRow?.current_handle ? <span className="text-muted">@{String(runRow.current_handle)}</span> : null}
    </div>
  );

  const columns: Column<ObservationItem>[] = [
    {
      key: 'creator',
      header: '达人',
      cell: (r) => (
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0" style={{ background: A.ink }}>
            {(r.handle[0] || '?').toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="text-xs font-medium text-gray-800 truncate">@{r.handle}</div>
            <div className="text-xxs text-muted truncate">{r.display_name || '—'}</div>
          </div>
        </div>
      ),
      width: '220px',
    },
    { key: 'followers', header: '粉丝', align: 'right', cell: (r) => <span className="text-xs num">{r.followers_raw || '—'}</span> },
    { key: 'gmv', header: 'GMV', align: 'right', cell: (r) => <span className="text-xs num font-medium" style={{ color: r.shop?.gmv_raw ? A.key : '#86909c' }}>{r.shop?.gmv_raw || '—'}</span> },
    { key: 'gpm', header: 'GPM', align: 'right', cell: (r) => <span className="text-xs num">{r.shop?.gpm_raw || '—'}</span> },
    { key: 'comm', header: '佣金', align: 'right', cell: (r) => <span className="text-xs num">{r.shop?.avg_commission_rate_raw || '—'}</span> },
    { key: 'cat', header: '类目', cell: (r) => <span className="text-xs">{r.shop?.category_text || '—'}</span> },
    {
      key: 'invite',
      header: '邀约 / 收藏',
      cell: (r) => (
        <div className="flex items-center gap-1">
          {r.shop?.invite_status ? <Pill tone="info">{r.shop.invite_status}</Pill> : null}
          {r.shop?.save_status ? <Pill tone="muted">{r.shop.save_status}</Pill> : null}
          {!r.shop?.invite_status && !r.shop?.save_status ? <span className="text-xxs text-muted">—</span> : null}
        </div>
      ),
    },
    {
      key: 'stage',
      header: '阶段',
      cell: (r) =>
        r.shop?.lead_status === 'shop_profile_collected' ? (
          <Pill tone="good">详情已采</Pill>
        ) : (
          <Pill tone="muted">仅列表</Pill>
        ),
    },
  ];

  return (
    <div className="space-y-4">
      <CollectHeader
        accent={A}
        icon={Store}
        title="采集 · TikTok Shop"
        subtitle="affiliate-us 全自动达人采集 · 列表与详情两阶段"
        right={runPanel}
      />

      <AsyncState
        loading={stats.isLoading || feed.isLoading}
        error={stats.error || feed.error}
        isEmpty={!feed.isLoading && items.length === 0}
        emptyMessage="还没有 TikTok Shop 采集数据"
        height={420}
      >
        <Reveal i={1}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard label="采集达人" value={num(derived.creators)} icon={Users} iconBg={A.soft} iconColor={A.key} />
            <KpiCard label="详情已采" value={num(funnel.shop_profile_collected)} icon={ScanLine} iconBg="#e0e7ff" iconColor="#4f46e5" />
            <KpiCard label="含 GMV" value={num(derived.withGmv)} icon={DollarSign} iconBg="#dcfce7" iconColor="#16a34a" />
            <KpiCard label="主类目" value={derived.topCategory} icon={Tag} iconBg="#fef3c7" iconColor="#ca8a04" />
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
            <div className="px-4 py-3 border-b border-line flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-800">采集明细 · {num(items.length)} 条观测</h3>
              <span className="text-xxs text-muted">实时来自 /observations-feed</span>
            </div>
            <DataTable columns={columns} data={items} rowKey={(r) => r.id} emptyText="还没有 TikTok Shop 采集数据" />
          </div>
        </Reveal>
      </AsyncState>
    </div>
  );
}
