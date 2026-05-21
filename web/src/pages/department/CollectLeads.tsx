import { useMemo } from 'react';
import { Radar, Search, Mail, Link2, CalendarDays } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { maskEmail } from '@/lib/format';
import { useSourceStats, useObservationsFeed, type ObservationItem } from '@/api/collector';
import { ACCENTS, CollectHeader, Reveal, dailyAreaOption, num } from './collectShared';

const A = ACCENTS.leads;

export default function CollectLeads() {
  const stats = useSourceStats();
  const feed = useObservationsFeed({ source: 'x9_leads', limit: 300 });

  const bucket = stats.data?.sources?.x9_leads;
  const items = feed.data?.items ?? [];

  // Prefer the contacts block from /source-stats (counts from `creators`
  // table — accurate even if raw_json is missing for some observations).
  // Fall back to client-side counting only when the backend hasn't been
  // updated yet.
  const d = useMemo(() => {
    if (bucket?.contacts) {
      const c = bucket.contacts;
      return {
        withEmail: c.today_with_email,
        withLinks: c.today_with_links,
        neither: Math.max(0, c.today_total - c.today_with_email - c.today_with_links),
      };
    }
    const withEmail = items.filter((i) => i.lead?.email).length;
    const withLinks = items.filter((i) => (i.lead?.external_links?.length ?? 0) > 0).length;
    const neither = items.filter((i) => !i.lead?.email && !(i.lead?.external_links?.length ?? 0)).length;
    return { withEmail, withLinks, neither };
  }, [items, bucket]);

  const coverageOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, textStyle: { fontSize: 11 } },
    series: [
      {
        type: 'pie',
        radius: ['46%', '70%'],
        center: ['50%', '44%'],
        label: { show: false },
        data: [
          { value: d.withEmail, name: '有邮箱', itemStyle: { color: A.key } },
          { value: d.withLinks, name: '仅外链', itemStyle: { color: '#34d399' } },
          { value: d.neither, name: '无直接联系', itemStyle: { color: '#cbd5e1' } },
        ],
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
    {
      key: 'email',
      header: '邮箱',
      cell: (r) => (r.lead?.email ? <span className="text-xs num">{maskEmail(r.lead.email)}</span> : <span className="text-xxs text-muted">—</span>),
    },
    {
      key: 'links',
      header: '外链',
      cell: (r) =>
        (r.lead?.external_links?.length ?? 0) > 0 ? (
          <Pill tone="good">{r.lead!.external_links.length} 个</Pill>
        ) : (
          <span className="text-xxs text-muted">—</span>
        ),
    },
    { key: 'kw', header: '关键词', cell: (r) => <span className="text-xs">{r.search_keyword || '—'}</span> },
    {
      key: 'video',
      header: '来源视频',
      cell: (r) =>
        r.lead?.source_video_url ? (
          <a className="text-xs text-brand-500 hover:underline" href={r.lead.source_video_url} target="_blank" rel="noreferrer">
            打开
          </a>
        ) : (
          <span className="text-xxs text-muted">—</span>
        ),
    },
    { key: 'status', header: '状态', cell: (r) => <span className="text-xs">{r.lead?.current_status || '—'}</span> },
  ];

  return (
    <div className="space-y-4">
      <CollectHeader accent={A} icon={Radar} title="采集 · X9 线索" subtitle="www.tiktok.com 全自动卡片流 · 仅保留可联系线索" />

      <AsyncState
        loading={stats.isLoading || feed.isLoading}
        error={stats.error || feed.error}
        isEmpty={!feed.isLoading && items.length === 0}
        emptyMessage="还没有 X9 线索数据"
        height={400}
      >
        <Reveal i={1}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard label="线索总数" value={num(bucket?.total ?? items.length)} icon={Search} iconBg={A.soft} iconColor={A.key} />
            <KpiCard label="今日新增" value={num(bucket?.today ?? 0)} icon={CalendarDays} iconBg="#cffafe" iconColor="#0891b2" />
            <KpiCard label="有邮箱" value={num(d.withEmail)} icon={Mail} iconBg="#d1fae5" iconColor="#16a34a" />
            <KpiCard label="有外链" value={num(d.withLinks)} icon={Link2} iconBg="#ede9fe" iconColor="#7c3aed" />
          </div>
        </Reveal>

        <Reveal i={2}>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-4">
            <ChartCard title="联系方式覆盖">
              <EChart option={coverageOption} height={260} />
            </ChartCard>
            <ChartCard title="近 7 天线索量" className="lg:col-span-2">
              <EChart option={dailyAreaOption(bucket?.daily ?? [], A.key)} height={260} />
            </ChartCard>
          </div>
        </Reveal>

        <Reveal i={3}>
          <div className="card mt-4">
            <div className="px-4 py-3 border-b border-line flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-800">线索明细 · {num(items.length)} 条</h3>
              <span className="text-xxs text-muted">实时来自 /observations-feed</span>
            </div>
            <DataTable columns={columns} data={items} rowKey={(r) => r.id} emptyText="还没有 X9 线索数据" />
          </div>
        </Reveal>
      </AsyncState>
    </div>
  );
}
