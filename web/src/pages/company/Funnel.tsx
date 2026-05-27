import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { AsyncState } from '@/components/states/States';
import { useDepartmentDashboardSummary } from '@/hooks/useApi';
import { chartPalette } from '@/lib/colors';

export default function Funnel() {
  const { data, isLoading, error } = useDepartmentDashboardSummary();
  const funnel = ((data?.stage_rows?.length ? data.stage_rows : data?.overview) ?? [])
    .map((row) => ({ name: row.name, value: row.count, key: row.key }));

  const totalProspect = funnel[0]?.value || 1;

  const funnelOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'funnel', left: '10%', top: 20, bottom: 20, width: '80%',
      minSize: '10%', maxSize: '100%', sort: 'descending', gap: 2,
      label: { show: true, position: 'inside', color: '#fff', fontSize: 12, fontWeight: 500 },
      labelLine: { length: 10, lineStyle: { width: 1, type: 'solid' } },
      data: funnel.map((d, i) => ({ name: d.name, value: d.value, itemStyle: { color: chartPalette.categorical[i] } })),
    }],
  };

  // 流转柱图
  const dropOption = {
    grid: { top: 30, right: 20, bottom: 50, left: 60, containLabel: true },
    tooltip: { trigger: 'axis' },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    xAxis: {
      type: 'category',
      data: funnel.map((d) => d.name),
      axisLine: { lineStyle: { color: '#e5e6eb' } }, axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 10, rotate: 20 },
    },
    yAxis: {
      type: 'value', splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLine: { show: false }, axisTick: { show: false },
    },
    series: [
      {
        name: '当前人数', type: 'bar', data: funnel.map((d) => d.value),
        barWidth: 28, itemStyle: { color: '#3370ff', borderRadius: [3, 3, 0, 0] },
        label: { show: true, position: 'top', fontSize: 11, color: '#4e5969' },
      },
    ],
  };

  return (
    <AsyncState loading={isLoading} error={error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: '潜在线索', value: funnel[0]?.value || 0, sub: '起始池' },
            { label: '已确认', value: funnel[2]?.value || 0, sub: '占总 ' + (((funnel[2]?.value || 0) / totalProspect) * 100).toFixed(1) + '%' },
            { label: '视频已发', value: funnel[5]?.value || 0, sub: '占总 ' + (((funnel[5]?.value || 0) / totalProspect) * 100).toFixed(1) + '%' },
            { label: '广告投放中', value: funnel[7]?.value || 0, sub: '占总 ' + (((funnel[7]?.value || 0) / totalProspect) * 100).toFixed(1) + '%' },
          ].map((k) => (
            <div key={k.label} className="card card-body">
              <div className="text-xs text-muted">{k.label}</div>
              <div className="text-3xl num font-bold mt-1">{k.value.toLocaleString()}</div>
              <div className="text-xxs text-muted mt-1">{k.sub}</div>
            </div>
          ))}
        </div>

        <ChartCard title="8 阶段转化漏斗" extra={<span>基于 creator.current_status</span>}>
          <EChart option={funnelOption} height={420} />
        </ChartCard>

        <ChartCard title="各阶段达人数">
          <EChart option={dropOption} height={280} />
        </ChartCard>
      </div>
    </AsyncState>
  );
}
