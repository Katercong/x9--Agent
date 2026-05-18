// Per-source collection data for the unified creator-info page.
// Uses the portal's `api` client (base /api/local, cookie session) + React Query.
import { useQuery } from '@tanstack/react-query';
import { api } from './client';

export type SourceKey = 'tiktok_shop' | 'x9_leads' | 'table_import' | 'other';

export interface DailyPoint { date: string; count: number }

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
  shop?: {
    lead_status: string | null;
    gmv_raw: string | null;
    gpm_raw: string | null;
    avg_commission_rate_raw: string | null;
    category_text: string | null;
    invite_status: string | null;
    save_status: string | null;
    shop_profile_url: string | null;
    detail_captured: boolean;
  };
  lead?: {
    email: string | null;
    external_links: string[];
    source_video_url: string | null;
    current_status: string | null;
  };
  import_meta?: {
    country: string | null;
    tier: string | null;
    language: string | null;
    engagement_rate: number | null;
    quality_score: number | null;
    email: string | null;
  };
}

export interface FeedResponse {
  ok: boolean;
  total: number;
  limit: number;
  offset: number;
  items: ObservationItem[];
}

export function useSourceStats() {
  return useQuery({
    queryKey: ['collector', 'source-stats'],
    queryFn: () => api.get<SourceStats>('/collector/source-stats'),
    refetchInterval: 60_000,
  });
}

export function useObservationsFeed(params: { source?: SourceKey | 'all'; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ['collector', 'feed', params],
    queryFn: () =>
      api.get<FeedResponse>('/collector/observations-feed', {
        source: params.source ?? 'all',
        limit: params.limit ?? 200,
        offset: params.offset ?? 0,
      }),
  });
}
