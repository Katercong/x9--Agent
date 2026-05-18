import type { LucideIcon } from 'lucide-react';
import { ArrowUp, ArrowDown, Minus } from 'lucide-react';
import { cn } from '@/lib/cn';

interface KpiCardProps {
  label: string;
  value: number | string;
  subLabel?: string;
  delta?: number | null;
  deltaLabel?: string;
  icon?: LucideIcon;
  iconBg?: string;
  iconColor?: string;
  compact?: boolean;
  hero?: boolean;
}

export function KpiCard({
  label, value, subLabel, delta, deltaLabel = '较昨日',
  icon: Icon, iconBg, iconColor, compact = false, hero = false,
}: KpiCardProps) {
  const tone =
    delta === undefined || delta === null ? 'flat' :
    delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat';

  const TrendIcon = tone === 'up' ? ArrowUp : tone === 'down' ? ArrowDown : Minus;
  const trendColor = tone === 'up' ? 'text-good' : tone === 'down' ? 'text-bad' : 'text-muted';

  return (
    <div className={cn('card card-body', hero && 'card-body !p-5')}>
      <div className="flex items-start gap-3">
        {Icon && (
          <div
            className={cn('flex items-center justify-center rounded-md shrink-0',
              compact ? 'w-8 h-8' : 'w-11 h-11')}
            style={{ background: iconBg || 'rgb(var(--accent) / 0.18)', color: iconColor || 'rgb(var(--accent))' }}
          >
            <Icon size={compact ? 14 : 18} />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className={cn('text-muted truncate', compact ? 'text-xxs' : 'text-xs')}>{label}</div>
          <div
            className={cn('num font-bold leading-tight',
              hero ? 'text-3xl mt-1' : compact ? 'text-lg mt-0.5' : 'text-2xl mt-1')}
            style={{ color: hero ? 'rgb(var(--accent))' : 'rgb(var(--text))' }}
          >
            {value}
          </div>
          {subLabel && !compact && (
            <div className="text-xxs text-muted mt-1">{subLabel}</div>
          )}
          {delta !== undefined && delta !== null && (
            <div className={cn('flex items-center gap-1 text-xxs mt-1.5', trendColor)}>
              <span className="text-muted">{deltaLabel}</span>
              <TrendIcon size={10} />
              <span className="font-medium">{delta === 0 ? '0%' : Math.abs(delta) + '%'}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
