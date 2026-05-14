import type { LucideIcon } from 'lucide-react';
import { ArrowUp, ArrowDown, Minus } from 'lucide-react';
import { cn } from '@/lib/cn';

interface KpiCardProps {
  label: string;
  value: number | string;
  subLabel?: string;
  delta?: number | null;
  deltaLabel?: string;
  icon: LucideIcon;
  iconBg: string;
  iconColor: string;
  compact?: boolean;
}

export function KpiCard({
  label,
  value,
  subLabel,
  delta,
  deltaLabel = '较昨日',
  icon: Icon,
  iconBg,
  iconColor,
  compact = false,
}: KpiCardProps) {
  const tone =
    delta === undefined || delta === null
      ? 'flat'
      : delta > 0
      ? 'up'
      : delta < 0
      ? 'down'
      : 'flat';

  const TrendIcon = tone === 'up' ? ArrowUp : tone === 'down' ? ArrowDown : Minus;
  const trendColor = tone === 'up' ? 'text-bad' : tone === 'down' ? 'text-good' : 'text-muted';
  // 注:按参考图,达人数据"增长用红色↑、下降用绿色↓"反直觉但是国内中后台常见(BD 中"上升=成本/任务增加")
  // 这里改为常规色:up=good (green), down=bad (red)
  const trendColorNormal = tone === 'up' ? 'text-good' : tone === 'down' ? 'text-bad' : 'text-muted';

  return (
    <div className={cn('card', compact ? 'card-body !p-3' : 'card-body')}>
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'kpi-icon',
            compact ? 'w-8 h-8' : 'w-12 h-12',
          )}
          style={{ background: iconBg, color: iconColor }}
        >
          <Icon size={compact ? 16 : 22} />
        </div>
        <div className="min-w-0 flex-1">
          <div className={cn('text-muted truncate', compact ? 'text-xxs' : 'text-xs')}>
            {label}
          </div>
          <div
            className={cn(
              'num font-bold text-gray-900 leading-tight',
              compact ? 'text-xl mt-0.5' : 'text-3xl mt-1',
            )}
          >
            {value}
          </div>
          {subLabel && !compact && (
            <div className="text-xxs text-muted mt-1">{subLabel}</div>
          )}
          {delta !== undefined && delta !== null && (
            <div className={cn('flex items-center gap-1 text-xxs mt-1.5', trendColorNormal)}>
              <span className="text-muted">{deltaLabel}</span>
              <TrendIcon size={10} />
              <span className="font-medium">{delta === 0 ? '0%' : Math.abs(delta) + '%'}</span>
              {tone === 'flat' && <span className="text-muted">—</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface KpiGroupProps {
  items: Array<Omit<KpiCardProps, 'compact'>>;
  cols?: 3 | 4 | 5 | 6;
  compact?: boolean;
}

export function KpiGroup({ items, cols = 5, compact = false }: KpiGroupProps) {
  const colsClass = {
    3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
    4: 'grid-cols-2 lg:grid-cols-4',
    5: 'grid-cols-2 lg:grid-cols-3 xl:grid-cols-5',
    6: 'grid-cols-2 lg:grid-cols-3 xl:grid-cols-6',
  }[cols];

  return (
    <div className={cn('grid gap-3', colsClass)}>
      {items.map((item, i) => (
        <KpiCard key={i} {...item} compact={compact} />
      ))}
    </div>
  );
}
