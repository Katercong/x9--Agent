import { cn } from '@/lib/cn';

interface PriorityRow {
  label: string;
  value: number;
  max?: number;
  color?: string;
}

interface PriorityBarProps {
  rows: PriorityRow[];
  labelHeader?: string;
  valueHeader?: string;
  defaultColor?: string;
}

export function PriorityBar({
  rows,
  labelHeader = '优先级',
  valueHeader = '数量',
  defaultColor = '#3370ff',
}: PriorityBarProps) {
  const max = Math.max(...rows.map((r) => r.max ?? r.value), 1);

  return (
    <div className="w-full">
      <div className="grid grid-cols-[80px_1fr_40px] gap-3 text-xxs text-muted px-2 py-2 border-b border-line">
        <span>{labelHeader}</span>
        <span></span>
        <span className="text-right">{valueHeader}</span>
      </div>
      {rows.map((r, i) => (
        <div
          key={i}
          className={cn(
            'grid grid-cols-[80px_1fr_40px] gap-3 items-center px-2 py-2.5',
            i !== rows.length - 1 && 'border-b border-line/60',
          )}
        >
          <span className="text-xs text-gray-700">{r.label}</span>
          <div className="h-1.5 rounded-full bg-[#eef2ff] overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${Math.max(((r.value / max) * 100), 6)}%`,
                background: r.color || defaultColor,
              }}
            />
          </div>
          <span className="text-right text-xs num text-gray-700">{r.value}</span>
        </div>
      ))}
    </div>
  );
}
