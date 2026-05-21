// Per-user detail page for the super-admin panel.
//
// Shows three layers of insight for one user:
//   1. KPI cards — collection, owned creators, outreach, conversion rates.
//   2. 30-day trend — daily collected / sent / replied as a line chart.
//   3. Outreach funnel — sent → replied → deal-closed.
//
// Data comes from three endpoints under /api/local/admin/users/:id/*. The
// "replied" and "deal_closed" numbers are placeholders today (see backend
// `services/user_stats_service.py` caveats); we surface that fact in a
// tooltip rather than pretending the data is exact.
import { useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Users, Send, Inbox, Trophy, Mail, Database, Loader2, Info } from 'lucide-react';
import { authApi } from '@/api/authClient';
import { KpiGroup } from '@/components/kpi/KpiCard';
import { EChart } from '@/components/charts/EChart';
import { Pill } from '@/components/Pill';

interface UserDetailResponse {
  ok: boolean;
  user: {
    id: string;
    username: string;
    display_name: string;
    email: string | null;
    role: string;
    department_code: string | null;
    is_active: boolean;
    approval_status: string;
    created_at: string | null;
  };
  stats: {
    collection: { scope: string; total: number; today: number };
    creators: { owned: number; pending_contact: number; contacted: number };
    outreach: { total: number; drafts: number; sent: number; failed: number; cancelled: number; last_at?: string | null };
  };
}

interface TrendResponse {
  ok: boolean;
  days: number;
  series: { date: string; collected: number; sent: number; replied: number }[];
  caveats?: Record<string, string>;
}

interface FunnelResponse {
  ok: boolean;
  funnel: { sent: number; replied: number; deal_closed: number };
  rates: { reply_rate: number; deal_rate_of_replied: number; deal_rate_of_sent: number };
  caveats?: Record<string, string>;
}

// Same auth wrapper authApi uses internally — we hit a couple of routes that
// aren't part of the authApi surface, so we share the cookie+JSON convention.
async function adminFetch<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: 'include' });
  if (!res.ok) {
    let body: unknown = null;
    try { body = await res.json(); } catch { /* ignore */ }
    const detail = (body && typeof body === 'object' && 'detail' in body && (body as any).detail) || res.statusText;
    throw new Error(String(detail));
  }
  return (await res.json()) as T;
}

const fmt = (n: number | null | undefined) => new Intl.NumberFormat('zh-CN').format(Number(n || 0));
const ROLE_LABEL: Record<string, string> = {
  super_admin: '超级管理员',
  company_admin: '公司管理员',
  department_admin: '部门管理员',
  department_user: '普通用户',
};

