import { api } from './client';
import type {
  ListResponse,
  Creator,
  Product,
  Outreach,
  ProductImage,
  Category,
  Staff,
  User,
  LlmProvider,
  NamedQuery,
  AuditLog,
  KeywordSnapshot,
  VersionInfo,
  ApiItems,
  DepartmentDashboardSummary,
  GmailReplySyncStatus,
  UnifiedDashboardResponse,
  AnalyticsSummary,
  OutreachArchiveDetail,
  OutreachArchiveItem,
  OutreachTrackingResponse,
  ProductAsset,
  SystemMetrics,
} from './types';

const BASE = '/api/v1'; // legacy core proxy (resources with NO x9db table)
const LOCAL = '/api/local'; // desktop backend = the real x9db

// Desktop-only resources stay on /api/local/data/*.
// Core business resources (creators/outreach/staff/products/etc.) must use
// /api/v1 so the role admin pages read the PostgreSQL business database and
// pass through the desktop proxy's department scoping.
const X9DB_RESOURCES = new Set([
  'outreach_emails', 'outreach_templates',
  'review_tasks', 'raw_observations', 'extension_sessions',
  'extension_commands', 'extension_run_progress', 'creator_recommendations',
  'creator_tags', 'tag_definitions', 'system_logs', 'audit_log',
  'app_users', 'users',
]);

const dataBase = (resource: string) =>
  X9DB_RESOURCES.has(resource) ? `${LOCAL}/data/${resource}` : `${BASE}/data/${resource}`;

