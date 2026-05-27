import { TrendingUp, Users, ShoppingBag, ShoppingCart, UserCheck } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { AsyncState } from '@/components/states/States';
import { useAnalyticsCompanyGrowth, useProducts, useDepartmentDashboardSummary } from '@/hooks/useApi';

export default function Growth() {
  const growth = useAnalyticsCompanyGrowth(90);
  const products = useProducts({ limit: 1 });
  const dashboard = useDepartmentDashboardSummary();

  const loading = growth.isLoading || products.isLoading || dashboard.isLoading;
  const error = growth.error || products.error || dashboard.error;

  const analytics = growth.data;
  const trendRows = analytics?.trend ?? [];
  const summary = analytics?.summary;
  const dashboardSummary = dashboard.data?.summary;

  const totalProcessedInWindow = trendRows.reduce((sum, row) => sum + row.processed, 0);
  const totalSentInWindow = trendRows.reduce((sum, row) => sum + row.sent, 0);
  const totalPartneredInWindow = trendRows.reduce((sum, row) => sum + row.partnered, 0);
  const conversionPct = totalSentInWindow > 0 ? ((totalPartneredInWindow / totalSentInWindow) * 100).toFixed(1) : '0';

  const linesOption = {
    grid: { top: 40, right: 20, bottom: 30, left: 50, containLabel: true },
    legend: { top: 4, textStyle: { fontSize: 11 } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category', data: trendRows.map((d) => d.date.slice(5)),
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
        name: '处理入库', type: 'line', data: trendRows.map((d) => d.processed),
        smooth: true, symbol: 'none', lineStyle: { color: '#3370ff', width: 2 },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: 'rgba(51,112,255,0.15)' }, { offset: 1, color: 'rgba(51,112,255,0)' }] } },
      },
      {
        name: '推荐', type: 'line', data: trendRows.map((d) => d.recommended),
        smooth: true, symbol: 'none', lineStyle: { color: '#8b5cf6', width: 2 },
      },
      {
        name: '已发送', type: 'line', data: trendRows.map((d) => d.sent),
        smooth: true, symbol: 'none', lineStyle: { color: '#f5a623', width: 2 },
      },
      {
        name: '合作', type: 'line', data: trendRows.map((d) => d.partnered),
        smooth: true, symbol: 'none', lineStyle: { color: '#16a34a', width: 2 },
      },
    ],
  };

  const dailyOption = {
    grid: { top: 30, right: 20, bottom: 30, left: 36, containLabel: true },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category', data: trendRows.slice(-30).map((d) => d.date.slice(5)),
      axisLine: { lineStyle: { color: '#e5e6eb' } }, axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 10, interval: 2 },
    },
    yAxis: {
      type: 'value', splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false }, axisTick: { show: false },
    },
    series: [
      {
        name: '处理入库', type: 'bar', data: trendRows.slice(-30).map((d) => d.processed),
        barWidth: 8, itemStyle: { color: '#3370ff', borderRadius: [2, 2, 0, 0] },
      },
      {
        name: '已发送', type: 'bar', data: trendRows.slice(-30).map((d) => d.sent),
        barWidth: 8, itemStyle: { color: '#16a34a', borderRadius: [2, 2, 0, 0] },
      },
    ],
  };

  return (
    <AsyncState loading={loading} error={error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <KpiCard label="总发现量" value={dashboardSummary?.total_creators ?? summary?.total_creators ?? 0} icon={Users} iconBg="#e0e7ff" iconColor="#4f46e5" />
          <KpiCard label="去重达人主档" value={summary?.processed_creators ?? dashboardSummary?.processed_creators ?? 0} icon={UserCheck} iconBg="#dcfce7" iconColor="#16a34a" />
          <KpiCard label="SKU 总数" value={products.data?.total ?? 0} icon={ShoppingBag} iconBg="#cffafe" iconColor="#0891b2" />
          <KpiCard label="90 日入库" value={totalProcessedInWindow} icon={ShoppingCart} iconBg="#d1fae5" iconColor="#16a34a" />
          <KpiCard label="合作转化" value={`${conversionPct}%`} icon={TrendingUp} iconBg="#fed7aa" iconColor="#ea580c" />
        </div>

        <ChartCard title="公司成长 KPI · 入库 / 推荐 / 发送 / 合作">
          <EChart option={linesOption} height={300} />
        </ChartCard>

        <ChartCard title="近 30 天每日处理入库 vs 建联发送">
          <EChart option={dailyOption} height={280} />
        </ChartCard>
      </div>
    </AsyncState>
  );
}
