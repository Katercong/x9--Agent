import { TrendingUp, Users, ShoppingBag, ShoppingCart } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { growthSeries } from '@/mock/company';

export default function Growth() {
  const linesOption = {
    grid: { top: 40, right: 20, bottom: 40, left: 50, containLabel: true },
    legend: { top: 4, textStyle: { fontSize: 11 } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: growthSeries.dates,
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 10, interval: 9 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    series: [
      {
        name: '达人数',
        type: 'line',
        data: growthSeries.creators,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#3370ff', width: 2 },
        itemStyle: { color: '#3370ff' },
        areaStyle: {
          color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: 'rgba(51,112,255,0.15)' }, { offset: 1, color: 'rgba(51,112,255,0)' }] },
        },
      },
      {
        name: 'SKU 数',
        type: 'line',
        data: growthSeries.skus,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#f5a623', width: 2 },
        itemStyle: { color: '#f5a623' },
      },
      {
        name: '订单数',
        type: 'line',
        data: growthSeries.orders,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#16a34a', width: 2 },
        itemStyle: { color: '#16a34a' },
      },
    ],
  };

  const calendarOption = {
    tooltip: { formatter: '{c}%' },
    visualMap: {
      min: -5,
      max: 35,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: { color: ['#fee2e2', '#fef3c7', '#d1fae5', '#16a34a'] },
      text: ['增长高', '下降'],
      textStyle: { fontSize: 11 },
    },
    calendar: {
      top: 36,
      left: 30,
      right: 30,
      cellSize: ['auto', 20],
      range: '2026-04',
      itemStyle: { borderColor: '#fff', borderWidth: 1 },
      yearLabel: { show: false },
      dayLabel: { color: '#86909c', fontSize: 10 },
      monthLabel: { color: '#4e5969', fontSize: 12 },
    },
    series: [
      {
        type: 'heatmap',
        coordinateSystem: 'calendar',
        data: Array.from({ length: 30 }, (_, i) => {
          const day = String(i + 1).padStart(2, '0');
          return [`2026-04-${day}`, Math.floor(Math.random() * 40 - 5)];
        }),
      },
    ],
  };

  const waterfallOption = {
    grid: { top: 30, right: 20, bottom: 30, left: 50, containLabel: true },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: ['月初', '新增', '复购', '流失', '迁移', '月底'],
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: 'bar',
        stack: 'wf',
        itemStyle: { borderColor: 'transparent', color: 'rgba(0,0,0,0)' },
        emphasis: { itemStyle: { borderColor: 'transparent', color: 'rgba(0,0,0,0)' } },
        data: [0, 380, 460, 720, 600, 0],
      },
      {
        type: 'bar',
        stack: 'wf',
        data: [
          { value: 380, itemStyle: { color: '#94a3b8' } },
          { value: 80, itemStyle: { color: '#16a34a' } },
          { value: 260, itemStyle: { color: '#16a34a' } },
          { value: -120, itemStyle: { color: '#ef4444' } },
          { value: -40, itemStyle: { color: '#ef4444' } },
          { value: 560, itemStyle: { color: '#3370ff' } },
        ],
        barWidth: 30,
        label: { show: true, position: 'top', fontSize: 11, color: '#4e5969' },
      },
    ],
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="达人池 + 90d" value="486" delta={28} icon={Users} iconBg="#e0e7ff" iconColor="#4f46e5" />
        <KpiCard label="SKU + 90d" value="44" delta={10} icon={ShoppingBag} iconBg="#cffafe" iconColor="#0891b2" />
        <KpiCard label="订单 + 90d" value="8.4K" delta={26} icon={ShoppingCart} iconBg="#d1fae5" iconColor="#16a34a" />
        <KpiCard label="月环比增长" value="+18%" delta={18} icon={TrendingUp} iconBg="#fed7aa" iconColor="#ea580c" />
      </div>

      <ChartCard title="近 90 天增长趋势 · 达人 / SKU / 订单">
        <EChart option={linesOption} height={300} />
      </ChartCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <ChartCard title="达人池流转 · 本月">
          <EChart option={waterfallOption} height={280} />
        </ChartCard>
        <ChartCard title="日增长率日历 · 4 月">
          <EChart option={calendarOption} height={280} />
        </ChartCard>
      </div>
    </div>
  );
}
