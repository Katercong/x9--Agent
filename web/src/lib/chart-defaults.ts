import { chartPalette } from './colors';

export const baseChartOption: any = {
  color: chartPalette.categorical,
  textStyle: {
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif',
    fontSize: 12,
    color: '#4e5969',
  },
  grid: { top: 30, right: 20, bottom: 30, left: 40, containLabel: true },
  tooltip: {
    backgroundColor: 'rgba(31, 31, 46, 0.92)',
    borderColor: 'transparent',
    textStyle: { color: '#fff', fontSize: 12 },
    padding: [8, 12],
  },
  legend: {
    icon: 'circle',
    itemWidth: 8,
    itemHeight: 8,
    textStyle: { color: '#86909c', fontSize: 12 },
  },
};

export function mergeChartOption(opt: any): any {
  return {
    ...baseChartOption,
    ...opt,
    textStyle: { ...(baseChartOption.textStyle || {}), ...(opt.textStyle || {}) },
  };
}
