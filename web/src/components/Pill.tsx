import { cn } from '@/lib/cn';
import { colors, statusLabel } from '@/lib/colors';

interface PillProps {
  tone?: 'good' | 'warn' | 'bad' | 'info' | 'muted';
  children: React.ReactNode;
  className?: string;
}

export function Pill({ tone = 'muted', children, className }: PillProps) {
  const toneClass = {
    good: 'bg-green-50 text-green-700',
    warn: 'bg-amber-50 text-amber-700',
    bad: 'bg-red-50 text-red-700',
    info: 'bg-blue-50 text-blue-700',
    muted: 'bg-gray-100 text-gray-600',
  }[tone];
  return (
    <span className={cn('pill', toneClass, className)}>
      {children}
    </span>
  );
}

interface StatusPillProps {
  status: string;
}

export function StatusPill({ status }: StatusPillProps) {
  const color = colors.status[status] || colors.muted;
  return (
    <span
      className="pill"
      style={{
        background: color + '1a',
        color: color,
      }}
    >
      {statusLabel[status] || status}
    </span>
  );
}

interface TierPillProps {
  tier: string;
}

export function TierPill({ tier }: TierPillProps) {
  const color = colors.tier[tier] || colors.muted;
  return (
    <span
      className="pill font-semibold"
      style={{
        background: color + '1a',
        color: color,
      }}
    >
      {tier}
    </span>
  );
}
