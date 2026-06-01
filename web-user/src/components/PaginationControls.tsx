import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { Language } from '@/lib/i18n';

type PaginationControlsProps = {
  page: number;
  pageSize: number;
  total: number;
  currentCount?: number;
  loading?: boolean;
  language?: Language;
  onPageChange: (page: number) => void;
};

const numberFmt: Record<Language, Intl.NumberFormat> = {
  zh: new Intl.NumberFormat('zh-CN'),
  en: new Intl.NumberFormat('en-US'),
};

export function PaginationControls({
  page,
  pageSize,
  total,
  currentCount = pageSize,
  loading = false,
  language = 'zh',
  onPageChange,
}: PaginationControlsProps) {
  const start = total === 0 ? 0 : page * pageSize + 1;
  const end = Math.min(page * pageSize + currentCount, total);
  const hasPrev = page > 0;
  const hasNext = (page + 1) * pageSize < total;
  const fmt = numberFmt[language];
  const labels = language === 'zh'
    ? { perPage: '每页', prev: '上一页', next: '下一页' }
    : { perPage: 'Per page', prev: 'Previous', next: 'Next' };
  const pageLabel = language === 'zh' ? `第 ${fmt.format(page + 1)} 页` : `Page ${fmt.format(page + 1)}`;

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-elev1 px-3 py-2">
      <div className="text-xs text-muted">
        {pageLabel} · {fmt.format(start)}-{fmt.format(end)} / {fmt.format(total)} · {labels.perPage} {fmt.format(pageSize)}
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(0, page - 1))}
          disabled={!hasPrev || loading}
          className="btn btn-ghost !h-8 text-xs disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ChevronLeft size={13} /> {labels.prev}
        </button>
        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={!hasNext || loading}
          className="btn btn-ghost !h-8 text-xs disabled:cursor-not-allowed disabled:opacity-50"
        >
          {labels.next} <ChevronRight size={13} />
        </button>
      </div>
    </div>
  );
}
