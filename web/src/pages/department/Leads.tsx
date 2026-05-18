import { Search, Inbox, Sparkles, CheckCircle2, ArrowRightCircle } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useNamedQuery } from '@/hooks/useApi';
import { formatCompact, maskEmail } from '@/lib/format';
import { toStringArray } from '@/lib/derive';

interface Lead {
  id: number;
  handle: string;
  platform: string | null;
  profile_url: string | null;
  followers: number | null;
  tier: string | null;
  avg_views: number | null;
  gmv_30d_usd: number | null;
  pps: number | null;
  category_tags: string[] | string | null;
  country: string | null;
  source: string | null;
  email?: string | null;
}

const columns: Column<Lead>[] = [
  { key: 'platform', header: '平台', cell: (r) => <Pill tone="info">{r.platform || 'tiktok'}</Pill> },
  {
    key: 'handle', header: '达人',
    cell: (r) => (
      <div className="min-w-0">
        <a href={r.profile_url || '#'} target="_blank" rel="noreferrer" className="text-xs font-medium text-brand-500 hover:underline truncate block">
          @{r.handle}
        </a>
        <div className="text-xxs text-muted">{r.source || '—'}</div>
      </div>
    ),
    width: '200px',
  },
  { key: 'followers', header: '粉丝', align: 'right', cell: (r) => <span className="text-xs num">{r.followers !== null ? formatCompact(r.followers) : '—'}</span> },
  { key: 'tier', header: 'Tier', cell: (r) => <span className="text-xs">{r.tier || '—'}</span> },
  {
    key: 'category', header: '主品类',
    cell: (r) => {
      const tags = toStringArray(r.category_tags);
      return (
        <div className="flex flex-wrap gap-1">
          {tags.slice(0, 2).map((t) => (
            <span key={t} className="pill pill-muted text-xxs">{t}</span>
          ))}
          {tags.length === 0 && <span className="text-xxs text-muted">—</span>}
        </div>
      );
    },
  },
  { key: 'country', header: '国家', cell: (r) => <span className="text-xs">{r.country || '—'}</span> },
  { key: 'email', header: '邮箱', cell: (r) => <span className="text-xs text-muted">{r.email ? maskEmail(r.email) : '—'}</span> },
  {
    key: 'actions', header: '', align: 'right',
    cell: () => (
      <button className="chip text-xxs">
        <ArrowRightCircle size={11} />邀约
      </button>
    ),
  },
];

export default function Leads() {
  // creators_to_contact = prospect 状态的待联系达人池
  const { data, isLoading, error } = useNamedQuery<Lead>('creators_to_contact', { limit: 200 });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  const withEmail = items.filter((l) => l.email).length;
  const highTier = items.filter((l) => l.tier === 'S' || l.tier === 'A').length;
  const today = items.filter((l: any) => l.created_at && l.created_at.startsWith(new Date().toISOString().slice(0, 10))).length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="池中线索" value={total} icon={Inbox} iconBg="#cffafe" iconColor="#0891b2" />
        <KpiCard label="头部线索 (S/A)" value={highTier} icon={Sparkles} iconBg="#fef3c7" iconColor="#ca8a04" />
        <KpiCard label="已带邮箱" value={withEmail} icon={CheckCircle2} iconBg="#d1fae5" iconColor="#16a34a" />
        <KpiCard label="今日新增" value={today} icon={Search} iconBg="#e0e7ff" iconColor="#4f46e5" />
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 flex-wrap border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">待邀约线索池</h3>
          <span className="text-xxs text-muted">数据源:命名查询 <code className="font-mono">creators_to_contact</code></span>
          <div className="ml-auto flex items-center gap-2">
            <button className="btn">批量转入</button>
            <button className="btn btn-primary">触发爬虫</button>
          </div>
        </div>
        <AsyncState loading={isLoading} error={error} isEmpty={items.length === 0} height={300}>
          <DataTable columns={columns} data={items} rowKey={(r) => r.id} />
        </AsyncState>
      </div>
    </div>
  );
}
