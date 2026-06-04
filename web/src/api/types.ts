// Backend response shapes (from /api/v1/*)

export interface ListResponse<T> {
  resource?: string;
  query?: string;
  total: number;
  limit?: number;
  offset?: number;
  items: T[];
  params?: Record<string, unknown>;
}

// ---------- Real user auth (desktop /api/local/auth/me) ----------
export type BackendRole = 'super_admin' | 'company_admin' | 'department_admin' | 'department_user';

export interface CurrentUser {
  id: number | string;
  username: string;
  email?: string | null;
  identity?: string | null;
  display_name?: string | null;
  role: BackendRole;
  base_role?: BackendRole;
  entry_scope?: 'admin' | 'workspace';
  department_code?: string | null;
  department_slug?: string | null;
  department_name?: string | null;
  approval_status?: 'active' | 'pending' | 'rejected' | 'disabled';
  is_active?: boolean;
  must_change_password?: boolean;
  gmail_account_id?: string | null;
  can_manage_users?: boolean;
  can_create_company_admin?: boolean;
  can_reset_password?: boolean;
}

export interface AuthMeResponse {
  ok: boolean;
  logged_in: boolean;
  user?: CurrentUser;
}

export interface ApiItems<T> {
  items: T[];
}

// ---------- Resource shapes ----------

export interface Creator {
  id: number;
  department_id?: number | null;
  handle: string;
  platform: string | null;
  profile_url: string | null;
  display_name: string | null;
  country: string | null;
  language: string | null;
  category_tags: string[] | null;
  followers: number | null;
  followers_raw: string | null;
  tier: string | null;
  avg_views: number | null;
  gmv_30d_usd: number | null;
  pps: number | null;
  sample_score: number | null;
  post_rate_est: number | null;
  email: string | null;
  whatsapp: string | null;
  instagram_handle: string | null;
  youtube_handle: string | null;
  current_status: string | null;
  store_assigned: string | null;
  owner_bd: string | null;
  first_contact_date: string | null;
  last_contact_date: string | null;
  notes: string | null;
  source: string | null;
  quality_score: number | null;
  created_at: string;
  updated_at: string;
  engagement_rate: number | null;
}

export interface Product {
  id: number;
  sku_code: string;
  art_no: string | null;
  name_en: string | null;
  name_zh: string | null;
  category_id: number | null;
  subcategory: string | null;
  series: string | null;
  size_label: string | null;
  pcs_per_pack: number | null;
  packs_per_case: number | null;
  price_tiktok: number | null;
  price_temu: number | null;
  price_ebay: number | null;
  price_ebay_local: number | null;
  price_independent: number | null;
  currency: string | null;
  tier: string | null;
  description_en: string | null;
  description_zh: string | null;
  selling_points_en: string[] | null;
  selling_points_zh: string[] | null;
  is_main_push: number | null;
  status: string | null;
  amazon_url: string | null;
  short_url: string | null;
}

export interface ProductAsset {
  id: string;
  department_code?: string | null;
  name: string;
  sku_code?: string | null;
  product_key: string;
  product_label?: string;
  selling_points?: string[];
  target_creator_types?: string[];
  image_url?: string | null;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
}

export type EmailAutoCampaignStatus = 'running' | 'paused' | 'draft';
export type EmailAutoJobStatus = 'pending' | 'sending' | 'sent' | 'failed' | 'skipped' | 'draft_created';
export type EmailAutoMailboxStatus = 'normal' | 'cooldown' | 'limit' | 'auth_expired' | 'bounce_risk';

export interface EmailAutoDashboardSummary {
  today_sent: number;
  today_target: number;
  available_mailboxes: number;
  mailbox_total: number;
  queue_count: number;
  reply_count: number;
  bounce_count: number;
  risk_mailboxes: number;
}

