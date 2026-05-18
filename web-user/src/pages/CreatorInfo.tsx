import { useMemo, useState } from 'react';
import { Users, CalendarDays, ScanLine, Mail } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { AsyncState } from '@/components/states/States';
import { maskEmail, shortRelative } from '@/lib/format';
import { useSourceStats, useObservationsFeed, type ObservationItem, type SourceKey } from '@/api/collector';

const SOURCE_META: Record<SourceKey, { label: string; color: string }> = {
  tiktok_shop: { label: 'TikTok Shop', color: '#FE2C55' },
  x9_leads: { label: 'X9 线索', color: '#10b981' },
  table_import: { label: '表格导入', color: '#f59e0b' },
  other: { label: '其他', color: '#86909c' },
};

const TABS: Array<{ key: SourceKey | 'all'; label: string }> = [
  { key: 'all', label: '全部来源' },
  { key: 'tiktok_shop', label: 'TikTok Shop' },
  { key: 'x9_leads', label: 'X9 线索' },
  { key: 'table_import', label: '表格导入' },
];

function itemEmail(r: ObservationItem): string | null {
  return r.lead?.email || r.import_meta?.email || null;
}

function keyInfo(r: ObservationItem): string {
  if (r.shop) {
    const stage = r.shop.lead_status === 'shop_profile_collected' ? '详情已采' : '仅列表';
    return `GMV ${r.shop.gmv_raw || '—'} · ${r.shop.category_text || '—'} · ${stage}`;
  }
  if (r.lead) {
    return `${r.search_keyword || '—'} · ${r.lead.current_status || '待联系'}`;
  }
  if (r.import_meta) {
    const q = typeof r.import_meta.quality_score === 'number' ? r.import_meta.quality_score : '—';
    return `${r.import_meta.country || '—'} · Tier ${r.import_meta.tier || '—'} · Q${q}`;
  }
  return '—';
}

export default function CreatorInfo() {
  const [source, setSource] = useState<SourceKey | 'all'>('all');
  const stats = useSourceStats();
  const feed = useObservationsFeed({ source, limit: 300 });

  const items = feed.data?.items ?? [];
  const s = stats.data?.sources;

  const kpis = useMemo(() => {
    const totalAll = s ? (['tiktok_shop', 'x9_leads', 'table_import', 'other'] as SourceKey[]).reduce((a, k) => a + (s[k]?.total ?? 0), 0) : 0;
    const todayAll = s ? (['tiktok_shop', 'x9_leads', 'table_import', 'other'] as SourceKey[]).reduce((a, k) => a + (s[k]?.today ?? 0), 0) : 0;
    const shopDetail = s?.tiktok_shop?.funnel?.shop_profile_collected ?? 0;
    const contactable = items.filter(itemEmail).length;
    return { totalAll, todayAll, shopDetail, contactable };
  }, [s, items]);

  const columns: Column<ObservationItem>[] = [
    {
      key: 'creator',
      header: '达人',
      cell: (r) => {
        const c = SOURCE_META[r.source]?.color || '#86909c';
        return (
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0" style={{ background: c }}>
              {(r.handle[0] || '?').toUpperCase()}
            </div>
            <div className="min-w-0">
              <div className="text-xs font-medium text-text truncate">@{r.handle}</div>
              <div className="text-xxs text-muted truncate">{r.display_name || '—'}</div>
            </div>
          </div>
        );
      },
      width: '220px',
    },
    {
      key: 'source',
      header: '来源',
      cell: (r) => {
        const m = SOURCE_META[r.source] || SOURCE_META.other;
        return (
          <span className="pill" style={{ background: m.color + '1a', color: m.color }}>
            {m.label}
          </span>
        );
      },
    },
    { key: 'followers', header: '粉丝', align: 'right', cell: (r) => <span className="text-xs num text-text">{r.followers_raw || '—'}</span> },
    {
      key: 'contact',
      header: '联系方式',
      cell: (r) => {
        const email = itemEmail(r);
        if (email) return <span className="text-xs num text-text">{maskEmail(email)}</span>;
        const links = r.lead?.external_links?.length ?? 0;
        return links > 0 ? <span className="pill pill-good">{links} 个外链</span> : <span className="text-xxs text-muted">—</span>;
      },
    },
    { key: 'info', header: '关键信息', cell: (r) => <span className="text-xs text-text">{keyInfo(r)}</span> },
    {
      key: 'collected',
      header: '采集时间',
      cell: (r) => <span className="text-xxs text-muted">{shortRelative(r.created_at || r.collected_at || '') || '—'}</span>,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        {TABS.map((t) => {
          const active = source === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setSource(t.key)}
              className="chip"
              style={active ? { background: 'rgba(6,182,212,0.18)', color: '#22d3ee', borderColor: 'rgba(6,182,212,0.45)' } : undefined}
            >
              {t.label}
            </button>
          );
        })}
        <span className="ml-auto text-xxs text-muted">实时来自采集端 · /collector</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="采集总量" value={kpis.totalAll} icon={Users} iconBg="rgba(6,182,212,0.14)" iconColor="#06b6d4" />
        <KpiCard label="今日新增" value={kpis.todayAll} icon={CalendarDays} iconBg="rgba(59,130,246,0.16)" iconColor="#60a5fa" />
        <KpiCard label="Shop 详情已采" value={kpis.shopDetail} icon={ScanLine} iconBg="rgba(254,44,85,0.16)" iconColor="#FE2C55" />
        <KpiCard label="当前可联系（有邮箱）" value={kpis.contactable} icon={Mail} iconBg="rgba(16,185,129,0.16)" iconColor="#34d399" />
      </div>

      <div className="card">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text">
            达人明细 · {TABS.find((t) => t.key === source)?.label} · {items.length} 条
          </h3>
        </div>
        <div className="p-3">
          <AsyncState
            loading={feed.isLoading}
            error={feed.error}
            isEmpty={!feed.isLoading && items.length === 0}
            emptyMessage="该来源还没有采集到达人"
            height={320}
          >
            <DataTable columns={columns} data={items} rowKey={(r) => r.id} />
          </AsyncState>
        </div>
      </div>
    </div>
  );
}