export default function UserDetail() {
  const { id } = useParams<{ id: string }>();
  const userId = id || '';

  const detail = useQuery({
    queryKey: ['admin', 'user-detail', userId],
    queryFn: () => adminFetch<UserDetailResponse>(`/api/local/admin/users/${encodeURIComponent(userId)}/detail`),
    enabled: !!userId,
  });
  const trend = useQuery({
    queryKey: ['admin', 'user-trend', userId],
    queryFn: () => adminFetch<TrendResponse>(`/api/local/admin/users/${encodeURIComponent(userId)}/trend?days=30`),
    enabled: !!userId,
  });
  const funnel = useQuery({
    queryKey: ['admin', 'user-funnel', userId],
    queryFn: () => adminFetch<FunnelResponse>(`/api/local/admin/users/${encodeURIComponent(userId)}/funnel`),
    enabled: !!userId,
  });

  // Line chart option, recomputed only when the trend series changes.
  const trendOption = useMemo(() => {
    const series = trend.data?.series ?? [];
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['采集', '发送', '回复'], top: 0 },
      grid: { left: 40, right: 16, top: 32, bottom: 24 },
      xAxis: {
        type: 'category',
        data: series.map((d) => d.date.slice(5)),
        boundaryGap: false,
      },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        { name: '采集', type: 'line', smooth: true, data: series.map((d) => d.collected) },
        { name: '发送', type: 'line', smooth: true, data: series.map((d) => d.sent) },
        { name: '回复', type: 'line', smooth: true, data: series.map((d) => d.replied) },
      ],
    };
  }, [trend.data]);

  const funnelOption = useMemo(() => {
    const f = funnel.data?.funnel;
    if (!f) return { series: [] };
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c}' },
      series: [
        {
          type: 'funnel',
          left: '10%',
          right: '10%',
          top: 16,
          bottom: 16,
          minSize: '20%',
          maxSize: '100%',
          sort: 'descending',
          gap: 4,
          label: { show: true, position: 'inside' },
          labelLine: { show: false },
          data: [
            { value: f.sent, name: '已发送' },
            { value: f.replied, name: '已回复（占位）' },
            { value: f.deal_closed, name: '已成交（占位）' },
          ],
        },
      ],
    };
  }, [funnel.data]);

  if (!userId) {
    return <div className="text-muted text-sm p-4">缺少用户 ID</div>;
  }

  if (detail.isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 text-muted text-sm p-8">
        <Loader2 size={16} className="animate-spin" />
        加载用户信息…
      </div>
    );
  }
  if (detail.error || !detail.data?.ok) {
    return (
      <div className="card card-body">
        <div className="text-bad text-sm">无法加载用户详情：{(detail.error as Error)?.message || '未知错误'}</div>
        <Link to="/a/users" className="btn btn-primary mt-3 inline-flex"><ArrowLeft size={14} />返回用户列表</Link>
      </div>
    );
  }

  const u = detail.data.user;
  const s = detail.data.stats;
  const f = funnel.data?.funnel;
  const r = funnel.data?.rates;

  const kpis = [
    { label: `${s.collection.scope === 'company' ? '公司' : '部门'}采集总量`, value: fmt(s.collection.total), subLabel: `今日 ${fmt(s.collection.today)}`, icon: Database, iconBg: '#e0f2fe', iconColor: '#0369a1' },
    { label: '负责达人', value: fmt(s.creators.owned), subLabel: `待联系 ${fmt(s.creators.pending_contact)} / 已建联 ${fmt(s.creators.contacted)}`, icon: Users, iconBg: '#fef3c7', iconColor: '#92400e' },
    { label: '邮件发送', value: fmt(f?.sent ?? s.outreach.sent), subLabel: s.outreach.last_at ? `最后 ${s.outreach.last_at.slice(0, 10)}` : '尚未发送', icon: Send, iconBg: '#dcfce7', iconColor: '#15803d' },
    { label: '邮件回复（占位）', value: fmt(f?.replied ?? 0), subLabel: `回复率 ${r?.reply_rate ?? 0}%`, icon: Inbox, iconBg: '#fce7f3', iconColor: '#9d174d' },
    { label: '成交（占位）', value: fmt(f?.deal_closed ?? 0), subLabel: `占发送 ${r?.deal_rate_of_sent ?? 0}%`, icon: Trophy, iconBg: '#ede9fe', iconColor: '#5b21b6' },
    { label: '草稿 / 失败', value: `${fmt(s.outreach.drafts)} / ${fmt(s.outreach.failed)}`, subLabel: `共计 ${fmt(s.outreach.total)} 封`, icon: Mail, iconBg: '#f3f4f6', iconColor: '#4b5563' },
  ];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="card card-body flex items-center gap-3">
        <Link to="/a/users" className="chip"><ArrowLeft size={12} />返回</Link>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-base font-semibold text-gray-900 truncate">{u.display_name || u.username}</span>
            <Pill tone={u.role === 'super_admin' ? 'warn' : u.role === 'company_admin' ? 'info' : u.role === 'department_admin' ? 'good' : 'muted'}>
              {ROLE_LABEL[u.role] || u.role}
            </Pill>
            {!u.is_active && <Pill tone="bad">已禁用</Pill>}
          </div>
          <div className="text-xxs text-muted mt-0.5">
            @{u.username} · {u.email || '无邮箱'} · {u.department_code || '全公司'}
          </div>
        </div>
      </div>

      {/* KPI grid */}
      <KpiGroup items={kpis} cols={6} compact />

      {/* Trend */}
      <div className="card">
        <div className="px-4 py-3 border-b border-line flex items-center gap-2">
          <h3 className="text-sm font-semibold text-gray-800">近 30 天活动趋势</h3>
          {trend.data?.caveats?.replied && (
            <span className="text-xxs text-muted inline-flex items-center gap-1">
              <Info size={12} />{trend.data.caveats.replied}
            </span>
          )}
        </div>
        <div className="p-3">
          {trend.isLoading ? (
            <div className="flex items-center justify-center gap-2 text-muted text-xs h-64">
              <Loader2 size={14} className="animate-spin" />加载趋势数据…
            </div>
          ) : (
            <EChart option={trendOption} height={280} />
          )}
        </div>
      </div>

      {/* Funnel */}
      <div className="card">
        <div className="px-4 py-3 border-b border-line flex items-center gap-2">
          <h3 className="text-sm font-semibold text-gray-800">外联转化漏斗</h3>
          {funnel.data?.caveats && (
            <span className="text-xxs text-muted inline-flex items-center gap-1">
              <Info size={12} />回复/成交为占位估算,后续接入精确字段。
            </span>
          )}
        </div>
        <div className="p-3 grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            {funnel.isLoading ? (
              <div className="flex items-center justify-center gap-2 text-muted text-xs h-64">
                <Loader2 size={14} className="animate-spin" />加载漏斗数据…
              </div>
            ) : (
              <EChart option={funnelOption} height={300} />
            )}
          </div>
          <div className="space-y-2 text-xs">
            <RateRow label="回复率（回复 / 发送）" value={`${r?.reply_rate ?? 0}%`} />
            <RateRow label="回复→成交（成交 / 回复）" value={`${r?.deal_rate_of_replied ?? 0}%`} />
            <RateRow label="整体转化（成交 / 发送）" value={`${r?.deal_rate_of_sent ?? 0}%`} />
            <div className="border-t border-line my-2" />
            <RateRow label="发送总数" value={fmt(f?.sent)} />
            <RateRow label="收到回复" value={fmt(f?.replied)} />
            <RateRow label="完成成交" value={fmt(f?.deal_closed)} />
          </div>
        </div>
      </div>
    </div>
  );
}

function RateRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between px-2 py-1.5 rounded hover:bg-gray-50">
      <span className="text-muted">{label}</span>
      <span className="num font-semibold text-gray-800">{value}</span>
    </div>
  );
}