export interface EmailAutoCampaign {
  id: string;
  name: string;
  status: EmailAutoCampaignStatus;
  schedule_type: 'daily' | 'weekly' | 'monthly' | string;
  weekdays?: string[];
  month_days?: number[];
  schedule_label: string;
  time_window: string;
  start_time: string;
  end_time: string;
  sent: number;
  daily_limit: number;
  hourly_limit: number;
  interval_min_seconds: number;
  interval_max_seconds: number;
  interval: string;
  mailbox_pool: string;
  send_mode: 'draft' | 'send' | string;
  filters: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface EmailAutoMailboxQuota {
  id: string;
  account_id: string;
  email: string;
  owner: string;
  status: EmailAutoMailboxStatus;
  enabled: boolean;
  auto_sent: number;
  quota: number;
  remaining: number;
  replies: number;
  bounces: number;
  failures: number;
  next_send_at: string;
  last_sync_at?: string | null;
  last_sent_at?: string | null;
}

export interface EmailAutoHealthCheckStep {
  action: string;
  label: string;
  status: 'pending' | 'running' | 'passed' | 'failed' | 'skipped' | string;
  detail?: string;
  at?: string | null;
}

export interface EmailAutoHealthCheckItem {
  check_id?: string;
  sender_email?: string | null;
  recipient_email?: string | null;
  subject?: string | null;
  send_ok?: boolean;
  read_ok?: boolean;
  status: 'pending' | 'sent' | 'passed' | 'failed' | string;
  reason?: string;
  message_id?: string | null;
  thread_id?: string | null;
  found_message_id?: string | null;
  current_action?: string;
  current_action_status?: string;
  started_at?: string | null;
  completed_at?: string | null;
  steps?: EmailAutoHealthCheckStep[];
}

export interface EmailAutoHealthCheckResponse {
  ok: boolean;
  marker?: string;
  started_at?: string | null;
  completed_at?: string | null;
  total: number;
  passed: number;
  failed: number;
  items: EmailAutoHealthCheckItem[];
}

export interface EmailAutoJob {
  id: string;
  time: string;
  scheduled_at?: string | null;
  sent_at?: string | null;
  creator_id: string;
  creator: string;
  recipient: string;
  sender: string;
  subject: string;
  body: string;
  body_format: 'plain' | 'html' | string;
  product_asset_id?: string | null;
  product: string;
  plan: string;
  campaign_id: string;
  status: EmailAutoJobStatus;
  reason: string;
  filters: string[];
  attempts: number;
  outreach_email_id?: string | null;
}

export interface EmailAutoDashboardResponse {
  ok: boolean;
  dashboard: EmailAutoDashboardSummary;
  campaigns: EmailAutoCampaign[];
  mailboxes: EmailAutoMailboxQuota[];
  jobs: EmailAutoJob[];
  jobs_total?: number;
  job_status_counts?: Record<string, number>;
}

export interface EmailAutoCampaignCreate {
  name: string;
  status?: EmailAutoCampaignStatus;
  schedule_type?: 'daily' | 'weekly' | 'monthly';
  weekdays?: string[];
  month_days?: number[];
  start_time?: string;
  end_time?: string;
  daily_limit?: number;
  hourly_limit?: number;
  interval_min_seconds?: number;
  interval_max_seconds?: number;
  mailbox_pool?: string;
  send_mode?: 'draft' | 'send';
  filters?: Record<string, unknown>;
  generate_jobs?: boolean;
  candidate_limit?: number;
}

export interface Outreach {
  id: number;
  department_id?: number | null;
  creator_id: number;
  event_date: string | null;
  store_name: string | null;
  bd_owner: string | null;
  action: string | null;
  status: string | null;
  channel: string | null;
  message: string | null;
  sample_qty: number | null;
  commission_rate: number | null;
  video_url: string | null;
  ad_auth_code: string | null;
  remark: string | null;
  created_at: string;
  video_views: number | null;
  video_likes: number | null;
  video_comments: number | null;
  video_shares: number | null;
  metrics_updated_at: string | null;
}

export interface ProductImage {
  id: number;
  product_id: number;
  rel_path: string;
  kind: string;
  caption: string | null;
  display_order: number;
}

export interface Category {
  id: number;
  code: string;
  name_zh: string;
  name_en: string;
  parent_id: number | null;
  sort_order: number;
}

export interface Staff {
  id: number;
  department_id?: number | null;
  name: string;
  role: string | null;
  note: string | null;
}

export interface AuditLog {
  id: number;
  ts: string;
  operator: string | null;
  table_name: string;
  action: string;
  record_id: number | null;
  changes: string | null;
}

export interface Webhook {
  id: number;
  name: string;
  kind: string;          // 'dingtalk' / 'http'
  url: string;
  secret: string | null;
  keyword: string | null;
  events: string[] | null;
  active: number;
  created_at: string;
  last_fired_at: string | null;
  last_status: string | null;
  last_error: string | null;
}

export interface Department {
  id: number;
  code: string;
  name_zh: string;
  name_en: string | null;
  parent_id: number | null;
  manager: string | null;
  description: string | null;
  active: number;
  sort_order: number;
}

export interface Notification {
  id: number;
  recipient: string;
  title: string;
  body: string | null;
  level: 'info' | 'success' | 'warning' | 'error';
  category: string | null;
  link_url: string | null;
  related_table: string | null;
  related_id: number | null;
  read_at: string | null;
  created_at: string;
}

export interface ApiMetric {
  id: number;
  endpoint: string;
  method: string;
  day: string;
  hour: number;
  call_count: number;
  error_count: number;
  total_ms: number;
  p99_ms: number | null;
  last_called_at: string;
}

export interface LlmTokenUsage {
  id: number;
  provider_code: string;
  model: string | null;
  feature: string | null;
  day: string;
  input_tokens: number;
  output_tokens: number;
  call_count: number;
  error_count: number;
  total_cost_usd: number;
}

export interface BusinessMetricDaily {
  id: number;
  day: string;
  scope_kind: 'company' | 'department' | 'staff';
  scope_id: string | null;
  creators_total: number;
  creators_new: number;
  creators_active: number;
  creators_prospect: number;
  outreach_total: number;
  outreach_new: number;
  contacted_count: number;
  confirmed_count: number;
  sample_shipped: number;
  video_published: number;
  ad_running: number;
  conversion_rate: number;
  avg_response_hours: number | null;
  gmv_30d_usd: number;
}

export interface DepartmentDashboardSummaryMetrics {
  total_creators: number;
  processed_creators?: number;
  today_collected: number;
  today_new_creators?: number;
  recent_30d_creators?: number;
  unique_creators?: number;
  collection_channel_rows_total?: number;
  business_with_bd_history_total?: number;
  all_channel_rows_total?: number;
  all_channel_rows_today?: number;
  all_channel_rows_recent_30d?: number;
  processed_rows_total?: number;
  processed_rows_today?: number;
  processed_rows_recent_30d?: number;
  raw_observations_total?: number;
  raw_observations_today?: number;
  raw_observations_recent_30d?: number;
  contacted: number;
  review_pending: number;
  progressed: number;
}

export interface DepartmentDashboardStageRow {
  key: string;
  name: string;
  count: number;
}

export interface DepartmentDashboardTrendRow {
  date: string;
  count: number;
}

export interface DepartmentDashboardCategoryRow {
  name: string;
  value: number;
}

export interface DepartmentDashboardOwnerRow {
  name: string;
  count: number;
}

export interface DepartmentDashboardBdRow {
  owner: string;
  creator_count: number;
  contacted: number;
  confirmed: number;
  samples: number;
  videos: number;
  authorized: number;
}

export interface DepartmentDashboardStaffHistoryRow {
  owner: string;
  role: string;
  contacted: number;
  confirmed: number;
  samples: number;
  videos: number;
  month: string;
}

export interface DepartmentDashboardSummary {
  ok: boolean;
  generated_at: string;
  scope: {
    type: 'company' | 'department';
    department_code: string | null;
    name: string | null;
  };
  summary: DepartmentDashboardSummaryMetrics;
  stage_counts: Record<string, number>;
  stage_rows: DepartmentDashboardStageRow[];
  overview: DepartmentDashboardStageRow[];
  trend_7d: DepartmentDashboardTrendRow[];
  category_counts: DepartmentDashboardCategoryRow[];
  owner_counts: DepartmentDashboardOwnerRow[];
  bd_rows: DepartmentDashboardBdRow[];
  source_counts: DepartmentDashboardOwnerRow[];
  processed_source_counts?: DepartmentDashboardOwnerRow[];
  source_row_counts?: DepartmentDashboardOwnerRow[];
  source_today_counts?: DepartmentDashboardOwnerRow[];
  source_recent_counts?: DepartmentDashboardOwnerRow[];
  staff_history?: {
    rows: DepartmentDashboardStaffHistoryRow[];
    totals: {
      contacted: number;
      confirmed: number;
      samples: number;
      videos: number;
    };
  };
  analytics?: AnalyticsSummary;
}

export interface UnifiedDashboardSummary {
  total_discovered: number;
  total_collected: number;
  today_discovered: number;
  today_collected: number;
  today_duplicate_creators: number;
  total_recommended: number;
  total_contacted: number;
  today_contacted: number;
  pending_contact: number;
  pending_reply: number;
  communicating: number;
  sample_shipped: number;
  sample_delivered: number;
  video_published: number;
  ad_authorized: number;
  ad_running: number;
}

export interface UnifiedDashboardStageRow {
  key: string;
  name: string;
  count: number;
}

export interface UnifiedDashboardFollowupItem {
  id: string;
  creator_id: string;
  department_code?: string | null;
  owner_user_id?: string | null;
  task_type: string;
  status: string;
  due_at?: string | null;
  completed_at?: string | null;
  priority: number;
  reason?: string | null;
  metadata?: Record<string, unknown>;
}

export interface UnifiedDashboardGmailAccount {
  account_id: string;
  email: string;
  department_code?: string | null;
  is_active: number;
  is_default: number;
  last_history_id?: string | null;
  last_sync_at?: string | null;
  next_sync_at?: string | null;
  interval_minutes: number;
  status: string;
  error_message?: string | null;
  readonly_scope: boolean;
  reauthorization_required: boolean;
}

export interface UnifiedDashboardResponse {
  ok: boolean;
  generated_at: string;
  scope: {
    type: 'department' | 'company' | 'super';
    department_code: string | null;
  };
  summary: UnifiedDashboardSummary;
  stage_rows: UnifiedDashboardStageRow[];
  followups: {
    overdue: number;
    due_today: number;
    items: UnifiedDashboardFollowupItem[];
  };
  gmail_sync: {
    accounts: UnifiedDashboardGmailAccount[];
  };
}

export interface OutreachArchiveItem {
  id: string;
  department_code?: string | null;
  creator_id: string;
  creator_handle?: string | null;
  creator_display_name?: string | null;
  creator_profile_url?: string | null;
  creator_platform?: string | null;
  to_email: string;
  from_email?: string | null;
  subject: string;
  body_preview?: string | null;
  body_format?: 'plain' | 'html' | string;
  status: string;
  sent_at?: string | null;
  created_at?: string | null;
  created_by?: string | null;
  gmail_thread_id?: string | null;
  gmail_message_id?: string | null;
  parent_email_id?: string | null;
  direction?: 'inbound' | 'outbound' | 'bounce' | string;
}

export interface OutreachArchiveDetail extends OutreachArchiveItem {
  body: string;
  error_message?: string | null;
  updated_at?: string | null;
}

export interface OutreachTrackingItem {
  creator_id: string;
  creator_handle?: string | null;
  creator_display_name?: string | null;
  creator_profile_url?: string | null;
  creator_platform?: string | null;
  creator_email?: string | null;
  current_status: string;
  to_email?: string | null;
  from_email?: string | null;
  latest_email_id?: string | null;
  gmail_thread_id?: string | null;
  latest_outbound_at?: string | null;
  latest_inbound_at?: string | null;
  latest_message_at?: string | null;
  latest_direction?: 'inbound' | 'outbound' | string;
  needs_followup?: boolean;
  email_count?: number;
  last_subject?: string | null;
  last_preview?: string | null;
  owner_bd?: string | null;
  followup_due_at?: string | null;
  followup_age_hours?: number | null;
}

export interface OutreachTrackingResponse extends ListResponse<OutreachTrackingItem> {
  ok?: boolean;
  status_counts?: Record<string, number>;
  direction_counts?: {
    inbound?: number;
    outbound?: number;
    needs_followup?: number;
  };
}

export interface GmailReplySyncAccount {
  account_id: string;
  email: string;
  user_id?: string | null;
  department_code?: string | null;
  has_readonly_scope?: boolean;
  status?: string;
  error_message?: string | null;
  last_sync_at?: string | null;
  next_sync_at?: string | null;
  interval_minutes?: number;
  tracked_threads?: number;
  stored_replies?: number;
  stored_bounces?: number;
  sent_rows?: number;
  threads_checked?: number;
  messages_seen?: number;
  new_replies?: number;
  new_bounces?: number;
  errors?: number;
  error?: string | null;
}

export interface GmailReplySyncStatus {
  ok: boolean;
  interval_minutes: number;
  totals: Record<string, number>;
  items?: GmailReplySyncAccount[];
  accounts?: GmailReplySyncAccount[];
  accepted?: boolean;
  running?: boolean;
  background?: {
    running?: boolean;
    started_at?: string | null;
    finished_at?: string | null;
    error?: string | null;
    totals?: Record<string, number> | null;
  };
}

export interface AnalyticsSourceCount {
  name: string;
  count: number;
}

export interface AnalyticsEventCount {
  name: string;
  count: number;
}

export interface AnalyticsTrendRow {
  date: string;
  collected?: number;
  processed: number;
  recommended: number;
  sent: number;
  partnered: number;
}

export interface AnalyticsRecentEvent {
  id: string;
  occurred_at: string;
  source: string;
  event_type: string;
  event_label: string;
  actor?: string | null;
  creator_id?: string | null;
  creator?: string | null;
  department_code?: string | null;
  title: string;
}

export interface AnalyticsMemberRow {
  member: string;
  tiktok_shop_processed?: number;
  tiktok_video_processed?: number;
  bd_processed?: number;
  other_processed?: number;
  recommended?: number;
  assigned?: number;
  total_contacted?: number;
  bd_history_contacted?: number;
  bd_history_confirmed?: number;
  bd_history_samples?: number;
  bd_history_videos?: number;
  sent?: number;
  pending_reply?: number;
  replied?: number;
  confirmed?: number;
  sample_shipped?: number;
  sample_delivered?: number;
  partnered?: number;
  video_published?: number;
  dropped?: number;
}

export interface AnalyticsDepartmentRow extends AnalyticsMemberRow {
  department_code: string;
  creators?: number;
}

export interface AnalyticsSummary {
  ok: boolean;
  scope: {
    type: string;
    department_code: string | null;
    actor_user_id?: string | null;
  };
  summary: {
    total_creators?: number;
    processed_creators: number;
    recommended: number;
    assigned: number;
    outreach_sent: number;
    pending_reply: number;
    replied: number;
    sample_shipped: number;
    partnered: number;
    total_contacted?: number;
    raw_observations_are_excluded: boolean;
    bd_history: {
      contacted: number;
      confirmed: number;
      samples: number;
      videos: number;
    };
  };
  source_counts: AnalyticsSourceCount[];
  event_counts: AnalyticsEventCount[];
  recent_events?: AnalyticsRecentEvent[];
  members: AnalyticsMemberRow[];
  departments: AnalyticsDepartmentRow[];
  trend: AnalyticsTrendRow[];
}

export interface SystemMetrics {
  ok: boolean;
  generated_at: string;
  cpu_percent?: number | null;
  disk: {
    path: string;
    percent: number;
    used: number;
    free: number;
    total: number;
  };
  database: {
    row_count: number;
    tables: { name: string; count: number }[];
  };
  requests_24h: { hour: string; count: number }[];
  request_total_24h: number;
  avg_duration_ms_24h: number;
  error_count_24h: number;
}

export interface KeywordSnapshot {
  id: number;
  keyword_id: number;
  captured_at: string;
  search_volume: number | null;
  growth_rate: number | null;
  rank_position: number | null;
  scrape_run_id: number | null;
}

export interface User {
  id: number;
  username: string;
  display_name: string | null;
  role: string;
  active: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
  active_keys: number;
  total_keys: number;
  last_used_at: string | null;
}

export interface LlmProvider {
  code: string;
  display_name: string;
  type: string;
  api_key: string | null;
  base_url: string | null;
  default_model: string | null;
  extra_headers: string | null;
  is_active: number;
  enabled: number;
  sort_order: number;
  last_tested_at: string | null;
  last_test_status: string | null;
  last_test_message: string | null;
}

export interface NamedQuery {
  name: string;
  description: string;
  is_builtin: boolean;
  params: { name: string; type: string; default: unknown }[];
  url: string;
}

export interface Resource {
  name: string;
  table: string;
  pk: string;
  writable: boolean;
  is_dynamic: boolean;
  description: string;
  columns: { name: string; type: string; pk: boolean; notnull: boolean }[];
}

export interface VersionInfo {
  api_version: string;
  server_version: string;
  compatibility: string;
  resources: { name: string; table: string; column_count: number; columns: string[] }[];
}
