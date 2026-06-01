// Foreign-trade department data: the desktop backend's
// /api/local/foreign-trade/* endpoints (recruitment + social-media lead
// aggregation that replaces the TikTok-creator dashboard). Uses the shared
// `api` fetch wrapper (same-origin, x9_session cookie) and React Query.
import { useQuery } from '@tanstack/react-query';
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

export function useForeignTradeDashboard() {
  return useQuery({
    queryKey: ['foreign-trade', 'dashboard'],
    queryFn: () => api.get<ForeignTradeDashboard>('/api/local/foreign-trade/dashboard'),
    refetchInterval: 60_000,
  });
}

export function useForeignTradeCollection(params: { channel: LeadChannel; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ['foreign-trade', 'collection', params],
    queryFn: () =>
      api.get<CollectionResponse>('/api/local/foreign-trade/collection', {
        channel: params.channel,
        limit: params.limit ?? 20,
        offset: params.offset ?? 0,
      }),
    refetchInterval: 60_000,
  });
}

// ---- recruitment lead management (Phase 2) ----

export interface CompanyLeadItem {
  id: string;
  platform: string;
  company_name: string;
  industry: string | null;
  size_range: string | null;
  city: string | null;
  province: string | null;
  company_description: string | null;
  tier: string | null;
  score: number;
  cooperation_type: string | null;
  data_quality: string | null;
  next_action: string | null;
  us_market: number;
  excluded: number;
  lead_tags: string[];
  score_reason: string | null;
  llm_score_suggestion: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  hr_wechat: string | null;
  status: string;
  owner_bd: string | null;
  notes: string | null;
  created_at: string | null;
}

export interface TalentLeadItem {
  id: string;
  platform: string;
  name_masked: string | null;
  desired_title: string | null;
  city: string | null;
  experience: string | null;
  education: string | null;
  salary_expectation: string | null;
  tier: string | null;
  score: number;
  cooperation_type: string | null;
  next_action: string | null;
  lead_tags: string[];
  score_reason: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  wechat: string | null;
  status: string;
  notes: string | null;
  created_at: string | null;
}

export interface LeadListResponse<T> {
  ok: boolean;
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export function useCompanyLeads(params: { tier?: string; status?: string; q?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ['foreign-trade', 'company-leads', params],
    queryFn: () =>
      api.get<LeadListResponse<CompanyLeadItem>>('/api/local/company-leads', {
        tier: params.tier,
        status: params.status,
        q: params.q,
        limit: params.limit ?? 20,
        offset: params.offset ?? 0,
      }),
    refetchInterval: 60_000,
  });
}

export function useTalentLeads(params: { tier?: string; status?: string; q?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ['foreign-trade', 'talent-leads', params],
    queryFn: () =>
      api.get<LeadListResponse<TalentLeadItem>>('/api/local/talents', {
        tier: params.tier,
        status: params.status,
        q: params.q,
        limit: params.limit ?? 20,
        offset: params.offset ?? 0,
      }),
    refetchInterval: 60_000,
  });
}

// ---- social-media lead management (Phase 3) ----

export interface XhsUserItem {
  id: string;
  platform: string;
  username: string | null;
  bio: string | null;
  location: string | null;
  follower_count: number | null;
  has_contact: number;
  contact_count: number;
  profile_url: string | null;
  fit_score: number | null;
  fit_level: string | null;
  decision: string | null;
  intent_type: string | null;
  created_at: string | null;
}

export function useXhsUsers(params: { platform?: string; has_contact?: number; decision?: string; q?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ['foreign-trade', 'xhs-users', params],
    queryFn: () =>
      api.get<LeadListResponse<XhsUserItem>>('/api/local/xhs/users', {
        platform: params.platform,
        has_contact: params.has_contact,
        decision: params.decision,
        q: params.q,
        limit: params.limit ?? 20,
        offset: params.offset ?? 0,
      }),
    refetchInterval: 60_000,
  });
}
