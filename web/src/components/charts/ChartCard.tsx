import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

interface ChartCardProps {
  title: string;
  extra?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function ChartCard({ title, extra, className, children }: ChartCardProps) {
  return (
    <div className={cn('card', className)}>
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
        {extra && <div className="text-xs text-muted">{extra}</div>}
      </div>
      <div className="px-2 pb-3">{children}</div>
    </div>
  );
}
