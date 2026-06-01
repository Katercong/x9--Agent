import { useState } from 'react';
import { Users } from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { PaginationControls } from '@/components/PaginationControls';
import { AsyncState } from '@/components/states/States';
import { useTalentLeads, type TalentLeadItem } from '@/api/foreignTrade';

const PAGE_SIZE = 20;

const TIER_TONE: Record<string, 'good' | 'warn' | 'muted'> = { A: 'good', B: 'warn', C: 'muted' };
const PLATFORM_LABELS: Record<string, string> = { '51job': '前程无忧', zhaopin: '智联招聘', qzrc: '大泉州人才网' };
const COOP_LABELS: Record<string, string> = {
  individual_bd: '渠道BD', operator: '运营合作', supply_chain: '供应链', individual_partner: '个体合作', unknown: '待定',
};
const STATUS_LABELS: Record<string, string> = { new: '新线索', contacted: '已联系', replied: '已回复', signed: '已签约', dropped: '已放弃' };

export default function TalentLeads() {
  const [page, setPage] = useState(0);
  const [tier, setTier] = useState('');
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');
  const [qInput, setQInput] = useState('');
  const query = useTalentLeads({ tier: tier || undefined, status: status || undefined, q: q || undefined, limit: PAGE_SIZE, offset: page * PAGE_SIZE });
  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;

  const reset = (fn: () => void) => { fn(); setPage(0); };

  const columns: Column<TalentLeadItem>[] = [
    {
      key: 'name',
      header: '意向职位 / 姓名',
      width: '260px',
      cell: (r) => (
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold text-gray-900">{r.desired_title || '—'}</div>
          <div className="truncate text-xxs text-muted">{[r.name_masked, r.city].filter(Boolean).join(' · ') || '—'}</div>
        </div>
      ),
    },
    { key: 'platform', header: '来源', cell: (r) => <span className="text-xs text-gray-700">{PLATFORM_LABELS[r.platform] || r.platform}</span> },
    { key: 'exp', header: '经验', cell: (r) => <span className="text-xs text-gray-700">{r.experience || '—'}</span> },
    { key: 'tier', header: '分级', cell: (r) => (r.tier ? <Pill tone={TIER_TONE[r.tier] || 'muted'}>{r.tier} 级</Pill> : <span className="text-xs text-muted">未评级</span>) },
    { key: 'score', header: '评分', align: 'right', cell: (r) => <span className="num text-xs font-semibold">{r.score}</span> },
    { key: 'coop', header: '合作类型', cell: (r) => <span className="text-xs text-gray-700">{COOP_LABELS[r.cooperation_type || ''] || r.cooperation_type || '—'}</span> },
    { key: 'contact', header: '联系方式', cell: (r) => <span className="truncate text-xs text-gray-700">{r.contact_email || r.contact_phone || r.wechat || '—'}</span> },
    { key: 'status', header: '状态', cell: (r) => <span className="text-xs text-gray-700">{STATUS_LABELS[r.status] || r.status}</span> },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-white px-4 py-3 shadow-card">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-900"><Users size={16} className="text-emerald-600" />跨境人才库</div>
        <span className="text-xxs text-muted">共 {total} 条</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <select value={tier} onChange={(e) => reset(() => setTier(e.target.value))} className="rounded-md border border-line px-2 py-1 text-xs">
            <option value="">全部分级</option>
            <option value="A">A 级</option>
            <option value="B">B 级</option>
            <option value="C">C 级</option>
          </select>
          <select value={status} onChange={(e) => reset(() => setStatus(e.target.value))} className="rounded-md border border-line px-2 py-1 text-xs">
            <option value="">全部状态</option>
            {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') reset(() => setQ(qInput)); }}
            placeholder="搜索职位/城市/专业"
            className="w-44 rounded-md border border-line px-2 py-1 text-xs"
          />
          <button onClick={() => reset(() => setQ(qInput))} className="rounded-md bg-gray-900 px-3 py-1 text-xs font-medium text-white">搜索</button>
        </div>
      </div>

      <div className="rounded-lg border border-line bg-white p-2 shadow-card">
        <AsyncState
          loading={query.isLoading}
          error={query.error}
          isEmpty={!query.isLoading && items.length === 0}
          emptyMessage="还没有跨境人才线索（采集打通后自动填充）"
          height={320}
        >
          <DataTable columns={columns} data={items} rowKey={(r) => r.id} emptyText="暂无数据" />
          <PaginationControls page={page} pageSize={PAGE_SIZE} total={total} currentCount={items.length} loading={query.isFetching} onPageChange={setPage} />
        </AsyncState>
      </div>
    </div>
  );
}
