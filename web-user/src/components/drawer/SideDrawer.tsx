import { useEffect } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/cn';

interface SideDrawerProps {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  width?: number | string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

export function SideDrawer({ open, onClose, title, subtitle, width = 560, children, footer }: SideDrawerProps) {
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = ''; };
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/50" onClick={onClose} aria-hidden="true" />
      <aside
        className={cn(
          'fixed inset-y-0 right-0 z-50 flex flex-col shadow-soft border-l border-border',
          'animate-in slide-in-from-right',
        )}
        style={{ width: typeof width === 'number' ? `${width}px` : width, maxWidth: '95vw', background: 'rgb(var(--bg-elev-1))' }}
      >
        <header className="h-14 px-5 flex items-center gap-3 shrink-0 border-b border-border">
          <div className="flex-1 min-w-0">
            {title && <h2 className="text-sm font-semibold truncate">{title}</h2>}
            {subtitle && <div className="text-xxs text-muted truncate">{subtitle}</div>}
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded flex items-center justify-center text-muted hover:text-text">
            <X size={16} />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
        {footer && (
          <footer className="border-t border-border p-3 flex items-center justify-end gap-2 shrink-0" style={{ background: 'rgb(var(--bg-elev-2))' }}>
            {footer}
          </footer>
        )}
      </aside>
    </>
  );
}
