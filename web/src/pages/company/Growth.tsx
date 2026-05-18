import { TrendingUp, Users, ShoppingBag, ShoppingCart } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { AsyncState } from '@/components/states/States';
import { useCreators, useOutreach, useProducts } from '@/hooks/useApi';
import { trendByDay, recentNDays } from '@/lib/derive';

export default function Growth() {
  const creators = useCreators({ limit: 1000 });
  const outreach = useOutreach({ limit: 1000 });
  const products = useProducts({ limit: 200 });

  const loading = creators.isLoading || outreach.isLoading || products.isLoading;
  const error = creators.error || outreach.error;

  const creatorList = creators.data?.items ?? [];
  const outreachList = outreach.data?.items ?? [];
  const productList = products.data?.items ?? [];

  // 90 天分段:实际数据可能不足 90 天,会自动只显示有数据的部分
  const trend90Creator = trendByDay(creatorList as any, 60);
  const trend90Outreach = trendByDay(outreachList as any, 60);

  // 累积统计
  const today30Creator = recentNDays(creatorList as any, 30);
  const today30Outreach = recentNDays(outreachList as any, 30);

  // 累积折线(从0开始累加新增)
  let cumCreator = (creators.data?.total ?? 0) - today30Creator;
  let cumOutreach = (outreach.data?.total ?? 0) - today30Outreach;
  const cumCreatorSeries = trend90Creator.map((d) => { cumCreator += d.count; return cumCreator; });
  const cumOutreachSeries = trend90Outreach.map((d) => { cumOutreach += d.count; return cumOutreach; });

  const linesOption = {
    grid: { top: 40, right: 20, bottom: 30, left: 50, containLabel: true },
    legend: { top: 4, textStyle: { fontSize: 11 } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category', data: trend90Creator.map((d) => d.date),
      axisLine: { lineStyle: { color: '#e5e6eb' } }, axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 10, interval: 5 },
    },
    yAxis: {
      type: 'value', splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    series: [
      {
        name: '累计达人', type: 'line', data: cumCreatorSeries,
        smooth: true, symbol: 'none', lineStyle: { color: '#3370ff', width: 2 },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: 'rgba(51,112,255,0.15)' }, { offset: 1, color: 'rgba(51,112,255,0)' }] } },
      },
      {
        name: '累计建联事件', type: 'line', data: cumOutreachSeries,
        smooth: true, symbol: 'none', lineStyle: { color: '#f5a623', width: 2 },
      },
    ],
  };

  // 日增长柱图(只创建者)
  const dailyOption = {
    grid: { top: 30, right: 20, bottom: 30, left: 36, containLabel: true },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category', data: trend90Creator.slice(-30).map((d) => d.date),
      axisLine: { lineStyle: { color: '#e5e6eb' } }, axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 10, interval: 2 },
    },
    yAxis: {
      type: 'value', splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false }, axisTick: { show: false },
    },
    series: [
      {
        name: '新增达人', type: 'bar', data: trend90Creator.slice(-30).map((d) => d.count),
        barWidth: 8, itemStyle: { color: '#3370ff', borderRadius: [2, 2, 0, 0] },
      },
      {
        name: '新增建联', type: 'bar', data: trend90Outreach.slice(-30).map((d) => d.count),
        barWidth: 8, itemStyle: { color: '#16a34a', borderRadius: [2, 2, 0, 0] },
      },
    ],
  };

  const growth30Pct = creators.data?.total
    ? ((today30Creator / (creators.data.total - today30Creator || 1)) * 100).toFixed(1)
    : '0';

  return (
    <AsyncState loading={loading} error={error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard label="达人总数" value={creators.data?.total ?? 0} icon={Users} iconBg="#e0e7ff" iconColor="#4f46e5" />
          <KpiCard label="SKU 总数" value={products.data?.total ?? 0} icon={ShoppingBag} iconBg="#cffafe" iconColor="#0891b2" />
          <KpiCard label="建联事件" value={outreach.data?.total ?? 0} icon={ShoppingCart} iconBg="#d1fae5" iconColor="#16a34a" />
          <KpiCard label="30 日增长" value={`+${growth30Pct}%`} icon={TrendingUp} iconBg="#fed7aa" iconColor="#ea580c" />
        </div>

        <ChartCard title="近 60 天累计趋势 · 达人 / 建联">
          <EChart option={linesOption} height={300} />
        </ChartCard>

        <ChartCard title="近 30 天每日新增 · 达人 vs 建联">
          <EChart option={dailyOption} height={280} />
        </ChartCard>
      </div>
    </AsyncState>
  );
}