export const endpoints = {
  // Resource CRUD — routed to x9db when a desktop table exists, else core.
  listResource: <T>(resource: string, params?: Record<string, unknown>) =>
    api.get<ListResponse<T>>(dataBase(resource), params),

  getRow: <T>(resource: string, id: string | number) =>
    api.get<T>(`${dataBase(resource)}/${id}`),

  // Typed resource shortcuts
  creators: (params?: Record<string, unknown>) =>
    api.get<ListResponse<Creator>>(`${BASE}/data/creators`, params),
  products: (params?: Record<string, unknown>) =>
    api.get<ListResponse<Product>>(`${BASE}/data/products`, params),
  outreach: (params?: Record<string, unknown>) =>
    api.get<ListResponse<Outreach>>(`${BASE}/data/outreach`, params),
  productImages: (params?: Record<string, unknown>) =>
    api.get<ListResponse<ProductImage>>(`${BASE}/data/product_images`, params),
  categories: (params?: Record<string, unknown>) =>
    api.get<ListResponse<Category>>(`${BASE}/data/categories`, params),
  staff: (params?: Record<string, unknown>) =>
    api.get<ListResponse<Staff>>(`${BASE}/data/staff`, params),
  auditLog: (params?: Record<string, unknown>) =>
    api.get<ListResponse<AuditLog>>(`${LOCAL}/data/audit_log`, params),
  keywordSnapshots: (params?: Record<string, unknown>) =>
    api.get<ListResponse<KeywordSnapshot>>(`${BASE}/data/keyword_snapshots`, params),

  // New (added in migrate_v18)
  webhooks: (params?: Record<string, unknown>) =>
    api.get<ListResponse<import('./types').Webhook>>(`${BASE}/data/webhooks`, params),
  departments: (params?: Record<string, unknown>) =>
    api.get<ListResponse<import('./types').Department>>(`${BASE}/data/departments`, params),
  notifications: (params?: Record<string, unknown>) =>
    api.get<ListResponse<import('./types').Notification>>(`${BASE}/data/notifications`, params),
  apiMetrics: (params?: Record<string, unknown>) =>
    api.get<ListResponse<import('./types').ApiMetric>>(`${BASE}/data/api_metrics`, params),
  llmTokenUsages: (params?: Record<string, unknown>) =>
    api.get<ListResponse<import('./types').LlmTokenUsage>>(`${BASE}/data/llm_token_usages`, params),
  businessMetricsDaily: (params?: Record<string, unknown>) =>
    api.get<ListResponse<import('./types').BusinessMetricDaily>>(`${BASE}/data/business_metrics_daily`, params),
  departmentDashboardSummary: () =>
    api.get<DepartmentDashboardSummary>(`${LOCAL}/dashboard/department-summary`),
  unifiedDashboard: () =>
    api.get<UnifiedDashboardResponse>(`${LOCAL}/dashboard/unified`),
  outreachTracking: (params?: Record<string, unknown>) =>
    api.get<OutreachTrackingResponse>(`${LOCAL}/outreach/tracking`, params),
  outreachArchive: (params?: Record<string, unknown>) =>
    api.get<ListResponse<OutreachArchiveItem>>(`${LOCAL}/outreach/archive`, params),
  outreachArchiveDetail: (id: string) =>
    api.get<{ ok: boolean; item: OutreachArchiveDetail }>(`${LOCAL}/outreach/archive/${encodeURIComponent(id)}`),
  replyOutreachArchive: (id: string, body: { subject?: string; body: string; body_format?: 'plain' | 'html' | string }) =>
    api.post<{ ok: boolean; item: OutreachArchiveDetail }>(
      `${LOCAL}/outreach/archive/${encodeURIComponent(id)}/reply`,
      body,
    ),
  listProductAssets: (creator_id?: string | number) =>
    api.get<{ ok: boolean; items: ProductAsset[]; total: number; matched?: ProductAsset | null }>(
      `${LOCAL}/outreach/product-assets`,
      creator_id !== undefined && creator_id !== null ? { creator_id } : undefined,
    ),
  gmailReplySyncStatus: () =>
    api.get<GmailReplySyncStatus>(`${LOCAL}/outreach/gmail/sync-status`),
  gmailSyncReplies: (body?: { account_ids?: string[]; limit_per_account?: number }) =>
    api.post<GmailReplySyncStatus>(`${LOCAL}/outreach/gmail/sync-replies`, body || {}),
  analyticsMe: (days = 30) =>
    api.get<AnalyticsSummary>(`${LOCAL}/analytics/me`, { days }),
  analyticsDepartment: (params?: { department_code?: string; days?: number }) =>
    api.get<AnalyticsSummary>(`${LOCAL}/analytics/department`, params),
  analyticsCompany: (days = 30) =>
    api.get<AnalyticsSummary>(`${LOCAL}/analytics/company`, { days }),
  analyticsCompanyGrowth: (days = 90) =>
    api.get<AnalyticsSummary>(`${LOCAL}/analytics/company-growth`, { days }),
  systemMetrics: () =>
    api.get<SystemMetrics>(`${LOCAL}/admin/system-metrics`),

  // Auth / Users
  users: () => api.get<ApiItems<User>>(`${BASE}/auth/users`),

  // LLM
  llmProviders: () => api.get<ApiItems<LlmProvider>>(`${BASE}/llm/providers`),

  // Named queries
  queries: () => api.get<ApiItems<NamedQuery>>(`${BASE}/queries`),
  runQuery: <T>(name: string, params?: Record<string, unknown>) =>
    api.get<ListResponse<T>>(`${BASE}/queries/${name}`, params),

  // Meta
  version: () => api.get<VersionInfo>(`${BASE}/version`),
  resources: () => api.get<{ total: number; items: import('./types').Resource[] }>(`${BASE}/resources`),
  info: () => api.get<{ version: string; resources: string[] }>(`${BASE}/`),

  // AI 项目助手 (read-only consultant; routed via desktop /api/v1 proxy → core)
  agentInfo: () =>
    api.get<{ ready: boolean; reason?: string; active_provider?: string; active_model?: string }>(
      `${BASE}/agent/info`,
    ),
  agentChat: (messages: { role: string; content: string }[]) =>
    api.post<{ answer: string; provider?: string; model?: string }>(`${BASE}/agent/chat`, {
      messages,
    }),
};
