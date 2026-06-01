import {
  Building2, Users, Heart, UserPlus, Star, Handshake, Flame,
  Inbox, MessageSquare, Mail, CheckCircle2, XCircle, Globe2, Briefcase,
} from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { AsyncState, Empty } from '@/components/states/States';
import { useForeignTradeDashboard } from '@/api/foreignTrade';

const topKpiIcons = [Building2, Users, Heart, UserPlus, Star, Handshake, Flame];
const topKpiBg = ['#e0e7ff', '#d1fae5', '#fce7f3', '#cffafe', '#fef3c7', '#ede9fe', '#fee2e2'];
const topKpiFg = ['#4f46e5', '#16a34a', '#db2777', '#0891b2', '#ca8a04', '#7c3aed', '#dc2626'];

const overviewIcons = [Inbox, MessageSquare, Mail, CheckCircle2, XCircle, Globe2, Briefcase];
const overviewBg = ['#dbeafe', '#dcfce7', '#fef3c7', '#dcfce7', '#f3f4f6', '#cffafe', '#ede9fe'];
const overviewFg = ['#2563eb', '#16a34a', '#ca8a04', '#16a34a', '#6b7280', '#0891b2', '#7c3aed'];

const tierColors: Record<string, string> = { A: '#16a34a', B: '#3370ff', C: '#f59e0b', unrated: '#94a3b8' };

function num(n: unknown): string {
  const v = typeof n === 'number' ? n : Number(n);
  return Number.isFinite(v) ? new Intl.NumberFormat('en-US').format(v) : '0';
}

function formatDay(value: string) {
  const parts = value.split('-');
  if (parts.length !== 3) return value;
  return `${Number(parts[1])}/${Number(parts[2])}`;
}

