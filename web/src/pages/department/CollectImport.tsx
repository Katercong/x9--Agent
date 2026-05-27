import { useMemo, useState } from 'react';
import { FileSpreadsheet, Upload, CalendarDays, Globe, Gauge } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { PaginationControls } from '@/components/PaginationControls';
import { AsyncState } from '@/components/states/States';
import { useSourceStats, useObservationsFeed, type ObservationItem } from '@/api/collector';
import { ACCENTS, CollectHeader, Reveal, dailyAreaOption, num } from './collectShared';

const A = ACCENTS.import;
const PAGE_SIZE = 10;

function tally(items: ObservationItem[], pick: (i: ObservationItem) => string | null | undefined) {
  const m = new Map<string, number>();
  for (const it of items) {
    const v = pick(it);
    if (v) m.set(v, (m.get(v) ?? 0) + 1);
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

export default function CollectImport() {
  const stats = useSourceStats();
  const [page, setPage] = useState(0);
  const feed = useObservationsFeed({ source: 'table_import', limit: PAGE_SIZE, offset: page * PAGE_SIZE });

  const bucket = stats.data?.sources?.table_import;
  const items = feed.data?.items ?? [];

  const d = useMemo(() => {
    const countries = tally(items, (i) => i.import_meta?.country);
    const tiers = tally(items, (i) => i.import_meta?.tier);
    const qs = items.map((i) => i.import_meta?.quality_score).filter((x): x is number => typeof x === 'number');
    const avgQuality = qs.length ? qs.reduce((a, b) => a + b, 0) / qs.length : null;
    return { countries, tiers, avgQuality, countryCount: countries.length };
  }, [items]);

  const tierOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, textStyle: { fontSize: 11 } },
    series: [
      {
        type: 'pie',
        radius: ['46%', '70%'],
        center: ['50%', '44%'],
        label: { show: false },
        data: d.tiers.map(([name, value], idx) => ({
          name,
          value,
          itemStyle: { color: ['#f59e0b', '#fbbf24', '#fcd34d', '#fde68a', '#fef3c7'][idx % 5] },
        })),
      },
    ],
  };

  const countryOption = {
    grid: { top: 10, right: 24, bottom: 20, left: 70, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } }, axisLabel: { fontSize: 11, color: '#86909c' } },
    yAxis: {
      type: 'category',
      data: d.countries.slice(0, 8).map((c) => c[0]).reverse(),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { fontSize: 11, color: '#4e5969' },
    },
    series: [
      {
        type: 'bar',
        data: d.countries.slice(0, 8).map((c) => c[1]).reverse(),
        barWidth: 14,
        itemStyle: { color: A.key, borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: 'right', fontSize: 11, color: '#4e5969' },
      },
    ],
  };

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
      width: '210px',
    },
    { key: 'followers', header: '粉丝', align: 'right', cell: (r) => <span className="text-xs num">{r.followers_raw || '—'}</span> },
    { key: 'country', header: '国家', cell: (r) => <span className="text-xs">{r.import_meta?.country || '—'}</span> },
    { key: 'tier', header: 'Tier', cell: (r) => (r.import_meta?.tier ? <Pill tone="warn">{r.import_meta.tier}</Pill> : <span className="text-xxs text-muted">—</span>) },
    { key: 'lang', header: '语言', cell: (r) => <span className="text-xs">{r.import_meta?.language || '—'}</span> },
    {
      key: 'eng',
      header: '互动率',
      align: 'right',
      cell: (r) => <span className="text-xs num">{typeof r.import_meta?.engagement_rate === 'number' ? r.import_meta.engagement_rate + '%' : '—'}</span>,
    },
    {
      key: 'q',
      header: '质量分',
      align: 'right',
      cell: (r) => <span className="text-xs num">{typeof r.import_meta?.quality_score === 'number' ? r.import_meta.quality_score : '—'}</span>,
    },
  ];

  return (
    <div className="space-y-4">
      <CollectHeader accent={A} icon={FileSpreadsheet} title="采集 · 表格导入" subtitle="CSV / XLSX 批量导入达人 · 中英文表头自动映射" />

      <AsyncState
        loading={stats.isLoading || feed.isLoading}
        error={stats.error || feed.error}
        isEmpty={!feed.isLoading && items.length === 0}
        emptyMessage="还没有表格导入数据"
        height={400}
      >
        <Reveal i={1}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard label="导入总数" value={num(bucket?.total ?? items.length)} icon={Upload} iconBg={A.soft} iconColor={A.key} />
            <KpiCard label="今日导入" value={num(bucket?.today ?? 0)} icon={CalendarDays} iconBg="#cffafe" iconColor="#0891b2" />
            <KpiCard label="覆盖国家" value={num(d.countryCount)} icon={Globe} iconBg="#e0e7ff" iconColor="#4f46e5" />
            <KpiCard label="平均质量分" value={d.avgQuality === null ? '—' : d.avgQuality.toFixed(1)} icon={Gauge} iconBg="#fef3c7" iconColor="#ca8a04" />
          </div>
        </Reveal>

        <Reveal i={2}>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-4">
            <ChartCard title="Tier 分布">
              <EChart option={tierOption} height={260} />
            </ChartCard>
            <ChartCard title="近 7 天导入量" className="lg:col-span-2">
              <EChart option={dailyAreaOption(bucket?.daily ?? [], A.key)} height={260} />
            </ChartCard>
          </div>
        </Reveal>

        <Reveal i={3}>
          <div className="mt-4">
            <ChartCard title="国家分布 Top 8">
              <EChart option={countryOption} height={Math.max(220, Math.min(d.countries.length, 8) * 34 + 40)} />
            </ChartCard>
          </div>
        </Reveal>

        <Reveal i={4}>
          <div className="card mt-4">
            <div className="px-4 py-3 border-b border-line flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-800">导入明细 · {num(feed.data?.total ?? items.length)} 条</h3>
              <span className="text-xxs text-muted">实时来自 /observations-feed</span>
            </div>
            <DataTable columns={columns} data={items} rowKey={(r) => r.id} emptyText="还没有表格导入数据" />
            <PaginationControls
              page={page}
              pageSize={PAGE_SIZE}
              total={feed.data?.total ?? 0}
              currentCount={items.length}
              loading={feed.isFetching}
              onPageChange={setPage}
            />
          </div>
        </Reveal>
      </AsyncState>
    </div>
  );
}
