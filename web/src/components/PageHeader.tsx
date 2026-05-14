import type { ReactNode } from 'react';

interface PageHeaderProps {
  title?: string;
  description?: string;
  extra?: ReactNode;
}

export function PageHeader({ title, description, extra }: PageHeaderProps) {
  if (!title && !description && !extra) return null;
  return (
    <div className="mb-4 flex items-end justify-between gap-4 flex-wrap">
      <div>
        {title && <h2 className="text-base font-semibold text-gray-800">{title}</h2>}
        {description && <div className="text-xs text-muted mt-1">{description}</div>}
      </div>
      {extra && <div className="flex items-center gap-2 flex-wrap">{extra}</div>}
    </div>
  );
}
