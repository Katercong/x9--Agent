import { Users, Sparkles, Mail, CheckCircle2, Clock, MessageSquare, Package, CalendarRange } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { AsyncState, Empty } from '@/components/states/States';
import { useBusinessDashboard } from '@/hooks/useApi';

type Row = { name?: string; label?: string; owner?: string; owner_bd?: string; count?: number; value?: number; recommended?: number; pending_contact?: number; contacted?: number };

function num(n: unknown): string {
  const v = typeof n === 'number' ? n : Number(n);
  return Number.isFinite(v) ? new Intl.NumberFormat('en-US').format(v) : '0';
}

const PALETTE = ['#06b6d4', '#3b82f6', '#10b981', '#f59e0b', '#a78bfa', '#FE2C55', '#34d399', '#f472b6', '#64748b'];

function MiniTable({ title, rows, valueKey = 'count' }: { title: string; rows: Row[]; valueKey?: 'count' | 'value' }) {
  return (
    <div className="card">
      <div className="px-4 py-3 border-b border-border">
        <h3 className="text-sm font-semibold text-text">{title}</h3>
      </div>
      <div className="p-2">
        {rows.length === 0 ? (
          <Empty height={120} message="暂无数据" />
        ) : (
          <table className="table-x9">
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td className="text-xs text-text">{r.name || r.label || '—'}</td>
                  <td className="text-xs text-right num text-text">{num(r[valueKey] ?? r.count ?? r.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default function Business() {
  const { data, isLoading, error } = useBusinessDashboard();
  const d: any = data || {};
  const s: any = d.summary || {};
  const businessStatus: Row[] = (d.business_status || []).filter((r: Row) => (r.count ?? 0) > 0);
  const products: Row[] = d.products || [];
  const priorities: Row[] = d.priorities || [];
  const collabTypes: Row[] = d.collab_types || [];
  const owners: Row[] = d.owners || [];

  const statusPie =
    businessStatus.length > 0
      ? {
          tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
          legend: { type: 'scroll', bottom: 0, icon: 'circle', itemWidth: 8, textStyle: { fontSize: 11, color: 'rgba(255,255,255,0.7)' } },
          series: [
            {
              type: 'pie',
              radius: ['46%', '70%'],
              center: ['50%', '44%'],
              label: { show: false },
              data: businessStatus.map((r, i) => ({ name: r.name || r.label, value: r.count, itemStyle: { color: PALETTE[i % PALETTE.length] } })),
            },
          ],
        }
      : null;

  const kpis = [
    { label: '达人总数', value: num(s.creator_count), icon: Users, c: '#06b6d4' },
    { label: '已推荐', value: num(s.recommended), icon: Sparkles, c: '#a78bfa' },
    { label: '可联系', value: num(s.contactable), icon: Mail, c: '#10b981' },
    { label: '已建联', value: num(s.contacted), icon: CheckCircle2, c: '#34d399' },
    { label: '待建联', value: num(s.pending_contact), icon: Clock, c: '#f59e0b' },
    { label: '待回复', value: num(s.pending_reply), icon: MessageSquare, c: '#60a5fa' },
    { label: '已寄样', value: num(s.sample_sent), icon: Package, c: '#FE2C55' },
    { label: '近 7 天采集', value: num(s.recent_collections_7d), icon: CalendarRange, c: '#22d3ee' },
  ];

  return (
    <AsyncState loading={isLoading} error={error} height={420}>
      <div className="space-y-4">
        <div className="text-xs text-muted">
          {d.scope?.name ? `范围:${d.scope.name}` : '按当前部门数据实时汇总'} ·
          已分配 {num(s.assigned)} · 未分配推荐 {num(s.unassigned_recommended)} · 邮件 草稿 {num(s.outreach_drafts)} / 已发 {num(s.outreach_sent)} / 失败 {num(s.outreach_failed)}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
          {kpis.map((k) => (
            <KpiCard
              key={k.label}
              label={k.label}
              value={k.value}
              icon={k.icon}
              iconBg={k.c + '24'}
              iconColor={k.c}
              compact
            />
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          {statusPie ? (
            <ChartCard title="业务状态分布" className="lg:col-span-1">
              <EChart option={statusPie} height={280} />
            </ChartCard>
          ) : (
            <div className="card lg:col-span-1">
              <div className="px-4 py-3 border-b border-border"><h3 className="text-sm font-semibold text-text">业务状态分布</h3></div>
              <Empty height={240} message="暂无状态数据(可能仅 admin 角色可见)" />
            </div>
          )}
          <div className="lg:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-3">
            <MiniTable title="业务状态" rows={businessStatus} />
            <MiniTable title="优先级" rows={priorities} />
            <MiniTable title="产品方向" rows={products} />
            <MiniTable title="协作类型" rows={collabTypes} />
          </div>
        </div>

        <div className="card">
          <div className="px-4 py-3 border-b border-border">
            <h3 className="text-sm font-semibold text-text">BD 跟进</h3>
          </div>
          <div className="p-2">
            {owners.length === 0 ? (
              <Empty height={140} message="暂无 BD 分配数据" />
            ) : (
              <table className="table-x9">
                <thead>
                  <tr>
                    <th className="text-left">BD</th>
                    <th className="text-right">推荐</th>
                    <th className="text-right">待建联</th>
                    <th className="text-right">已建联</th>
                  </tr>
                </thead>
                <tbody>
                  {owners.map((o, i) => (
                    <tr key={i}>
                      <td className="text-xs text-text">{o.owner || o.owner_bd || o.name || '未分配'}</td>
                      <td className="text-xs text-right num text-text">{num(o.recommended)}</td>
                      <td className="text-xs text-right num text-text">{num(o.pending_contact)}</td>
                      <td className="text-xs text-right num text-text">{num(o.contacted)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </AsyncState>
  );
}
