// Foreign-trade department data for the portal: the desktop backend's
// /api/local/foreign-trade/* endpoints (recruitment + social-media lead
// aggregation that replaces the TikTok-creator dashboard).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';

export interface BreakdownRow {
  key: string;
  name: string;
  count: number;
}

export interface PlatformRow {
  name: string;
  value: number;
}

export interface TrendPoint {
  date: string;
  count: number;
}

export interface ForeignTradeDashboard {
  ok: boolean;
  generated_at: string;
  scope: { type: string; department_code: string | null };
  summary: {
    total_company_leads: number;
    total_talent_leads: number;
    total_social_leads: number;
    today_new: number;
    tier_a: number;
    contacted: number;
    high_intent: number;
    us_market: number;
    social_contacts: number;
  };
  tier_rows: BreakdownRow[];
  status_rows: BreakdownRow[];
  source_rows: BreakdownRow[];
  decision_rows: BreakdownRow[];
  platform_rows: PlatformRow[];
  trend_7d: TrendPoint[];
}

export type LeadChannel = 'jobs' | 'social';

export interface ContactItem {
  type: string;
  label?: string | null;
  value: string;
  source?: string | null;
  rule?: string | null;
}

export interface SocialCommentEvidence {
  id?: string;
  content?: string;
  location?: string;
  like_count?: number | null;
  like_count_text?: string | null;
  published_at_text?: string | null;
  created_at?: string | null;
  depth?: number;
  note_title?: string;
  note_url?: string;
  keyword?: string | null;
}

export interface SocialNoteEvidence {
  id?: string;
  title?: string;
  desc?: string;
  url?: string;
  cover_url?: string;
  images?: string[];
  like_count?: number | null;
  collect_count?: number | null;
  comment_count?: number | null;
  published_at_text?: string | null;
  created_at?: string | null;
  keyword?: string | null;
}

export interface SocialSourceEvidence {
  source_type?: string;
  keyword?: string | null;
  evidence_text?: string | null;
  evidence_url?: string | null;
  evidence_images?: string[];
  comment_depth?: number | null;
  created_at?: string | null;
}

export interface LeadItem {
  id: string;
  kind: 'company' | 'talent' | 'social';
  kind_label?: string;
  name: string;
  subtitle?: string;
  platform?: string;
  tier?: string | null;
  status?: string | null;
  score?: number;
  contact?: string;
  contacts?: ContactItem[];
  contact_name?: string | null;
  contact_title?: string | null;
  contact_source?: string | null;
  us_market?: number;
  location?: string | null;
  title?: string | null;
  summary?: string | null;
  source_type?: string | null;
  source_mode?: string | null;
  source_url?: string | null;
  resume_download_url?: string | null;
  data_quality?: string | null;
  next_action?: string | null;
  cooperation_type?: string | null;
  score_reason?: string | null;
  score_suggestion?: string | null;
  llm_score_status?: string | null;
  consent_status?: string | null;
  size_range?: string | null;
  experience?: string | null;
  education?: string | null;
  major?: string | null;
  salary_expectation?: string | null;
  tags?: string[];
  keywords?: string[];
  raw_titles?: string[];
  external_user_id?: string | null;
  xhs_user_id?: string | null;
  account?: string | null;
  avatar_url?: string | null;
  followers?: number | null;
  following?: number | null;
  liked_collect_count?: number | null;
  profile_note_count?: number | null;
  source_notes_count?: number;
  notes_count?: number;
  comments_count?: number;
  has_contact?: number;
  profile_url?: string | null;
  bio?: string | null;
  clean_status?: string | null;
  contact_signals?: string[];
  platform_signals?: string[];
  contact_signals_data?: Record<string, unknown> | unknown[];
  platform_signals_data?: Record<string, unknown> | unknown[];
  profile_quality?: Record<string, unknown>;
  recent_comments?: SocialCommentEvidence[];
  recent_notes?: SocialNoteEvidence[];
  source_samples?: SocialSourceEvidence[];
  history_posts?: SocialNoteEvidence[];
  raw_user?: Record<string, unknown>;
  fit_score?: number | null;
  fit_level?: string | null;
  decision?: string | null;
  intent_type?: string | null;
  judgment?: string | null;
  judgment_data?: Record<string, unknown> | null;
  judgment_evidence?: string | null;
  judgment_suggestion?: string | null;
  judged_at?: string | null;
  profile_collected_at?: string | null;
  created_at?: string | null;
}

export interface CollectionResponse {
  ok: boolean;
  channel: LeadChannel;
  stats: Record<string, number>;
  total: number;
  items: LeadItem[];
}

export interface CleaningChannel {
  key: string;
  name: string;
  total: number;
  cleaned: number;
  pending: number;
  with_contact?: number;
  unjudged_with_contact?: number;
}

export interface CleaningStatus {
  ok: boolean;
  generated_at: string;
  scope: { type: string; department_code: string | null };
  summary: {
    company_total: number;
    talent_total: number;
    social_total: number;
    raw_snapshots: number;
    contacts_total: number;
    judgments_total: number;
    ready_total: number;
    needs_cleaning: number;
    unjudged_with_contact: number;
    openai_configured: boolean;
  };
  channels: CleaningChannel[];
  raw: {
    total: number;
    queued: number;
  };
}

export interface CleaningRunResult {
  ok: boolean;
  run_id: string;
  started_at: string;
  finished_at: string;
  duration_ms: number;
  include_gpt: boolean;
  company: Record<string, number>;
  talent: Record<string, number>;
  social: Record<string, number>;
  gpt: Record<string, unknown>;
  status: CleaningStatus;
}

export function useForeignTradeDashboard() {
  return useQuery({
    queryKey: ['foreign-trade', 'dashboard'],
    queryFn: () => api.get<ForeignTradeDashboard>('/foreign-trade/dashboard'),
    refetchInterval: 60_000,
  });
}

export function useForeignTradeCollection(params: { channel: LeadChannel; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ['foreign-trade', 'collection', params],
    queryFn: () =>
      api.get<CollectionResponse>('/foreign-trade/collection', {
        channel: params.channel,
        limit: params.limit ?? 20,
        offset: params.offset ?? 0,
      }),
    refetchInterval: 60_000,
  });
}

export function useForeignTradeCleaningStatus() {
  return useQuery({
    queryKey: ['foreign-trade', 'cleaning', 'status'],
    queryFn: () => api.get<CleaningStatus>('/foreign-trade/cleaning/status'),
    refetchInterval: 60_000,
  });
}

export function useRunForeignTradeCleaning() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { include_gpt?: boolean; force_gpt?: boolean; gpt_limit?: number } = {}) =>
      api.post<CleaningRunResult>('/foreign-trade/cleaning/run', body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['foreign-trade'] });
    },
  });
}
