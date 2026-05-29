export type Language = 'zh' | 'en';

export const DEFAULT_LANGUAGE: Language = 'zh';

export function normalizeLanguage(value: string | null | undefined): Language {
  return value === 'en' || value === 'zh' ? value : DEFAULT_LANGUAGE;
}

export function localeFor(language: Language): string {
  return language === 'en' ? 'en-US' : 'zh-CN';
}

export function applyDocumentLanguage(language: Language) {
  if (typeof document === 'undefined') return;
  document.documentElement.lang = localeFor(language);
}

export function formatRelativeTime(iso: string | null | undefined, language: Language): string {
  if (!iso) return '--';
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso || '--';

  const diffMs = dt.getTime() - Date.now();
  const absMs = Math.abs(diffMs);
  const formatter = new Intl.RelativeTimeFormat(localeFor(language), { numeric: 'auto' });

  if (absMs < 60_000) {
    return language === 'en' ? 'just now' : '刚刚';
  }
  const minutes = Math.round(diffMs / 60_000);
  if (absMs < 3_600_000) return formatter.format(minutes, 'minute');
  const hours = Math.round(diffMs / 3_600_000);
  if (absMs < 86_400_000) return formatter.format(hours, 'hour');
  const days = Math.round(diffMs / 86_400_000);
  if (absMs < 2_592_000_000) return formatter.format(days, 'day');

  return new Intl.DateTimeFormat(localeFor(language), {
    month: 'numeric',
    day: 'numeric',
  }).format(dt);
}
