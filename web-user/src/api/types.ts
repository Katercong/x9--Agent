// 后端响应类型 — 镜像 desktop/backend 的 schema

export interface CurrentUser {
  id: number;
  username: string;
  display_name: string | null;
  email: string | null;
  role: string;
  department_code: string | null;
  entry_scope?: string | null;
  active: number;
}

export interface AuthMe {
  logged_in: boolean;
  user?: CurrentUser;
}

export interface AppStatus {
  ok: boolean;
  service?: string;
  version?: string;
  uptime?: number;
  [k: string]: any;
}

export interface DbStats {
  creators?: number;
  recommendations?: number;
  observations?: number;
  review_pending?: number;
  outreach?: number;
  [k: string]: any;
}

export interface Creator {
  id: number;
  handle?: string | null;
  display_name?: string | null;
  platform?: string | null;
  profile_url?: string | null;
  avatar_url?: string | null;
  source?: string | null;
  source_label?: string | null;
  source_tags?: string[] | null;
  country?: string | null;
  language?: string | null;
  followers?: number | null;
  followers_count?: number | null;
  followers_raw?: string | null;
  tier?: string | null;
  avg_views?: number | null;
  email?: string | null;
  external_links?: string[] | null;
  contact_methods?: Array<Record<string, unknown>> | Record<string, unknown> | null;
  has_contact?: boolean | null;
  current_status?: string | null;
  bd_owner?: string | null;
  owner_bd?: string | null;
  outreach_priority?: string | null;
  primary_product_category?: string | null;
  primary_product_fit_score?: number | null;
  commercial_value_score?: number | null;
  data_quality_score?: number | null;
  contactability_score?: number | null;
  content_format_score?: number | null;
  content_format_status?: string | null;
  category_tags?: string[] | null;
  tiktok_shop?: Record<string, unknown> | null;
  department_code?: string | null;
  recommendation_score?: number | null;
  recommendation_status?: string | null;
  recommendation_reason?: string | null;
  collected_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  [k: string]: any;
}

export interface ReviewTask {
  id: number;
  creator_id: number;
  status: string;
  priority?: string | null;
  reason?: string | null;
  ai_score?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  [k: string]: any;
}

export interface ExtensionStatus {
  ok?: boolean;
  online?: boolean;
  worker_id?: string | null;
  last_heartbeat_at?: string | null;
  tiktok_logged_in?: boolean;
  [k: string]: any;
}

export interface RunProgress {
  ok?: boolean;
  status?: string;
  total?: number;
  done?: number;
  message?: string;
  [k: string]: any;
}

export interface BusinessDashboard {
  ok?: boolean;
  generated_at?: string;
  scope?: {
    type?: 'company' | 'department';
    department_code?: string | null;
    name?: string | null;
  };
  summary?: {
    total_creators?: number;
    today_collected?: number;
    today_new_creators?: number;
    recent_30d_creators?: number;
    unique_creators?: number;
    unique_today_creators?: number;
    business_unique_creators?: number;
    all_channel_rows_total?: number;
    all_channel_rows_today?: number;
    all_channel_rows_recent_30d?: number;
    processed_rows_total?: number;
    processed_rows_today?: number;
    processed_rows_recent_30d?: number;
    raw_observations_total?: number;
    raw_observations_today?: number;
    raw_observations_recent_30d?: number;
    bd_history_creators?: number;
    bd_history_contacted?: number;
    bd_history_confirmed?: number;
    bd_history_samples?: number;
    bd_history_videos?: number;
    legacy_staff_contacted?: number;
    legacy_staff_confirmed?: number;
    legacy_staff_samples?: number;
    legacy_staff_videos?: number;
    contacted?: number;
    review_pending?: number;
    progressed?: number;
  };
  stage_counts?: Record<string, number>;
  stage_rows?: { key: string; name: string; count: number }[];
  overview?: { key: string; name: string; count: number }[];
  trend_7d?: { date: string; count: number }[];
  category_counts?: { name: string; value: number }[];
  owner_counts?: { name: string; count: number }[];
  bd_rows?: {
    owner: string;
    creator_count: number;
    contacted: number;
    confirmed: number;
    samples: number;
    videos: number;
    authorized: number;
  }[];
  source_counts?: { name: string; count: number }[];
  source_row_counts?: { name: string; count: number }[];
  source_today_counts?: { name: string; count: number }[];
  staff_history?: {
    rows?: Array<Record<string, unknown>>;
    totals?: Record<string, number>;
  };
  [k: string]: any;
}

