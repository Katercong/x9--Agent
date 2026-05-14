import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export type Column<T> = {
  key: string;
  header: ReactNode;
  cell: (row: T, index: number) => ReactNode;
  width?: string;
  align?: 'left' | 'right' | 'center';
  className?: string;
};

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  rowKey?: (row: T, index: number) => string | number;
  emptyText?: string;
  compact?: boolean;
  onRowClick?: (row: T, index: number) => void;
  className?: string;
}

export function DataTable<T>({
  columns,
  data,
  rowKey,
  emptyText = '暂无数据',
  compact = false,
  onRowClick,
  className,
}: DataTableProps<T>) {
  if (data.length === 0) {
    return (
      <div className="text-xs text-muted text-center py-10 border border-dashed border-line rounded">
        {emptyText}
      </div>
    );
  }

  return (
    <div className={cn('overflow-x-auto', className)}>
      <table className="table-x9">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                style={{ width: col.width, textAlign: col.align || 'left' }}
                className={col.className}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr
              key={rowKey ? rowKey(row, i) : i}
              onClick={onRowClick ? () => onRowClick(row, i) : undefined}
              className={cn(
                onRowClick && 'cursor-pointer',
                compact && '[&>td]:py-1.5',
              )}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  style={{ textAlign: col.align || 'left' }}
                  className={col.className}
                >
                  {col.cell(row, i)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
