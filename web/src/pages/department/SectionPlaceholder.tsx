import type { LucideIcon } from 'lucide-react';

interface SectionPlaceholderProps {
  icon: LucideIcon;
  title: string;
  description: string;
  accent?: string;
  phaseNote?: string;
}

/**
 * Lightweight section landing used by lead-management pages whose full CRUD
 * lands in a later phase. Renders a styled empty-state rather than dead-linking
 * the menu entry, so the foreign-trade information architecture is complete.
 */
export default function SectionPlaceholder({
  icon: Icon,
  title,
  description,
  accent = '#6d28d9',
  phaseNote = '数据接入与完整管理功能将在后续阶段交付（采集打通后自动填充）。',
}: SectionPlaceholderProps) {
  return (
    <div className="flex min-h-[420px] items-center justify-center">
      <div className="max-w-md rounded-xl border border-line bg-white px-8 py-10 text-center shadow-card">
        <div
          className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl"
          style={{ background: `${accent}1a`, color: accent }}
        >
          <Icon size={28} />
        </div>
        <h2 className="text-lg font-bold text-gray-900">{title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted">{description}</p>
        <p className="mt-4 rounded-lg bg-stone-50 px-4 py-3 text-xs leading-relaxed text-stone-500">{phaseNote}</p>
      </div>
    </div>
  );
}
