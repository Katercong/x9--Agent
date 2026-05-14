import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import {
  LineChart,
  BarChart,
  PieChart,
  ScatterChart,
  FunnelChart,
  HeatmapChart,
  TreemapChart,
  RadarChart,
  GaugeChart,
  SankeyChart,
  CustomChart,
} from 'echarts/charts';
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  DatasetComponent,
  TransformComponent,
  ToolboxComponent,
  DataZoomComponent,
  MarkLineComponent,
  MarkAreaComponent,
  VisualMapComponent,
  PolarComponent,
  CalendarComponent,
  GraphicComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { mergeChartOption } from '@/lib/chart-defaults';

echarts.use([
  LineChart,
  BarChart,
  PieChart,
  ScatterChart,
  FunnelChart,
  HeatmapChart,
  TreemapChart,
  RadarChart,
  GaugeChart,
  SankeyChart,
  CustomChart,
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  DatasetComponent,
  TransformComponent,
  ToolboxComponent,
  DataZoomComponent,
  MarkLineComponent,
  MarkAreaComponent,
  VisualMapComponent,
  PolarComponent,
  CalendarComponent,
  GraphicComponent,
  CanvasRenderer,
]);

interface EChartProps {
  option: any;
  height?: number | string;
  className?: string;
}

export function EChart({ option, height = 280, className }: EChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chartRef.current = chart;
    chart.setOption(mergeChartOption(option));

    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);
    const ro = new ResizeObserver(handleResize);
    ro.observe(ref.current);

    return () => {
      window.removeEventListener('resize', handleResize);
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.setOption(mergeChartOption(option), true);
    }
  }, [option]);

  return (
    <div
      ref={ref}
      className={className}
      style={{ width: '100%', height: typeof height === 'number' ? `${height}px` : height }}
    />
  );
}
