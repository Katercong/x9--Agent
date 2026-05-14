import { Users, Activity, Clock, UserPlus, Search, Plus, Download } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { TierPill, StatusPill } from '@/components/Pill';
import { creators } from '@/mock/department';
import { formatCompact, formatCurrency, formatDate } from '@/lib/format';

type Creator = typeof creators[number];

const columns: Column<Creator>[] = [
  {
    key: 'creator',
    header: '达人',
    cell: (r) => (
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center text-white text-xs font-medium shrink-0">
          {r.handle[0].toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className="text-xs font-medium text-gray-800">@{r.handle}</div>
          <div className="text-xxs text-muted truncate">{r.nickname}</div>
        </div>
      </div>
    ),
    width: '220px',
  },
  { key: 'tier', header: 'Tier', cell: (r) => <TierPill tier={r.tier} /> },
  { key: 'followers', header: '粉丝', align: 'right', cell: (r) => <span className="text-xs num">{formatCompact(r.followers)}</span> },
  { key: 'gmv30d', header: '30d GMV', align: 'right', cell: (r) => <span className="text-xs num">{formatCurrency(r.gmv30d)}</span> },
  { key: 'status', header: '当前状态', cell: (r) => <StatusPill status={r.status} /> },
  { key: 'owner', header: '对接人', cell: (r) => <span className="text-xs">{r.owner}</span> },
  { key: 'country', header: '国家', cell: (r) => <span className="text-xs">{r.country}</span> },
  { key: 'lastContact', header: '最近联系', cell: (r) => <span className="text-xs text-muted">{r.lastContact ? formatDate(r.lastContact) : '—'}</span> },
  { key: 'priority', header: '优先级', cell: (r) => <span className="text-xs num">{r.priority}</span> },
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
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="管辖达人" value={creators.length} delta={5} icon={Users} iconBg="#e0e7ff" iconColor="#4f46e5" />
        <KpiCard label="活跃达人" value={9} delta={12} icon={Activity} iconBg="#d1fae5" iconColor="#16a34a" />
        <KpiCard label="待联系" value={6} delta={-2} icon={Clock} iconBg="#fed7aa" iconColor="#ea580c" />
        <KpiCard label="30d 新增" value={4} delta={33} icon={UserPlus} iconBg="#ede9fe" iconColor="#7c3aed" />
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 flex-wrap border-b border-line">
          <div className="flex items-center gap-1.5 bg-soft border border-line rounded px-2.5 py-1.5 w-72">
            <Search size={14} className="text-muted shrink-0" />
            <input
              type="text"
              placeholder="搜索 handle / 备注"
              className="flex-1 bg-transparent outline-none text-xs"
            />
          </div>
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>全部 Tier</option><option>S</option><option>A</option><option>B</option><option>C</option><option>D</option>
          </select>
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>全部状态</option>
          </select>
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>全部对接人</option>
          </select>
          <div className="ml-auto flex items-center gap-2">
            <button className="btn"><Download size={12} />导出</button>
            <button className="btn btn-primary"><Plus size={12} />新增达人</button>
          </div>
        </div>
        <DataTable columns={columns} data={creators} rowKey={(r) => r.id} />
      </div>
    </div>
  );
}
