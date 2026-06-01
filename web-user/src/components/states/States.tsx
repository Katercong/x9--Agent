import { Loader2, AlertCircle, Inbox } from 'lucide-react';
import { cn } from '@/lib/cn';

interface BlockProps {
  className?: string;
  height?: number | string;
}

export function Loading({ className, height = 160, message = '加载中...' }: BlockProps & { message?: string }) {
  return (
    <div
      className={cn('flex items-center justify-center text-muted text-xs gap-2', className)}
      style={{ minHeight: typeof height === 'number' ? `${height}px` : height }}
    >
      <Loader2 size={14} className="animate-spin" />
      {message}
    </div>
  );
}

export function ErrorBlock({
  message, title = '加载失败', className, height = 160,
}: BlockProps & { message?: string; title?: string }) {
  return (
    <div
      className={cn('flex flex-col items-center justify-center text-muted text-xs gap-2 px-4', className)}
      style={{ minHeight: typeof height === 'number' ? `${height}px` : height }}
    >
      <AlertCircle size={20} className="text-bad" />
      <div className="text-bad font-medium">{title}</div>
      {message && <div className="text-xxs text-muted text-center max-w-md truncate">{message}</div>}
    </div>
  );
}

export function Empty({
  message = '暂无数据', className, height = 160,
}: BlockProps & { message?: string }) {
  return (
    <div
      className={cn('flex flex-col items-center justify-center text-muted text-xs gap-2', className)}
      style={{ minHeight: typeof height === 'number' ? `${height}px` : height }}
    >
      <Inbox size={20} />
      <div>{message}</div>
    </div>
  );
}

interface AsyncStateProps {
  loading?: boolean;
  error?: unknown;
  isEmpty?: boolean;
  loadingMessage?: string;
  errorTitle?: string;
  emptyMessage?: string;
  height?: number | string;
  children: React.ReactNode;
}

export function AsyncState({
  loading, error, isEmpty, loadingMessage, errorTitle, emptyMessage, height = 160, children,
}: AsyncStateProps) {
  if (loading) return <Loading height={height} message={loadingMessage} />;
  if (error) {
    const msg = error instanceof Error ? error.message : String(error);
    return <ErrorBlock title={errorTitle} message={msg} height={height} />;
  }
  if (isEmpty) return <Empty message={emptyMessage} height={height} />;
  return <>{children}</>;
}
