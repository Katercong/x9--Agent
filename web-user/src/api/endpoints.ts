import { api } from './client';
import type {
  AuthMe, AppStatus, DbStats, Creator, ReviewTask,
  ExtensionStatus, RunProgress, BusinessDashboard, KeywordsDashboard,
  AssistantInfo, AssistantReply, User, ListResp,
  ExtensionCommand, ExtensionSession, CollectorObservation,
  OutreachTemplate, PreviewResult, OutreachDraft, GmailAccount, GmailStatus, OutreachHistoryItem,
  CreatorOutreachLock, OutreachArchiveItem, OutreachArchiveDetail, OutreachTrackingItem,
  ReviewTaskUpdate, TkPrompt, TkScriptResult, ProductAsset,
} from './types';

export const endpoints = {
  // Auth
  me: () => api.get<AuthMe>('/auth/me'),
  logout: () => api.post<{ ok: boolean }>('/auth/logout'),
  users: () => api.get<ListResp<User>>('/auth/users'),

  // App / DB
  appStatus: () => api.get<AppStatus>('/app/status'),
  dbStats: () => api.get<DbStats>('/db/stats'),
  dbStatus: () => api.get<AppStatus>('/db/status'),

  // Business / Shared
  businessDashboard: () => api.get<BusinessDashboard>('/dashboard/department-summary'),

  // Creators
  creators: (params?: Record<string, unknown>) =>
    api.get<ListResp<Creator>>('/creators', params),
  creatorsRecommended: (params?: Record<string, unknown>) =>
    api.get<ListResp<Creator>>('/creators/recommended', params),
  creator: (id: number | string) => api.get<Creator>(`/creators/${id}`),

  // Review queue
  reviewTasks: (params?: Record<string, unknown>) =>
    api.get<ListResp<ReviewTask>>('/review-tasks', params),

  // Extension / Pipeline
  extensionStatus: () => api.get<ExtensionStatus>('/extension/status'),
  runProgress: (workerId?: string) =>
    api.get<RunProgress>('/extension/run-progress' + (workerId ? `?worker_id=${encodeURIComponent(workerId)}` : '')),
  runPipeline: () => api.post<{ ok: boolean }>('/process/run-full-pipeline'),

  // Keywords / TK hot search
  keywordsDashboard: () => api.get<KeywordsDashboard>('/shared/keywords/dashboard'),

  // AI Assistant
  assistantInfo: () => api.get<AssistantInfo>('/shared/assistant/info'),
  assistantChat: (message: string, history?: Array<{ role: string; content: string }>) =>
    api.post<AssistantReply>('/shared/assistant/chat', {
      // Backend expects { messages: [{role, content}, ...] }; the page passes
      // prior turns as `history` and the new user text as `message`.
      messages: [...(history ?? []), { role: 'user', content: message }],
    }),

  // ---------- Extension / Collection ----------
  extensionSessions: () => api.get<{ sessions: ExtensionSession[] }>('/extension/status'),
  postExtensionCommand: (body: { command_type: string; worker_id?: string; payload?: Record<string, unknown>; department_code?: string }) =>
    api.post<{ command: ExtensionCommand }>('/extension/commands', body),
  recentObservations: (limit = 50) =>
    api.get<ListResp<CollectorObservation>>('/collector/recent-observations', { limit }),

  // ---------- Outreach ----------
  outreachTemplates: (params?: Record<string, unknown>) =>
    api.get<ListResp<OutreachTemplate>>('/outreach/templates', params),
  createOutreachTemplate: (body: Partial<OutreachTemplate>) =>
    api.post<OutreachTemplate>('/outreach/templates', body),
  patchOutreachTemplate: (id: string, body: Partial<OutreachTemplate>) =>
    api.patch<OutreachTemplate>(`/outreach/templates/${id}`, body),
  deleteOutreachTemplate: (id: string) => api.del<{ ok: boolean }>(`/outreach/templates/${id}`),

  previewOutreach: (creator_id: string | number, body: {
    template_id?: string; language?: string; use_ai?: boolean;
    tone?: string; max_length?: number; n?: 1 | 2 | 3;
    sender_name?: string; sender_signature?: string; script_keywords?: string;
  }) => api.post<PreviewResult>(`/outreach/preview/${encodeURIComponent(String(creator_id))}`, body),

  createDraft: (body: Partial<OutreachDraft> & { creator_id: string | number; to_email: string; subject: string; body: string }) =>
    api.post<OutreachDraft>('/outreach/draft', body),
  listDrafts: (params?: Record<string, unknown>) =>
    api.get<ListResp<OutreachDraft>>('/outreach/drafts', params),
  patchDraft: (id: string, body: Partial<OutreachDraft>) =>
    api.patch<OutreachDraft>(`/outreach/draft/${id}`, body),
  deleteDraft: (id: string) => api.del<{ ok: boolean }>(`/outreach/draft/${id}`),
  sendDraft: (id: string, body: { confirm?: boolean; update_creator_status?: boolean; from_account_id?: string }) =>
    api.post<OutreachDraft>(`/outreach/send/${id}`, { confirm: true, ...body }),

  outreachHistory: (creator_id: string | number, params?: Record<string, unknown>) =>
    api.get<ListResp<OutreachHistoryItem>>(`/outreach/history/${encodeURIComponent(String(creator_id))}`, params),

  acquireOutreachLock: (creator_id: string | number, body?: { ttl_seconds?: number; force?: boolean }) =>
    api.post<{ ok: boolean; lock: CreatorOutreachLock }>(`/outreach/locks/${encodeURIComponent(String(creator_id))}`, body || {}),
  heartbeatOutreachLock: (lock_id: string, body?: { ttl_seconds?: number }) =>
    api.post<{ ok: boolean; lock: CreatorOutreachLock }>(`/outreach/locks/${encodeURIComponent(lock_id)}/heartbeat`, body || {}),
  releaseOutreachLock: (lock_id: string, body?: { force?: boolean; reason?: string }) =>
    api.post<{ ok: boolean; lock: CreatorOutreachLock }>(`/outreach/locks/${encodeURIComponent(lock_id)}/release`, body || {}),
  myOutreachLocks: () =>
    api.get<ListResp<CreatorOutreachLock>>('/outreach/locks/mine'),
  activeOutreachLocks: () =>
    api.get<ListResp<CreatorOutreachLock>>('/outreach/locks/active'),

  outreachArchive: (params?: Record<string, unknown>) =>
    api.get<ListResp<OutreachArchiveItem>>('/outreach/archive', params),
  outreachArchiveDetail: (id: string) =>
    api.get<{ ok: boolean; item: OutreachArchiveDetail }>(`/outreach/archive/${encodeURIComponent(id)}`),
  outreachTracking: (params?: Record<string, unknown>) =>
    api.get<ListResp<OutreachTrackingItem>>('/outreach/tracking', params),
  patchOutreachTrackingStatus: (creator_id: string | number, body: { current_status: string; note?: string }) =>
    api.post<{ ok: boolean; creator_id: string; current_status: string }>(
      `/outreach/tracking/${encodeURIComponent(String(creator_id))}/status`,
      body,
    ),

  generateTkScript: (creator_id: string | number, body: {
    commission: number;
    strategy?: string;
    custom_prompt?: string;
    prompt_id?: string;
    product_asset_id?: string;
  }) =>
    api.post<TkScriptResult>(
      `/outreach/tk-script/${encodeURIComponent(String(creator_id))}`,
      body,
    ),

  listProductAssets: (creator_id?: string | number) =>
    api.get<{ ok: boolean; items: ProductAsset[]; total: number; matched?: ProductAsset | null }>(
      '/outreach/product-assets',
      creator_id !== undefined && creator_id !== null ? { creator_id } : undefined,
    ),
  createProductAsset: (body: {
    name: string;
    sku_code?: string;
    product_key: string;
    selling_points?: string[];
    target_creator_types?: string[];
    image_data_url?: string;
  }) => api.post<{ ok: boolean; asset: ProductAsset }>('/outreach/product-assets', body),
  deleteProductAsset: (id: string) => api.del<{ ok: boolean }>(`/outreach/product-assets/${id}`),

  listTkPrompts: () =>
    api.get<{ items: TkPrompt[]; total: number }>('/outreach/tk-prompts'),
  createTkPrompt: (body: { name: string; prompt: string; strategy: string }) =>
    api.post<{ ok: boolean; prompt: TkPrompt }>('/outreach/tk-prompts', body),
  deleteTkPrompt: (id: string) =>
    api.del<{ ok: boolean }>(`/outreach/tk-prompts/${id}`),

  // Gmail OAuth
  gmailAuthUrl: (label = 'workspace', returnTo = '/') =>
    api.get<{ auth_url: string }>('/outreach/gmail/auth-url', { label, return_to: returnTo }),
  gmailStatus: () => api.get<GmailStatus>('/outreach/gmail/status'),
  gmailAccounts: () => api.get<ListResp<GmailAccount>>('/outreach/gmail/accounts'),
  gmailSetDefault: (id: string) => api.post<{ ok: boolean }>(`/outreach/gmail/accounts/${id}/default`),
  gmailDeleteAccount: (id: string) => api.del<{ ok: boolean }>(`/outreach/gmail/accounts/${id}`),

  // ---------- Creators write ----------
  claimCreator: (creator_id: string | number, body?: { owner_bd?: string; store_assigned?: string; current_status?: string; force?: boolean }) =>
    api.post<Creator>(`/creators/${encodeURIComponent(String(creator_id))}/claim`, body || {}),
  releaseCreator: (creator_id: string | number, force = false) =>
    api.post<Creator>(`/creators/${encodeURIComponent(String(creator_id))}/release`, { force }),

  // ---------- Review tasks write ----------
  patchReviewTask: (id: string | number, body: ReviewTaskUpdate) =>
    api.patch<ReviewTask>(`/review-tasks/${encodeURIComponent(String(id))}`, body),
};
