import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

type Tone = 'good' | 'warn' | 'bad' | 'info' | 'muted';

interface PillProps {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}

// Tone tints via inline style so this does not depend on which .pill-* utility
// classes happen to exist in the portal stylesheet.
const TONE: Record<Tone, { bg: string; fg: string }> = {
  good: { bg: '#dcfce7', fg: '#15803d' },
  warn: { bg: '#fef3c7', fg: '#b45309' },
  bad: { bg: '#fee2e2', fg: '#b91c1c' },
  info: { bg: '#e0e7ff', fg: '#4338ca' },
  muted: { bg: '#f3f4f6', fg: '#4b5563' },
};

export function Pill({ tone = 'muted', children, className }: PillProps) {
  const t = TONE[tone] ?? TONE.muted;
  return (
    <span className={cn('pill', className)} style={{ background: t.bg, color: t.fg }}>
      {children}
    </span>
  );
}
