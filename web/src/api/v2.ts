// API client for the v2 preview dashboards (/preview/*).
// Hits the new /api/v2/* backend routes that aggregate the existing data
// across creators / creator / tk_creators tables.

const BASE = '/api/v2';

async function v2Fetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...((init?.headers as Record<string, string>) || {}) },
    ...init,
  });
  if (!res.ok) {
    let body: unknown = null;
    try { body = await res.json(); } catch { /* ignore */ }
    const detail =
      (body && typeof body === 'object' && 'detail' in body && (body as any).detail) ||
      res.statusText;
    throw new Error(String(detail));
  }
  return (await res.json()) as T;
}

// ---------- Types ----------
export type RangeKey = 'today' | 'week' | 'month';
export type HealthColor = 'green' | 'yellow' | 'red' | 'grey';

export interface NorthStarKpi {
  key: string;
  label: string;
  value: number;
  delta_pct: number | null;
  compare_label: string;
}

export interface FunnelStage {
  stage: string;
  label: string;
  count: number;
}

export interface DepartmentRow {
  department_code: string;
  creator_count: number;
  today_collected: number;
  contacted: number;
  video_published: number;
  by_day_7: number[];
  health: HealthColor;
}

export interface AlertRow {
  severity: 'red' | 'yellow' | 'green';
  label: string;
  count: number;
  action: string;
}

export interface PulseResponse {
  ok: boolean;
  range: RangeKey;
  generated_at: string;
  north_star: NorthStarKpi[];
  funnel: FunnelStage[];
  departments: DepartmentRow[];
  alerts: AlertRow[];
}

export interface CreatorQueueItem {
  handle: string;
  handle_key: string;
  platform: string;
  display_name: string | null;
  followers_count: number | null;
  recommendation_score: number;
  current_status: string | null;
  stage_label: string;
  reason: string;
}

export interface SparklinePoint {
  date: string;
  collected: number;
  contacted: number;
}

export interface PersonalFunnelRow {
  stage: string;
  label: string;
  mine: number;
  department: number;
}

export interface MeResponse {
  ok: boolean;
  generated_at: string;
  user: { id: string; display_name: string; role: string; department_code: string | null };
  owned_count: number;
  weekly: { contacted: number; sample_shipped: number; video_published: number; deal_closed: number };
  queues: {
    must_today: CreatorQueueItem[];
    follow_up: CreatorQueueItem[];
    sample_log: CreatorQueueItem[];
  };
  sparkline_7d: SparklinePoint[];
  personal_funnel: PersonalFunnelRow[];
}

export interface UnifiedCreatorRow {
  platform: string;
  handle: string;
  handle_key: string;
  display_name: string | null;
  avatar_url: string | null;
  profile_url: string | null;
  followers_count: number | null;
  email: string | null;
  tier: string | null;
  country: string | null;
  gmv_30d_usd: number | null;
  recommendation_score: number;
  primary_product_category: string | null;
  current_status: string | null;
  stage: string | null;
  stage_label: string;
  owner_bd: string | null;
  department_code: string | null;
  last_contact_date: string | null;
  collected_at: string | null;
  source_table: string;
  health: { color: HealthColor; reason: string };
}

export interface CreatorsResponse {
  ok: boolean;
  total: number;
  limit: number;
  offset: number;
  summary: {
    filtered_count: number;
    avg_recommendation_score: number;
    contact_rate_pct: number;
    with_email: number;
    with_owner: number;
  };
  items: UnifiedCreatorRow[];
}

export interface CreatorEmailRow {
  id: string;
  subject: string;
  status: string;
  to_email: string;
  from_email: string;
  sent_at: string | null;
  created_at: string;
  has_reply: boolean;
}

export interface TimelineEvent {
  ts: string;
  kind: string;
  label: string;
}

export interface CreatorDetailResponse {
  ok: boolean;
  creator: UnifiedCreatorRow & {
    bio: string | null;
    language: string | null;
    store_assigned: string | null;
    queue_type: string | null;
    fit_level: string | null;
    notes: string | null;
    last_seen_at: string | null;
    updated_at: string | null;
  };
  health: { color: HealthColor; reason: string };
  emails: CreatorEmailRow[];
  timeline: TimelineEvent[];
  observation_count: number;
}

// ---------- Calls ----------
export const v2Api = {
  pulse: (range: RangeKey = 'week') =>
    v2Fetch<PulseResponse>(`/pulse?range=${range}`),
  me: () => v2Fetch<MeResponse>('/me'),
  creators: (params: {
    tab?: string;
    q?: string;
    platform?: string;
    tier?: string;
    status?: string;
    owner?: string;
    limit?: number;
    offset?: number;
  } = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
    });
    const q = qs.toString();
    return v2Fetch<CreatorsResponse>('/creators' + (q ? '?' + q : ''));
  },
  creatorDetail: (platform: string, handle: string) =>
    v2Fetch<CreatorDetailResponse>(
      `/creators/${encodeURIComponent(platform)}/${encodeURIComponent(handle)}`,
    ),
};
