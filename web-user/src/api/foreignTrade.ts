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

export interface LeadItem {
  id: string;
  kind: 'company' | 'social';
  name: string;
  subtitle?: string;
  platform?: string;
  tier?: string | null;
  status?: string | null;
  score?: number;
  contact?: string;
  us_market?: number;
  followers?: number | null;
  has_contact?: number;
  profile_url?: string | null;
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