export interface KeywordRow {
  id?: number;
  keyword: string;
  search_volume?: number | null;
  growth_rate?: number | null;
  rank_position?: number | null;
  category?: string | null;
  [k: string]: any;
}

export interface KeywordsDashboard {
  total?: number;
  new_24h?: number;
  pending_classify?: number;
  last_captured_at?: string | null;
  top_growth?: KeywordRow[];
  top_volume?: KeywordRow[];
  items?: KeywordRow[];
  [k: string]: any;
}

export interface AssistantInfo {
  provider?: string;
  model?: string;
  ready?: boolean;
  greeting?: string;
  [k: string]: any;
}

export interface AssistantMessage {
  role: 'user' | 'assistant';
  content: string;
  ts?: string;
}

export interface AssistantReply {
  reply?: string;
  message?: string;
  [k: string]: any;
}

export interface User {
  id: number;
  username: string;
  display_name?: string | null;
  email?: string | null;
  role: string;
  department_code?: string | null;
  active: number;
  created_at?: string;
  updated_at?: string;
}

export interface ListResp<T> {
  ok?: boolean;
  total?: number;
  items?: T[];
  data?: T[];
  results?: T[];
  [k: string]: any;
}

// ---------- Extension / Collection ----------
export interface ExtensionCommand {
  id: number;
  command_type: string;
  worker_id?: string | null;
  payload_json?: string | null;
  status: 'pending' | 'claimed' | 'done' | 'error' | 'cancelled';
  created_at?: string;
  claimed_at?: string | null;
  finished_at?: string | null;
  result?: string | null;
}

export interface ExtensionSession {
  session_id: string;
  worker_id?: string | null;
  account_id?: string | null;
  online: boolean;
  last_heartbeat_at?: string | null;
  current_url?: string | null;
  page_type?: string | null;
  tiktok_login_status?: string | null;
}

export interface CollectorObservation {
  id: number;
  platform?: string | null;
  worker_id?: string | null;
  search_keyword?: string | null;
  content_hash?: string | null;
  collected_at?: string | null;
  created_at: string;
}

// ---------- Outreach ----------
export interface OutreachTemplate {
  id: string;
  name: string;
  description?: string | null;
  language?: string;            // 'en' / 'zh'
  collab_type?: string | null;
  product_type?: string | null;
  subject_template?: string | null;
  body_template?: string | null;
  sender_name?: string | null;
  sender_signature?: string | null;
  is_default?: number;
  is_active?: number;
  tone?: string | null;
  max_length?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface PreviewResult {
  subject: string;
  body: string;
  variants?: { subject: string; body: string }[];
  ai_used?: boolean;
  ai_status?: string | null;
  context?: Record<string, any>;
}

export interface OutreachDraft {
  id: string;
  creator_id: string;
  template_id?: string | null;
  to_email: string;
  subject: string;
  body: string;
  body_format?: 'plain' | 'html';
  sender_name?: string | null;
  sender_signature?: string | null;
  status: 'draft' | 'queued' | 'sent' | 'failed' | 'cancelled';
  ai_versions?: number | null;
  ai_tone?: string | null;
  ai_language?: string | null;
  sent_at?: string | null;
  gmail_message_id?: string | null;
  gmail_thread_id?: string | null;
  from_email?: string | null;
  from_account_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface GmailAccount {
  id: string;
  email: string;
  display_name?: string | null;
  label?: string | null;
  is_default?: number;
  is_active?: number;
  expires_at?: string | null;
  created_at?: string;
}

export interface OutreachHistoryItem {
  id: string;
  subject: string;
  to_email: string;
  status: string;
  sent_at?: string | null;
  from_email?: string | null;
}

// ---------- Review tasks (extended) ----------
export interface ReviewTaskUpdate {
  status?: string;               // approved / rejected / pending / assigned
  reviewer_notes?: string;
  review_result?: string;
  assigned_staff_id?: string;
  change_product_type?: string;
  change_collab_type?: string;
  upgrade_priority?: string;
}

// 从响应里安全取 items 数组
export function pickItems<T>(r: ListResp<T> | undefined | null): T[] {
  if (!r) return [];
  return r.items ?? r.data ?? r.results ?? [];
}
