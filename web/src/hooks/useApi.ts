import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import { endpoints } from '@/api/endpoints';
import { authApi } from '@/api/authClient';
import type { ListResponse } from '@/api/types';

type Params = Record<string, unknown> | undefined;

// Desktop-backend user list (source of truth for registration approval).
export function useAuthUsers() {
  return useQuery({ queryKey: ['auth', 'users'], queryFn: () => authApi.users() });
}

// Generic resource list
export function useResource<T>(
  resource: string,
  params?: Params,
  options?: Partial<UseQueryOptions<ListResponse<T>>>,
) {
  return useQuery({
    queryKey: ['data', resource, params],
    queryFn: () => endpoints.listResource<T>(resource, params),
    ...options,
  });
}

export function useCreators(params?: Params) {
  return useQuery({ queryKey: ['data', 'creators', params], queryFn: () => endpoints.creators(params) });
}
export function useProducts(params?: Params) {
  return useQuery({ queryKey: ['data', 'products', params], queryFn: () => endpoints.products(params) });
}
export function useOutreach(params?: Params) {
  return useQuery({ queryKey: ['data', 'outreach', params], queryFn: () => endpoints.outreach(params) });
}
export function useProductImages(params?: Params) {
  return useQuery({ queryKey: ['data', 'product_images', params], queryFn: () => endpoints.productImages(params) });
}
export function useCategories(params?: Params) {
  return useQuery({ queryKey: ['data', 'categories', params], queryFn: () => endpoints.categories(params) });
}
export function useStaff(params?: Params) {
  return useQuery({ queryKey: ['data', 'staff', params], queryFn: () => endpoints.staff(params) });
}
export function useAuditLog(params?: Params) {
  return useQuery({ queryKey: ['data', 'audit_log', params], queryFn: () => endpoints.auditLog(params) });
}
export function useKeywordSnapshots(params?: Params) {
  return useQuery({ queryKey: ['data', 'keyword_snapshots', params], queryFn: () => endpoints.keywordSnapshots(params) });
}

export function useWebhooks(params?: Params) {
  return useQuery({ queryKey: ['data', 'webhooks', params], queryFn: () => endpoints.webhooks(params) });
}
export function useDepartments(params?: Params) {
  return useQuery({ queryKey: ['data', 'departments', params], queryFn: () => endpoints.departments(params) });
}
export function useNotifications(params?: Params) {
  return useQuery({ queryKey: ['data', 'notifications', params], queryFn: () => endpoints.notifications(params) });
}
export function useApiMetrics(params?: Params) {
  return useQuery({ queryKey: ['data', 'api_metrics', params], queryFn: () => endpoints.apiMetrics(params) });
}
export function useLlmTokenUsages(params?: Params) {
  return useQuery({ queryKey: ['data', 'llm_token_usages', params], queryFn: () => endpoints.llmTokenUsages(params) });
}
export function useBusinessMetricsDaily(params?: Params) {
  return useQuery({ queryKey: ['data', 'business_metrics_daily', params], queryFn: () => endpoints.businessMetricsDaily(params) });
}
export function useDepartmentDashboardSummary() {
  return useQuery({ queryKey: ['dashboard', 'department-summary'], queryFn: () => endpoints.departmentDashboardSummary() });
}

export function useUnifiedDashboard() {
  return useQuery({ queryKey: ['dashboard', 'unified'], queryFn: () => endpoints.unifiedDashboard() });
}

export function useOutreachTracking(params?: Params) {
  return useQuery({
    queryKey: ['outreach', 'tracking', params],
    queryFn: async () => {
      const pageSize = 200;
      const first = await endpoints.outreachTracking({ ...params, limit: pageSize, offset: 0 });
      const items = [...(first.items ?? [])];
      while (items.length < first.total && items.length < 1000) {
        const next = await endpoints.outreachTracking({ ...params, limit: pageSize, offset: items.length });
        if (!next.items?.length) break;
        items.push(...next.items);
      }
      return { ...first, limit: items.length, offset: 0, items };
    },
  });
}

export function useOutreachArchive(params?: Params) {
  return useQuery({ queryKey: ['outreach', 'archive', params], queryFn: () => endpoints.outreachArchive(params) });
}

export function useReplyOutreachArchive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof endpoints.replyOutreachArchive>[1] }) =>
      endpoints.replyOutreachArchive(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['outreach', 'tracking'] });
      qc.invalidateQueries({ queryKey: ['outreach', 'archive'] });
      qc.invalidateQueries({ queryKey: ['dashboard', 'unified'] });
      qc.invalidateQueries({ queryKey: ['gmail', 'reply-sync-status'] });
    },
  });
}

export function useProductAssets(creator_id?: string | number) {
  return useQuery({
    queryKey: ['outreach', 'product-assets', creator_id ?? 'all'],
    queryFn: () => endpoints.listProductAssets(creator_id),
  });
}

export function useGmailReplySyncStatus() {
  return useQuery({
    queryKey: ['gmail', 'reply-sync-status'],
    queryFn: () => endpoints.gmailReplySyncStatus(),
    refetchInterval: 10_000,
  });
}

