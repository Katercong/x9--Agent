import { useState } from 'react';
import { Users, Activity, Clock, UserPlus, Search, Plus, Download } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { TierPill, StatusPill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useCreators } from '@/hooks/useApi';
import { formatCompact, formatCurrency, formatDate } from '@/lib/format';
import type { Creator } from '@/api/types';

const columns: Column<Creator>[] = [
  {
    key: 'creator',
    header: '达人',
    cell: (r) => (
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center text-white text-xs font-medium shrink-0">
          {r.handle[0]?.toUpperCase() || '?'}
        </div>
        <div className="min-w-0">
          <div className="text-xs font-medium text-gray-800">@{r.handle}</div>
          <div className="text-xxs text-muted truncate">{r.display_name || r.handle}</div>
        </div>
      </div>
    ),
    width: '220px',
  },
  { key: 'tier', header: 'Tier', cell: (r) => r.tier ? <TierPill tier={r.tier} /> : <span className="text-xxs text-muted">—</span> },
  { key: 'followers', header: '粉丝', align: 'right', cell: (r) => <span className="text-xs num">{r.followers !== null ? formatCompact(r.followers) : '—'}</span> },
  { key: 'gmv', header: '30d GMV', align: 'right', cell: (r) => <span className="text-xs num">{r.gmv_30d_usd !== null ? formatCurrency(r.gmv_30d_usd, '$') : '—'}</span> },
  { key: 'status', header: '当前状态', cell: (r) => r.current_status ? <StatusPill status={r.current_status} /> : <span className="text-xxs text-muted">—</span> },
  { key: 'owner', header: '对接人', cell: (r) => <span className="text-xs">{r.owner_bd || '—'}</span> },
  { key: 'country', header: '国家', cell: (r) => <span className="text-xs">{r.country || '—'}</span> },
  { key: 'lastContact', header: '最近联系', cell: (r) => <span className="text-xs text-muted">{r.last_contact_date ? formatDate(r.last_contact_date) : '—'}</span> },
  {
    key: 'actions', header: '', align: 'right',
    cell: () => (
      <div className="flex items-center justify-end gap-1.5">
        <button className="chip text-xxs">+ 建联</button>
        <button className="chip text-xxs">话术</button>
      </div>
    ),
  },
];

export default function Creators() {
  const [q, setQ] = useState('');
  const [tier, setTier] = useState('');
  const [status, setStatus] = useState('');

  const params: Record<string, unknown> = { limit: 200 };
  if (q) params.q = q;
  if (tier) params.tier = tier;
  if (status) params.current_status = status;

  const { data, isLoading, error } = useCreators(params);
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  // local KPI calcs
  const active = items.filter((c) => c.current_status && !['prospect', 'dropped'].includes(c.current_status)).length;
  const prospect = items.filter((c) => c.current_status === 'prospect').length;
  const recent30 = items.filter((c) => c.created_at && (new Date().getTime() - new Date(c.created_at).getTime() < 30 * 24 * 3600_000)).length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="管辖达人" value={total} icon={Users} iconBg="#e0e7ff" iconColor="#4f46e5" />
        <KpiCard label="活跃达人" value={active} icon={Activity} iconBg="#d1fae5" iconColor="#16a34a" />
        <KpiCard label="待联系" value={prospect} icon={Clock} iconBg="#fed7aa" iconColor="#ea580c" />
        <KpiCard label="30d 新增" value={recent30} icon={UserPlus} iconBg="#ede9fe" iconColor="#7c3aed" />
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 flex-wrap border-b border-line">
          <div className="flex items-center gap-1.5 bg-soft border border-line rounded px-2.5 py-1.5 w-72">
            <Search size={14} className="text-muted shrink-0" />
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索 handle / 备注"
              className="flex-1 bg-transparent outline-none text-xs"
            />
          </div>
          <select value={tier} onChange={(e) => setTier(e.target.value)} className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option value="">全部 Tier</option>
            <option value="S">S</option><option value="A">A</option><option value="B">B</option>
            <option value="C">C</option><option value="D">D</option>
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option value="">全部状态</option>
            <option value="prospect">潜在</option>
            <option value="contacted">已联系</option>
            <option value="confirmed">已确认</option>
            <option value="sample_shipped">样品已寄</option>
            <option value="video_published">视频已发</option>
            <option value="ad_authorized">已授权</option>
            <option value="ad_running">广告投放中</option>
          </select>
          <div className="ml-auto flex items-center gap-2">
            <button className="btn"><Download size={12} />导出</button>
            <button className="btn btn-primary"><Plus size={12} />新增达人</button>
          </div>
        </div>
        <AsyncState loading={isLoading} error={error} isEmpty={items.length === 0} height={300}>
          <DataTable columns={columns} data={items} rowKey={(r) => r.id} />
        </AsyncState>
      </div>
    </div>
  );
}
