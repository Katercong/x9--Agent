import { Wallet, ShoppingCart, Users, TrendingUp, Building2, Video, ArrowUpRight, AlertOctagon } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useCreators, useOutreach, useProducts, useStaff, useDepartmentDashboardSummary } from '@/hooks/useApi';
import { trendByDay, recentNDays, groupByOutreachStatus, groupByOwner, staffStats } from '@/lib/derive';
import { chartPalette } from '@/lib/colors';
import { formatDate } from '@/lib/format';

interface RecentEvent {
  id: number;
  date: string;
  type: string;
  level: 'good' | 'info' | 'warn' | 'bad';
  title: string;
  dept: string;
}

const eventColumns: Column<RecentEvent>[] = [
  { key: 'date', header: '日期', cell: (r) => <span className="text-xs text-muted">{r.date}</span>, width: '100px' },
  { key: 'type', header: '类型', cell: (r) => <Pill tone={r.level}>{r.type}</Pill> },
  { key: 'title', header: '事件', cell: (r) => <span className="text-xs">{r.title}</span> },
  { key: 'dept', header: '部门', cell: (r) => <span className="text-xs text-muted">{r.dept}</span> },
];

export default function Overview() {
  const creators = useCreators({ limit: 1000 });
  const outreach = useOutreach({ limit: 1000, order_by: 'created_at:desc' });
  const products = useProducts({ limit: 200 });
  const staff = useStaff({ limit: 100 });
  const dashboard = useDepartmentDashboardSummary();

  const loading = creators.isLoading || outreach.isLoading || products.isLoading || dashboard.isLoading;
  const error = creators.error || outreach.error || products.error || dashboard.error;

  const creatorList = creators.data?.items ?? [];
  const outreachList = outreach.data?.items ?? [];
  const productList = products.data?.items ?? [];
  const staffList = staff.data?.items ?? [];
  const summary = dashboard.data?.summary;

  const statusMap = groupByOutreachStatus(outreachList);
  const activeDepts = new Set(creatorList.map((c) => c.store_assigned).filter(Boolean)).size;
  const totalContacted = staffStats(staffList).reduce((s, r) => s + r.contacted, 0);

  // 30 天趋势(按 outreach 事件)
  const trend30 = trendByDay(creatorList as any, 30);

  // 部门贡献(按 store_assigned 分组的达人数)
  const deptContrib = groupByOwner(creatorList as any, 8).map((o, i) => ({
    name: o.name, value: o.count, itemStyle: { color: chartPalette.categorical[i % chartPalette.categorical.length] },
  }));

  // 近期事件(从 outreach 取最近的)
  const recentEvents: RecentEvent[] = outreachList.slice(0, 8).map((o) => {
    const type = o.action || o.status || '事件';
    const level: 'good' | 'info' | 'warn' | 'bad' =
      o.status === 'ad_running' || o.status === 'ad_authorized' ? 'good' :
      o.status === 'dropped' ? 'bad' :
      o.status === 'video_published' ? 'warn' : 'info';
    return {
      id: o.id,
      date: formatDate(o.event_date || o.created_at),
      type,
      level,
      title: o.message ? o.message.slice(0, 30) + (o.message.length > 30 ? '...' : '') :
        `BD ${o.bd_owner || '-'} 对 #${o.creator_id} ${type}`,
      dept: o.store_name || '—',
    };
  });

  const overviewKpis = [
    { label: '总达人', value: summary?.total_creators ?? creators.data?.total ?? 0, icon: Users, bg: '#e0e7ff', fg: '#4f46e5' },
    { label: '建联事件', value: outreach.data?.total ?? 0, icon: ShoppingCart, bg: '#d1fae5', fg: '#16a34a' },
    { label: 'SKU 总数', value: products.data?.total ?? 0, icon: Wallet, bg: '#cffafe', fg: '#0891b2' },
    { label: '已联系(BD 累计)', value: totalContacted, icon: TrendingUp, bg: '#fed7aa', fg: '#ea580c' },
    { label: '活跃店铺', value: activeDepts, icon: Building2, bg: '#ede9fe', fg: '#7c3aed' },
    { label: '在投视频', value: outreachList.filter((o) => o.video_url).length, icon: Video, bg: '#fce7f3', fg: '#db2777' },
    { label: '近 30 天新达人', value: summary?.recent_30d_creators ?? recentNDays(creatorList as any, 30), icon: ArrowUpRight, bg: '#fef3c7', fg: '#ca8a04' },
    { label: '已放弃', value: statusMap['dropped'] || 0, icon: AlertOctagon, bg: '#fee2e2', fg: '#dc2626' },
  ];

  // 趋势图
  const trendOption = {
    grid: { top: 30, right: 16, bottom: 30, left: 36, containLabel: true },
    xAxis: {
      type: 'category', data: trend30.map((d) => d.date),
      axisLine: { lineStyle: { color: '#e5e6eb' } }, axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 10, interval: 4 },
    },
    yAxis: {
      type: 'value', axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    tooltip: { trigger: 'axis' },
    series: [{
      type: 'line', data: trend30.map((d) => d.count), smooth: true, symbol: 'none',
      lineStyle: { color: '#3370ff', width: 2 },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: 'rgba(51,112,255,0.18)' }, { offset: 1, color: 'rgba(51,112,255,0)' }] } },
    }],
  };

  const deptOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, textStyle: { fontSize: 10 } },
    series: [{
      type: 'pie', radius: ['45%', '70%'], center: ['50%', '42%'],
      label: { show: false }, data: deptContrib,
    }],
  };

  return (
    <AsyncState loading={loading} error={error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
          {overviewKpis.map((k) => (
            <KpiCard key={k.label} label={k.label} value={k.value} icon={k.icon} iconBg={k.bg} iconColor={k.fg} />
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <ChartCard title="近 30 天达人新增" className="lg:col-span-2">
            <EChart option={trendOption} height={280} />
          </ChartCard>
          <ChartCard title="对接人分布 Top 8">
            <EChart option={deptOption} height={280} />
          </ChartCard>
        </div>

        <div className="card">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">最近事件流水</h3>
            <div className="text-xxs text-muted mt-0.5">数据源:outreach (按 created_at desc)</div>
          </div>
          <DataTable columns={eventColumns} data={recentEvents} rowKey={(r) => r.id} compact />
        </div>
      </div>
    </AsyncState>
  );
}
