// Collection-dashboard data: the desktop backend's /api/local/collector/*
// endpoints (per-source stats + observation feed) and the extension run
// progress. Uses the shared `api` fetch wrapper (same-origin, x9_session
// cookie) and React Query, matching the rest of the app.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';

export type SourceKey = 'tiktok_shop' | 'x9_leads' | 'table_import' | 'other';

export interface DailyPoint {
  date: string;
  count: number;
}

export interface SourceContactStats {
  total: number;
  with_email: number;
  with_links: number;
  with_gmv?: number;
  valid_detail_total?: number;
  today_total: number;
  today_with_email: number;
  today_with_links: number;
  today_with_gmv?: number;
}

export interface SourceBucket {
  total: number;
  today: number;
  daily: DailyPoint[];
  queued_total?: number;
  ingested_total?: number;
  last_collected_at?: string | null;
  user_status?: 'online' | 'offline' | 'collecting' | 'idle' | 'error' | string;
  funnel?: { shop_list_seen: number; shop_profile_collected: number };
  // Per-source contact-coverage counts from the `creators` table —
  // accurate even when raw_json is missing. Use these for KPI cards.
  contacts?: SourceContactStats;
}

export interface SourceStats {
  ok: boolean;
  generated_at: string;
  sources: Record<SourceKey, SourceBucket>;
}

export interface CollectionActor {
  id: string;
  username: string;
  display_name: string | null;
  email: string | null;
  role: string;
  department_code: string | null;
  collection: {
    scope?: string;
    total: number;
    today: number;
    shop_total?: number;
    shop_today?: number;
    shop_detail_total?: number;
    valid_detail_total?: number;
    with_email?: number;
    with_links?: number;
    with_gmv?: number;
    queued_total?: number;
    ingested_total?: number;
    last_collected_at?: string | null;
    user_status?: 'online' | 'offline' | 'collecting' | 'idle' | 'error' | string;
    sources?: Record<SourceKey, SourceBucket>;
  };
}

export interface UnassignedCollectionWorker {
  worker_id: string | null;
  platform: string | null;
  source: string | null;
  total: number;
  last_collected_at: string | null;
}

export interface UnassignedCollectionStats {
  total: number;
  today: number;
  sources?: Record<SourceKey, SourceBucket>;
  recent_workers?: UnassignedCollectionWorker[];
}

export interface CollectionActorsResponse {
  ok: boolean;
  scope: 'admin' | 'user';
  items: CollectionActor[];
  unassigned: UnassignedCollectionStats;
}

export interface ActorSummary {
  id: string;
  username: string;
  display_name: string | null;
  email: string | null;
  role: string;
  department_code: string | null;
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
  actor_user_id?: string | null;
  worker_id?: string | null;
  account_id?: string | null;
  handle: string;
  display_name: string | null;
  followers_raw: string | null;
  search_keyword: string | null;
  collected_at: string | null;
  created_at: string | null;
  ingest_status?: 'queued' | 'ingested' | string;
  ingested_at?: string | null;
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

export interface ExtensionSessionItem {
  session_id: string;
  department_code?: string | null;
  actor_user_id?: string | null;
  actor?: ActorSummary | null;
  worker_id: string;
  account_id?: string | null;
  extension_version?: string | null;
  current_url?: string | null;
  page_type?: string | null;
  tiktok_page_status?: string | null;
  tiktok_login_status?: string | null;
  online: boolean;
  last_heartbeat_at?: string | null;
}

export interface ExtensionStatusResponse {
  ok: boolean;
  sessions: ExtensionSessionItem[];
  any_online: boolean;
}

export interface BindWorkerInput {
  worker_id: string;
  actor_user_id?: string | null;
  backfill?: boolean;
}

export interface BindWorkerResponse {
  ok: boolean;
  worker_id: string;
  actor_user_id: string | null;
  actor?: ActorSummary | null;
  backfill: { raw_observations: number; creator_sources: number };
}

export function useSourceStats(params?: { actor_user_id?: string }) {
  return useQuery({
    queryKey: ['collector', 'source-stats', params],
    queryFn: () => api.get<SourceStats>('/api/local/collector/source-stats', params),
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
  actor_user_id?: string;
}) {
  return useQuery({
    queryKey: ['collector', 'feed', params],
    queryFn: () =>
      api.get<FeedResponse>('/api/local/collector/observations-feed', {
        source: params.source ?? 'all',
        platform: params.platform,
        date_from: params.date_from,
        date_to: params.date_to,
        limit: params.limit ?? 10,
        offset: params.offset ?? 0,
        actor_user_id: params.actor_user_id,
      }),
  });
}

export function useCollectionActors(enabled = true) {
  return useQuery({
    queryKey: ['collector', 'actors'],
    queryFn: () => api.get<CollectionActorsResponse>('/api/local/collector/actors'),
    enabled,
    refetchInterval: 60_000,
  });
}

export function useRunProgress() {
  return useQuery({
    queryKey: ['collector', 'run-progress'],
    queryFn: () => api.get<RunProgress>('/api/local/extension/run-progress'),
    refetchInterval: 15_000,
  });
}

export function useExtensionStatus() {
  return useQuery({
    queryKey: ['collector', 'extension-status'],
    queryFn: () => api.get<ExtensionStatusResponse>('/api/local/extension/status'),
    refetchInterval: 15_000,
  });
}

export function useBindExtensionWorker() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: BindWorkerInput) =>
      api.post<BindWorkerResponse>(
        `/api/local/extension/workers/${encodeURIComponent(input.worker_id)}/binding`,
        {
          actor_user_id: input.actor_user_id ?? null,
          backfill: input.backfill ?? false,
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['collector'] });
    },
  });
}