export function useGmailSyncReplies() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body?: Parameters<typeof endpoints.gmailSyncReplies>[0]) => endpoints.gmailSyncReplies(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['gmail', 'reply-sync-status'] });
      qc.invalidateQueries({ queryKey: ['outreach', 'tracking'] });
      qc.invalidateQueries({ queryKey: ['outreach', 'archive'] });
      qc.invalidateQueries({ queryKey: ['dashboard', 'unified'] });
    },
  });
}

export function useEmailAutoDashboard(params?: Parameters<typeof endpoints.emailAutoDashboard>[0]) {
  return useQuery({
    queryKey: ['email-auto', 'dashboard', params],
    queryFn: () => endpoints.emailAutoDashboard(params),
    refetchInterval: 10_000,
  });
}

export function useEmailAutoSyncMailboxes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => endpoints.emailAutoSyncMailboxes(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['email-auto', 'dashboard'] }),
  });
}

export function useEmailAutoCreateCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Parameters<typeof endpoints.emailAutoCreateCampaign>[0]) => endpoints.emailAutoCreateCampaign(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['email-auto', 'dashboard'] }),
  });
}

export function useEmailAutoUpdateCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof endpoints.emailAutoUpdateCampaign>[1] }) => endpoints.emailAutoUpdateCampaign(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['email-auto', 'dashboard'] }),
  });
}

export function useEmailAutoCampaignStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: Parameters<typeof endpoints.emailAutoCampaignStatus>[1] }) => endpoints.emailAutoCampaignStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['email-auto', 'dashboard'] }),
  });
}

export function useEmailAutoMailboxUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof endpoints.emailAutoUpdateMailbox>[1] }) => endpoints.emailAutoUpdateMailbox(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['email-auto', 'dashboard'] }),
  });
}

export function useEmailAutoMailboxRemove() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => endpoints.emailAutoRemoveMailbox(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['email-auto', 'dashboard'] }),
  });
}

export function useEmailAutoActions() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ['email-auto', 'dashboard'] });
  return {
    pauseAll: useMutation({ mutationFn: () => endpoints.emailAutoPauseAll(), onSuccess: invalidate }),
    previewCampaign: useMutation({ mutationFn: (body: Parameters<typeof endpoints.emailAutoCampaignPreview>[0]) => endpoints.emailAutoCampaignPreview(body) }),
    healthCheck: useMutation({ mutationFn: (body?: Parameters<typeof endpoints.emailAutoHealthCheck>[0]) => endpoints.emailAutoHealthCheck(body), onSuccess: invalidate }),
    deleteCampaign: useMutation({ mutationFn: (id: string) => endpoints.emailAutoDeleteCampaign(id), onSuccess: invalidate }),
    generateJobs: useMutation({ mutationFn: ({ id, limit }: { id: string; limit?: number }) => endpoints.emailAutoGenerateJobs(id, limit), onSuccess: invalidate }),
    processJobs: useMutation({ mutationFn: (body: Parameters<typeof endpoints.emailAutoProcessJobs>[0]) => endpoints.emailAutoProcessJobs(body), onSuccess: invalidate }),
    retryJob: useMutation({ mutationFn: (id: string) => endpoints.emailAutoRetryJob(id), onSuccess: invalidate }),
    retryFailed: useMutation({ mutationFn: () => endpoints.emailAutoRetryFailed(), onSuccess: invalidate }),
    skipJob: useMutation({ mutationFn: (id: string) => endpoints.emailAutoSkipJob(id), onSuccess: invalidate }),
    cancelJob: useMutation({ mutationFn: (id: string) => endpoints.emailAutoCancelJob(id), onSuccess: invalidate }),
  };
}

export function useAnalyticsMe(days = 30) {
  return useQuery({ queryKey: ['analytics', 'me', days], queryFn: () => endpoints.analyticsMe(days) });
}

export function useAnalyticsDepartment(params?: { department_code?: string; days?: number }) {
  return useQuery({
    queryKey: ['analytics', 'department', params],
    queryFn: () => endpoints.analyticsDepartment(params),
  });
}

export function useAnalyticsCompany(days = 30) {
  return useQuery({ queryKey: ['analytics', 'company', days], queryFn: () => endpoints.analyticsCompany(days) });
}

export function useAnalyticsCompanyGrowth(days = 90) {
  return useQuery({ queryKey: ['analytics', 'company-growth', days], queryFn: () => endpoints.analyticsCompanyGrowth(days) });
}

export function useSystemMetrics() {
  return useQuery({
    queryKey: ['admin', 'system-metrics'],
    queryFn: () => endpoints.systemMetrics(),
    refetchInterval: 10_000,
  });
}

export function useUsers() {
  return useQuery({ queryKey: ['auth', 'users'], queryFn: () => endpoints.users() });
}

export function useLlmProviders() {
  return useQuery({ queryKey: ['llm', 'providers'], queryFn: () => endpoints.llmProviders() });
}

export function useNamedQueries() {
  return useQuery({ queryKey: ['queries'], queryFn: () => endpoints.queries() });
}

export function useNamedQuery<T>(name: string, params?: Params, enabled = true) {
  return useQuery({
    queryKey: ['nq', name, params],
    queryFn: () => endpoints.runQuery<T>(name, params),
    enabled,
  });
}

export function useVersion() {
  return useQuery({ queryKey: ['version'], queryFn: () => endpoints.version() });
}

export function useResources() {
  return useQuery({ queryKey: ['resources'], queryFn: () => endpoints.resources() });
}
