import { useMemo } from 'react';
import { ListChecks, Radar, Search, Mail, Link2, CalendarDays } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { maskEmail } from '@/lib/format';
import { useSourceStats, useObservationsFeed, type ObservationItem } from '@/api/collector';
import { ACCENTS, CHART_AXIS, CollectHeader, Reveal, dailyAreaOption, num } from './collectShared';

const A = ACCENTS.leads;

export default function CollectLeads() {
  const stats = useSourceStats();
  const feed = useObservationsFeed({ source: 'x9_leads', limit: 300 });

  const bucket = stats.data?.sources?.x9_leads;
  const items = feed.data?.items ?? [];

  const hasContact = (i: ObservationItem) =>
    Boolean(i.lead?.email) ||
    (i.lead?.contact_methods?.length ?? 0) > 0 ||
    (i.lead?.external_links?.length ?? 0) > 0;

  const d = useMemo(() => {
    const withEmail = items.filter((i) => i.lead?.email).length;
    const withLinks = items.filter((i) => (i.lead?.external_links?.length ?? 0) > 0).length;
    const withContact = items.filter(hasContact).length;
    const neither = items.length - withContact;
    return { withEmail, withLinks, withContact, neither };
  }, [items]);

  const pendingItems = useMemo(
    () => items.filter((item) => {
      const status = item.lead?.current_status || '';
      return status === 'prospect' || status === 'raw_only_no_contact' || !status;
    }).slice(0, 8),
    [items],
  );
  const pendingTotal = items.filter((item) => {
    const status = item.lead?.current_status || '';
    return status === 'prospect' || status === 'raw_only_no_contact' || !status;
  }).length;

  const statusText = (value: string | null | undefined) => {
    if (value === 'raw_only_no_contact') return '未入库：无联系方式';
    if (value === 'dropped') return '已过滤';
    if (value === 'skipped') return '已跳过';
    return value || '—';
  };

  const contactCell = (r: ObservationItem) => {
    const methods = r.lead?.contact_methods ?? [];
    if (r.lead?.email) {
      return <span className="text-xs num text-text">{maskEmail(r.lead.email)}</span>;
    }
    if (methods.length > 0) {
      return (
        <div className="flex items-center gap-1.5 flex-wrap">
          {methods.slice(0, 2).map((m) => <Pill key={`${m.type}-${m.value}`} tone="good">{m.label}</Pill>)}
          {methods.length > 2 && <span className="text-xxs text-muted">+{methods.length - 2}</span>}
        </div>
      );
    }
    if ((r.lead?.external_links?.length ?? 0) > 0) {
      return <Pill tone="good">外链 {r.lead!.external_links.length}</Pill>;
    }
    return <span className="text-xxs text-muted">无联系方式</span>;
  };

  const coverageOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, textStyle: { fontSize: 11, color: CHART_AXIS } },
    series: [
      {
        type: 'pie',
        radius: ['46%', '70%'],
        center: ['50%', '44%'],
        label: { show: false },
        data: [
          { value: d.withEmail, name: '有邮箱', itemStyle: { color: A.key } },
          { value: Math.max(d.withContact - d.withEmail, 0), name: '其他联系', itemStyle: { color: '#34d399' } },
          { value: d.neither, name: '无直接联系', itemStyle: { color: '#475569' } },
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
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0" style={{ background: A.key }}>
            {(r.handle[0] || '?').toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="text-xs font-medium text-text truncate">@{r.handle}</div>
            <div className="text-xxs text-muted truncate">{r.display_name || '—'}</div>
          </div>
        </div>
      ),
      width: '210px',
    },
    {
      key: 'followers',
      header: '粉丝',
      align: 'right',
      cell: (r) => (
        <span className="text-xs num text-text">
          {r.followers_raw || '—'}
        </span>
      ),
    },
    {
      key: 'email',
      header: '联系方式',
      cell: contactCell,
    },
    {
      key: 'links',
      header: '外链',
      cell: (r) =>
        (r.lead?.external_links?.length ?? 0) > 0 ? <Pill tone="good">{r.lead!.external_links.length} 个</Pill> : <span className="text-xxs text-muted">—</span>,
    },
    { key: 'kw', header: '关键词', cell: (r) => <span className="text-xs text-text">{r.search_keyword || '—'}</span> },
    {
      key: 'video',
      header: '来源视频',
      cell: (r) =>
        r.lead?.source_video_url ? (
          <a className="text-xs text-accent hover:underline" href={r.lead.source_video_url} target="_blank" rel="noreferrer">打开</a>
        ) : (
          <span className="text-xxs text-muted">—</span>
        ),
    },
    { key: 'status', header: '状态', cell: (r) => <span className="text-xs text-text">{statusText(r.lead?.current_status)}</span> },
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
            <KpiCard label="raw 总回传" value={num(bucket?.total ?? items.length)} icon={Search} iconBg={A.dim} iconColor={A.key} />
            <KpiCard label="今日回传" value={num(bucket?.today ?? 0)} icon={CalendarDays} iconBg="rgba(6,182,212,0.14)" iconColor="#06b6d4" />
            <KpiCard label="有联系方式" value={num(d.withContact)} icon={Mail} iconBg="rgba(16,185,129,0.14)" iconColor="#10b981" />
            <KpiCard label="有外链" value={num(d.withLinks)} icon={Link2} iconBg="rgba(139,92,246,0.16)" iconColor="#a78bfa" />
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
                  <div className="text-xxs text-muted">等待补充联系方式、确认状态或推进建联</div>
                </div>
              </div>
              <span className="rounded-full bg-elev2 px-2.5 py-1 text-xs font-semibold text-text">{num(pendingTotal)} 条</span>
            </div>
            {pendingItems.length === 0 ? (
              <div className="rounded-md border border-dashed border-border py-4 text-center text-xs text-muted">当前没有待处理线索</div>
            ) : (
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
                {pendingItems.map((item) => (
                  <div key={item.id} className="rounded-md border border-border bg-elev2 px-3 py-2">
                    <div className="truncate text-xs font-semibold text-text">@{item.handle}</div>
                    <div className="mt-1 truncate text-xxs text-muted">{item.display_name || item.search_keyword || '未命名线索'}</div>
                    <div className="mt-2 flex items-center justify-between gap-2 text-xxs text-muted">
                      <span>{item.followers_raw || '粉丝未知'}</span>
                      <Pill tone={hasContact(item) ? 'good' : 'warn'}>{hasContact(item) ? '待建联' : '待补联系方式'}</Pill>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Reveal>

        <Reveal i={3}>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-4">
            <ChartCard title="联系方式覆盖">
              <EChart option={coverageOption} height={260} />
            </ChartCard>
            <ChartCard title="近 7 天 raw 回传量" className="lg:col-span-2">
              <EChart option={dailyAreaOption(bucket?.daily ?? [], A.key)} height={260} />
            </ChartCard>
          </div>
        </Reveal>

        <Reveal i={4}>
          <div className="card mt-4">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-text">raw 回传明细 · {num(items.length)} 条</h3>
              <span className="text-xxs text-muted">实时来自 /observations-feed</span>
            </div>
            <div className="p-2">
              <DataTable columns={columns} data={items} rowKey={(r) => r.id} emptyText="还没有 X9 线索数据" />
            </div>
          </div>
        </Reveal>
      </AsyncState>
    </div>
  );
}
