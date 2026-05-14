import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { funnelData, funnelStageDetail } from '@/mock/company';
import { chartPalette } from '@/lib/colors';

export default function Funnel() {
  const funnelOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [
      {
        type: 'funnel',
        left: '10%',
        top: 20,
        bottom: 20,
        width: '80%',
        minSize: '10%',
        maxSize: '100%',
        sort: 'descending',
        gap: 2,
        label: { show: true, position: 'inside', color: '#fff', fontSize: 12, fontWeight: 500 },
        labelLine: { length: 10, lineStyle: { width: 1, type: 'solid' } },
        data: funnelData.map((d, i) => ({ ...d, itemStyle: { color: chartPalette.categorical[i] } })),
      },
    ],
  };

  const dropOption = {
    grid: { top: 30, right: 20, bottom: 40, left: 60, containLabel: true },
    tooltip: { trigger: 'axis' },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    xAxis: {
      type: 'category',
      data: funnelStageDetail.map((d) => d.stage),
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 10, rotate: 20 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        name: '流失',
        type: 'bar',
        stack: 's',
        barWidth: 28,
        data: funnelStageDetail.map((d) => d.drop),
        itemStyle: { color: '#ef4444' },
      },
      {
        name: '继续',
        type: 'bar',
        stack: 's',
        data: funnelStageDetail.map((d) => d.retained),
        itemStyle: { color: '#3370ff' },
      },
    ],
  };

  const daysOption = {
    grid: { top: 30, right: 20, bottom: 40, left: 50, containLabel: true },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: funnelStageDetail.map((d) => d.stage),
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 10, rotate: 20 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 11, formatter: '{value} 天' },
    },
    series: [
      {
        type: 'line',
        data: funnelStageDetail.map((d) => d.days),
        smooth: true,
        symbol: 'circle',
        symbolSize: 8,
        lineStyle: { color: '#f5a623', width: 2 },
        itemStyle: { color: '#f5a623' },
        label: { show: true, position: 'top', fontSize: 11, color: '#4e5969', formatter: '{c} 天' },
        areaStyle: {
          color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: 'rgba(245,166,35,0.2)' }, { offset: 1, color: 'rgba(245,166,35,0)' }] },
        },
      },
    ],
  };

  const total = funnelData[0].value;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: '总线索', value: funnelData[0].value, sub: '近 30 天' },
          { label: '已签收样品', value: funnelData[4].value, sub: '占总 ' + ((funnelData[4].value / total) * 100).toFixed(1) + '%' },
          { label: '视频已发', value: funnelData[5].value, sub: '占总 ' + ((funnelData[5].value / total) * 100).toFixed(1) + '%' },
          { label: '广告投放中', value: funnelData[7].value, sub: '占总 ' + ((funnelData[7].value / total) * 100).toFixed(1) + '%' },
        ].map((k) => (
          <div key={k.label} className="card card-body">
            <div className="text-xs text-muted">{k.label}</div>
            <div className="text-3xl num font-bold mt-1">{k.value.toLocaleString()}</div>
            <div className="text-xxs text-muted mt-1">{k.sub}</div>
          </div>
        ))}
      </div>

      <ChartCard title="全公司 8 阶段转化漏斗">
        <EChart option={funnelOption} height={420} />
      </ChartCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <ChartCard title="各阶段流失 vs 继续">
          <EChart option={dropOption} height={280} />
        </ChartCard>
        <ChartCard title="各阶段平均时长(天)">
          <EChart option={daysOption} height={280} />
        </ChartCard>
      </div>
    </div>
  );
}
