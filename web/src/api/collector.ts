// Collection-dashboard data: the desktop backend's /api/local/collector/*
// endpoints (per-source stats + observation feed) and the extension run
// progress. Uses the shared `api` fetch wrapper (same-origin, x9_session
// cookie) and React Query, matching the rest of the app.
import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';

export type SourceKey = 'tiktok_shop' | 'x9_leads' | 'table_import' | 'other';

export interface DailyPoint {
  date: string;
  count: number;
}

export interface SourceBucket {
  total: number;
  today: number;
  daily: DailyPoint[];
  funnel?: { shop_list_seen: number; shop_profile_collected: number };
}

export interface SourceStats {
  ok: boolean;
  generated_at: string;
  sources: Record<SourceKey, SourceBucket>;
}

export interface ShopFields {
  lead_status: string | null;
  gmv_raw: string | null;
  gpm_raw: string | null;
  avg_commission_rate_raw: string | null;
  category_text: string | null;
  invite_status: string | null;
  save_status: string | null;
  shop_profile_url: string | null;
  detail_captured: boolean;
}

export interface LeadFields {
  email: string | null;
  external_links: string[];
  source_video_url: string | null;
  current_status: string | null;
}

export interface ImportFields {
  country: string | null;
  tier: string | null;
  language: string | null;
  engagement_rate: number | null;
  quality_score: number | null;
  email: string | null;
}

export interface ObservationItem {
  id: string;
  source: SourceKey;
  platform: string;
  handle: string;
  display_name: string | null;
  followers_raw: string | null;
  search_keyword: string | null;
  collected_at: string | null;
  created_at: string | null;
  shop?: ShopFields;
  lead?: LeadFields;
  import_meta?: ImportFields;
}

export interface FeedResponse {
  ok: boolean;
  total: number;
  limit: number;
  offset: number;
  items: ObservationItem[];
}

export interface RunProgress {
  ok?: boolean;
  items?: Array<Record<string, unknown>>;
  progress?: Record<string, unknown>;
  [k: string]: unknown;
}

export function useSourceStats() {
  return useQuery({
    queryKey: ['collector', 'source-stats'],
    queryFn: () => api.get<SourceStats>('/api/local/collector/source-stats'),
    refetchInterval: 60_000,
  });
}

export function useObservationsFeed(params: {
  source?: SourceKey | 'all';
  platform?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: ['collector', 'feed', params],
    queryFn: () =>
      api.get<FeedResponse>('/api/local/collector/observations-feed', {
        source: params.source ?? 'all',
        platform: params.platform,
        date_from: params.date_from,
        date_to: params.date_to,
        limit: params.limit ?? 100,
        offset: params.offset ?? 0,
      }),
  });
}

export function useRunProgress() {
  return useQuery({
    queryKey: ['collector', 'run-progress'],
    queryFn: () => api.get<RunProgress>('/api/local/extension/run-progress'),
    refetchInterval: 15_000,
  });
}
