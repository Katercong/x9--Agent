import { Search, Inbox, Sparkles, CheckCircle2, ArrowRightCircle } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { leads } from '@/mock/department';
import { formatCompact, formatDate, maskEmail } from '@/lib/format';

type Lead = typeof leads[number];

const columns: Column<Lead>[] = [
  { key: 'platform', header: '平台', cell: (r) => <Pill tone="info">{r.platform}</Pill> },
  {
    key: 'handle', header: '达人',
    cell: (r) => (
      <div className="min-w-0">
        <div className="text-xs font-medium text-gray-800 truncate">@{r.handle}</div>
        <div className="text-xxs text-muted">{r.name}</div>
      </div>
    ),
    width: '180px',
  },
  { key: 'followers', header: '粉丝', align: 'right', cell: (r) => <span className="text-xs num">{formatCompact(r.followers)}</span> },
  {
    key: 'fitLevel', header: '匹配度',
    cell: (r) => <Pill tone={r.fitLevel === '高' ? 'good' : r.fitLevel === '中' ? 'warn' : 'muted'}>{r.fitLevel}</Pill>,
  },
  {
    key: 'priority', header: '优先级',
    cell: (r) => (
      <div className="flex items-center gap-2">
        <span className="text-xs num">{r.priority}</span>
        <div className="w-12 h-1 rounded-full bg-soft overflow-hidden">
          <div
            className="h-full rounded-full"
            style={{
              width: r.priority === 'P2' ? '90%' : r.priority === 'P3' ? '60%' : '30%',
              background: r.priority === 'P2' ? '#ef4444' : r.priority === 'P3' ? '#f5a623' : '#86909c',
            }}
          />
        </div>
      </div>
    ),
  },
  { key: 'category', header: '主品类', cell: (r) => <span className="text-xs">{r.category}</span> },
  { key: 'email', header: '邮箱', cell: (r) => <span className="text-xs text-muted">{r.email ? maskEmail(r.email) : '—'}</span> },
  { key: 'status', header: '状态', cell: (r) => <Pill tone="muted">{r.status}</Pill> },
  { key: 'collectedAt', header: '采集时间', cell: (r) => <span className="text-xs text-muted">{formatDate(r.collectedAt)}</span> },
  { key: 'score', header: '评分', align: 'right', cell: (r) => <span className="text-xs num font-medium">{r.score}</span> },
  {
    key: 'actions', header: '', align: 'right',
    cell: () => (
      <button className="chip text-xxs">
        <ArrowRightCircle size={11} />转入
      </button>
    ),
  },
];

export default function Leads() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="池中线索" value={leads.length} delta={8} icon={Inbox} iconBg="#cffafe" iconColor="#0891b2" />
        <KpiCard label="高匹配度" value={leads.filter((l) => l.fitLevel === '高').length} delta={15} icon={Sparkles} iconBg="#fef3c7" iconColor="#ca8a04" />
        <KpiCard label="已带邮箱" value={leads.filter((l) => l.email).length} delta={4} icon={CheckCircle2} iconBg="#d1fae5" iconColor="#16a34a" />
        <KpiCard label="今日新增" value={6} delta={20} icon={Search} iconBg="#e0e7ff" iconColor="#4f46e5" />
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 flex-wrap border-b border-line">
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>全部平台</option><option>TikTok</option><option>Instagram</option><option>YouTube</option>
          </select>
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>全部匹配度</option><option>高</option><option>中</option><option>低</option>
          </select>
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>全部优先级</option>
          </select>
          <label className="text-xs flex items-center gap-1.5">
            <input type="checkbox" className="rounded" />仅带邮箱
          </label>
          <div className="ml-auto flex items-center gap-2">
            <button className="btn">批量转入</button>
            <button className="btn btn-primary">触发爬虫</button>
          </div>
        </div>
        <DataTable columns={columns} data={leads} rowKey={(r) => r.id} />
      </div>
    </div>
  );
}
