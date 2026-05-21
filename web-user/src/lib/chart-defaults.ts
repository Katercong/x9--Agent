const accent = '#06b6d4';
const accentSoft = 'rgba(6, 182, 212, 0.18)';

export const baseChartOption: any = {
  color: [accent, '#3b82f6', '#8b5cf6', '#22c55e', '#f59e0b', '#ef4444', '#ec4899', '#84cc16'],
  textStyle: {
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
    fontSize: 12,
    color: '#8691a2',
  },
  grid: { top: 30, right: 20, bottom: 30, left: 40, containLabel: true },
  tooltip: {
    backgroundColor: 'rgba(11, 13, 18, 0.92)',
    borderColor: '#262f40',
    borderWidth: 1,
    textStyle: { color: '#ecf0f8', fontSize: 12 },
    padding: [8, 12],
  },
  legend: {
    icon: 'circle', itemWidth: 8, itemHeight: 8,
    textStyle: { color: '#8691a2', fontSize: 12 },
  },
};

export const chartColors = {
  accent,
  accentSoft,
  good: '#22c55e',
  warn: '#f59e0b',
  bad: '#ef4444',
  muted: '#8691a2',
  border: '#262f40',
  dashed: 'rgba(38, 47, 64, 0.5)',
};

export function mergeChartOption(opt: any): any {
  const merged = {
    ...baseChartOption,
    ...opt,
    textStyle: { ...(baseChartOption.textStyle || {}), ...(opt.textStyle || {}) },
  };
  if (opt.tooltip) {
    merged.tooltip = {
      ...(baseChartOption.tooltip || {}),
      ...opt.tooltip,
      textStyle: {
        ...(baseChartOption.tooltip?.textStyle || {}),
        ...(opt.tooltip.textStyle || {}),
      },
    };
  }
  if (opt.legend) {
    merged.legend = {
      ...(baseChartOption.legend || {}),
      ...opt.legend,
      textStyle: {
        ...(baseChartOption.legend?.textStyle || {}),
        ...(opt.legend.textStyle || {}),
      },
    };
  }
  return merged;
}
