import type { LucideIcon } from 'lucide-react';

interface SectionPlaceholderProps {
  icon: LucideIcon;
  title: string;
  description: string;
  accent?: string;
  phaseNote?: string;
}

/**
 * Portal section landing for lead pages whose full functionality lands in a
 * later phase. Renders a themed empty-state instead of dead-linking the menu.
 */
export default function SectionPlaceholder({
  icon: Icon,
  title,
  description,
  accent = '#22d3ee',
  phaseNote = '数据接入与完整功能将在后续阶段交付（采集打通后自动填充）。',
}: SectionPlaceholderProps) {
  return (
    <div className="flex min-h-[420px] items-center justify-center">
      <div className="card card-body max-w-md text-center">
        <div
          className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl"
          style={{ background: `${accent}22`, color: accent }}
        >
          <Icon size={28} />
        </div>
        <h2 className="text-lg font-bold text-text">{title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted">{description}</p>
        <p className="mt-4 rounded-lg px-4 py-3 text-xs leading-relaxed text-muted" style={{ background: 'rgb(var(--bg-elev-2) / 0.5)' }}>
          {phaseNote}
        </p>
      </div>
    </div>
  );
}
