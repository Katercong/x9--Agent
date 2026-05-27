import { ChevronLeft, ChevronRight } from 'lucide-react';

type PaginationControlsProps = {
  page: number;
  pageSize: number;
  total: number;
  currentCount?: number;
  loading?: boolean;
  onPageChange: (page: number) => void;
};

const numberFmt = new Intl.NumberFormat('zh-CN');

export function PaginationControls({
  page,
  pageSize,
  total,
  currentCount = pageSize,
  loading = false,
  onPageChange,
}: PaginationControlsProps) {
  const start = total === 0 ? 0 : page * pageSize + 1;
  const end = Math.min(page * pageSize + currentCount, total);
  const hasPrev = page > 0;
  const hasNext = (page + 1) * pageSize < total;

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-elev1 px-3 py-2">
      <div className="text-xs text-muted">
        第 {numberFmt.format(page + 1)} 页 · {numberFmt.format(start)}-{numberFmt.format(end)} / {numberFmt.format(total)} · 每页 {pageSize}
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(0, page - 1))}
          disabled={!hasPrev || loading}
          className="btn btn-ghost !h-8 text-xs disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ChevronLeft size={13} /> 上一页
        </button>
        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={!hasNext || loading}
          className="btn btn-ghost !h-8 text-xs disabled:cursor-not-allowed disabled:opacity-50"
        >
          下一页 <ChevronRight size={13} />
        </button>
      </div>
    </div>
  );
}
