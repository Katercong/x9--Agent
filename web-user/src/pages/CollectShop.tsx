import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, ListChecks, Store, Users, ScanLine, DollarSign, Tag } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useSourceStats, useObservationsFeed, type ObservationItem } from '@/api/collector';
import { ACCENTS, CHART_AXIS, CHART_GRID, CHART_TEXT, CollectHeader, Reveal, dailyAreaOption, num } from './collectShared';
import { CreatorDetailDrawer } from './CreatorDetailDrawer';

const A = ACCENTS.shop;
const CATEGORY_LABEL_LIMIT = 28;

function cleanCategoryName(value: string | null | undefined): string {
  return String(value || '')
    .normalize('NFKC')
    .replace(/[\u200D\uFE0E\uFE0F]/g, '')
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function shortCategoryName(value: string): string {
  return value.length > CATEGORY_LABEL_LIMIT ? `${value.slice(0, CATEGORY_LABEL_LIMIT)}...` : value;
}
export default function CollectShop() {
  const stats = useSourceStats();
  const feed = useObservationsFeed({ source: 'tiktok_shop', limit: 300 });
  const [openHandle, setOpenHandle] = useState<string | null>(null);
  const [rawOpen, setRawOpen] = useState(false);

  const shop = stats.data?.sources?.tiktok_shop;
  const items = feed.data?.items ?? [];

  const derived = useMemo(() => {
    const handles = new Set(items.map((i) => i.handle).filter(Boolean));
    const withGmv = items.filter((i) => i.shop?.gmv_raw).length;
    const cat = new Map<string, number>();
    for (const it of items) {
      const c = cleanCategoryName(it.shop?.category_text);
      if (c) cat.set(c, (cat.get(c) ?? 0) + 1);
    }
    const categories = [...cat.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
    return { creators: handles.size, withGmv, categories, topCategory: categories[0]?.[0] ?? '—' };
  }, [items]);

  const funnel = shop?.funnel ?? { shop_list_seen: 0, shop_profile_collected: 0 };
  const pendingItems = useMemo(
    () => items.filter((item) => item.shop?.lead_status !== 'shop_profile_collected').slice(0, 8),
    [items],
  );
  const pendingTotal = items.filter((item) => item.shop?.lead_status !== 'shop_profile_collected').length;

  const funnelOption = {
    tooltip: { trigger: 'item', formatter: (p: any) => `${p.name}: ${p.data?.count ?? p.value}` },
    series: [
      {
        type: 'funnel',
        left: '10%', right: '10%', top: 18, bottom: 18,
        minSize: '36%', gap: 6,
        label: {
          show: true,
          position: 'inside',
          color: '#fff',
          fontSize: 12,
          lineHeight: 18,
          fontWeight: 700,
          formatter: (p: any) => `${p.name}\n${p.data?.count ?? p.value}`,
        },
        labelLine: { show: false },
        data: [
          { value: Math.max(funnel.shop_list_seen, funnel.shop_profile_collected, 1), count: funnel.shop_list_seen, name: '列表发现', itemStyle: { color: '#7a1733' } },
          { value: Math.max(funnel.shop_profile_collected, 0.0001), count: funnel.shop_profile_collected, name: '详情采集', itemStyle: { color: A.key } },
        ],
      },
    ],
  };

  const categoryOption = {
    grid: { top: 10, right: 24, bottom: 20, left: 90, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (params: any) => { const p = Array.isArray(params) ? params[0] : params; return String(p?.name ?? '') + ': ' + String(p?.value ?? 0); } },
    xAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: CHART_GRID } }, axisLabel: { fontSize: 11, color: CHART_AXIS } },
    yAxis: {
      type: 'category',
      data: derived.categories.map((c) => c[0]).reverse(),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { fontSize: 11, color: CHART_TEXT, fontWeight: 600, width: 190, overflow: 'truncate', formatter: shortCategoryName },
    },
    series: [
      {
        type: 'bar',
        data: derived.categories.map((c) => c[1]).reverse(),
        barWidth: 14,
        itemStyle: { color: A.key, borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: 'right', fontSize: 11, color: CHART_TEXT, fontWeight: 600 },
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
            <KpiCard label="去重达人" value={num(derived.creators)} icon={Users} iconBg={A.dim} iconColor={A.key} />
            <KpiCard label="详情已采" value={num(funnel.shop_profile_collected)} icon={ScanLine} iconBg="rgba(6,182,212,0.14)" iconColor="#06b6d4" />
            <KpiCard label="含 GMV" value={num(derived.withGmv)} icon={DollarSign} iconBg="rgba(16,185,129,0.14)" iconColor="#10b981" />
            <KpiCard label="主类目" value={derived.topCategory} icon={Tag} iconBg="rgba(245,158,11,0.14)" iconColor="#f59e0b" compact />
          </div>
        </Reveal>

        <Reveal i={2}>
          <div className="card card-body mt-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-md" style={{ background: A.dim, color: A.key }}>
                  <ListChecks size={16} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-text">待处理队列</h3>
                  <div className="text-xxs text-muted">列表发现后，等待进入详情或补齐 GMV / 类目</div>
                </div>
              </div>
              <span className="rounded-full bg-elev2 px-2.5 py-1 text-xs font-semibold text-text">{num(pendingTotal)} 条</span>
            </div>
            {pendingItems.length === 0 ? (
              <div className="rounded-md border border-dashed border-border py-4 text-center text-xs text-muted">当前没有待处理达人</div>
            ) : (
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
                {pendingItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setOpenHandle(item.handle)}
                    className="rounded-md border border-border bg-elev2 px-3 py-2 text-left transition-colors hover:border-accent"
                  >
                    <div className="truncate text-xs font-semibold text-text">@{item.handle}</div>
                    <div className="mt-1 truncate text-xxs text-muted">{item.display_name || item.search_keyword || '未命名达人'}</div>
                    <div className="mt-2 flex items-center justify-between gap-2 text-xxs text-muted">
                      <span>{item.followers_raw || '粉丝未知'}</span>
                      <Pill tone="muted">仅列表</Pill>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </Reveal>

        <Reveal i={3}>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-4">
            <ChartCard title="列表 → 详情 漏斗">
              <EChart option={funnelOption} height={260} />
            </ChartCard>
            <ChartCard title="近 7 天 raw 回传量" className="lg:col-span-2">
              <EChart option={dailyAreaOption(shop?.daily ?? [], A.key)} height={260} />
            </ChartCard>
          </div>
        </Reveal>

        <Reveal i={4}>
          <div className="mt-4">
            <ChartCard title="类目分布 Top 8">
              <EChart option={categoryOption} height={Math.max(220, derived.categories.length * 34 + 40)} />
            </ChartCard>
          </div>
        </Reveal>

        <Reveal i={5}>
          <div className="card mt-4">
            <button
              type="button"
              onClick={() => setRawOpen((value) => !value)}
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
            >
              <div>
                <h3 className="text-sm font-semibold text-text">raw 回传明细 · {num(items.length)} 条观测</h3>
                <div className="text-xxs text-muted">默认折叠，展开后可查看完整回传表</div>
              </div>
              <span className="inline-flex items-center gap-1 rounded-md border border-border bg-elev2 px-2.5 py-1 text-xs text-muted">
                {rawOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                {rawOpen ? '收起' : '展开明细'}
              </span>
            </button>
            {rawOpen && (
              <div className="border-t border-border p-2">
                <DataTable columns={columns} data={items} rowKey={(r) => r.id} emptyText="还没有 TikTok Shop 采集数据" />
              </div>
            )}
          </div>
        </Reveal>
      </AsyncState>

      <CreatorDetailDrawer handle={openHandle} rows={drawerRows} onClose={() => setOpenHandle(null)} />
    </div>
  );
}
