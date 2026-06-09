import { useQuery } from '@tanstack/react-query';
import { api } from './client';

const LOCAL_YOUTUBE = '/api/local/youtube';

export type YoutubeImportRun = {
  id: string;
  filename: string;
  keyword: string;
  source_search_url: string;
  status: string;
  total_rows: number;
  kept_rows: number;
  dropped_no_contact: number;
  inserted: number;
  updated: number;
  sources_added: number;
  manual_review: number;
  errors_count: number;
  started_at: string;
  finished_at: string;
  created_at: string;
  updated_at: string;
};

export type YoutubeStats = {
  ok: boolean;
  local_mode: boolean;
  db_status: string;
  db_url: string;
  runs: number;
  today_runs: number;
  raw_rows: number;
  leads: number;
  has_email: number;
  manual_review: number;
  dropped_no_contact: number;
  latest_run: YoutubeImportRun | null;
};

export type YoutubeActor = {
  id: string;
  username: string;
  display_name: string;
  email: string;
  role: string;
  department_code: string;
  collection: {
    scope: string;
    total: number;
    today: number;
    lead_total: number;
    with_email: number;
    manual_review: number;
    last_collected_at: string;
    user_status: string;
    latest_run: YoutubeImportRun | null;
  };
};

export type YoutubeLead = {
  id: string;
  platform: string;
  channel_key: string;
  channel_id: string;
  channel_handle: string;
  channel_url: string;
  display_name: string;
  email: string;
  emails: string[];
  has_email: boolean;
  needs_manual_review: boolean;
  review_reasons: string[];
  manual_review_url: string;
  latest_source_type: string;
  latest_video_id: string;
  latest_video_url: string;
  latest_video_title: string;
  latest_keyword: string;
  source_types: string[];
  first_seen_at: string;
  last_seen_at: string;
  created_at: string;
  updated_at: string;
};

export type YoutubeLeadSource = {
  id: string;
  lead_id: string;
  run_id: string;
  source_type: string;
  keyword: string;
  video_id: string;
  video_url: string;
  video_title: string;
  evidence_url: string;
  manual_review_url: string;
  email: string;
  review_reason: string;
  collected_at: string;
  created_at: string;
  updated_at: string;
};

export type YoutubeListResponse<T> = {
  ok: boolean;
  total: number;
  items: T[];
};

export type YoutubeActorsResponse = YoutubeListResponse<YoutubeActor> & {
  scope: 'admin' | 'user' | string;
  unassigned: Record<string, unknown>;
};

export type YoutubeSourcesResponse = YoutubeListResponse<YoutubeLeadSource> & {
  lead: YoutubeLead;
};

export type YoutubeLeadParams = {
  keyword?: string;
  source_type?: string;
  has_email?: boolean;
  needs_manual_review?: boolean;
  limit?: number;
  offset?: number;
};

export function useYoutubeStats() {
  return useQuery({
    queryKey: ['youtube', 'stats'],
    queryFn: () => api.get<YoutubeStats>(`${LOCAL_YOUTUBE}/stats`),
    refetchInterval: 30_000,
  });
}

export function useYoutubeActors() {
  return useQuery({
    queryKey: ['youtube', 'actors'],
    queryFn: () => api.get<YoutubeActorsResponse>(`${LOCAL_YOUTUBE}/actors`),
    refetchInterval: 30_000,
  });
}

export function useYoutubeRuns(params: { limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ['youtube', 'runs', params],
    queryFn: () => api.get<YoutubeListResponse<YoutubeImportRun>>(`${LOCAL_YOUTUBE}/runs`, params),
  });
}

export function useYoutubeLeads(params: YoutubeLeadParams) {
  return useQuery({
    queryKey: ['youtube', 'leads', params],
    queryFn: () => api.get<YoutubeListResponse<YoutubeLead>>(`${LOCAL_YOUTUBE}/leads`, params),
  });
}

export function useYoutubeManualReview(params: Omit<YoutubeLeadParams, 'has_email' | 'needs_manual_review'>) {
  return useQuery({
    queryKey: ['youtube', 'manual-review', params],
    queryFn: () => api.get<YoutubeListResponse<YoutubeLead>>(`${LOCAL_YOUTUBE}/manual-review`, params),
  });
}

export function useYoutubeSources(leadId: string | null, params: { limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ['youtube', 'sources', leadId, params],
    enabled: Boolean(leadId),
    queryFn: () =>
      api.get<YoutubeSourcesResponse>(`${LOCAL_YOUTUBE}/sources`, {
        lead_id: leadId,
        ...params,
      }),
  });
}