export default function Business() {
  const dashboardQ = useForeignTradeDashboard();
  const data = dashboardQ.data;
  const summary = data?.summary ?? {
    total_company_leads: 0, total_talent_leads: 0, total_social_leads: 0,
    today_new: 0, tier_a: 0, contacted: 0, high_intent: 0, us_market: 0, social_contacts: 0,
  };
  const statusByKey = Object.fromEntries((data?.status_rows ?? []).map((row) => [row.key, row.count]));
  const sourceRows = data?.source_rows ?? [];
  const tierRows = (data?.tier_rows ?? []).filter((row) => row.count > 0);
  const platformRows = data?.platform_rows?.length ? data.platform_rows : [{ name: '未填写', value: 0 }];
  const trend7 = data?.trend_7d ?? [];

  const topRow = [
    { label: '总公司客户线索', value: summary.total_company_leads },
    { label: '总跨境人才', value: summary.total_talent_leads },
    { label: '总社媒线索', value: summary.total_social_leads },
    { label: '今日新增', value: summary.today_new },
    { label: 'A 级线索', value: summary.tier_a },
    { label: '已联系', value: summary.contacted },
    { label: '高意向客户', value: summary.high_intent },
  ];

  const overview = [
    { label: '新线索', value: statusByKey.new || 0 },
    { label: '沟通中', value: statusByKey.contacted || 0 },
    { label: '已回复', value: statusByKey.replied || 0 },
    { label: '已签约', value: statusByKey.signed || 0 },
    { label: '已放弃', value: statusByKey.dropped || 0 },
    { label: '美区线索', value: summary.us_market },
    { label: '社媒联系方式', value: summary.social_contacts },
  ];

  const donutData = tierRows.map((row) => ({ name: row.name, value: row.count, color: tierColors[row.key] || '#94a3b8' }));
  const donutTotal = donutData.reduce((sum, row) => sum + row.value, 0);

  const trendOption = {
    grid: { top: 30, right: 16, bottom: 30, left: 36, containLabel: true },
    xAxis: {
      type: 'category', data: trend7.map((d) => formatDay(d.date)),
      axisLine: { lineStyle: { color: 'rgba(134,145,162,0.35)' } }, axisTick: { show: false },
      axisLabel: { color: 'rgba(255,255,255,0.58)', fontSize: 11 },
    },
    yAxis: {
      type: 'value', splitNumber: 4, axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: 'rgba(134,145,162,0.18)', type: 'dashed' } },
      axisLabel: { color: 'rgba(255,255,255,0.58)', fontSize: 11 },
    },
    tooltip: { trigger: 'axis' },
    series: [{
      type: 'line', data: trend7.map((d) => d.count), smooth: true, symbol: 'circle', symbolSize: 6,
      lineStyle: { color: '#22d3ee', width: 2 },
      itemStyle: { color: '#22d3ee', borderColor: '#0f172a', borderWidth: 2 },
      label: { show: true, position: 'top', color: '#22d3ee', fontSize: 11, fontWeight: 600 },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(34,211,238,0.20)' }, { offset: 1, color: 'rgba(34,211,238,0)' }] } },
    }],
  };

  const donutOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: {
      type: 'scroll', orient: 'vertical', right: '2%', top: 'center', icon: 'circle',
      itemWidth: 8, itemGap: 10, textStyle: { color: 'rgba(255,255,255,0.72)', fontSize: 11 },
    },
    series: [{
      type: 'pie', radius: ['58%', '78%'], center: ['28%', '50%'], label: { show: false }, labelLine: { show: false },
      data: donutData.map((row) => ({ name: row.name, value: row.value, itemStyle: { color: row.color } })),
    }],
    graphic: [
      { type: 'text', left: '28%', top: '42%', style: { text: '总计', textAlign: 'center', fontSize: 12, fill: 'rgba(255,255,255,0.58)' } },
      { type: 'text', left: '28%', top: '52%', style: { text: String(donutTotal), textAlign: 'center', fontSize: 22, fontWeight: 700, fill: '#fff' } },
    ],
  };

  const platformOption = {
    grid: { top: 10, right: 24, bottom: 30, left: 88, containLabel: true },
    xAxis: {
      type: 'value', splitLine: { lineStyle: { color: 'rgba(134,145,162,0.18)', type: 'dashed' } },
      axisLabel: { color: 'rgba(255,255,255,0.58)', fontSize: 11 }, axisLine: { show: false }, axisTick: { show: false },
    },
    yAxis: {
      type: 'category', data: platformRows.map((d) => d.name).reverse(),
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: 'rgba(255,255,255,0.72)', fontSize: 12 },
    },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [{
      type: 'bar', data: platformRows.map((d) => d.value).reverse(), barWidth: 14,
      itemStyle: { color: '#3b82f6', borderRadius: [0, 3, 3, 0] },
      label: { show: true, position: 'right', color: 'rgba(255,255,255,0.72)', fontSize: 11, fontWeight: 500 },
    }],
  };

  const sourceIcons = [Briefcase, Heart, Mail];
  const sourceBg = ['#ede9fe', '#fce7f3', '#dbeafe'];
  const sourceFg = ['#7c3aed', '#db2777', '#2563eb'];

  return (
    <AsyncState loading={dashboardQ.isLoading} error={dashboardQ.error} height={420}>
      <div className="space-y-4">
        <div className="text-xs text-muted">
          范围: {data?.scope?.department_code || '当前部门'} · 数据源: /api/local/foreign-trade/dashboard ·
          生成时间: {data?.generated_at ? new Date(data.generated_at).toLocaleString() : '-'}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-7 gap-3">
          {topRow.map((item, i) => (
            <KpiCard
              key={item.label}
              label={item.label}
              value={num(item.value)}
              icon={topKpiIcons[i]}
              iconBg={topKpiBg[i]}
              iconColor={topKpiFg[i]}
            />
          ))}
        </div>

        <div className="pt-1">
          <h3 className="sec-title">业务概览</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            {overview.map((item, i) => (
              <KpiCard
                key={item.label}
                label={item.label}
                value={num(item.value)}
                icon={overviewIcons[i % overviewIcons.length]}
                iconBg={overviewBg[i % overviewBg.length]}
                iconColor={overviewFg[i % overviewFg.length]}
                compact
              />
            ))}
          </div>
        </div>

        <div className="pt-1">
          <h3 className="sec-title">采集来源拆分</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {sourceRows.map((item, i) => (
              <KpiCard
                key={item.key}
                label={item.name}
                value={num(item.count)}
                icon={sourceIcons[i % sourceIcons.length]}
                iconBg={sourceBg[i % sourceBg.length]}
                iconColor={sourceFg[i % sourceFg.length]}
                compact
              />
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <ChartCard title="近 7 天采集趋势">
            <EChart option={trendOption} height={240} />
          </ChartCard>
          <ChartCard title="线索分级分布">
            {donutData.length ? <EChart option={donutOption} height={240} /> : <Empty height={240} message="暂无分级数据" />}
          </ChartCard>
          <ChartCard title="平台来源分布">
            {platformRows.length ? <EChart option={platformOption} height={240} /> : <Empty height={240} message="暂无平台数据" />}
          </ChartCard>
        </div>
      </div>
    </AsyncState>
  );
}
