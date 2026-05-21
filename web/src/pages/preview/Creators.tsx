// /preview/creators — Unified creator table.
// Single page replacing /c/creators + /d/creators + /d/leads.
// Source data: union of creators / creator / tk_creators (no rows dropped),
// dedup by (platform, lower(handle)). See services/v2_service.py.
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Search, Filter, ChevronRight, Mail, MailX, Users, Activity, Target } from 'lucide-react';
import { v2Api, type UnifiedCreatorRow, type HealthColor } from '@/api/v2';
import { Pill } from '@/components/Pill';

const fmt = (n: number | null | undefined) => new Intl.NumberFormat('zh-CN').format(Number(n || 0));

const TABS = [
  { key: 'all', label: '全部' },
  { key: 'mine', label: '我负责的' },
  { key: 'pool', label: '推荐池' },
  { key: 'pending', label: '待联系' },
  { key: 'contacted', label: '建联中' },
  { key: 'active', label: '已转化' },
] as const;

const HEALTH_BG: Record<HealthColor, string> = {
  green: 'bg-emerald-500',
  yellow: 'bg-amber-500',
  red: 'bg-rose-500',
  grey: 'bg-gray-300',
};

export default function Creators() {
  const [tab, setTab] = useState<string>('all');
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');

  const { data, isLoading, error } = useQuery({
    queryKey: ['v2', 'creators', tab, q, status],
    queryFn: () => v2Api.creators({ tab, q: q || undefined, status: status || undefined, limit: 200 }),
    staleTime: 30_000,
  });

  return (
    <div className="space-y-3">
      <PreviewBanner />

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-line overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={
              'px-3 py-2 text-xs whitespace-nowrap border-b-2 -mb-px transition-colors ' +
              (tab === t.key ? 'border-brand-500 text-brand-700 font-semibold' : 'border-transparent text-muted hover:text-gray-700')
            }
          >
            {t.label}
          </button>
        ))}
        <span className="ml-auto text-xxs text-muted px-2">
          {data ? `${fmt(data.total)} 位达人` : '加载中...'}
        </span>
      </div>

      {/* Filters */}
      <div className="card card-body flex items-center gap-2 flex-wrap">
        <div className="flex items-center gap-1 border border-line rounded px-2 py-1 min-w-[200px]">
          <Search size={12} className="text-muted" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜索 handle / 名字 / 邮箱"
            className="text-xs flex-1 outline-none"
          />
        </div>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="text-xs border border-line rounded px-2 py-1 bg-white"
        >
          <option value="">全部阶段</option>
          <option value="prospect">潜在线索</option>
          <option value="contacted">已联系</option>
          <option value="pending_reply">待回复</option>
          <option value="confirmed">已确认</option>
          <option value="sample_shipped">已寄样</option>
          <option value="video_published">视频已发</option>
          <option value="ad_running">广告投放中</option>
        </select>
        <Filter size={12} className="text-muted ml-auto" />
        <span className="text-xxs text-muted">{data?.summary && `平均推荐分 ${data.summary.avg_recommendation_score} · 联系率 ${data.summary.contact_rate_pct}%`}</span>
      </div>

      {/* Summary KPI cards (4) */}
      {data?.summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <SummaryCard icon={Users} label="筛选后达人" value={data.summary.filtered_count} color="text-blue-600" bg="bg-blue-50" />
          <SummaryCard icon={Target} label="平均推荐分" value={data.summary.avg_recommendation_score} color="text-purple-600" bg="bg-purple-50" />
          <SummaryCard icon={Mail} label="含邮箱" value={data.summary.with_email} color="text-emerald-600" bg="bg-emerald-50" suffix={`/${data.summary.filtered_count}`} />
          <SummaryCard icon={Activity} label="联系率" value={`${data.summary.contact_rate_pct}%`} color="text-rose-600" bg="bg-rose-50" />
        </div>
      )}

      {/* Table */}
      <div className="card">
        {isLoading && <div className="p-6 text-center text-muted text-sm">加载中...</div>}
        {error && <div className="p-6 text-center text-bad text-sm">{(error as Error).message}</div>}
        {data && (
          <div className="overflow-x-auto">
            <table className="table-x9">
              <thead>
                <tr>
                  <th style={{ width: 22 }}></th>
                  <th>达人</th>
                  <th>平台</th>
                  <th className="!text-right">粉丝</th>
                  <th className="!text-right">推荐分</th>
                  <th>当前阶段</th>
                  <th>负责人</th>
                  <th>部门</th>
                  <th>邮箱</th>
                  <th className="!text-right">最近联系</th>
                  <th>来源</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <CreatorRow key={`${row.platform}/${row.handle_key}`} row={row} />
                ))}
              </tbody>
            </table>
            {data.items.length === 0 && (
              <div className="p-6 text-center text-muted text-sm">当前筛选下没有达人</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ icon: Icon, label, value, color, bg, suffix }: any) {
  return (
    <div className="card card-body">
      <div className="flex items-start gap-3">
        <div className={`w-9 h-9 rounded-full ${bg} ${color} flex items-center justify-center`}>
          <Icon size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xxs text-muted">{label}</div>
          <div className="text-xl font-bold num text-gray-900 leading-none mt-1">
            {typeof value === 'number' ? fmt(value) : value}
            {suffix && <span className="text-xxs text-muted ml-1">{suffix}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

function CreatorRow({ row }: { row: UnifiedCreatorRow }) {
  const toUrl = `/preview/creators/${encodeURIComponent(row.platform)}/${encodeURIComponent(row.handle_key)}`;
  return (
    <tr className="hover:bg-gray-50">
      <td>
        <span
          className={`inline-block w-2 h-2 rounded-full ${HEALTH_BG[row.health.color]}`}
          title={row.health.reason}
        />
      </td>
      <td>
        <Link to={toUrl} className="flex items-center gap-2">
          {row.avatar_url ? (
            <img src={row.avatar_url} alt="" className="w-7 h-7 rounded-full object-cover" />
          ) : (
            <div className="w-7 h-7 rounded-full bg-brand-100 text-brand-700 text-xs font-semibold flex items-center justify-center">
              {(row.handle?.[0] || '?').toUpperCase()}
            </div>
          )}
          <div className="min-w-0">
            <div className="text-xs font-medium truncate text-brand-700 hover:underline">@{row.handle}</div>
            <div className="text-xxs text-muted truncate">{row.display_name || '—'}</div>
          </div>
        </Link>
      </td>
      <td><Pill tone="muted">{row.platform}</Pill></td>
      <td className="text-xs num text-right">{fmt(row.followers_count)}</td>
      <td className="text-xs num text-right">
        <span className={row.recommendation_score >= 70 ? 'font-semibold text-emerald-600' : ''}>
          {row.recommendation_score}
        </span>
      </td>
      <td>{row.stage_label ? <Pill tone={stageColor(row.stage)}>{row.stage_label}</Pill> : <span className="text-xxs text-muted">—</span>}</td>
      <td className="text-xs">{row.owner_bd || <span className="text-muted">—</span>}</td>
      <td className="text-xxs text-muted">{row.department_code || '—'}</td>
      <td>
        {row.email ? (
          <Mail size={12} className="text-emerald-600" />
        ) : (
          <MailX size={12} className="text-gray-300" />
        )}
      </td>
      <td className="text-xxs text-right text-muted">{row.last_contact_date?.slice(0, 10) || '—'}</td>
      <td><span className="text-xxs text-muted">{row.source_table}</span></td>
    </tr>
  );
}

function stageColor(stage: string | null): 'muted' | 'info' | 'good' | 'warn' | 'bad' {
  if (!stage) return 'muted';
  if (['video_published', 'ad_authorized', 'ad_running'].includes(stage)) return 'good';
  if (['confirmed', 'sample_shipped', 'sample_delivered'].includes(stage)) return 'info';
  if (['contacted', 'pending_reply'].includes(stage)) return 'warn';
  if (stage === 'dropped') return 'bad';
  return 'muted';
}

function PreviewBanner() {
  return (
    <div className="card card-body bg-amber-50 border-amber-200 flex items-center gap-2 text-xs">
      <span className="px-2 py-0.5 rounded bg-amber-200 text-amber-900 font-semibold text-xxs">PREVIEW</span>
      <span className="text-amber-900">v2 看板 · 统一达人主表 — 合并三张表 (creators + creator + tk_creators) 去重展示</span>
      <Link to="/preview/pulse" className="ml-auto chip text-xxs">公司脉搏</Link>
      <Link to="/preview/me" className="chip text-xxs">我的工作台</Link>
    </div>
  );
}
