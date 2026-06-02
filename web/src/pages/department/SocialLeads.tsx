import { useState } from 'react';
import { Heart, ExternalLink } from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { PaginationControls } from '@/components/PaginationControls';
import { AsyncState } from '@/components/states/States';
import { useXhsUsers, type XhsUserItem } from '@/api/foreignTrade';

const PAGE_SIZE = 20;

const PLATFORM_LABELS: Record<string, string> = { xhs: '小红书', douyin: '抖音' };
const DECISION_LABELS: Record<string, string> = {
  target_customer: '目标客户', potential: '潜在', irrelevant: '无关', high_priority: '高优先',
};
const LEVEL_TONE: Record<string, 'good' | 'warn' | 'muted'> = { high: 'good', medium: 'warn', low: 'muted' };
const INTENT_LABELS: Record<string, string> = {
  sourcing: '找货源', dropship: '一件代发', cross_border_ecom: '跨境电商', consumer: '消费者', peer_supplier: '同行', other: '其他',
};

function followers(value: number | null): string {
  if (!value) return '—';
  if (value >= 10000) return `${(value / 10000).toFixed(1)}w`;
  return new Intl.NumberFormat('en-US').format(value);
}

export default function SocialLeads() {
  const [page, setPage] = useState(0);
  const [platform, setPlatform] = useState('');
  const [decision, setDecision] = useState('');
  const [onlyContact, setOnlyContact] = useState(false);
  const [q, setQ] = useState('');
  const [qInput, setQInput] = useState('');
  const query = useXhsUsers({
    platform: platform || undefined,
    decision: decision || undefined,
    has_contact: onlyContact ? 1 : undefined,
    q: q || undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });
  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const reset = (fn: () => void) => { fn(); setPage(0); };

  const columns: Column<XhsUserItem>[] = [
    {
      key: 'user',
      header: '博主',
      width: '240px',
      cell: (r) => (
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold text-gray-900">{r.username || '—'}</div>
          <div className="truncate text-xxs text-muted">{r.bio || r.location || '—'}</div>
        </div>
      ),
    },
    { key: 'platform', header: '平台', cell: (r) => <span className="text-xs text-gray-700">{PLATFORM_LABELS[r.platform] || r.platform}</span> },
    { key: 'followers', header: '粉丝', align: 'right', cell: (r) => <span className="num text-xs font-semibold">{followers(r.follower_count)}</span> },
    { key: 'contact', header: '联系方式', cell: (r) => (r.has_contact ? <Pill tone="good">{r.contact_count || 1} 个</Pill> : <span className="text-xs text-muted">无</span>) },
    { key: 'fit', header: '意向分', align: 'right', cell: (r) => (r.fit_score != null ? <span className="num text-xs font-semibold">{r.fit_score}</span> : <span className="text-xs text-muted">—</span>) },
    { key: 'level', header: '意向级别', cell: (r) => (r.fit_level ? <Pill tone={LEVEL_TONE[r.fit_level] || 'muted'}>{r.fit_level}</Pill> : <span className="text-xs text-muted">未判定</span>) },
    { key: 'decision', header: 'GPT 判定', cell: (r) => <span className="text-xs text-gray-700">{DECISION_LABELS[r.decision || ''] || r.decision || '—'}</span> },
    { key: 'intent', header: '意图类型', cell: (r) => <span className="text-xs text-gray-700">{INTENT_LABELS[r.intent_type || ''] || r.intent_type || '—'}</span> },
    {
      key: 'profile',
      header: '主页',
      cell: (r) => (r.profile_url ? (
        <a href={r.profile_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="inline-flex items-center gap-1 text-xs text-blue-700 hover:underline">
          <ExternalLink size={12} /> 打开
        </a>
      ) : <span className="text-xs text-muted">—</span>),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-white px-4 py-3 shadow-card">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-900"><Heart size={16} className="text-pink-600" />社媒线索</div>
        <span className="text-xxs text-muted">共 {total} 个博主</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <select value={platform} onChange={(e) => reset(() => setPlatform(e.target.value))} className="rounded-md border border-line px-2 py-1 text-xs">
            <option value="">全部平台</option>
            <option value="xhs">小红书</option>
            <option value="douyin">抖音</option>
          </select>
          <select value={decision} onChange={(e) => reset(() => setDecision(e.target.value))} className="rounded-md border border-line px-2 py-1 text-xs">
            <option value="">全部判定</option>
            <option value="target_customer">目标客户</option>
            <option value="potential">潜在</option>
            <option value="irrelevant">无关</option>
          </select>
          <label className="flex items-center gap-1 text-xs text-gray-700">
            <input type="checkbox" checked={onlyContact} onChange={(e) => reset(() => setOnlyContact(e.target.checked))} />仅含联系方式
          </label>
          <input
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') reset(() => setQ(qInput)); }}
            placeholder="搜索博主/简介/地区"
            className="w-40 rounded-md border border-line px-2 py-1 text-xs"
          />
          <button onClick={() => reset(() => setQ(qInput))} className="rounded-md bg-gray-900 px-3 py-1 text-xs font-medium text-white">搜索</button>
        </div>
      </div>

      <div className="rounded-lg border border-line bg-white p-2 shadow-card">
        <AsyncState
          loading={query.isLoading}
          error={query.error}
          isEmpty={!query.isLoading && items.length === 0}
          emptyMessage="还没有社媒线索（采集打通后自动填充）"
          height={320}
        >
          <DataTable
            columns={columns}
            data={items}
            rowKey={(r) => r.id}
            emptyText="暂无数据"
            onRowClick={(r) => { if (r.profile_url) window.open(r.profile_url, '_blank', 'noopener'); }}
          />
          <PaginationControls page={page} pageSize={PAGE_SIZE} total={total} currentCount={items.length} loading={query.isFetching} onPageChange={setPage} />
        </AsyncState>
      </div>
    </div>
  );
}
