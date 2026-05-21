import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import type { DailyPoint } from '@/api/collector';

// Per-source signature identity so the three dashboards never blur together.
export const ACCENTS = {
  shop: { key: '#FE2C55', soft: '#FFE5EC', ink: '#161823', label: 'TikTok Shop' },
  leads: { key: '#10b981', soft: '#d1fae5', ink: '#064e3b', label: 'X9 线索' },
  import: { key: '#f59e0b', soft: '#fef3c7', ink: '#78350f', label: '表格导入' },
} as const;

export type Accent = (typeof ACCENTS)[keyof typeof ACCENTS];

// Staggered reveal — one orchestrated page load-in (.collect-reveal in index.css).
export function Reveal({ i = 0, className, children }: { i?: number; className?: string; children: ReactNode }) {
  return (
    <div className={`collect-reveal ${className ?? ''}`} style={{ animationDelay: `${i * 70}ms` }}>
      {children}
    </div>
  );
}

export function CollectHeader({
  accent,
  icon: Icon,
  title,
  subtitle,
  right,
}: {
  accent: Accent;
  icon: LucideIcon;
  title: string;
  subtitle: string;
  right?: ReactNode;
}) {
  return (
    <Reveal i={0}>
      <div
        className="card overflow-hidden relative"
        style={{ background: `linear-gradient(110deg, ${accent.ink} 0%, ${accent.ink} 38%, #ffffff 38.2%)` }}
      >
        <div className="flex items-center gap-4 px-5 py-4">
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: accent.key, color: '#fff', boxShadow: `0 6px 18px ${accent.key}55` }}
          >
            <Icon size={24} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-base font-bold text-gray-900 leading-tight">{title}</div>
            <div className="text-xs text-muted mt-0.5 truncate">{subtitle}</div>
          </div>
          {right && <div className="shrink-0">{right}</div>}
        </div>
        <div className="h-1 w-full" style={{ background: accent.key }} />
      </div>
    </Reveal>
  );
}

// Smooth 7-day area series in the source's signature colour.
export function dailyAreaOption(daily: DailyPoint[], color: string) {
  return {
    grid: { top: 16, right: 16, bottom: 24, left: 36 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: daily.map((d) => d.date.slice(5)),
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisLabel: { fontSize: 11, color: '#86909c' },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } },
      axisLabel: { fontSize: 11, color: '#86909c' },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        data: daily.map((d) => d.count),
        lineStyle: { color, width: 2.5 },
        itemStyle: { color },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: color + '40' },
              { offset: 1, color: color + '00' },
            ],
          },
        },
      },
    ],
  };
}

export function num(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '0';
  return new Intl.NumberFormat('en-US').format(n);
}
