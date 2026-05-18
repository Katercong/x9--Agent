// Helper utilities to derive aggregated stats from raw resource data.
// These compensate for backend endpoints that don't pre-aggregate.

import type { Creator, Outreach, Product, Staff } from '@/api/types';

export type DateCount = { date: string; count: number };

export function toStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
  }
  if (typeof value !== 'string') return [];
  const text = value.trim();
  if (!text) return [];
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) return toStringArray(parsed);
  } catch {
    // Some SQL paths return plain text rather than JSON.
  }
  return [text];
}

// --- Creator aggregations ---

export function groupByTier(creators: Creator[]): { name: string; value: number; color: string }[] {
  const colors: Record<string, string> = { S: '#dc2626', A: '#ea580c', B: '#3370ff', C: '#16a34a', D: '#86909c' };
  const buckets: Record<string, number> = { S: 0, A: 0, B: 0, C: 0, D: 0, '未分级': 0 };
  for (const c of creators) {
    const t = (c.tier || '').toUpperCase();
    if (t === 'S' || t === 'A' || t === 'B' || t === 'C' || t === 'D') buckets[t]++;
    else buckets['未分级']++;
  }
  return Object.entries(buckets)
    .filter(([_, v]) => v > 0)
    .map(([k, v]) => ({ name: k === '未分级' ? '未分级' : `${k} 级`, value: v, color: colors[k] || '#94a3b8' }));
}

export function groupByCountry(creators: Creator[], top = 9) {
  const map: Record<string, number> = {};
  for (const c of creators) {
    const k = c.country || '未知';
    map[k] = (map[k] || 0) + 1;
  }
  return Object.entries(map)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, top);
}

export function groupByStatus(creators: Creator[]): Record<string, number> {
  const map: Record<string, number> = {};
  for (const c of creators) {
    const k = c.current_status || 'unknown';
    map[k] = (map[k] || 0) + 1;
  }
  return map;
}

export function groupByOwner(creators: Creator[], top = 8) {
  const map: Record<string, number> = {};
  for (const c of creators) {
    const k = c.owner_bd || '未分配';
    map[k] = (map[k] || 0) + 1;
  }
  return Object.entries(map)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, top);
}

export function groupByCategoryTags(creators: Creator[], top = 8) {
  const map: Record<string, number> = {};
  for (const c of creators) {
    const tags = toStringArray(c.category_tags);
    if (tags.length === 0) {
      map['未填写'] = (map['未填写'] || 0) + 1;
    } else {
      for (const t of tags) map[t] = (map[t] || 0) + 1;
    }
  }
  return Object.entries(map)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, top);
}

// --- Outreach aggregations ---

export function groupByOutreachStatus(items: Outreach[]) {
  const map: Record<string, number> = {};
  for (const o of items) {
    const k = o.status || 'unknown';
    map[k] = (map[k] || 0) + 1;
  }
  return map;
}

// Days-window growth trend
export function trendByDay(items: Creator[], days = 7): DateCount[] {
  const today = new Date();
  const result: DateCount[] = [];
  const tally: Record<string, number> = {};
  for (const c of items) {
    if (!c.created_at) continue;
    const d = c.created_at.slice(0, 10); // YYYY-MM-DD
    tally[d] = (tally[d] || 0) + 1;
  }
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    result.push({ date: `${d.getMonth() + 1}/${d.getDate()}`, count: tally[key] || 0 });
  }
  return result;
}

export function todayCount(items: { created_at?: string | null }[]): number {
  const t = new Date();
  const todayStr = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
  return items.filter((i) => (i.created_at || '').startsWith(todayStr)).length;
}

export function recentNDays(items: { created_at?: string | null }[], days = 7): number {
  const cut = new Date();
  cut.setDate(cut.getDate() - days);
  return items.filter((i) => i.created_at && new Date(i.created_at) >= cut).length;
}

// --- Product aggregations ---

export function categoryNameMap(categories: { id: number; name_zh: string }[]) {
  const m: Record<number, string> = {};
  for (const c of categories) m[c.id] = c.name_zh;
  return m;
}

export function productsByCategory(products: Product[], catMap: Record<number, string>) {
  const map: Record<string, number> = {};
  for (const p of products) {
    const k = (p.category_id && catMap[p.category_id]) || p.subcategory || '其他';
    map[k] = (map[k] || 0) + 1;
  }
  return Object.entries(map)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
}

// --- Staff (BD) monthly stats inside note JSON ---

export function staffStats(staff: Staff[]) {
  type Row = { name: string; role: string; contacted: number; confirmed: number; samples: number; videos: number; month: string };
  const rows: Row[] = [];
  for (const s of staff) {
    let parsed: any = {};
    if (s.note) {
      try { parsed = JSON.parse(s.note); } catch { /* ignore */ }
    }
    rows.push({
      name: s.name,
      role: s.role || '',
      contacted: Number(parsed.contacted ?? 0),
      confirmed: Number(parsed.confirmed ?? 0),
      samples: Number(parsed.samples ?? 0),
      videos: Number(parsed.videos ?? 0),
      month: parsed.month || '',
    });
  }
  return rows;
}

// --- Funnel from creators.current_status ---

export const funnelOrder = [
  'prospect',
  'contacted',
  'confirmed',
  'sample_shipped',
  'sample_delivered',
  'video_published',
  'ad_authorized',
  'ad_running',
];

export function buildFunnel(creators: Creator[]) {
  const map = groupByStatus(creators);
  const labelMap: Record<string, string> = {
    prospect: '潜在', contacted: '已联系', confirmed: '已确认',
    sample_shipped: '样品已寄', sample_delivered: '样品签收',
    video_published: '视频已发', ad_authorized: '已授权', ad_running: '广告投放中',
  };
  return funnelOrder.map((k) => ({ name: labelMap[k] || k, value: map[k] || 0, key: k }));
}
