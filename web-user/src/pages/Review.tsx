import { ClipboardCheck, CheckCircle2, XCircle, Clock, AlertTriangle, Star } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { AsyncState } from '@/components/states/States';
import { useReviewTasks } from '@/hooks/useApi';
import { pickItems } from '@/api/types';
import type { ReviewTask } from '@/api/types';
import { formatDateTime, shortRelative } from '@/lib/format';

export default function Review() {
  const pendingQ = useReviewTasks({ status: 'pending', limit: 200 });
  const approvedQ = useReviewTasks({ status: 'approved', limit: 1 });
  const rejectedQ = useReviewTasks({ status: 'rejected', limit: 1 });

  const items = pickItems<ReviewTask>(pendingQ.data as any);
  const pendingTotal = (pendingQ.data as any)?.total ?? items.length;
  const approvedTotal = (approvedQ.data as any)?.total ?? 0;
  const rejectedTotal = (rejectedQ.data as any)?.total ?? 0;
  const total = pendingTotal + approvedTotal + rejectedTotal;
  const passRate = total > 0 ? Math.round((approvedTotal / total) * 100) : 0;

  const columns: Column<ReviewTask>[] = [
    {
      key: 'priority', header: '优先级', align: 'center', width: '70px',
      cell: (r) => {
        const tone = r.priority === 'P1' ? 'bad' : r.priority === 'P2' ? 'warn' : 'muted';
        return <span className={`pill pill-${tone}`}>{r.priority || 'P3'}</span>;
      },
    },
    {
      key: 'score', header: 'AI 分', align: 'center', width: '70px',
      cell: (r) => {
        const s = r.ai_score;
        if (s === null || s === undefined) return <span className="text-xxs text-muted">—</span>;
        return (
          <div className="flex items-center gap-1 justify-center">
            <Star size={11} className="text-warn" />
            <span className="text-xs num font-bold">{Math.round(s)}</span>
          </div>
        );
      },
    },
    { key: 'creator', header: '达人 ID', cell: (r) => <span className="text-xs font-mono">#{r.creator_id}</span> },
    {
      key: 'reason', header: '审核理由',
      cell: (r) => <span className="text-xs text-muted truncate max-w-[280px] block">{r.reason || '—'}</span>,
    },
    { key: 'created', header: '入队', cell: (r) => <span className="text-xs text-muted">{shortRelative(r.created_at)}</span> },
    { key: 'updated', header: '最近更新', cell: (r) => <span className="text-xs text-muted">{formatDateTime(r.updated_at)}</span> },
    {
      key: 'actions', header: '', align: 'right',
      cell: () => (
        <div className="flex items-center justify-end gap-1.5">
          <button className="chip text-xxs"><CheckCircle2 size={11} className="text-good" />通过</button>
          <button className="chip text-xxs"><Clock size={11} className="text-warn" />挂起</button>
          <button className="chip text-xxs"><XCircle size={11} className="text-bad" />拒绝</button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="待审核" value={pendingTotal} icon={ClipboardCheck} iconBg="rgb(245 158 11 / 0.18)" iconColor="#fbbf24" subLabel="低置信度推荐" />
        <KpiCard label="已通过" value={approvedTotal} icon={CheckCircle2} iconBg="rgb(34 197 94 / 0.18)" iconColor="#4ade80" />
        <KpiCard label="已拒绝" value={rejectedTotal} icon={XCircle} iconBg="rgb(239 68 68 / 0.18)" iconColor="#fca5a5" />
        <KpiCard label="通过率" value={`${passRate}%`} icon={AlertTriangle} iconBg="rgb(139 92 246 / 0.18)" iconColor="#a78bfa" />
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-border">
          <h3 className="text-sm font-semibold">待审核队列</h3>
          <span className="text-xxs text-muted">共 {pendingTotal} 项</span>
          <div className="ml-auto flex items-center gap-2">
            <select className="text-xs border border-border rounded px-2 py-1.5"
                    style={{ background: 'rgb(var(--bg-elev-1))', color: 'rgb(var(--text))' }}>
              <option>全部优先级</option><option>P1</option><option>P2</option><option>P3</option>
            </select>
            <button className="btn text-xs">批量通过</button>
          </div>
        </div>
        <AsyncState loading={pendingQ.isLoading} error={pendingQ.error} isEmpty={items.length === 0} emptyMessage="审核队列已清空 ✓" height={300}>
          <DataTable columns={columns} data={items} rowKey={(r) => r.id} />
        </AsyncState>
      </div>
    </div>
  );
}
