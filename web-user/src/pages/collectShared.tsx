import { useEffect, type ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import type { DailyPoint } from '@/api/collector';

// Per-source signature identity (works on the portal's dark surfaces).
export const ACCENTS = {
  shop: { key: '#FE2C55', dim: 'rgba(254,44,85,0.14)', label: 'TikTok Shop' },
  leads: { key: '#10b981', dim: 'rgba(16,185,129,0.14)', label: 'X9 线索' },
  import: { key: '#f59e0b', dim: 'rgba(245,158,11,0.14)', label: '表格导入' },
  other: { key: '#06b6d4', dim: 'rgba(6,182,212,0.14)', label: '其他' },
} as const;

export type Accent = (typeof ACCENTS)[keyof typeof ACCENTS];

export const CHART_TEXT = '#334155';
export const CHART_AXIS = '#64748b';
export const CHART_GRID = 'rgba(148,163,184,0.22)';
export const CHART_AXIS_LINE = 'rgba(148,163,184,0.38)';

// Inject the staggered load-in keyframes once (self-contained — does not
// touch the portal's shared stylesheet).
let injected = false;
function useRevealStyles() {
  useEffect(() => {
    if (injected) return;
    injected = true;
    const el = document.createElement('style');
    el.textContent =
      '@keyframes crReveal{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}' +
      '.cr-reveal{opacity:0;animation:crReveal .5s cubic-bezier(.22,1,.36,1) forwards}' +
      '@media (prefers-reduced-motion:reduce){.cr-reveal{animation:none;opacity:1}}';
    document.head.appendChild(el);
  }, []);
}

export function Reveal({ i = 0, className, children }: { i?: number; className?: string; children: ReactNode }) {
  useRevealStyles();
  return (
    <div className={`cr-reveal ${className ?? ''}`} style={{ animationDelay: `${i * 70}ms` }}>
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
      <div className="card overflow-hidden">
        <div className="flex items-center gap-4 px-5 py-4">
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: accent.key, color: '#fff', boxShadow: `0 6px 20px ${accent.key}40` }}
          >
            <Icon size={24} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-base font-bold text-text leading-tight">{title}</div>
            <div className="text-xs text-muted mt-0.5 truncate">{subtitle}</div>
          </div>
          {right && <div className="shrink-0">{right}</div>}
        </div>
        <div className="h-1 w-full" style={{ background: accent.key }} />
      </div>
    </Reveal>
  );
}

// 7-day area series tuned for light dashboard cards.
export function dailyAreaOption(daily: DailyPoint[], color: string) {
  return {
    grid: { top: 16, right: 16, bottom: 24, left: 36 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: daily.map((d) => d.date.slice(5)),
      axisLine: { lineStyle: { color: CHART_AXIS_LINE } },
      axisLabel: { fontSize: 11, color: CHART_AXIS },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: CHART_GRID } },
      axisLabel: { fontSize: 11, color: CHART_AXIS },
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
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: color + '55' },
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
